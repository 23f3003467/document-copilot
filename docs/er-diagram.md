# Database ER Diagram

This diagram reflects the SQLAlchemy models in `backend/app/database/` and the
PostgreSQL-generated search column defined by the initial Alembic migration.

```mermaid
erDiagram
    USERS {
        uuid id PK "Supabase Auth user ID"
        varchar_320 email
        varchar_255 display_name "nullable"
        timestamptz created_at
        timestamptz updated_at
    }

    CHAT_THREADS {
        uuid id PK
        uuid user_id FK
        varchar_255 title
        timestamptz created_at
        timestamptz updated_at
    }

    CHAT_MESSAGES {
        uuid id PK
        uuid thread_id FK
        varchar_20 role "user, assistant, or system"
        text content "nullable"
        jsonb parts "nullable"
        integer sequence
        timestamptz created_at
    }

    MESSAGE_CITATIONS {
        uuid id PK
        uuid message_id FK
        uuid chunk_id FK
        integer citation_index
        text excerpt
        varchar_16 ticker
        varchar_255 company_name "nullable"
        varchar_16 form
        date filing_date
        varchar_64 page "nullable"
        text section "nullable"
        timestamptz created_at
    }

    SOURCE_DOCUMENTS {
        uuid id PK
        varchar_16 ticker
        varchar_10 cik
        varchar_255 company_name "nullable"
        varchar_16 form
        date filing_date
        date report_date "nullable"
        integer fiscal_year "nullable"
        varchar_32 accession_number UK
        varchar_255 primary_document
        text source_url
        text markdown_content "nullable"
        timestamptz ingested_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }

    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK
        integer chunk_index
        varchar_64 page "nullable"
        text section "nullable"
        text text
        vector_768 embedding "nullable"
        integer token_count "nullable"
        jsonb chunk_metadata
        tsvector search_vector "PostgreSQL-generated, not in SQLAlchemy model"
        timestamptz created_at
    }

    DOCUMENT_TABLES {
        uuid id PK
        uuid document_id FK
        integer table_index
        text title "nullable"
        varchar_255 units "nullable"
        text markdown
        jsonb table_data
        varchar_64 source_html_hash
        timestamptz created_at
    }

    USERS ||--o{ CHAT_THREADS : owns
    CHAT_THREADS ||--o{ CHAT_MESSAGES : contains
    CHAT_MESSAGES ||--o{ MESSAGE_CITATIONS : has
    DOCUMENT_CHUNKS ||--o{ MESSAGE_CITATIONS : supports
    SOURCE_DOCUMENTS ||--o{ DOCUMENT_CHUNKS : split_into
    SOURCE_DOCUMENTS ||--o{ DOCUMENT_TABLES : contains
```

## Constraints and indexes

- `source_documents.accession_number` is unique.
- `(document_chunks.document_id, chunk_index)` is unique.
- `(document_tables.document_id, table_index)` is unique.
- `(chat_messages.thread_id, sequence)` is unique.
- `(message_citations.message_id, citation_index)` is unique.
- `document_chunks.search_vector` is generated from `text`; it has a GIN index.
- `document_chunks.embedding` is `vector(768)` and has an HNSW cosine index.
- Chat threads, messages, and citations have row-level security policies scoped
  to the owning authenticated user through `chat_threads.user_id`.

The full-text column and vector indexes are migration-defined PostgreSQL
features; `search_vector` is not declared as a regular SQLAlchemy model column.
