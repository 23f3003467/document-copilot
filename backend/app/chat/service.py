"""Chat use cases coordinating API schemas and database repositories."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.chat.messages import (
    extract_last_user_message,
    text_from_parts,
    title_from_user_message,
    ui_message_to_insert,
)
from app.database.models import ChatThread, MessageRole
from app.database.repositories import chats as chat_repository
from app.database.repositories import documents as document_repository
from app.database.repositories import users as user_repository
from app.schemas.chat import (
    ChatMessageResponse,
    CitationContextChunk,
    CitationContextResponse,
    CitationContextTable,
    CitationPart,
    CreateThreadRequest,
    MessageHistoryResponse,
    StreamRequest,
    ThreadListResponse,
    ThreadResponse,
    UIMessage,
)

DEFAULT_THREAD_TITLE = "New chat"


class ChatServiceError(Exception):
    """Base error for chat use cases that the API maps to an HTTP response."""


class ThreadNotFoundError(ChatServiceError):
    pass


class ThreadAccessDeniedError(ChatServiceError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedTurn:
    thread_id: uuid.UUID
    user_message: UIMessage


def _thread_response(thread: ChatThread) -> ThreadResponse:
    return ThreadResponse(
        id=str(thread.id),
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _owned_thread(
    session: Session,
    thread_id: str,
    user_id: uuid.UUID,
) -> ChatThread:
    try:
        parsed_thread_id = uuid.UUID(thread_id)
    except ValueError as exc:
        raise ThreadNotFoundError from exc

    thread = chat_repository.get_thread(session, parsed_thread_id)
    if thread is None:
        raise ThreadNotFoundError
    if thread.user_id != user_id:
        raise ThreadAccessDeniedError
    return thread


def list_threads(session: Session, user_id: uuid.UUID) -> ThreadListResponse:
    threads = chat_repository.list_threads(session, user_id)
    return ThreadListResponse(threads=[_thread_response(thread) for thread in threads])


def create_thread(
    session: Session,
    user_id: uuid.UUID,
    payload: CreateThreadRequest,
    *,
    email: str,
) -> ThreadResponse:
    title = (payload.title or DEFAULT_THREAD_TITLE).strip() or DEFAULT_THREAD_TITLE
    user_repository.ensure_user(session, user_id=user_id, email=email)
    thread = chat_repository.add_thread(session, user_id=user_id, title=title)
    session.commit()
    session.refresh(thread)
    return _thread_response(thread)


def delete_thread(
    session: Session,
    user_id: uuid.UUID,
    thread_id: str,
) -> None:
    thread = _owned_thread(session, thread_id, user_id)
    chat_repository.delete_thread(session, thread)
    session.commit()


def get_thread_messages(
    session: Session,
    user_id: uuid.UUID,
    thread_id: str,
) -> MessageHistoryResponse:
    thread = _owned_thread(session, thread_id, user_id)
    messages = chat_repository.list_messages(session, thread.id)
    response_messages = []
    for message in messages:
        parts: list[dict[str, Any]] = message.parts or []
        if not parts and message.content:
            parts = [{"type": "text", "text": message.content}]
        response_messages.append(
            ChatMessageResponse(
                id=str(message.id),
                role=message.role.value,
                parts=parts,
                created_at=message.created_at,
            )
        )
    return MessageHistoryResponse(messages=response_messages)


def get_citation_context(
    session: Session,
    chunk_id: uuid.UUID,
    radius: int,
) -> CitationContextResponse | None:
    chunks = document_repository.get_chunk_context(session, chunk_id, radius)
    if chunks is None or not chunks:
        return None

    anchor = next((chunk for chunk in chunks if chunk.id == chunk_id), None)
    if anchor is None or anchor.document is None:
        return None
    document = anchor.document

    context_chunks = [
        CitationContextChunk(
            chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            role=(
                "anchor"
                if chunk.id == anchor.id
                else "previous"
                if chunk.chunk_index < anchor.chunk_index
                else "next"
            ),
            text=chunk.text,
            page=chunk.page,
            section=chunk.section,
        )
        for chunk in chunks
    ]

    table: CitationContextTable | None = None
    table_metadata = (anchor.chunk_metadata or {}).get("table")
    if isinstance(table_metadata, dict):
        table_data = table_metadata.get("table_data")
        if not isinstance(table_data, dict):
            table_data = {
                key: table_metadata[key]
                for key in ("rows", "columns", "footnotes")
                if key in table_metadata
            }
        table = CitationContextTable(
            table_index=int(table_metadata["table_index"]),
            title=table_metadata.get("title"),
            units=table_metadata.get("units"),
            markdown=table_metadata["markdown"],
            table_data=table_data,
        )

    return CitationContextResponse(
        anchor_chunk_id=anchor.id,
        document_id=document.id,
        ticker=document.ticker,
        company_name=document.company_name,
        form=document.form,
        filing_date=document.filing_date,
        source_url=document.source_url,
        chunks=context_chunks,
        table=table,
    )


def prepare_turn(
    session: Session,
    user_id: uuid.UUID,
    payload: StreamRequest,
) -> PreparedTurn:
    thread = _owned_thread(session, payload.thread_id, user_id)
    latest_user_message = extract_last_user_message(payload.messages)
    if not text_from_parts(latest_user_message.parts).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The latest user message must contain text.",
        )
    thread_id = thread.id
    session.rollback()
    return PreparedTurn(thread_id=thread_id, user_message=latest_user_message)


def persist_grounded_turn(
    session: Session,
    *,
    thread: ChatThread,
    user_message: UIMessage,
    assistant_message: UIMessage,
) -> None:
    sequence = chat_repository.next_message_sequence(session, thread.id)
    user_row = ui_message_to_insert(user_message, thread_id=thread.id, sequence=sequence)
    chat_repository.add_message(
        session,
        thread_id=thread.id,
        role=MessageRole.USER,
        content=user_row["content"],
        parts=user_row["parts"],
        sequence=sequence,
        message_id=uuid.UUID(user_row["id"]),
    )
    assistant_id = (
        uuid.UUID(assistant_message.id)
        if assistant_message.id is not None
        else uuid.uuid4()
    )
    assistant_row = ui_message_to_insert(
        assistant_message,
        thread_id=thread.id,
        sequence=sequence + 1,
        message_id=assistant_id,
    )
    chat_repository.add_message(
        session,
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=assistant_row["content"],
        parts=assistant_row["parts"],
        sequence=sequence + 1,
        message_id=assistant_id,
    )

    for part in assistant_message.parts:
        if isinstance(part, CitationPart):
            citation = part.data
            chat_repository.add_citation(
                session,
                message_id=assistant_id,
                chunk_id=citation.chunk_id,
                citation_index=citation.citation_index,
                excerpt=citation.excerpt,
                ticker=citation.ticker,
                company_name=citation.company_name,
                form=citation.form,
                filing_date=citation.filing_date,
                page=citation.page,
                section=citation.section,
            )

    if thread.title == DEFAULT_THREAD_TITLE:
        thread.title = title_from_user_message(user_message)
    thread.updated_at = datetime.now(UTC)
    session.commit()
