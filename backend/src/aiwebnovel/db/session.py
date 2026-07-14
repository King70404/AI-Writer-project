"""Database session factories and per-request lifecycle management."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create an independent session factory bound to one application engine."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def database_session(
    session_factory: sessionmaker[Session],
) -> Iterator[Session]:
    """Yield one session, rolling back failures and always releasing resources."""
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        try:
            if session.in_transaction():
                session.rollback()
        finally:
            session.close()


def get_database_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency that supplies one non-shared session per request."""
    session_factory = getattr(
        request.app.state, "database_session_factory", None
    )
    if session_factory is None:
        raise RuntimeError("Database session factory is not initialized")
    with database_session(session_factory) as session:
        yield session
