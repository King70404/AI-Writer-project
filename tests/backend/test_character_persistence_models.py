"""Character record shape and deterministic metadata registration tests."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from aiwebnovel.character.persistence.models import (
    CharacterHeadRecord,
    CharacterRecord,
    CharacterRevisionRecord,
)
from aiwebnovel.db.base import Base
from aiwebnovel.db.model_registry import (
    AI_WORKFLOW_TABLE_NAMES,
    BUSINESS_TABLE_NAMES,
    CHARACTER_TABLE_NAMES,
    NOVEL_STRUCTURE_TABLE_NAMES,
    load_model_metadata,
)


def test_registry_contains_exactly_authorized_business_tables() -> None:
    metadata = load_model_metadata()

    assert metadata is Base.metadata
    assert frozenset(metadata.tables) == BUSINESS_TABLE_NAMES
    assert (
        frozenset({"characters", "character_revisions", "character_heads"}) == CHARACTER_TABLE_NAMES
    )
    assert len(NOVEL_STRUCTURE_TABLE_NAMES) == 9
    assert set(metadata.tables) == {
        "projects",
        "project_revisions",
        "project_heads",
        "story_bibles",
        "story_bible_revisions",
        "story_bible_heads",
        "characters",
        "character_revisions",
        "character_heads",
        *NOVEL_STRUCTURE_TABLE_NAMES,
        *AI_WORKFLOW_TABLE_NAMES,
    }
    assert "alembic_version" not in metadata.tables


def test_records_have_only_authorized_columns_and_no_relationships() -> None:
    assert set(CharacterRecord.__table__.columns.keys()) == {
        "id",
        "project_id",
        "concurrency_version",
        "created_at",
        "updated_at",
    }
    assert set(CharacterRevisionRecord.__table__.columns.keys()) == {
        "id",
        "character_id",
        "revision_number",
        "name",
        "role",
        "profile",
        "created_at",
    }
    assert set(CharacterHeadRecord.__table__.columns.keys()) == {
        "character_id",
        "revision_id",
        "updated_at",
    }
    assert not inspect(CharacterRecord).relationships
    assert not inspect(CharacterRevisionRecord).relationships
    assert not inspect(CharacterHeadRecord).relationships
    assert all(
        column.default is None and column.server_default is None and column.onupdate is None
        for table_name in CHARACTER_TABLE_NAMES
        for column in Base.metadata.tables[table_name].columns
    )


def test_project_index_is_non_unique_and_project_is_not_unique() -> None:
    index = next(
        item
        for item in CharacterRecord.__table__.indexes
        if item.name == "ix_characters_project_id"
    )

    assert index.unique is False
    assert [column.name for column in index.columns] == ["project_id"]
    assert all(
        constraint.name != "uq_characters_project_id"
        for constraint in CharacterRecord.__table__.constraints
    )


def test_revision_repr_never_contains_user_text() -> None:
    record = CharacterRevisionRecord(
        name="CHARACTER_PERSISTENCE_SECRET_CANARY",
        role="private role",
        profile="private profile",
    )

    assert repr(record) == "<CharacterRevisionRecord>"
    assert "private" not in repr(record)
    assert "CANARY" not in repr(record)


def test_pure_import_registers_no_tables_and_orm_import_registers_only_three() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root / "backend" / "src")
    pure = subprocess.run(
        [
            sys.executable,
            "-c",
            "from aiwebnovel.db.base import Base; import aiwebnovel.character; "
            "print(','.join(sorted(Base.metadata.tables)))",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    orm = subprocess.run(
        [
            sys.executable,
            "-c",
            "from aiwebnovel.db.base import Base; "
            "import aiwebnovel.character.persistence.models; "
            "print(','.join(sorted(Base.metadata.tables)))",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert pure.returncode == 0, pure.stderr
    assert pure.stdout.strip() == ""
    assert orm.returncode == 0, orm.stderr
    assert orm.stdout.strip() == ("character_heads,character_revisions,characters")
