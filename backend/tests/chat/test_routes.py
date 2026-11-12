import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import CurrentUser, get_current_user
from app.chat.service import PreparedTurn
from app.database.session import get_db_session
from app.main import app
from app.schemas.chat import (
    CitationContextChunk,
    CitationContextResponse,
    CitationPart,
    StreamRequest,
    ThreadListResponse,
    ThreadResponse,
    UIMessage,
)

USER_ID = uuid.uuid4()
THREAD_ID = uuid.uuid4()
NOW = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)
TEST_USER = CurrentUser(
    id=str(USER_ID),
    email="analyst@example.com",
    last_sign_in_at=None,
)


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _thread_response() -> ThreadResponse:
    return ThreadResponse(
        id=str(THREAD_ID),
        title="Test",
        created_at=NOW,
        updated_at=NOW,
    )


def test_list_threads_returns_thread_list(client: TestClient) -> None:
    expected = ThreadListResponse(threads=[_thread_response()])
    with patch("app.api.chat.chat_service.list_threads", return_value=expected):
        response = client.get("/chat/threads")

    assert response.status_code == 200
    assert response.json()["threads"][0]["id"] == str(THREAD_ID)


def test_create_thread_passes_authenticated_identity(client: TestClient) -> None:
    expected = _thread_response()
    with patch(
        "app.api.chat.chat_service.create_thread",
        return_value=expected,
    ) as create:
        response = client.post("/chat/threads", json={"title": "Test"})

    assert response.status_code == 200
    assert response.json()["id"] == str(THREAD_ID)
    assert create.call_args.args[1] == USER_ID
    assert create.call_args.kwargs["email"] == TEST_USER["email"]


def test_create_thread_requires_json_body(client: TestClient) -> None:
    response = client.post("/chat/threads")
    assert response.status_code == 422


def test_create_thread_rejects_user_without_email(client: TestClient) -> None:
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=str(USER_ID),
        email=None,
        last_sign_in_at=None,
    )
    response = client.post("/chat/threads", json={})
    assert response.status_code == 422


def test_delete_thread_returns_no_content_for_owner(client: TestClient) -> None:
    with patch("app.api.chat.chat_service.delete_thread") as delete:
        response = client.delete(f"/chat/threads/{THREAD_ID}")

    assert response.status_code == 204
    assert response.content == b""
    delete.assert_called_once()


def test_delete_thread_maps_foreign_owner_to_forbidden(client: TestClient) -> None:
    from app.chat.service import ThreadAccessDeniedError

    with patch(
        "app.api.chat.chat_service.delete_thread",
        side_effect=ThreadAccessDeniedError,
    ):
        response = client.delete(f"/chat/threads/{THREAD_ID}")

    assert response.status_code == 403


def test_get_thread_messages_maps_missing_thread_to_not_found(
    client: TestClient,
) -> None:
    from app.chat.service import ThreadNotFoundError

    with patch(
        "app.api.chat.chat_service.get_thread_messages",
        side_effect=ThreadNotFoundError,
    ):
        response = client.get(f"/chat/threads/{THREAD_ID}/messages")

    assert response.status_code == 404


def test_get_thread_messages_returns_camel_case_timestamps(
    client: TestClient,
) -> None:
    from app.schemas.chat import ChatMessageResponse, MessageHistoryResponse, TextPart

    messages = MessageHistoryResponse(
        messages=[
            ChatMessageResponse(
                id=str(uuid.uuid4()),
                role="assistant",
                parts=[TextPart(text="Saved answer")],
                created_at=NOW,
            )
        ]
    )
    with patch(
        "app.api.chat.chat_service.get_thread_messages",
        return_value=messages,
    ):
        response = client.get(f"/chat/threads/{THREAD_ID}/messages")

    assert response.status_code == 200
    assert response.json()["messages"][0]["createdAt"] == NOW.isoformat().replace(
        "+00:00", "Z"
    )


def test_get_citation_context_returns_neighbor_chunks(client: TestClient) -> None:
    chunk_id = uuid.uuid4()
    context = CitationContextResponse(
        anchor_chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        ticker="AAPL",
        company_name="Apple Inc.",
        form="10-K",
        filing_date="2024-11-01",
        source_url="https://example.com/aapl-10k",
        chunks=[
            CitationContextChunk(
                chunk_id=uuid.uuid4(),
                chunk_index=36,
                role="previous",
                text="Prior context",
                page="7",
                section="Products",
            ),
            CitationContextChunk(
                chunk_id=chunk_id,
                chunk_index=37,
                role="anchor",
                text="Anchor context",
                page="8",
                section="Products",
            ),
            CitationContextChunk(
                chunk_id=uuid.uuid4(),
                chunk_index=38,
                role="next",
                text="Following context",
                page="8",
                section="Products",
            ),
        ],
    )
    with patch(
        "app.api.chat.chat_service.get_citation_context",
        return_value=context,
    ) as get_context:
        response = client.get(
            f"/chat/citations/{chunk_id}/context?radius=2",
        )

    assert response.status_code == 200
    assert response.json()["anchorChunkId"] == str(chunk_id)
    assert [chunk["role"] for chunk in response.json()["chunks"]] == [
        "previous",
        "anchor",
        "next",
    ]
    assert get_context.call_args.args[1:] == (chunk_id, 2)


def test_get_citation_context_returns_404_for_missing_chunk(
    client: TestClient,
) -> None:
    chunk_id = uuid.uuid4()
    with patch("app.api.chat.chat_service.get_citation_context", return_value=None):
        response = client.get(f"/chat/citations/{chunk_id}/context")
    assert response.status_code == 404


def test_get_citation_context_validates_radius(client: TestClient) -> None:
    response = client.get(f"/chat/citations/{uuid.uuid4()}/context?radius=6")
    assert response.status_code == 422


def test_post_stream_returns_event_stream(client: TestClient) -> None:
    turn = PreparedTurn(
        thread_id=THREAD_ID,
        user_message=UIMessage(
            role="user",
            parts=[{"type": "text", "text": "Hello"}],
        ),
    )

    async def fake_stream(**_kwargs):
        yield 'data: {"type":"text-start","id":"message-id"}\n\n'
        yield 'data: {"type":"text-end","id":"message-id"}\n\n'

    with (
        patch("app.api.chat.chat_service.prepare_turn", return_value=turn),
        patch("app.api.chat.orchestrator.run_turn", fake_stream),
    ):
        response = client.post(
            "/chat/stream",
            json={
                "threadId": str(THREAD_ID),
                "messages": [
                    {
                        "role": "user",
                        "parts": [{"type": "text", "text": "Hello"}],
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "text-start" in response.text


def test_stream_request_accepts_camel_case_citation_parts() -> None:
    thread_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    request = StreamRequest.model_validate(
        {
            "threadId": str(thread_id),
            "messages": [
                {
                    "id": "assistant-message",
                    "role": "assistant",
                    "parts": [
                        {"type": "text", "text": "Answer with a citation."},
                        {
                            "type": "data-citation",
                            "id": str(chunk_id),
                            "data": {
                                "citationIndex": 1,
                                "chunkId": str(chunk_id),
                                "excerpt": "Relevant excerpt",
                                "ticker": "AAPL",
                                "companyName": "Apple Inc.",
                                "form": "10-K",
                                "filingDate": "2024-10-31",
                                "page": "42",
                                "section": "Risk Factors",
                            },
                        },
                    ],
                },
                {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Follow up"}],
                },
            ],
        }
    )

    citation_part = request.messages[0].parts[1]
    assert isinstance(citation_part, CitationPart)
    assert citation_part.data.citation_index == 1
    assert citation_part.data.chunk_id == chunk_id
