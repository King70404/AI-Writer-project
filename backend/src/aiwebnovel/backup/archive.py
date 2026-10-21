"""Author backup archive format: one SQLite snapshot plus a checksummed manifest.

An archive is a ZIP file with exactly two members, ``manifest.json`` and
``aiwebnovel.sqlite3``. The manifest records the database SHA-256, size, schema
revision and a per-table row count and content digest. Verification rejects any
other member, size mismatch, checksum mismatch, SQLite integrity failure,
unsupported schema revision or content digest mismatch. The checksums detect
corruption and inconsistent edits; they are not a cryptographic signature.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import zipfile
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from aiwebnovel.db.author_schema import (
    CURRENT_REVISION,
    SUPPORTED_SCHEMA_TABLES,
    AuthorSchemaUnsupported,
    inspect_author_schema,
)

FORMAT_NAME = "aiwebnovel-author-backup"
FORMAT_VERSION = 1
MANIFEST_MEMBER = "manifest.json"
DATABASE_MEMBER = "aiwebnovel.sqlite3"
ARCHIVE_PREFIX = "aiwebnovel-backup-"
ARCHIVE_SUFFIX = ".zip"
BACKUP_ID_PATTERN = re.compile(r"\A\d{8}T\d{6}Z-[0-9a-f]{12}\Z")
ARCHIVE_NAME_PATTERN = re.compile(r"\Aaiwebnovel-backup-(\d{8}T\d{6}Z-[0-9a-f]{12})\.zip\Z")
MAX_MANIFEST_BYTES = 1_048_576
DEFAULT_MAX_DATABASE_BYTES = 8 * 1024 * 1024 * 1024
_CHUNK_BYTES = 1_048_576
_SHA256_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")
_TIMESTAMP_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
COUNT_FIELDS = (
    "projects",
    "chapters",
    "chapter_revisions",
    "confirmed_facts",
    "workflow_runs",
)
_CONFIRMED_FACTS_QUERY = (
    "SELECT COUNT(*) FROM story_memory_revisions AS item "
    "WHERE json_extract(item.payload, '$.kind') = 'fact' "
    "AND json_extract(item.payload, '$.status') = 'confirmed' "
    "AND item.version = (SELECT MAX(latest.version) FROM story_memory_revisions AS latest "
    "WHERE latest.entity_id = item.entity_id)"
)


class BackupArchiveError(RuntimeError):
    """Base class; messages never contain paths or author content."""

    code = "BACKUP_INVALID"


class BackupCorrupt(BackupArchiveError):
    """The archive is damaged, tampered with, or not a backup archive."""

    code = "BACKUP_CORRUPT"


class BackupIncompatible(BackupArchiveError):
    """The archive is intact but its format or schema is not supported."""

    code = "BACKUP_INCOMPATIBLE"


def is_backup_id(value: str) -> bool:
    return BACKUP_ID_PATTERN.fullmatch(value) is not None


def archive_name(backup_id: str) -> str:
    if not is_backup_id(backup_id):
        raise ValueError("Invalid backup identifier")
    return f"{ARCHIVE_PREFIX}{backup_id}{ARCHIVE_SUFFIX}"


@dataclass(frozen=True, slots=True)
class TableDigest:
    rows: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DatabaseSummary:
    """Schema revision, author-facing counts and per-table digests of one snapshot."""

    schema_revision: str
    counts: Mapping[str, int]
    tables: Mapping[str, TableDigest]

    @property
    def requires_upgrade(self) -> bool:
        return self.schema_revision != CURRENT_REVISION


@dataclass(frozen=True, slots=True)
class BackupManifest:
    backup_id: str
    created_at: str
    app_version: str
    database_sha256: str
    database_bytes: int
    summary: DatabaseSummary

    def to_json(self) -> bytes:
        document = {
            "format": FORMAT_NAME,
            "format_version": FORMAT_VERSION,
            "backup_id": self.backup_id,
            "created_at": self.created_at,
            "app_version": self.app_version,
            "database": {
                "member": DATABASE_MEMBER,
                "sha256": self.database_sha256,
                "bytes": self.database_bytes,
            },
            "schema_revision": self.summary.schema_revision,
            "counts": dict(self.summary.counts),
            "tables": {
                name: {"rows": digest.rows, "sha256": digest.sha256}
                for name, digest in sorted(self.summary.tables.items())
            },
        }
        return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _cell(value: object) -> object:
    if isinstance(value, bytes):
        return {"blob": value.hex()}
    return value


def _table_digest(connection: sqlite3.Connection, table: str) -> TableDigest:
    digest = hashlib.sha256()
    rows = 0
    for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
        rows += 1
        encoded = json.dumps([_cell(value) for value in row], ensure_ascii=False)
        digest.update(encoded.encode("utf-8"))
        digest.update(b"\n")
    return TableDigest(rows, digest.hexdigest())


def summarize_database(connection: sqlite3.Connection) -> DatabaseSummary:
    """Inspect a recognized schema, then digest every author table in rowid order."""
    try:
        revision = inspect_author_schema(connection)
    except AuthorSchemaUnsupported as exc:
        raise BackupIncompatible(str(exc)) from None
    tables = {
        name: _table_digest(connection, name) for name in sorted(SUPPORTED_SCHEMA_TABLES[revision])
    }
    confirmed = 0
    if "story_memory_revisions" in tables:
        confirmed = int(connection.execute(_CONFIRMED_FACTS_QUERY).fetchone()[0])
    workflow = tables.get("ai_workflow_runs")
    counts = {
        "projects": tables["projects"].rows,
        "chapters": tables["chapters"].rows,
        "chapter_revisions": tables["chapter_revisions"].rows,
        "confirmed_facts": confirmed,
        "workflow_runs": 0 if workflow is None else workflow.rows,
    }
    return DatabaseSummary(revision, counts, tables)


def open_readonly(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    return sqlite3.connect(path.as_uri() + suffix, uri=True)


def check_sqlite_file(path: Path, *, immutable: bool) -> DatabaseSummary:
    """Run a full SQLite integrity check, then summarize the recognized schema."""
    try:
        with closing(open_readonly(path, immutable=immutable)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise BackupCorrupt("The backup database failed SQLite integrity verification")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise BackupCorrupt("The backup database has broken references")
            return summarize_database(connection)
    except sqlite3.DatabaseError:
        raise BackupCorrupt("The backup database cannot be read") from None


def file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _fsync_file(path: Path) -> None:
    # Windows _commit (used by os.fsync) requires a writable file descriptor.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def snapshot_database(
    source_file: Path,
    destination: Path,
    *,
    progress: Callable[[int, int, int], object] | None = None,
) -> None:
    """Copy one committed, consistent snapshot of a live WAL database.

    A single-step SQLite backup reads one transaction snapshot on a separate
    read-only connection, so concurrent writers are neither blocked nor mixed
    into the copy. The copy is switched to rollback-journal mode so its bytes stay
    stable for checksums.
    """
    with destination.open("xb"):
        pass
    with (
        closing(sqlite3.connect(source_file.as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(destination.as_uri() + "?mode=rw", uri=True)) as target,
    ):
        source.backup(target, pages=-1, progress=progress)
        target.execute("PRAGMA journal_mode=DELETE").fetchall()
    _fsync_file(destination)


def write_archive(destination: Path, manifest: BackupManifest, database_file: Path) -> None:
    """Write a new archive exclusively; the caller renames it into place."""
    with (
        destination.open("xb") as raw,
        zipfile.ZipFile(raw, mode="w", compression=zipfile.ZIP_DEFLATED) as archive,
    ):
        archive.writestr(MANIFEST_MEMBER, manifest.to_json())
        archive.write(database_file, DATABASE_MEMBER)
    _fsync_file(destination)


def _require(condition: bool, message: str = "The backup manifest is invalid") -> None:
    if not condition:
        raise BackupCorrupt(message)


def _strict_int(value: object) -> int:
    _require(type(value) is int and value >= 0)
    assert isinstance(value, int)
    return value


def _strict_text(value: object, pattern: re.Pattern[str] | None = None) -> str:
    _require(isinstance(value, str) and 0 < len(value) <= 200)
    assert isinstance(value, str)
    if pattern is not None:
        _require(pattern.fullmatch(value) is not None)
    return value


def _parse_manifest(raw: bytes, expected_backup_id: str) -> BackupManifest:
    try:
        document: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BackupCorrupt("The backup manifest is unreadable") from None
    _require(isinstance(document, dict))
    if document.get("format") != FORMAT_NAME:
        raise BackupCorrupt("The file is not an AIWebNovel backup")
    if document.get("format_version") != FORMAT_VERSION:
        raise BackupIncompatible("The backup format version is not supported")
    _require(
        set(document)
        == {
            "format",
            "format_version",
            "backup_id",
            "created_at",
            "app_version",
            "database",
            "schema_revision",
            "counts",
            "tables",
        }
    )
    backup_id = _strict_text(document["backup_id"], BACKUP_ID_PATTERN)
    _require(backup_id == expected_backup_id, "The backup manifest belongs to another backup")
    database = document["database"]
    _require(isinstance(database, dict) and set(database) == {"member", "sha256", "bytes"})
    _require(database["member"] == DATABASE_MEMBER)
    revision = _strict_text(document["schema_revision"])
    if revision not in SUPPORTED_SCHEMA_TABLES:
        raise BackupIncompatible("The backup schema version is not supported by this version")
    counts = document["counts"]
    _require(isinstance(counts, dict) and set(counts) == set(COUNT_FIELDS))
    tables = document["tables"]
    _require(isinstance(tables, dict) and set(tables) == SUPPORTED_SCHEMA_TABLES[revision])
    parsed_tables: dict[str, TableDigest] = {}
    for name, entry in tables.items():
        _require(isinstance(entry, dict) and set(entry) == {"rows", "sha256"})
        parsed_tables[name] = TableDigest(
            _strict_int(entry["rows"]), _strict_text(entry["sha256"], _SHA256_PATTERN)
        )
    return BackupManifest(
        backup_id=backup_id,
        created_at=_strict_text(document["created_at"], _TIMESTAMP_PATTERN),
        app_version=_strict_text(document["app_version"]),
        database_sha256=_strict_text(database["sha256"], _SHA256_PATTERN),
        database_bytes=_strict_int(database["bytes"]),
        summary=DatabaseSummary(
            revision,
            {name: _strict_int(counts[name]) for name in COUNT_FIELDS},
            parsed_tables,
        ),
    )


def _open_archive(path: Path) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path, mode="r")
    except (zipfile.BadZipFile, OSError, ValueError):
        raise BackupCorrupt("The backup file is not a readable archive") from None
    members = archive.infolist()
    names = [member.filename for member in members]
    if sorted(names) != sorted((MANIFEST_MEMBER, DATABASE_MEMBER)) or any(
        member.is_dir() or member.flag_bits & 0x1 for member in members
    ):
        archive.close()
        raise BackupCorrupt("The backup archive has unexpected contents")
    return archive


def read_manifest(path: Path, backup_id: str) -> BackupManifest:
    """Read and validate the manifest only; this is not an integrity verification."""
    with _open_archive(path) as archive:
        info = archive.getinfo(MANIFEST_MEMBER)
        _require(info.file_size <= MAX_MANIFEST_BYTES)
        try:
            raw = archive.read(MANIFEST_MEMBER)
        except (zipfile.BadZipFile, OSError, ValueError, EOFError):
            raise BackupCorrupt("The backup manifest is damaged") from None
        return _parse_manifest(raw, backup_id)


def _copy_member(stream: IO[bytes], destination: IO[bytes], limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(_CHUNK_BYTES):
        size += len(chunk)
        if size > limit:
            raise BackupCorrupt("The backup database is larger than its manifest states")
        digest.update(chunk)
        destination.write(chunk)
    return digest.hexdigest(), size


def extract_and_verify(
    path: Path,
    backup_id: str,
    destination: Path,
    *,
    max_database_bytes: int = DEFAULT_MAX_DATABASE_BYTES,
) -> BackupManifest:
    """Extract the database to an exclusive new file and verify everything.

    On success ``destination`` holds a byte-identical, integrity-checked database
    whose schema and per-table digests match the manifest. On failure the caller
    removes ``destination``.
    """
    manifest = read_manifest(path, backup_id)
    if manifest.database_bytes > max_database_bytes:
        raise BackupCorrupt("The backup database exceeds the supported size")
    with _open_archive(path) as archive:
        info = archive.getinfo(DATABASE_MEMBER)
        if info.file_size != manifest.database_bytes:
            raise BackupCorrupt("The backup database size does not match its manifest")
        try:
            with archive.open(info) as member, destination.open("xb") as output:
                sha256, size = _copy_member(member, output, manifest.database_bytes)
                output.flush()
                os.fsync(output.fileno())
        except (zipfile.BadZipFile, OSError, EOFError, ValueError) as exc:
            if isinstance(exc, FileExistsError):
                raise
            raise BackupCorrupt("The backup database is damaged") from None
    if size != manifest.database_bytes or sha256 != manifest.database_sha256:
        raise BackupCorrupt("The backup database checksum does not match its manifest")
    summary = check_sqlite_file(destination, immutable=True)
    if summary.schema_revision != manifest.summary.schema_revision:
        raise BackupCorrupt("The backup database schema does not match its manifest")
    if dict(summary.counts) != dict(manifest.summary.counts) or dict(summary.tables) != dict(
        manifest.summary.tables
    ):
        raise BackupCorrupt("The backup database content does not match its manifest")
    return manifest
