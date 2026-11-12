"""SQLAlchemy persistence operations for chat threads and messages."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import (
    ChatMessage,
    ChatThread,
    MessageCitation,
    MessageRole,
)


def list_threads(session: Session, user_id: uuid.UUID) -> list[ChatThread]:
    return list(
        session.scalars(
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc())
        ).all()
    )


def get_thread(session: Session, thread_id: uuid.UUID) -> ChatThread | None:
    return session.get(ChatThread, thread_id)


def get_thread_for_update(
    session: Session,
    thread_id: uuid.UUID,
) -> ChatThread | None:
    return session.scalar(
        select(ChatThread)
        .where(ChatThread.id == thread_id)
        .with_for_update()
    )


def add_thread(
    session: Session,
    *,
    user_id: uuid.UUID,
    title: str,
) -> ChatThread:
    thread = ChatThread(user_id=user_id, title=title)
    session.add(thread)
    return thread


def delete_thread(session: Session, thread: ChatThread) -> None:
    session.delete(thread)


def list_messages(session: Session, thread_id: uuid.UUID) -> list[ChatMessage]:
    return list(
        session.scalars(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.sequence.asc())
        ).all()
    )


def next_message_sequence(session: Session, thread_id: uuid.UUID) -> int:
    latest_sequence = session.scalar(
        select(func.max(ChatMessage.sequence)).where(
            ChatMessage.thread_id == thread_id
        )
    )
    return 0 if latest_sequence is None else latest_sequence + 1


def add_message(
    session: Session,
    *,
    thread_id: uuid.UUID,
    role: MessageRole,
    content: str | None,
    parts: list[dict[str, Any]],
    sequence: int,
    message_id: uuid.UUID | None = None,
) -> ChatMessage:
    message = ChatMessage(
        id=message_id or uuid.uuid4(),
        thread_id=thread_id,
        role=role,
        content=content,
        parts=parts,
        sequence=sequence,
    )
    session.add(message)
    return message


def add_citation(
    session: Session,
    *,
    message_id: uuid.UUID,
    chunk_id: uuid.UUID,
    citation_index: int,
    excerpt: str,
    ticker: str,
    company_name: str | None,
    form: str,
    filing_date: date,
    page: str | None,
    section: str | None,
) -> MessageCitation:
    citation = MessageCitation(
        message_id=message_id,
        chunk_id=chunk_id,
        citation_index=citation_index,
        excerpt=excerpt,
        ticker=ticker,
        company_name=company_name,
        form=form,
        filing_date=filing_date,
        page=page,
        section=section,
    )
    session.add(citation)
    return citation
