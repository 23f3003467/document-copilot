# FastAPI Backend Folder Structure

This is the backend structure used by this project, with each folder's responsibility. Use it as a starting template for future FastAPI projects; add or remove feature-specific folders as needed.

```text
backend/
├── alembic/                       # Database migration environment and revision files
│   ├── versions/                   # Versioned schema changes
│   ├── env.py                      # Alembic configuration and model metadata
│   └── script.py.mako              # Template used to generate revisions
├── app/
│   ├── api/                        # HTTP routers: parse requests and call application services
│   ├── auth/                       # Authentication and current-user dependencies
│   ├── chat/                       # Chat application logic and orchestration
│   ├── assistant/                  # LLM agent setup, tools, instructions, and output handling
│   ├── database/
│   │   ├── models/                 # SQLAlchemy table models and database enums
│   │   ├── repositories/           # Database query and persistence functions
│   │   ├── base.py                 # Shared SQLAlchemy declarative base and mixins
│   │   └── session.py              # Engine, session factory, and session dependencies
│   ├── grounding/                  # Validation that generated answers are supported by sources
│   ├── retrieval/                  # Search, query construction, embeddings, and result ranking
│   ├── schemas/                    # Pydantic request/response and application data schemas
│   ├── utils/                      # Small cross-cutting utilities
│   ├── config.py                   # Centralized application settings
│   └── main.py                     # FastAPI app creation and router registration
├── ingest/                         # Data import, parsing, chunking, and embedding workflows
├── scripts/                        # Manual developer and operational scripts
├── tests/                          # Automated tests, organized by application area
├── alembic.ini                     # Alembic configuration
├── pyproject.toml                  # Project metadata, dependencies, and tool configuration
├── uv.lock                         # Locked dependency versions
└── Dockerfile                      # Container build instructions
```

## What goes where

- **`app/api/`**: FastAPI endpoints and HTTP-specific concerns. Keep business logic in application/service modules rather than in route handlers.
- **`app/schemas/`**: Pydantic types used to validate or serialize data at application boundaries. These are distinct from SQLAlchemy database models.
- **`app/database/models/`**: SQLAlchemy representations of database tables and their relationships.
- **`app/database/repositories/`**: Functions that read and write data. Keep SQL/query details here so callers do not need to know how persistence works.
- **`app/database/session.py`**: Database connection and session lifecycle. Repositories receive/use a session rather than creating independent connections.
- **`app/auth/`**: Authentication verification and reusable authorization dependencies.
- **Feature folders such as `app/chat/` and `app/assistant/`**: Application and domain logic grouped by responsibility.
- **`alembic/`**: Database schema history. Models describe the current schema; migrations record how the schema changes over time.
- **`ingest/`**: Batch or offline data workflows, separate from request/response handling.
- **`tests/`**: Tests grouped to mirror the application areas they cover.

## Typical request flow

```text
HTTP request
  -> app/api route
  -> feature service or application logic
  -> app/database/repositories
  -> app/database/session
  -> database
```

Routes should handle HTTP concerns, schemas should handle boundary data shapes, repositories should handle persistence queries, and database models should describe stored tables. Keep those responsibilities separate as the project grows.
