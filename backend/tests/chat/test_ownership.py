import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.chat import service
from app.schemas.chat import StreamRequest, TextPart, UIMessage


def test_delete_thread_allows_owner() -> None:
    user_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    thread = SimpleNamespace(id=thread_id, user_id=user_id)
    session = MagicMock()

    with (
        patch("app.chat.service.chat_repository.get_thread", return_value=thread),
        patch("app.chat.service.chat_repository.delete_thread") as delete,
    ):
        service.delete_thread(session, user_id, str(thread_id))

    delete.assert_called_once_with(session, thread)
    session.commit.assert_called_once()


def test_delete_thread_rejects_foreign_owner() -> None:
    thread_id = uuid.uuid4()
    thread = SimpleNamespace(id=thread_id, user_id=uuid.uuid4())
    session = MagicMock()

    with (
        patch("app.chat.service.chat_repository.get_thread", return_value=thread),
        patch("app.chat.service.chat_repository.delete_thread") as delete,
        pytest.raises(service.ThreadAccessDeniedError),
    ):
        service.delete_thread(session, uuid.uuid4(), str(thread_id))

    delete.assert_not_called()
    session.commit.assert_not_called()


def test_invalid_thread_id_is_not_found() -> None:
    with pytest.raises(service.ThreadNotFoundError):
        service.delete_thread(MagicMock(), uuid.uuid4(), "not-a-uuid")


def test_prepare_turn_releases_read_transaction() -> None:
    thread_id = uuid.uuid4()
    session = MagicMock()
    message = UIMessage(role="user", parts=[TextPart(text="Question")])
    payload = StreamRequest(thread_id=str(thread_id), messages=[message])
    thread = SimpleNamespace(id=thread_id)

    with patch("app.chat.service._owned_thread", return_value=thread):
        turn = service.prepare_turn(session, uuid.uuid4(), payload)

    assert turn.thread_id == thread_id
    assert turn.user_message is message
    session.rollback.assert_called_once()
