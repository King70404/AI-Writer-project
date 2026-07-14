"""Session commit, rollback, request isolation, and release tests."""

from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from aiwebnovel.core.config import Settings
from aiwebnovel.db.engine import create_database_engine
from aiwebnovel.db.session import (
    create_database_session_factory,
    database_session,
    get_database_session,
)
from aiwebnovel.main import create_app

pytestmark = pytest.mark.integration


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _settings(path: Path) -> Settings:
    return Settings(environment="test", database_url=_database_url(path))


def _remove_sqlite_artifacts(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def test_session_requires_explicit_commit_and_rolls_back_failures(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "session.sqlite3"
    engine = create_database_engine(_settings(database_path))
    session_factory = create_database_session_factory(engine)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE session_test (id INTEGER PRIMARY KEY, value TEXT)"
            )

        with database_session(session_factory) as session:
            session.execute(text("INSERT INTO session_test (id, value) VALUES (1, 'committed')"))
            session.commit()

        with database_session(session_factory) as session:
            session.execute(text("INSERT INTO session_test (id, value) VALUES (2, 'uncommitted')"))

        with (
            pytest.raises(RuntimeError, match="rollback marker"),
            database_session(session_factory) as session,
        ):
            session.execute(text("INSERT INTO session_test (id, value) VALUES (3, 'failed')"))
            raise RuntimeError("rollback marker")

        with database_session(session_factory) as session:
            rows = session.execute(text("SELECT id, value FROM session_test ORDER BY id")).all()

        assert rows == [(1, "committed")]
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
        _remove_sqlite_artifacts(database_path)


def test_fastapi_requests_receive_distinct_sessions(tmp_path: Path) -> None:
    database_path = tmp_path / "request-sessions.sqlite3"
    app = create_app(_settings(database_path))
    observed_sessions: list[Session] = []

    @app.get("/_test/session")
    def session_route(
        session: Annotated[Session, Depends(get_database_session)],
    ) -> dict[str, int]:
        observed_sessions.append(session)
        session.execute(text("SELECT 1"))
        return {"request": len(observed_sessions)}

    with TestClient(app) as client:
        assert client.get("/_test/session").status_code == 200
        assert client.get("/_test/session").status_code == 200
        engine = app.state.database_engine
        assert engine.pool.checkedout() == 0

    assert len(observed_sessions) == 2
    assert observed_sessions[0] is not observed_sessions[1]
    assert app.state.database_engine is None
    assert app.state.database_session_factory is None
    _remove_sqlite_artifacts(database_path)
