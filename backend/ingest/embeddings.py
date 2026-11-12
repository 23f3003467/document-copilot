"""OpenAI embedding generation for document chunks."""

from __future__ import annotations

import re
from collections import deque
from time import monotonic, sleep

from openai import OpenAI, RateLimitError

from app.config import settings

EMBED_BATCH_SIZE = 100
EMBED_BATCH_TOKEN_LIMIT = 9_000
EMBED_TOKEN_RATE_LIMIT = 20_000
EMBED_TOKEN_RATE_WINDOW_SECONDS = 60.0
MAX_RATE_LIMIT_RETRIES = 3

_recent_token_requests: deque[tuple[float, int]] = deque()


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        max_retries=0,
    )


def _embedding_batches(
    texts: list[str],
    token_counts: list[int],
    batch_size: int,
):
    batch: list[str] = []
    batch_tokens = 0

    for text, token_count in zip(texts, token_counts, strict=True):
        if token_count < 0 or token_count > EMBED_BATCH_TOKEN_LIMIT:
            raise ValueError(
                f"Embedding input token count must be between 0 and "
                f"{EMBED_BATCH_TOKEN_LIMIT}, got {token_count}"
            )
        if batch and (
            len(batch) >= batch_size
            or batch_tokens + token_count > EMBED_BATCH_TOKEN_LIMIT
        ):
            yield batch, batch_tokens
            batch = []
            batch_tokens = 0

        batch.append(text)
        batch_tokens += token_count

    if batch:
        yield batch, batch_tokens


def _wait_for_token_quota(token_count: int) -> None:
    while True:
        now = monotonic()
        while (
            _recent_token_requests
            and now - _recent_token_requests[0][0] >= EMBED_TOKEN_RATE_WINDOW_SECONDS
        ):
            _recent_token_requests.popleft()

        tokens_in_window = sum(tokens for _, tokens in _recent_token_requests)
        if tokens_in_window + token_count <= EMBED_TOKEN_RATE_LIMIT:
            _recent_token_requests.append((now, token_count))
            return

        wait_seconds = (
            _recent_token_requests[0][0]
            + EMBED_TOKEN_RATE_WINDOW_SECONDS
            - now
        )
        print(f"  Embedding quota reached; waiting {wait_seconds:.0f}s...")
        sleep(wait_seconds)


def _retry_delay(error: RateLimitError) -> float:
    retry_after = error.response.headers.get("retry-after")
    if retry_after is not None:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass

    match = re.search(r"retry in ([\d.]+)s", str(error), re.IGNORECASE)
    if match:
        return max(float(match.group(1)), 1.0)
    return EMBED_TOKEN_RATE_WINDOW_SECONDS


def embed_texts(
    texts: list[str],
    *,
    token_counts: list[int],
    batch_size: int = EMBED_BATCH_SIZE,
) -> list[list[float]]:
    if not texts:
        return []
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if len(token_counts) != len(texts):
        raise ValueError("token_counts must contain one count per input text")

    expected_dims = settings.openai_embedding_dimensions
    vectors: list[list[float]] = []
    client = _client()

    for batch, batch_tokens in _embedding_batches(texts, token_counts, batch_size):
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            _wait_for_token_quota(batch_tokens)
            try:
                response = client.embeddings.create(
                    input=batch,
                    model=settings.openai_embedding_model,
                    dimensions=expected_dims,
                )
                break
            except RateLimitError as error:
                if attempt == MAX_RATE_LIMIT_RETRIES:
                    raise
                wait_seconds = _retry_delay(error)
                print(f"  Embedding API rate limited; retrying in {wait_seconds:.0f}s...")
                sleep(wait_seconds)

        ordered = list(response.data)
        if all(item.index is not None for item in ordered):
            ordered.sort(key=lambda item: item.index)
        if len(ordered) != len(batch):
            raise ValueError(
                f"Expected {len(batch)} embeddings, got {len(ordered)}"
            )
        for item in ordered:
            embedding = item.embedding
            if len(embedding) != expected_dims:
                raise ValueError(
                    f"Expected embedding dimension {expected_dims}, got {len(embedding)}"
                )
            vectors.append(embedding)

    return vectors
