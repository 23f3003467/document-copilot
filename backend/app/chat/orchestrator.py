"""Grounded chat turn orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from uuid import UUID

from openai import RateLimitError
from pydantic_ai.exceptions import ModelRateLimitError
from sqlalchemy.orm import Session

from app.assistant.agent import run_document_agent
from app.assistant.deps import DocumentAgentDeps, TurnRegistry
from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import CurrentUser
from app.chat.messages import text_from_parts
from app.chat.streaming import stream_grounded_turn_and_persist, stream_status
from app.grounding.validator import GroundingValidator, prune_unreferenced_citations
from app.retrieval.retriever import DocumentRetriever
from app.schemas.chat import UIMessage

logger = logging.getLogger(__name__)


async def run_turn(
    *,
    session: Session,
    thread_id: UUID,
    user: CurrentUser,
    user_message: UIMessage,
    retriever: DocumentRetriever,
) -> AsyncGenerator[str, None]:
    status_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    registry = TurnRegistry()
    deps = DocumentAgentDeps(
        retriever=retriever,
        registry=registry,
        thread_id=thread_id,
        user_id=UUID(user["id"]),
        on_status=lambda stage, message: loop.call_soon_threadsafe(
            status_queue.put_nowait, (stage, message)
        ),
    )
    query = text_from_parts(user_message.parts).strip()
    validator = GroundingValidator()
    answer: GroundedAnswer | None = None
    validation = None

    for attempt in range(2):
        agent_query = query
        if attempt:
            agent_query = (
                f"{query}\n\nYour previous answer failed citation validation. "
                "Try again and cite only evidence from retrieved filing passages."
            )
            async for event in stream_status(
                "retrying",
                "Rechecking the answer against retrieved filing evidence…",
            ):
                yield event

        task = asyncio.create_task(
            asyncio.to_thread(run_document_agent, agent_query, deps)
        )
        while not task.done():
            try:
                stage, message = await asyncio.wait_for(status_queue.get(), timeout=0.05)
            except TimeoutError:
                continue
            async for event in stream_status(stage, message):
                yield event

        try:
            answer = prune_unreferenced_citations(await task)
        except Exception as error:
            logger.exception("Document agent failed for thread %s", thread_id)
            error_text = "The assistant could not complete this request."
            if isinstance(error, (ModelRateLimitError, RateLimitError)):
                error_text = (
                    "The Gemini API quota for this model has been reached. "
                    "Check your Google AI Studio quotas and billing, or try again "
                    "after the quota resets."
                )
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "errorText": error_text,
                    },
                    separators=(",", ":"),
                )
                + "\n\n"
            )
            return

        await asyncio.sleep(0)
        while not status_queue.empty():
            stage, message = status_queue.get_nowait()
            async for event in stream_status(stage, message):
                yield event

        validation = await validator.validate(answer, registry)
        if validation.ok:
            break

    if answer is None or validation is None:
        raise RuntimeError("The chat turn did not produce an answer.")

    async for event in stream_grounded_turn_and_persist(
        session=session,
        thread_id=thread_id,
        user_message=user_message,
        answer=answer,
        registry=registry,
        validation=validation,
    ):
        yield event
