import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.chat.service import get_citation_context


def test_get_citation_context_includes_neighbors_and_table_data() -> None:
    document = SimpleNamespace(
        id=uuid.uuid4(),
        ticker="AAPL",
        company_name="Apple Inc.",
        form="10-K",
        filing_date=date(2025, 10, 31),
        source_url="https://example.com/aapl",
    )
    previous = SimpleNamespace(
        id=uuid.uuid4(),
        chunk_index=36,
        text="Previous passage",
        page="7",
        section="Products",
        chunk_metadata={},
        document=document,
    )
    anchor_id = uuid.uuid4()
    anchor = SimpleNamespace(
        id=anchor_id,
        chunk_index=37,
        text="Table excerpt",
        page="8",
        section="Products",
        chunk_metadata={
            "table": {
                "table_index": 2,
                "title": "Products and Services",
                "units": "dollars in millions",
                "markdown": "| Category | Sales |\n| --- | --- |\n| iPhone | 209,586 |",
                "rows": [{"label": "iPhone", "cells": ["209,586"]}],
                "columns": [{"label": "Category"}, {"label": "Sales"}],
                "footnotes": ["Includes related products."],
            }
        },
        document=document,
    )
    following = SimpleNamespace(
        id=uuid.uuid4(),
        chunk_index=38,
        text="Following passage",
        page="8",
        section="Products",
        chunk_metadata={},
        document=document,
    )
    session = MagicMock()

    with patch(
        "app.chat.service.document_repository.get_chunk_context",
        return_value=[previous, anchor, following],
    ) as get_context:
        result = get_citation_context(session, anchor_id, 1)

    assert result is not None
    assert [chunk.role for chunk in result.chunks] == ["previous", "anchor", "next"]
    assert result.ticker == "AAPL"
    assert result.table is not None
    assert result.table.table_index == 2
    assert result.table.table_data["rows"] == [
        {"label": "iPhone", "cells": ["209,586"]}
    ]
    assert result.table.table_data["footnotes"] == ["Includes related products."]
    get_context.assert_called_once_with(session, anchor_id, 1)


def test_get_citation_context_returns_none_for_unknown_chunk() -> None:
    with patch(
        "app.chat.service.document_repository.get_chunk_context",
        return_value=None,
    ):
        assert get_citation_context(MagicMock(), uuid.uuid4(), 1) is None
