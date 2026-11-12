"""SQLAlchemy engine and session factory for direct Postgres access."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(settings.app_database_url)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def _create_session() -> Session:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _create_session()
    try:
        yield session
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session
