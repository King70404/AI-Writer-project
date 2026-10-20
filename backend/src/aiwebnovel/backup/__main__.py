"""Command-line author backups for the configured data root.

The data root comes from the same settings as the application
(``AIWEBNOVEL_DATA_ROOT`` or the formal LocalAppData default). Output is one JSON
document on stdout. Exit codes: 0 success, 1 operation refused or failed,
3 the verified backup is damaged or incompatible, 2 invalid arguments.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aiwebnovel.backup.archive import BackupArchiveError, DatabaseSummary
from aiwebnovel.backup.composition import compose_backup_service
from aiwebnovel.backup.service import AuthorBackupService, BackupServiceError
from aiwebnovel.core.config import get_settings
from aiwebnovel.storage.paths import StoragePaths


def _summary(summary: DatabaseSummary) -> dict[str, Any]:
    return {
        "schema_revision": summary.schema_revision,
        "requires_upgrade": summary.requires_upgrade,
        "counts": dict(summary.counts),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m aiwebnovel.backup")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="create a verified backup of the current data")
    commands.add_parser("list", help="list backups, newest first")
    verify = commands.add_parser("verify", help="fully verify one backup")
    verify.add_argument("backup_id")
    restore = commands.add_parser("restore", help="restore into a new, empty folder")
    restore.add_argument("backup_id")
    restore.add_argument("--target", required=True, help="absolute path of a new folder")
    return parser


def run(arguments: argparse.Namespace, service: AuthorBackupService) -> tuple[int, dict[str, Any]]:
    """Execute one parsed command and return its exit code and JSON document."""
    try:
        if arguments.command == "create":
            created = service.create()
            assert created.manifest is not None
            return 0, {
                "status": "created",
                "backup_id": created.backup_id,
                "file_bytes": created.file_bytes,
                "summary": _summary(created.manifest.summary),
            }
        if arguments.command == "list":
            return 0, {
                "status": "ok",
                "items": [
                    {
                        "backup_id": item.backup_id,
                        "file_bytes": item.file_bytes,
                        "readable": item.manifest is not None,
                        "created_at": None if item.manifest is None else item.manifest.created_at,
                    }
                    for item in service.list()
                ],
            }
        if arguments.command == "verify":
            result = service.verify(arguments.backup_id)
            document: dict[str, Any] = {
                "status": result.status,
                "backup_id": result.backup_id,
                "problem": result.problem,
            }
            if result.manifest is not None:
                document["summary"] = _summary(result.manifest.summary)
            return (0 if result.status == "valid" else 3), document
        restored = service.restore(arguments.backup_id, Path(arguments.target))
        return 0, {
            "status": "restored",
            "backup_id": restored.backup_id,
            "target": str(restored.target_root),
            "summary": _summary(restored.summary),
        }
    except BackupArchiveError as exc:
        return 3, {"status": "failed", "problem": exc.code}
    except BackupServiceError as exc:
        return 1, {"status": "failed", "problem": exc.code}


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        settings = get_settings()
        service = compose_backup_service(settings, StoragePaths.from_settings(settings))
    except Exception:  # noqa: BLE001 - configuration errors never print paths.
        code, document = 1, {"status": "failed", "problem": "CONFIGURATION_UNAVAILABLE"}
    else:
        code, document = run(arguments, service)
    sys.stdout.write(json.dumps(document, ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
