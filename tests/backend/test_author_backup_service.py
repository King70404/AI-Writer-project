"""Backup format, integrity verification, consistency, restore boundaries and CLI."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import zipfile
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.backend.author_backup_support import (
    CURRENT,
    author_rows,
    backup_service,
    build_template,
    owned_root,
)

import aiwebnovel.backup.__main__ as cli
import aiwebnovel.backup.archive as archive_module
import aiwebnovel.backup.service as service_module
from aiwebnovel.backup.archive import (
    DATABASE_MEMBER,
    MANIFEST_MEMBER,
    BackupCorrupt,
    archive_name,
    file_sha256,
    open_readonly,
    read_manifest,
    summarize_database,
)
from aiwebnovel.backup.composition import compose_backup_service
from aiwebnovel.backup.service import (
    AuthorBackupService,
    BackupBusy,
    BackupNotFound,
    BackupServiceError,
    BackupStorageChecks,
    BackupUnavailable,
    RestoreTargetInvalid,
    RestoreTargetNotEmpty,
    validate_target_name,
)
from aiwebnovel.core.config import Settings, get_settings
from aiwebnovel.storage.initializer import initialize_storage, validate_storage_layout
from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.integration
_PROJECT = "prj_01J0000000000000000000000{0}"


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_template(tmp_path_factory.mktemp("backup-service-template"), CURRENT)


def _insert_project(connection: sqlite3.Connection, suffix: str) -> None:
    connection.execute(
        "INSERT INTO projects VALUES (?, 1, '2026-01-01T00:00:00.000000Z', "
        "'2026-01-01T00:00:00.000000Z')",
        (_PROJECT.format(suffix),),
    )


def _archive(paths: StoragePaths, backup_id: str) -> Path:
    return paths.backups / archive_name(backup_id)


def _rewrite(
    path: Path,
    *,
    manifest: Callable[[dict[str, object]], object] | None = None,
    database: Callable[[bytes], bytes] | None = None,
    extra: dict[str, bytes] | None = None,
) -> None:
    with zipfile.ZipFile(path) as source:
        manifest_bytes = source.read(MANIFEST_MEMBER)
        database_bytes = source.read(DATABASE_MEMBER)
    if manifest is not None:
        document = json.loads(manifest_bytes)
        changed = manifest(document)
        manifest_bytes = (
            changed if isinstance(changed, bytes) else json.dumps(document).encode("utf-8")
        )
    if database is not None:
        database_bytes = database(database_bytes)
    path.unlink()
    with zipfile.ZipFile(path, "w") as target:
        target.writestr(MANIFEST_MEMBER, manifest_bytes)
        target.writestr(DATABASE_MEMBER, database_bytes)
        for name, content in (extra or {}).items():
            target.writestr(name, content)


def test_snapshot_is_consistent_while_another_writer_holds_uncommitted_work(
    tmp_path: Path, template: Path
) -> None:
    paths = owned_root(tmp_path, template)
    with closing(sqlite3.connect(paths.database_file)) as setup:
        setup.execute("PRAGMA journal_mode=WAL")
        _insert_project(setup, "1")
        setup.commit()
    service = backup_service(paths)
    with closing(sqlite3.connect(paths.database_file, isolation_level=None)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        _insert_project(writer, "2")
        first = service.create()
        writer.execute("COMMIT")
    second = service.create()
    assert first.manifest is not None and second.manifest is not None
    assert first.manifest.summary.counts["projects"] == 1
    assert second.manifest.summary.counts["projects"] == 2
    assert [item.backup_id for item in service.list()] == sorted(
        [first.backup_id, second.backup_id], reverse=True
    )
    for created in (first, second):
        assert service.verify(created.backup_id).status == "valid"
    assert not any(paths.runtime_temp.iterdir())
    assert sorted(path.name for path in paths.backups.iterdir()) == sorted(
        archive_name(item.backup_id) for item in (first, second)
    )


def _sha(document: dict[str, object], value: str) -> None:
    database = document["database"]
    assert isinstance(database, dict)
    database["sha256"] = value


def _counts(document: dict[str, object]) -> None:
    counts = document["counts"]
    assert isinstance(counts, dict)
    counts["chapters"] = 99


def _table_digest(document: dict[str, object]) -> None:
    tables = document["tables"]
    assert isinstance(tables, dict)
    tables["projects"]["sha256"] = "0" * 64


@pytest.mark.parametrize(
    ("change", "status"),
    [
        (lambda d: _sha(d, "f" * 64), "corrupt"),
        (_counts, "corrupt"),
        (_table_digest, "corrupt"),
        (lambda d: d.update(schema_revision="0010_future"), "incompatible"),
        (
            lambda d: d.update(schema_revision="0005_create_novel_structure_foundation"),
            "incompatible",
        ),
        (lambda d: d.update(format_version=2), "incompatible"),
        (lambda d: d.update(format="other"), "corrupt"),
        (lambda d: d.update(backup_id="20200101T000000Z-000000000000"), "corrupt"),
        (lambda d: d.update(extra=True), "corrupt"),
        (lambda d: d.update(created_at="yesterday"), "corrupt"),
        (lambda d: d["database"].update(member="../evil"), "corrupt"),
        (lambda d: d["database"].update(bytes=-1), "corrupt"),
        (lambda d: d["database"].update(bytes=True), "corrupt"),
        (lambda d: d["tables"].pop("projects"), "corrupt"),
        (lambda d: d["counts"].pop("chapters"), "corrupt"),
        (lambda d: d.update(tables=[]), "corrupt"),
        (lambda d: d["tables"].update(projects={"rows": 1}), "corrupt"),
        (lambda d: d.update(app_version=""), "corrupt"),
        (lambda _d: b"\xff\xfe not json", "corrupt"),
        (lambda _d: b"[]", "corrupt"),
    ],
)
def test_manifest_tampering_is_detected(
    tmp_path: Path,
    template: Path,
    change: Callable[[dict[str, object]], object],
    status: str,
) -> None:
    paths = owned_root(tmp_path, template)
    service = backup_service(paths)
    backup_id = service.create().backup_id
    _rewrite(_archive(paths, backup_id), manifest=change)
    result = service.verify(backup_id)
    assert result.status == status
    assert result.manifest is None
    with pytest.raises((BackupCorrupt, archive_module.BackupIncompatible)):
        service.restore(backup_id, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()
    assert not any(paths.runtime_temp.iterdir())


def _mutated_database(
    original: bytes, scratch: Path, mutate: Callable[[sqlite3.Connection], None]
) -> bytes:
    scratch.write_bytes(original)
    try:
        with closing(sqlite3.connect(scratch)) as connection:
            mutate(connection)
            connection.commit()
        return scratch.read_bytes()
    finally:
        scratch.unlink()


@pytest.mark.parametrize(
    ("mutate", "status"),
    [
        (lambda c: _insert_project(c, "9"), "corrupt"),
        (
            lambda c: c.execute("UPDATE alembic_version SET version_num='0010_future'"),
            "incompatible",
        ),
        (lambda c: c.execute("CREATE TABLE intruder (id INTEGER)"), "incompatible"),
        (lambda c: c.execute("DROP TABLE alembic_version"), "incompatible"),
    ],
)
def test_database_substitution_with_matching_checksum_is_detected(
    tmp_path: Path,
    template: Path,
    mutate: Callable[[sqlite3.Connection], None],
    status: str,
) -> None:
    paths = owned_root(tmp_path, template)
    service = backup_service(paths)
    backup_id = service.create().backup_id
    path = _archive(paths, backup_id)
    with zipfile.ZipFile(path) as source:
        replaced = _mutated_database(
            source.read(DATABASE_MEMBER), tmp_path / "scratch.sqlite3", mutate
        )
    scratch = tmp_path / "replaced.sqlite3"
    scratch.write_bytes(replaced)
    sha256, size = file_sha256(scratch)

    def update(document: dict[str, object]) -> None:
        document["database"] = {"member": DATABASE_MEMBER, "sha256": sha256, "bytes": size}

    _rewrite(path, manifest=update, database=lambda _old: replaced)
    assert service.verify(backup_id).status == status


@pytest.mark.parametrize(
    "damage",
    ["flip", "truncate", "extra", "not-zip", "directory-member", "garbage-sqlite"],
)
def test_damaged_archives_are_corrupt(tmp_path: Path, template: Path, damage: str) -> None:
    paths = owned_root(tmp_path, template)
    service = backup_service(paths)
    backup_id = service.create().backup_id
    path = _archive(paths, backup_id)
    if damage == "flip":
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0xFF
        path.write_bytes(bytes(data))
    elif damage == "truncate":
        path.write_bytes(path.read_bytes()[:-200])
    elif damage == "extra":
        _rewrite(path, extra={"../../escape.txt": b"x"})
    elif damage == "not-zip":
        path.write_bytes(b"PK not really")
    elif damage == "directory-member":
        _rewrite(path, extra={"folder/": b""})
    else:
        garbage = b"SQLite format 3\x00" + b"\x00" * 4096

        def update(document: dict[str, object]) -> None:
            document["database"] = {
                "member": DATABASE_MEMBER,
                "sha256": hashlib.sha256(garbage).hexdigest(),
                "bytes": len(garbage),
            }

        _rewrite(path, manifest=update, database=lambda _old: garbage)
    assert service.verify(backup_id).status == "corrupt"
    assert not any(paths.runtime_temp.iterdir())


def test_size_limits_and_member_size_mismatch_are_corrupt(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)
    backup_id = backup_service(paths).create().backup_id
    assert backup_service(paths, max_database_bytes=1024).verify(backup_id).status == "corrupt"
    path = _archive(paths, backup_id)
    _rewrite(path, manifest=lambda d: d["database"].update(bytes=10))
    assert backup_service(paths).verify(backup_id).status == "corrupt"


def test_copy_member_rejects_more_bytes_than_declared() -> None:
    with pytest.raises(BackupCorrupt):
        archive_module._copy_member(io.BytesIO(b"x" * 20), io.BytesIO(), 10)


def test_restore_verifies_copy_and_never_writes_current_root(
    tmp_path: Path, template: Path
) -> None:
    paths = owned_root(tmp_path, template)
    with closing(sqlite3.connect(paths.database_file)) as connection:
        _insert_project(connection, "1")
        connection.commit()
    service = backup_service(paths)
    backup_id = service.create().backup_id
    before = author_rows(paths.database_file)
    target = tmp_path / "nested" / "copy"
    with pytest.raises(RestoreTargetInvalid):
        service.restore(backup_id, target)
    (tmp_path / "nested").mkdir()
    result = service.restore(backup_id, target)
    assert result.target_root == target
    assert result.summary.counts["projects"] == 1
    assert author_rows(target / "data" / "aiwebnovel.sqlite3") == before
    assert author_rows(paths.database_file) == before
    validate_storage_layout(StoragePaths.from_root(target))


@pytest.mark.parametrize(
    "target",
    [
        "relative/copy",
        "",
        "/",
        "inside",
        "same",
        "parent",
        "dotdot-inside",
    ],
)
def test_restore_rejects_targets_overlapping_current_data(
    tmp_path: Path, template: Path, target: str
) -> None:
    paths = owned_root(tmp_path, template, name="root")
    service = backup_service(paths)
    backup_id = service.create().backup_id
    candidates = {
        "inside": paths.backups / "copy",
        "same": paths.root,
        "parent": tmp_path,
        "dotdot-inside": Path(f"{tmp_path}/other/../root/copy"),
    }
    with pytest.raises((RestoreTargetInvalid, RestoreTargetNotEmpty)):
        service.restore(backup_id, candidates.get(target, Path(target)))
    assert not (paths.backups / "copy").exists()
    assert not (paths.root / "copy").exists()


def _redirected_directory(link: Path, target: Path) -> None:
    """Create a directory link, falling back to a junction when Windows refuses symlinks.

    Unprivileged Windows accounts cannot create symbolic links (WinError 1314), but a
    directory junction is also a reparse point and exercises the same redirect checks.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError as exc:
        if sys.platform != "win32" or getattr(exc, "winerror", None) != 1314:
            raise
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Windows denied both symbolic-link and junction creation")


def test_restore_rejects_symlinked_targets_and_allowed_parent_escape(
    tmp_path: Path, template: Path
) -> None:
    paths = owned_root(tmp_path, template, name="root")
    service = backup_service(paths)
    backup_id = service.create().backup_id
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    _redirected_directory(link, real)
    assert link.is_symlink() or link.is_junction()
    with pytest.raises(RestoreTargetInvalid):
        service.restore(backup_id, link)
    with pytest.raises(RestoreTargetInvalid):
        service.restore(backup_id, link / "copy")
    with pytest.raises(RestoreTargetInvalid):
        service.restore(backup_id, real / "copy", allowed_parent=tmp_path)
    assert not any(real.iterdir())


@pytest.mark.parametrize("name", ["新书-备份", "copy_2", "a", "v1.2-final"])
def test_plain_target_names_are_accepted(name: str) -> None:
    assert validate_target_name(name) == name


@pytest.mark.parametrize(
    "name", ["", "-a", "a-", "a b", "a/b", "NUL", "com9.zip", "e\u0301", "x" * 65, "a\x00"]
)
def test_unsafe_target_names_are_rejected(name: str) -> None:
    with pytest.raises(RestoreTargetInvalid):
        validate_target_name(name)


@pytest.mark.parametrize("existing", [False, True])
def test_failed_restore_removes_only_what_it_created(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    paths = owned_root(tmp_path, template, name="root")
    service = backup_service(paths)
    backup_id = service.create().backup_id
    target = tmp_path / "copy"
    if existing:
        target.mkdir()
    original = archive_module.check_sqlite_file
    calls = {"count": 0}

    def fail_on_restored(path: Path, *, immutable: bool):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        if not immutable:
            raise BackupCorrupt("simulated damage after copying")
        return original(path, immutable=immutable)

    monkeypatch.setattr(service_module, "check_sqlite_file", fail_on_restored)
    with pytest.raises(BackupServiceError):
        service.restore(backup_id, target)
    assert target.exists() is existing
    if existing:
        assert not any(target.iterdir())
    assert not any(paths.runtime_temp.iterdir())


def test_restored_copy_mismatch_and_write_failures_are_reported(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = owned_root(tmp_path, template, name="root")
    service = backup_service(paths)
    backup_id = service.create().backup_id
    real_sha = service_module.file_sha256
    monkeypatch.setattr(service_module, "file_sha256", lambda _path: ("0" * 64, 0))
    with pytest.raises(BackupServiceError, match="did not match"):
        service.restore(backup_id, tmp_path / "copy-a")
    monkeypatch.setattr(service_module, "file_sha256", real_sha)
    real_check = service_module.check_sqlite_file

    def different_summary(path: Path, *, immutable: bool):  # type: ignore[no-untyped-def]
        summary = real_check(path, immutable=immutable)
        if immutable:
            return summary
        return archive_module.DatabaseSummary(summary.schema_revision, {}, summary.tables)

    monkeypatch.setattr(service_module, "check_sqlite_file", different_summary)
    with pytest.raises(BackupServiceError, match="did not match"):
        service.restore(backup_id, tmp_path / "copy-b")
    monkeypatch.setattr(service_module, "check_sqlite_file", real_check)

    def broken_initialize(_paths: StoragePaths) -> None:
        raise OSError("disk full")

    broken = AuthorBackupService(
        paths,
        BackupStorageChecks(validate_storage_layout, lambda _p: False, broken_initialize),
        app_version="test",
    )
    with pytest.raises(BackupServiceError, match="could not be written"):
        broken.restore(backup_id, tmp_path / "copy-c")
    for name in ("copy-a", "copy-b", "copy-c"):
        assert not (tmp_path / name).exists()


def test_uncreatable_target_and_unreadable_backup_are_reported(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = owned_root(tmp_path, template, name="root")
    service = backup_service(paths)
    backup_id = service.create().backup_id
    original_mkdir = Path.mkdir

    def refuse(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "copy":
            raise PermissionError("denied")
        original_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", refuse)
    with pytest.raises(RestoreTargetInvalid):
        service.restore(backup_id, tmp_path / "copy")
    monkeypatch.setattr(Path, "mkdir", original_mkdir)

    def unreadable(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(service_module, "extract_and_verify", unreadable)
    with pytest.raises(BackupServiceError, match="could not be read"):
        service.restore(backup_id, tmp_path / "copy")
    with pytest.raises(BackupServiceError, match="could not be verified"):
        service.verify(backup_id)


def test_create_failures_leave_no_partial_archive(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = owned_root(tmp_path, template)
    service = backup_service(
        paths, clock=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC), token=lambda: "a" * 12
    )
    first = service.create()
    assert first.backup_id == "20260102T030405Z-aaaaaaaaaaaa"
    assert first.manifest is not None and first.manifest.created_at == "2026-01-02T03:04:05Z"
    with pytest.raises(BackupServiceError, match="already in use"):
        service.create()

    def broken_extract(*_args: object, **_kwargs: object) -> None:
        raise BackupCorrupt("simulated")

    other = backup_service(paths)
    monkeypatch.setattr(service_module, "extract_and_verify", broken_extract)
    with pytest.raises(BackupServiceError, match="BACKUP_CORRUPT"):
        other.create()
    monkeypatch.undo()

    def disk_full(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(service_module, "write_archive", disk_full)
    with pytest.raises(BackupServiceError, match="could not be written"):
        other.create()
    assert [path.name for path in paths.backups.iterdir()] == [archive_name(first.backup_id)]
    assert not any(paths.runtime_temp.iterdir())


def test_busy_progress_and_lock_refuse_concurrent_work(tmp_path: Path, template: Path) -> None:
    with pytest.raises(BackupBusy):
        service_module._busy_progress(sqlite3.SQLITE_BUSY, 1, 2)
    service_module._busy_progress(sqlite3.SQLITE_OK, 0, 2)
    paths = owned_root(tmp_path, template)
    service = backup_service(paths)
    backup_id = service.create().backup_id
    assert service._lock.acquire(blocking=False)
    try:
        for operation in (
            service.create,
            lambda: service.verify(backup_id),
            lambda: service.restore(backup_id, tmp_path / "copy"),
        ):
            with pytest.raises(BackupBusy):
                operation()
    finally:
        service._lock.release()


def test_unsafe_source_layouts_are_unavailable(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)

    def unsafe_layout(_paths: StoragePaths) -> None:
        raise RuntimeError("layout")

    def failing_detector(_path: Path) -> bool:
        raise OSError("cannot inspect")

    for checks in (
        BackupStorageChecks(unsafe_layout, lambda _p: False, initialize_storage),
        BackupStorageChecks(validate_storage_layout, failing_detector, initialize_storage),
    ):
        service = AuthorBackupService(paths, checks, app_version="test")
        with pytest.raises(BackupUnavailable):
            service.create()
        with pytest.raises(BackupUnavailable):
            service.list()
    missing = owned_root(tmp_path, template, name="missing")
    missing.database_file.unlink()
    with pytest.raises(BackupUnavailable):
        backup_service(missing).create()


def test_list_skips_foreign_names_and_marks_unreadable(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)
    service = backup_service(paths)
    good = service.create().backup_id
    (paths.backups / "before-ai-workflow-legacy.sqlite3").write_bytes(b"legacy")
    (paths.backups / "aiwebnovel-backup-../x.zip.partial").parent.mkdir(exist_ok=True)
    unreadable_id = "29991231T235959Z-bbbbbbbbbbbb"
    _archive(paths, unreadable_id).write_bytes(b"broken")
    directory_id = "29991231T235959Z-cccccccccccc"
    _archive(paths, directory_id).mkdir()
    listed = service.list()
    assert [(item.backup_id, item.manifest is not None) for item in listed] == [
        (unreadable_id, False),
        (good, True),
    ]
    with pytest.raises(BackupNotFound):
        service.download_path("not-an-id")
    with pytest.raises(BackupNotFound):
        service.download_path(directory_id)
    with pytest.raises(BackupCorrupt):
        service.download_path(unreadable_id)
    assert service.download_path(good) == _archive(paths, good)
    with pytest.raises(ValueError):
        archive_name("../x")


def test_compose_rejects_unmanaged_database_url(tmp_path: Path) -> None:
    paths = StoragePaths.from_root(tmp_path / "root")
    managed = Settings(
        environment="test",
        data_root=paths.root,
        database_url=f"sqlite+pysqlite:///{paths.database_file.as_posix()}",
    )
    assert isinstance(compose_backup_service(managed, paths), AuthorBackupService)
    for url in (f"sqlite+pysqlite:///{(tmp_path / 'x.sqlite3').as_posix()}", "sqlite://"):
        settings = Settings(environment="test", data_root=paths.root, database_url=url)
        with pytest.raises(BackupUnavailable):
            compose_backup_service(settings, paths)


def test_summary_counts_latest_confirmed_fact_revision_only(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)
    with closing(sqlite3.connect(paths.database_file)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        rows = [
            ("r1", "fact-a", 1, "confirmed"),
            ("r2", "fact-a", 2, "rejected"),
            ("r3", "fact-b", 1, "pending"),
            ("r4", "fact-b", 2, "confirmed"),
        ]
        for revision, entity, version, status in rows:
            connection.execute(
                "INSERT INTO story_memory_revisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    revision,
                    entity,
                    version,
                    _PROJECT.format("1"),
                    "chp_01J00000000000000000000001",
                    json.dumps({"kind": "fact", "status": status}),
                ),
            )
        connection.commit()
        summary = summarize_database(connection)
    assert summary.counts["confirmed_facts"] == 1
    with closing(open_readonly(paths.database_file)) as connection:
        assert summarize_database(connection).tables["story_memory_revisions"].rows == 4


def test_unreadable_manifest_member_is_corrupt(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = owned_root(tmp_path, template)
    backup_id = backup_service(paths).create().backup_id

    def broken_read(*_args: object, **_kwargs: object) -> bytes:
        raise zipfile.BadZipFile("crc")

    monkeypatch.setattr(zipfile.ZipFile, "read", broken_read)
    with pytest.raises(BackupCorrupt):
        read_manifest(_archive(paths, backup_id), backup_id)


def test_cli_creates_lists_verifies_and_restores(
    tmp_path: Path,
    template: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = owned_root(tmp_path, template)
    monkeypatch.setenv("AIWEBNOVEL_DATA_ROOT", str(paths.root))
    monkeypatch.delenv("AIWEBNOVEL_DATABASE_URL", raising=False)

    def invoke(*arguments: str) -> tuple[int, dict[str, object]]:
        get_settings.cache_clear()
        code = cli.main(list(arguments))
        return code, json.loads(capsys.readouterr().out)

    code, created = invoke("create")
    assert code == 0 and created["status"] == "created"
    backup_id = str(created["backup_id"])
    code, listed = invoke("list")
    assert code == 0 and [item["backup_id"] for item in listed["items"]] == [backup_id]  # type: ignore[index, union-attr]
    code, verified = invoke("verify", backup_id)
    assert code == 0 and verified["status"] == "valid" and "summary" in verified
    target = tmp_path / "cli-copy"
    code, restored = invoke("restore", backup_id, "--target", str(target))
    assert code == 0 and restored["target"] == str(target)
    code, refused = invoke("restore", backup_id, "--target", str(target))
    assert (code, refused) == (1, {"status": "failed", "problem": "RESTORE_TARGET_NOT_EMPTY"})
    code, missing = invoke("verify", "20000101T000000Z-000000000000")
    assert (code, missing["problem"]) == (1, "BACKUP_NOT_FOUND")
    _rewrite(_archive(paths, backup_id), manifest=lambda d: d.update(format_version=9))
    code, damaged = invoke("verify", backup_id)
    assert (code, damaged["status"]) == (3, "incompatible")
    code, refused = invoke("restore", backup_id, "--target", str(tmp_path / "other"))
    assert (code, refused["problem"]) == (3, "BACKUP_INCOMPATIBLE")
    monkeypatch.setenv("AIWEBNOVEL_DATA_ROOT", "relative")
    code, configuration = invoke("list")
    assert (code, configuration["problem"]) == (1, "CONFIGURATION_UNAVAILABLE")
    with pytest.raises(SystemExit):
        cli.main(["restore", backup_id])


def test_schema_drift_broken_references_and_blob_digests(tmp_path: Path, template: Path) -> None:
    assert archive_module._cell(b"\x00\xff") == {"blob": "00ff"}
    assert archive_module._cell("文") == "文"
    paths = owned_root(tmp_path, template)
    service = backup_service(paths)
    backup_id = service.create().backup_id
    path = _archive(paths, backup_id)
    with zipfile.ZipFile(path) as source:
        original = source.read(DATABASE_MEMBER)

    def drift(connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE projects ADD COLUMN extra TEXT")

    def dangling(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO project_heads VALUES (?, 'prr_missing', '2026-01-01')",
            (_PROJECT.format("7"),),
        )

    for mutate, status in ((drift, "incompatible"), (dangling, "corrupt")):
        replaced = _mutated_database(original, tmp_path / "scratch.sqlite3", mutate)

        def update(document: dict[str, object], data: bytes = replaced) -> None:
            document["database"] = {
                "member": DATABASE_MEMBER,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }

        _rewrite(path, manifest=update, database=lambda _old, data=replaced: data)
        assert service.verify(backup_id).status == status


def test_manifest_schema_revision_must_match_database(tmp_path: Path, template: Path) -> None:
    from aiwebnovel.db.author_schema import SUPPORTED_SCHEMA_TABLES, WRITING_STUDIO_REVISION

    paths = owned_root(tmp_path, template)
    service = backup_service(paths)
    backup_id = service.create().backup_id

    def downgrade(document: dict[str, object]) -> None:
        document["schema_revision"] = WRITING_STUDIO_REVISION
        tables = document["tables"]
        assert isinstance(tables, dict)
        for name in set(tables) - SUPPORTED_SCHEMA_TABLES[WRITING_STUDIO_REVISION]:
            del tables[name]

    _rewrite(_archive(paths, backup_id), manifest=downgrade)
    assert service.verify(backup_id).status == "corrupt"


def test_extract_refuses_to_overwrite_existing_destination(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)
    backup_id = backup_service(paths).create().backup_id
    occupied = tmp_path / "occupied.sqlite3"
    occupied.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        archive_module.extract_and_verify(_archive(paths, backup_id), backup_id, occupied)
    assert occupied.read_bytes() == b"keep"


def test_integrity_check_failure_is_corrupt(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(self, sql: str) -> object:
            if sql == "PRAGMA integrity_check":
                return self._connection.execute("SELECT 'row 1 missing from index'")
            return self._connection.execute(sql)

        def close(self) -> None:
            self._connection.close()

    original = archive_module.open_readonly
    monkeypatch.setattr(
        archive_module,
        "open_readonly",
        lambda path, *, immutable=False: FailingConnection(original(path, immutable=immutable)),
    )
    with pytest.raises(BackupCorrupt, match="integrity"):
        archive_module.check_sqlite_file(template, immutable=True)
