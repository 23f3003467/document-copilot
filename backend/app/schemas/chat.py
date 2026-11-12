"""Schemas shared by chat persistence and the chat API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ThreadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]


class CreateThreadRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class CitationPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    citation_index: int = Field(alias="citationIndex")
    chunk_id: UUID = Field(alias="chunkId")
    excerpt: str
    ticker: str
    company_name: str | None = Field(default=None, alias="companyName")
    form: str
    filing_date: date = Field(alias="filingDate")
    page: str | None = None
    section: str | None = None


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class CitationPart(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["data-citation"] = "data-citation"
    id: str | None = None
    data: CitationPayload


class StatusPart(BaseModel):
    type: Literal["data-status"] = "data-status"
    data: dict[str, Any]


MessagePart = TextPart | CitationPart | StatusPart | dict[str, Any]


class UIMessage(BaseModel):
    id: str | None = None
    role: Literal["system", "user", "assistant"]
    parts: list[MessagePart] = Field(default_factory=list)

    @field_validator("parts", mode="before")
    @classmethod
    def parse_known_parts(cls, parts: Any) -> Any:
        if not isinstance(parts, list):
            return parts

        parsed: list[Any] = []
        for part in parts:
            if not isinstance(part, dict):
                parsed.append(part)
                continue
            if part.get("type") == "text":
                parsed.append(TextPart.model_validate(part))
            elif part.get("type") == "data-citation":
                parsed.append(CitationPart.model_validate(part))
            elif part.get("type") == "data-status":
                parsed.append(StatusPart.model_validate(part))
            else:
                parsed.append(part)
        return parsed


class ChatMessageResponse(UIMessage):
    model_config = ConfigDict(populate_by_name=True)

    created_at: datetime = Field(alias="createdAt")


class MessageHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]


class CitationContextChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    chunk_id: UUID = Field(alias="chunkId")
    chunk_index: int = Field(alias="chunkIndex")
    role: Literal["previous", "anchor", "next"]
    text: str
    page: str | None = None
    section: str | None = None


class CitationContextTable(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    table_index: int = Field(alias="tableIndex")
    title: str | None = None
    units: str | None = None
    markdown: str
    table_data: dict[str, Any] = Field(default_factory=dict, alias="tableData")


class CitationContextResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    anchor_chunk_id: UUID = Field(alias="anchorChunkId")
    document_id: UUID = Field(alias="documentId")
    ticker: str
    company_name: str | None = Field(default=None, alias="companyName")
    form: str
    filing_date: date = Field(alias="filingDate")
    source_url: str = Field(alias="sourceUrl")
    chunks: list[CitationContextChunk]
    table: CitationContextTable | None = None


class StreamRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    thread_id: str = Field(alias="threadId")
    messages: list[UIMessage] = Field(default_factory=list)
