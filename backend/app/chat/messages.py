"""Conversions between persisted chat messages and AI SDK UI messages."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status

from app.assistant.deps import TurnRegistry
from app.assistant.outputs import GroundedAnswer
from app.schemas.chat import CitationPart, CitationPayload, TextPart, UIMessage

DEFAULT_THREAD_TITLE = "New chat"
MAX_THREAD_TITLE_LENGTH = 255


def text_from_parts(parts: list[Any]) -> str:
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, TextPart):
            text_parts.append(part.text)
        elif isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "".join(text_parts)


def extract_last_user_message(messages: list[UIMessage]) -> UIMessage:
    for message in reversed(messages):
        if message.role == "user":
            return message
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="At least one user message is required.",
    )


def ui_message_to_insert(
    message: UIMessage,
    *,
    thread_id: uuid.UUID,
    sequence: int,
    message_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    text = text_from_parts(message.parts).strip()
    return {
        "id": str(message_id or uuid.uuid4()),
        "thread_id": str(thread_id),
        "role": message.role,
        "content": text or None,
        "parts": message.model_dump(
            mode="json",
            by_alias=True,
            include={"parts"},
        )["parts"],
        "sequence": sequence,
    }


def row_to_ui_message(row: Mapping[str, Any]) -> UIMessage:
    parts = row.get("parts") or []
    if not parts and row.get("content"):
        parts = [{"type": "text", "text": row["content"]}]
    return UIMessage(id=str(row["id"]), role=row["role"], parts=parts)


def title_from_user_message(message: UIMessage) -> str:
    title = text_from_parts(message.parts).strip()
    if len(title) > MAX_THREAD_TITLE_LENGTH:
        return f"{title[: MAX_THREAD_TITLE_LENGTH - 3].rstrip()}..."
    return title or DEFAULT_THREAD_TITLE


def citation_parts_from_grounded_answer(
    answer: GroundedAnswer,
    registry: TurnRegistry,
) -> list[CitationPart]:
    parts: list[CitationPart] = []
    for citation in answer.citations:
        passage = registry.passages_by_chunk_id.get(citation.chunk_id)
        if passage is None:
            raise ValueError(f"Citation references unregistered chunk {citation.chunk_id}.")
        parts.append(
            CitationPart(
                id=str(citation.chunk_id),
                data=CitationPayload(
                    citation_index=citation.citation_index,
                    chunk_id=citation.chunk_id,
                    excerpt=citation.excerpt,
                    ticker=passage.ticker,
                    company_name=passage.company_name,
                    form=passage.form,
                    filing_date=passage.filing_date,
                    page=passage.page,
                    section=passage.section,
                ),
            )
        )
    return parts


def build_assistant_message(
    answer: GroundedAnswer,
    registry: TurnRegistry,
) -> UIMessage:
    return UIMessage(
        id=str(uuid.uuid4()),
        role="assistant",
        parts=[
            TextPart(type="text", text=answer.answer),
            *citation_parts_from_grounded_answer(answer, registry),
        ],
    )
