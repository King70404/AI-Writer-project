"""Dependency-backed diagnostic probes that run only inside the project venv."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from aiwebnovel.core.config import (
    Settings,
    resolve_default_data_root,
    resolve_local_app_data_root,
)
from aiwebnovel.db import run_database_diagnostic
from aiwebnovel.security import (
    diagnose_security_configuration,
)
from aiwebnovel.storage import (
    StoragePaths,
    check_storage_health,
    initialize_storage,
    is_reparse_point,
)

_DOCTOR_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_OWNERSHIP_MARKER = ".aiwebnovel-doctor-owner"


def run_configuration_probe() -> dict[str, object]:
    """Construct safe defaults without accessing local-session storage."""
    local_app_data = resolve_local_app_data_root()
    placeholder_root = local_app_data / "AIWebNovel-Doctor-Configuration"
    settings = Settings(data_root=placeholder_root)
    production = Settings(environment="production", data_root=placeholder_root)
    snapshot = diagnose_security_configuration(settings, production)
    result = {
        "default_loopback": snapshot.default_loopback,
        "proxy_headers_disabled": snapshot.proxy_headers_disabled,
        "trusted_hosts_safe": snapshot.trusted_hosts_safe,
        "cors_safe": snapshot.cors_safe,
        "production_docs_closed": snapshot.production_docs_closed,
        "request_limit_valid": snapshot.request_limit_valid,
        "middleware_assembled": snapshot.middleware_assembled,
    }
    return {"ok": snapshot.ready, **result}


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def _path_entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _assert_owned_doctor_root(root: Path, local_app_data: Path, token: str) -> None:
    expected_leaf = f"AIWebNovel-Doctor-{token}"
    if not _DOCTOR_TOKEN.fullmatch(token):
        raise ValueError("diagnostic root identity is invalid")
    if not _same_path(root.parent, local_app_data) or root.name != expected_leaf:
        raise ValueError("diagnostic root is not an owned LocalAppData child")


def _assert_tree_has_no_reparse_points(root: Path) -> None:
    if not root.exists():
        return
    pending = [root]
    while pending:
        current = pending.pop()
        if is_reparse_point(current):
            raise RuntimeError("diagnostic root contains a reparse point")
        if not current.is_dir():
            continue
        with os.scandir(current) as entries:
            for entry in entries:
                child = Path(entry.path)
                if is_reparse_point(child):
                    raise RuntimeError("diagnostic root contains a reparse point")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(child)


def _cleanup_owned_root(root: Path, local_app_data: Path, token: str) -> None:
    _assert_owned_doctor_root(root, local_app_data, token)
    _assert_tree_has_no_reparse_points(root)
    if root.exists():
        shutil.rmtree(root)
    if root.exists():
        raise RuntimeError("diagnostic root cleanup failed")


CleanupFunction = Callable[[Path, Path, str], None]


def _write_ownership_marker(root: Path, token: str) -> None:
    marker = root / _OWNERSHIP_MARKER
    marker.write_text(f"{token}\n", encoding="utf-8", newline="\n")


def _has_valid_ownership_marker(root: Path, token: str) -> bool:
    marker = root / _OWNERSHIP_MARKER
    if not marker.is_file() or is_reparse_point(marker):
        return False
    try:
        if marker.stat().st_size > 64:
            return False
        return marker.read_text(encoding="utf-8") == f"{token}\n"
    except (OSError, UnicodeError):
        return False


def run_storage_probe(
    token: str,
    *,
    cleanup_function: CleanupFunction = _cleanup_owned_root,
) -> dict[str, object]:
    """Probe storage and SQLite in one owned LocalAppData child, then remove it."""
    result: dict[str, object] = {
        "ok": False,
        "formal_root_exists": False,
        "formal_root_unchanged": False,
        "formal_content_accessed": False,
        "standard_directories": 0,
        "storage": False,
        "database": False,
        "cleanup": False,
    }
    if _DOCTOR_TOKEN.fullmatch(token) is None:
        return result

    local_app_data: Path | None = None
    doctor_root: Path | None = None
    formal_root: Path | None = None
    owns_doctor_root = False
    formal_exists_before = False
    probe_succeeded = False
    try:
        local_app_data = resolve_local_app_data_root()
        if not local_app_data.is_dir() or is_reparse_point(local_app_data):
            return result
        formal_root = resolve_default_data_root()
        formal_exists_before = formal_root.exists()
        result["formal_root_exists"] = formal_exists_before

        doctor_root = local_app_data / f"AIWebNovel-Doctor-{token}"
        _assert_owned_doctor_root(doctor_root, local_app_data, token)
        if doctor_root.exists():
            return result
        doctor_root.mkdir(exist_ok=False)
        owns_doctor_root = True
        _write_ownership_marker(doctor_root, token)

        paths = StoragePaths.from_root(doctor_root)
        initialization = initialize_storage(paths)
        result["standard_directories"] = initialization.total_directories
        check_storage_health(paths)
        result["storage"] = True

        settings = Settings(
            data_root=doctor_root,
            database_url=None,
            environment="diagnostic",
        )
        run_database_diagnostic(settings, paths)
        result["database"] = True
        probe_succeeded = True
    except Exception:  # noqa: BLE001 - the caller receives path-free booleans only.
        probe_succeeded = False
    finally:
        if local_app_data is not None and doctor_root is not None and owns_doctor_root:
            try:
                cleanup_function(doctor_root, local_app_data, token)
            except Exception:  # noqa: BLE001 - cleanup state is represented safely.
                result["cleanup"] = False
            else:
                result["cleanup"] = True
            if formal_root is not None:
                formal_exists_after = formal_root.exists()
                result["formal_root_unchanged"] = formal_exists_after == formal_exists_before
        elif local_app_data is not None and formal_root is not None:
            formal_exists_after = formal_root.exists()
            result["formal_root_unchanged"] = formal_exists_after == formal_exists_before

    result["ok"] = bool(
        probe_succeeded
        and result["storage"]
        and result["database"]
        and result["cleanup"]
        and result["formal_root_unchanged"]
        and result["standard_directories"] == 12
    )
    return result


def run_cleanup_probe(token: str) -> dict[str, object]:
    """Remove only residue bearing this invocation's validated ownership marker."""
    result: dict[str, object] = {
        "ok": False,
        "cleanup": False,
        "root_exists": False,
    }
    if _DOCTOR_TOKEN.fullmatch(token) is None:
        return result

    try:
        local_app_data = resolve_local_app_data_root()
        if not local_app_data.is_dir() or is_reparse_point(local_app_data):
            return result
        doctor_root = local_app_data / f"AIWebNovel-Doctor-{token}"
        _assert_owned_doctor_root(doctor_root, local_app_data, token)
        if not _path_entry_exists(doctor_root):
            result.update(ok=True, cleanup=True, root_exists=False)
            return result
        result["root_exists"] = True
        _assert_tree_has_no_reparse_points(doctor_root)
        if not _has_valid_ownership_marker(doctor_root, token):
            return result
        _cleanup_owned_root(doctor_root, local_app_data, token)
        result.update(ok=True, cleanup=True, root_exists=False)
    except Exception:  # noqa: BLE001 - cleanup state is represented safely.
        return result
    return result


def _safe_failure(error: BaseException) -> dict[str, object]:
    return {"ok": False, "error_type": type(error).__name__}


def main(argv: list[str] | None = None) -> int:
    """Run exactly one internal probe and emit only safe JSON."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("probe", choices=("configuration", "storage", "cleanup"))
    parser.add_argument("--token", default="")
    try:
        arguments = parser.parse_args(argv)
        if arguments.probe == "configuration":
            payload = run_configuration_probe()
        elif arguments.probe == "storage":
            payload = run_storage_probe(str(arguments.token))
        else:
            payload = run_cleanup_probe(str(arguments.token))
    except BaseException as exc:  # noqa: BLE001 - internal probe must not print a stack.
        payload = _safe_failure(exc)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
