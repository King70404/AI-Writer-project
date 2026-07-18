"""Alembic online and offline migration baseline tests."""

import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy.engine import URL

pytestmark = pytest.mark.integration


_BASELINE_REVISION = "0001_initialize_database"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG = _REPOSITORY_ROOT / "backend" / "alembic.ini"


def _database_url(path: Path) -> str:
    return str(URL.create("sqlite+pysqlite", database=path.as_posix()))


def _storage_root(database_path: Path) -> Path:
    return database_path.parents[1] / f"{database_path.stem}-storage"


def _run_alembic(database_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["AIWEBNOVEL_DATA_ROOT"] = str(_storage_root(database_path))
    environment["AIWEBNOVEL_DATABASE_URL"] = _database_url(database_path)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(_ALEMBIC_CONFIG),
            *arguments,
        ],
        cwd=_REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _database_state(path: Path) -> tuple[list[str], list[str]]:
    with closing(sqlite3.connect(path)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        versions = (
            [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
            if "alembic_version" in tables
            else []
        )
    return tables, versions


def _remove_sqlite_artifacts(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def test_migration_upgrade_downgrade_and_reupgrade_are_repeatable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "migration cycle" / "migration.sqlite3"
    try:
        upgrade = _run_alembic(database_path, "upgrade", _BASELINE_REVISION)
        assert upgrade.returncode == 0, upgrade.stderr
        current = _run_alembic(database_path, "current")
        assert current.returncode == 0, current.stderr
        assert _BASELINE_REVISION in current.stdout
        assert _database_state(database_path) == (["alembic_version"], [_BASELINE_REVISION])

        downgrade = _run_alembic(database_path, "downgrade", "base")
        assert downgrade.returncode == 0, downgrade.stderr
        base_current = _run_alembic(database_path, "current")
        assert base_current.returncode == 0, base_current.stderr
        assert _BASELINE_REVISION not in base_current.stdout
        assert _database_state(database_path) == (["alembic_version"], [])

        reupgrade = _run_alembic(database_path, "upgrade", _BASELINE_REVISION)
        assert reupgrade.returncode == 0, reupgrade.stderr
        assert _database_state(database_path) == (["alembic_version"], [_BASELINE_REVISION])

        combined_output = "\n".join(
            result.stdout + result.stderr
            for result in (upgrade, current, downgrade, base_current, reupgrade)
        )
        assert str(database_path) not in combined_output
    finally:
        _remove_sqlite_artifacts(database_path)
        storage_root = _storage_root(database_path)
        if storage_root.exists():
            assert storage_root.is_relative_to(tmp_path)
            shutil.rmtree(storage_root)
            assert not storage_root.exists()


def test_offline_migration_generates_sql_without_creating_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "offline migration" / "offline.sqlite3"
    data_root = _storage_root(database_path)

    result = _run_alembic(database_path, "upgrade", _BASELINE_REVISION, "--sql")

    assert result.returncode == 0, result.stderr
    assert "alembic_version" in result.stdout
    assert _BASELINE_REVISION in result.stdout
    assert "project" not in result.stdout.lower()
    assert "character" not in result.stdout.lower()
    assert "chapter" not in result.stdout.lower()
    assert not database_path.parent.exists()
    assert not database_path.exists()
    assert not data_root.exists()
