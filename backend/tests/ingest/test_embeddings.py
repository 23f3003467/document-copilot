from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from ingest.embeddings import _client, embed_texts


def test_embedding_client_uses_configured_openai_compatible_endpoint() -> None:
    with patch("ingest.embeddings.OpenAI") as openai_client:
        _client()

    openai_client.assert_called_once_with(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        max_retries=0,
    )


def test_embed_texts_splits_batches_by_token_budget() -> None:
    create = MagicMock(
        side_effect=[
            SimpleNamespace(
                data=[
                    SimpleNamespace(
                        index=0,
                        embedding=[0.0] * settings.openai_embedding_dimensions,
                    ),
                    SimpleNamespace(
                        index=1,
                        embedding=[1.0] * settings.openai_embedding_dimensions,
                    ),
                ]
            ),
            SimpleNamespace(
                data=[
                    SimpleNamespace(
                        index=0,
                        embedding=[2.0] * settings.openai_embedding_dimensions,
                    )
                ]
            ),
        ]
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))

    with (
        patch("ingest.embeddings._client", return_value=client),
        patch("ingest.embeddings._wait_for_token_quota") as wait_for_quota,
    ):
        vectors = embed_texts(
            ["first", "second", "third"],
            token_counts=[6_000, 3_000, 3_000],
        )

    assert len(vectors) == 3
    assert [call.kwargs["input"] for call in client.embeddings.create.call_args_list] == [
        ["first", "second"],
        ["third"],
    ]
    assert [call.args[0] for call in wait_for_quota.call_args_list] == [9_000, 3_000]


def test_embed_texts_requires_token_count_per_input() -> None:
    with pytest.raises(ValueError, match="one count per input"):
        embed_texts(["first"], token_counts=[])


def test_embed_texts_rejects_batch_token_count_over_limit() -> None:
    with pytest.raises(ValueError, match="token count"):
        embed_texts(["oversized"], token_counts=[10_000])


def test_embed_texts_preserves_response_order_when_index_is_missing() -> None:
    create = MagicMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=None,
                    embedding=[0.0] * settings.openai_embedding_dimensions,
                ),
                SimpleNamespace(
                    index=1,
                    embedding=[1.0] * settings.openai_embedding_dimensions,
                ),
            ]
        )
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))

    with (
        patch("ingest.embeddings._client", return_value=client),
        patch("ingest.embeddings._wait_for_token_quota"),
    ):
        vectors = embed_texts(["first", "second"], token_counts=[1, 1])

    assert vectors[0][0] == 0.0
    assert vectors[1][0] == 1.0
