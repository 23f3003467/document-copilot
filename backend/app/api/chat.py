"""Thread management and streaming chat endpoints for the Phase 3 backend slice.

The request flow is intentionally straightforward:
1. the auth dependency verifies the caller owns a valid Supabase session,
2. thread lookup checks ownership before any reads or deletes,
3. chat messages are stored in the database with a sequence number, and
4. the stub stream returns a synthetic assistant reply in the AI SDK event format.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.chat_message import ChatMessage
from app.database.chat_thread import ChatThread
from app.database.message_role import MessageRole
from app.database.session import get_db_session

router = APIRouter()


class CreateThreadRequest(BaseModel):
    title: str | None = Field(default=None, description="Optional thread title")


class MessageRequest(BaseModel):
    id: str | None = None
    role: str
    content: Any = None


class StreamRequest(BaseModel):
    threadId: str | None = None
    messages: list[MessageRequest] = Field(default_factory=list)


def get_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _user_id(current_user: dict[str, Any]) -> uuid.UUID:
    user_id = current_user.get("id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return uuid.UUID(str(user_id))


def _serialize_thread(thread: ChatThread) -> dict[str, Any]:
    return {
        "id": str(thread.id),
        "title": thread.title,
        "createdAt": thread.created_at.isoformat(),
        "updatedAt": thread.updated_at.isoformat(),
    }


def _serialize_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": message.role.value,
        "content": message.content or "",
        "createdAt": message.created_at.isoformat(),
    }


def _extract_message_text(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        text = content.strip()
        return text or None
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                part_text = item.get("text")
                if isinstance(part_text, str):
                    parts.append(part_text)
            elif isinstance(item, str):
                parts.append(item)
        combined = " ".join(part.strip() for part in parts if part and part.strip())
        return combined or None
    return str(content).strip() or None


def _thread_or_403(
    db: Session,
    thread_id: str,
    user_id: uuid.UUID,
) -> ChatThread:
    try:
        target_id = uuid.UUID(thread_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found.",
        ) from exc

    thread = db.get(ChatThread, target_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found.",
        )
    if thread.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation.",
        )
    return thread


@router.get("/chat/threads")
async def list_threads(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, list[dict[str, Any]]]:
    user_id = _user_id(current_user)
    threads = (
        db.execute(
            select(ChatThread)
            .where(ChatThread.user_id == user_id)
            .order_by(ChatThread.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return {"threads": [_serialize_thread(thread) for thread in threads]}


@router.post("/chat/threads")
async def create_thread(
    payload: CreateThreadRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    user_id = _user_id(current_user)
    title = (payload.title or "New chat").strip() or "New chat"
    thread = ChatThread(user_id=user_id, title=title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return _serialize_thread(thread)


@router.delete("/chat/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    user_id = _user_id(current_user)
    thread = _thread_or_403(db, thread_id, user_id)
    db.delete(thread)
    db.commit()
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


@router.get("/chat/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: str,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, list[dict[str, Any]]]:
    user_id = _user_id(current_user)
    thread = _thread_or_403(db, thread_id, user_id)
    messages = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread.id)
            .order_by(ChatMessage.sequence.asc())
        )
        .scalars()
        .all()
    )
    return {"messages": [_serialize_message(message) for message in messages]}


@router.post("/chat/stream")
async def stream_chat(
    request: Request,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    raw_body = await request.json()
    payload = StreamRequest.model_validate(raw_body)

    user_id = _user_id(current_user)
    thread: ChatThread | None = None
    if payload.threadId:
        thread = _thread_or_403(db, payload.threadId, user_id)

    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid threadId is required for chat streaming.",
        )

    next_sequence = 0
    latest_messages = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread.id)
            .order_by(ChatMessage.sequence.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if latest_messages is not None:
        next_sequence = latest_messages.sequence + 1

    persisted_user_message: ChatMessage | None = None
    for index, item in enumerate(payload.messages):
        text = _extract_message_text(item.content)
        if text is None:
            continue
        if item.role == "user":
            user_message = ChatMessage(
                id=uuid.UUID(str(item.id)) if item.id else uuid.uuid4(),
                thread_id=thread.id,
                role=MessageRole.USER,
                content=text,
                sequence=next_sequence,
                parts=[{"type": "text", "text": text}],
            )
            db.add(user_message)
            db.flush()
            persisted_user_message = user_message
            next_sequence += 1

    db.commit()

    if persisted_user_message is None:
        user_prompt = "New conversation"
    else:
        user_prompt = persisted_user_message.content or "New conversation"

    assistant_text = (
        "This is a stubbed assistant reply while the retrieval pipeline is still being wired in. "
        f"Your latest message: {user_prompt}"
    )

    assistant_message = ChatMessage(
        id=uuid.uuid4(),
        thread_id=thread.id,
        role=MessageRole.ASSISTANT,
        content=assistant_text,
        sequence=next_sequence,
        parts=[{"type": "text", "text": assistant_text}],
    )
    db.add(assistant_message)
    db.commit()

    def stream_response() -> Generator[str, None, None]:
        message_id = str(uuid.uuid4())
        text_part_id = str(uuid.uuid4())

        def emit(event: dict[str, Any]) -> str:
            return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

        yield emit(
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
        yield emit({"type": "text-start", "id": text_part_id})

        chunk_size = 18
        for index in range(0, len(assistant_text), chunk_size):
            chunk = assistant_text[index : index + chunk_size]
            yield emit({"type": "text-delta", "id": text_part_id, "delta": chunk})

        yield emit({"type": "text-end", "id": text_part_id})
        yield emit(
            {
                "type": "finish",
                "finishReason": "stop",
                "usage": {
                    "promptTokens": 0,
                    "completionTokens": len(assistant_text.split()),
                    "totalTokens": len(assistant_text.split()),
                },
                "providerMetadata": {},
            }
        )

    return StreamingResponse(stream_response(), media_type="text/event-stream")
