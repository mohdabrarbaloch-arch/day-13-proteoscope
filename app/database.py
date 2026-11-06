"""Database engine, session factory, and declarative base.

SQLite for development, PostgreSQL for production — the ORM layer is identical.
On serverless platforms the filesystem is read-only except /tmp, so a SQLite URL
is transparently redirected there.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


def _resolve_url() -> str:
    url = settings.database_url
    # Serverless filesystems are read-only outside /tmp.
    if settings.is_serverless and url.startswith("sqlite") and "/tmp/" not in url:
        url = "sqlite:////tmp/proteoscope.db"
    return url


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
        # An in-memory database lives inside a single connection. Without a
        # StaticPool every new connection gets its own empty database, so the
        # tables created at startup are invisible to the request that follows —
        # which is exactly the failure the API tests hit.
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return kwargs
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


DATABASE_URL = _resolve_url()

engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Safe to call repeatedly."""
    from app import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)