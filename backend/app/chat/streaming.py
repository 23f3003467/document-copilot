"""AI SDK-compatible grounded answer events and persistence."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.assistant.deps import TurnRegistry
from app.assistant.outputs import GroundedAnswer
from app.chat.messages import build_assistant_message
from app.chat.service import ThreadNotFoundError, persist_grounded_turn
from app.database.repositories import chats as chat_repository
from app.grounding.validator import ValidationResult
from app.schemas.chat import CitationPart, UIMessage


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def stream_status(stage: str, message: str) -> AsyncGenerator[str, None]:
    yield _event({"type": "data-status", "data": {"stage": stage, "message": message}})


async def stream_grounded_answer(
    answer: GroundedAnswer,
    registry: TurnRegistry,
    *,
    message_id: str,
) -> AsyncGenerator[str, None]:
    assistant_message = build_assistant_message(answer, registry)
    assistant_message.id = message_id
    text = answer.answer
    yield _event(
        {
            "type": "start",
            "messageId": message_id,
            "message": {
                "id": message_id,
                "role": "assistant",
                "parts": [{"type": "text", "text": "", "state": "streaming"}],
            },
        }
    )
    yield _event({"type": "text-start", "id": message_id})
    for offset in range(0, len(text), 18):
        yield _event(
            {
                "type": "text-delta",
                "id": message_id,
                "delta": text[offset : offset + 18],
            }
        )
    yield _event({"type": "text-end", "id": message_id})

    for part in assistant_message.parts:
        if isinstance(part, CitationPart):
            yield _event(
                {
                    "type": "data-citation",
                    "id": part.id,
                    "data": part.data.model_dump(mode="json", by_alias=True),
                }
            )

    completion_tokens = len(text.split())
    yield _event(
        {
            "type": "finish",
            "finishReason": "stop",
            "usage": {
                "promptTokens": 0,
                "completionTokens": completion_tokens,
                "totalTokens": completion_tokens,
            },
            "providerMetadata": {},
        }
    )


async def append_grounded_turn(
    session: Session,
    *,
    thread_id: UUID,
    user_message: UIMessage,
    assistant_message: UIMessage,
) -> None:
    thread = chat_repository.get_thread_for_update(session, thread_id)
    if thread is None:
        raise ThreadNotFoundError
    persist_grounded_turn(
        session,
        thread=thread,
        user_message=user_message,
        assistant_message=assistant_message,
    )


async def stream_grounded_turn_and_persist(
    *,
    session: Session,
    thread_id: UUID,
    user_message: UIMessage,
    answer: GroundedAnswer,
    registry: TurnRegistry,
    validation: ValidationResult,
) -> AsyncGenerator[str, None]:
    if not validation.ok:
        yield _event(
            {
                "type": "error",
                "errorText": (
                    "I found relevant source passages but could not fully verify "
                    "an answer. Please try rephrasing your question."
                ),
            }
        )
        return

    assistant_message = build_assistant_message(answer, registry)
    try:
        await append_grounded_turn(
            session,
            thread_id=thread_id,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except ThreadNotFoundError:
        yield _event(
            {
                "type": "error",
                "errorText": "This conversation was deleted before the answer could be saved.",
            }
        )
        return
    async for event in stream_status("streaming", "Preparing your answer…"):
        yield event
    async for event in stream_grounded_answer(
        answer,
        registry,
        message_id=assistant_message.id or "",
    ):
        yield event
