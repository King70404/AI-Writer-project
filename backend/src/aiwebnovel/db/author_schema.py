"""Recognized author database schema revisions shared by upgrade and backup checks."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from types import MappingProxyType

from aiwebnovel.db.model_registry import (
    AI_WORKFLOW_TABLE_NAMES,
    BUSINESS_TABLE_NAMES,
    STORY_MEMORY_TABLE_NAMES,
    WORKBENCH_TABLE_NAMES,
    WRITING_STUDIO_TABLE_NAMES,
    load_model_metadata,
)

LEGACY_MANUSCRIPT_REVISION = "0006_add_chapter_manuscript_content"
AI_WORKFLOW_REVISION = "0007_add_ai_workflows"
WRITING_STUDIO_REVISION = "0008_add_writing_studio"
STORY_MEMORY_REVISION = "0009_add_story_memory"
CURRENT_REVISION = "0010_add_chapter_editorial_states"

SUPPORTED_SCHEMA_TABLES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        LEGACY_MANUSCRIPT_REVISION: BUSINESS_TABLE_NAMES
        - AI_WORKFLOW_TABLE_NAMES
        - WRITING_STUDIO_TABLE_NAMES
        - STORY_MEMORY_TABLE_NAMES
        - WORKBENCH_TABLE_NAMES,
        AI_WORKFLOW_REVISION: BUSINESS_TABLE_NAMES
        - WRITING_STUDIO_TABLE_NAMES
        - STORY_MEMORY_TABLE_NAMES
        - WORKBENCH_TABLE_NAMES,
        WRITING_STUDIO_REVISION: BUSINESS_TABLE_NAMES
        - STORY_MEMORY_TABLE_NAMES
        - WORKBENCH_TABLE_NAMES,
        STORY_MEMORY_REVISION: BUSINESS_TABLE_NAMES - WORKBENCH_TABLE_NAMES,
        CURRENT_REVISION: BUSINESS_TABLE_NAMES,
    }
)
TABLE_QUERY = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"


class AuthorSchemaUnsupported(ValueError):
    """The database is not one recognized, complete author schema revision."""


def inspect_author_schema(connection: sqlite3.Connection) -> str:
    """Return the recognized revision after checking exact tables and columns.

    The check reads only SQLite metadata and the single ``alembic_version`` row, so
    it never exposes author content or local paths through its error messages.
    """
    tables = frozenset(str(row[0]) for row in connection.execute(TABLE_QUERY))
    if "alembic_version" not in tables:
        raise AuthorSchemaUnsupported("The database version is not recorded")
    versions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    if len(versions) != 1 or versions[0] not in SUPPORTED_SCHEMA_TABLES:
        raise AuthorSchemaUnsupported("The database version is not supported")
    revision = str(versions[0])
    expected_tables = SUPPORTED_SCHEMA_TABLES[revision]
    if tables != expected_tables | {"alembic_version"}:
        raise AuthorSchemaUnsupported("The database tables do not match its version")
    metadata = load_model_metadata()
    for table in sorted(expected_tables):
        columns = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if columns != set(metadata.tables[table].columns.keys()):
            raise AuthorSchemaUnsupported("The database columns do not match its version")
    return revision
