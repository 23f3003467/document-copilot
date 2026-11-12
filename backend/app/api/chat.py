"""HTTP endpoints for chat threads and streaming replies."""

from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_current_user
from app.chat import orchestrator
from app.chat import service as chat_service
from app.database.session import get_db_session
from app.retrieval.retriever import DocumentRetriever
from app.schemas.chat import (
    CitationContextResponse,
    CreateThreadRequest,
    MessageHistoryResponse,
    StreamRequest,
    ThreadListResponse,
    ThreadResponse,
)

router = APIRouter()


def _raise_http_error(error: chat_service.ChatServiceError) -> NoReturn:
    if isinstance(error, chat_service.ThreadNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found.",
        ) from error
    if isinstance(error, chat_service.ThreadAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation.",
        ) from error
    raise error


@router.get("/chat/threads", response_model=ThreadListResponse)
async def list_threads(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> ThreadListResponse:
    """List the authenticated user's chat threads, most recently updated first."""
    return chat_service.list_threads(db, UUID(current_user["id"]))


@router.post("/chat/threads", response_model=ThreadResponse)
async def create_thread(
    payload: CreateThreadRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> ThreadResponse:
    """Create a chat thread for the authenticated user."""
    email = current_user.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An email address is required to create a chat thread.",
        )
    return chat_service.create_thread(
        db,
        UUID(current_user["id"]),
        payload,
        email=email,
    )


@router.delete(
    "/chat/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_thread(
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> Response:
    """Delete the specified thread after confirming the user owns it."""
    try:
        chat_service.delete_thread(db, UUID(current_user["id"]), thread_id)
    except chat_service.ChatServiceError as error:
        _raise_http_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/chat/threads/{thread_id}/messages",
    response_model=MessageHistoryResponse,
)
async def get_thread_messages(
    thread_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> MessageHistoryResponse:
    """Return a thread's messages in conversation order."""
    try:
        return chat_service.get_thread_messages(
            db,
            UUID(current_user["id"]),
            thread_id,
        )
    except chat_service.ChatServiceError as error:
        _raise_http_error(error)


@router.get(
    "/chat/citations/{chunk_id}/context",
    response_model=CitationContextResponse,
)
async def get_citation_context(
    chunk_id: UUID,
    db: Annotated[Session, Depends(get_db_session)],
    _current_user: Annotated[CurrentUser, Depends(get_current_user)],
    radius: Annotated[int, Query(ge=0, le=5)] = 1,
) -> CitationContextResponse:
    """Return a cited chunk with nearby passages and any associated table."""
    context = chat_service.get_citation_context(db, chunk_id, radius)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Citation source not found.",
        )
    return context


@router.post("/chat/stream")
async def stream_chat(
    payload: StreamRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> StreamingResponse:
    """Run a grounded assistant turn and stream its answer as server-sent events."""
    try:
        turn = chat_service.prepare_turn(
            db,
            UUID(current_user["id"]),
            payload,
        )
    except chat_service.ChatServiceError as error:
        _raise_http_error(error)
    return StreamingResponse(
        orchestrator.run_turn(
            session=db,
            thread_id=turn.thread_id,
            user=current_user,
            user_message=turn.user_message,
            retriever=DocumentRetriever(),
        ),
        media_type="text/event-stream",
    )
