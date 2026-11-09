"""SQLAlchemy session factory used by the backend request layer.

The app keeps database access behind a small session factory so every route can
open a transaction, read or write rows, and close cleanly. This lets us keep the
same ORM models for chat threads, messages, and future retrieval work without
duplicating connection setup in each endpoint.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session() -> Session:
    """Return a database session for a single request lifecycle."""
    return SessionLocal()
