import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.chat.service import persist_grounded_turn
from app.database.models import MessageRole
from app.schemas.chat import CitationPart, CitationPayload, TextPart, UIMessage


def test_persist_grounded_turn_saves_messages_and_citations() -> None:
    thread_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    assistant_id = uuid.uuid4()
    thread = SimpleNamespace(
        id=thread_id,
        title="New chat",
        updated_at=None,
    )
    user_message = UIMessage(
        id="client-user-id",
        role="user",
        parts=[TextPart(type="text", text="What changed in cloud revenue?")],
    )
    assistant_message = UIMessage(
        id=str(assistant_id),
        role="assistant",
        parts=[
            TextPart(type="text", text="Cloud revenue increased [1]."),
            CitationPart(
                id=str(chunk_id),
                data=CitationPayload(
                    citation_index=1,
                    chunk_id=chunk_id,
                    excerpt="Cloud revenue increased significantly.",
                    ticker="MSFT",
                    company_name="Microsoft Corporation",
                    form="10-K",
                    filing_date=date(2024, 7, 30),
                    page="15",
                    section="MD&A",
                ),
            ),
        ],
    )
    session = MagicMock()
    messages = []
    citations = []

    def record_message(_session, **kwargs):
        messages.append(kwargs)

    def record_citation(_session, **kwargs):
        citations.append(kwargs)

    with (
        patch(
            "app.chat.service.chat_repository.next_message_sequence",
            return_value=3,
        ),
        patch("app.chat.service.chat_repository.add_message", side_effect=record_message),
        patch(
            "app.chat.service.chat_repository.add_citation",
            side_effect=record_citation,
        ),
    ):
        persist_grounded_turn(
            session,
            thread=thread,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    assert [message["role"] for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert [message["sequence"] for message in messages] == [3, 4]
    assert messages[0]["content"] == "What changed in cloud revenue?"
    assert messages[1]["content"] == "Cloud revenue increased [1]."
    assert isinstance(messages[0]["message_id"], uuid.UUID)
    assert messages[1]["message_id"] == assistant_id
    assert citations == [
        {
            "message_id": assistant_id,
            "chunk_id": chunk_id,
            "citation_index": 1,
            "excerpt": "Cloud revenue increased significantly.",
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "form": "10-K",
            "filing_date": date(2024, 7, 30),
            "page": "15",
            "section": "MD&A",
        }
    ]
    assert thread.title == "What changed in cloud revenue?"
    session.commit.assert_called_once()
