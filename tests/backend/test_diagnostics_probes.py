"""Real isolated configuration, storage, database, and cleanup probe tests."""

import os
import shutil
from pathlib import Path

import pytest

from aiwebnovel.diagnostics.probes import (
    run_cleanup_probe,
    run_configuration_probe,
    run_storage_probe,
)

pytestmark = pytest.mark.integration


def _isolate_application_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.upper().startswith("AIWEBNOVEL_"):
            monkeypatch.delenv(key, raising=False)


def test_configuration_probe_uses_defaults_without_creating_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_application_environment(monkeypatch)
    local_app_data = tmp_path / "LocalAppData"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))

    result = run_configuration_probe()

    assert result == {
        "ok": True,
        "default_loopback": True,
        "proxy_headers_disabled": True,
        "trusted_hosts_safe": True,
        "cors_safe": True,
        "production_docs_closed": True,
        "request_limit_valid": True,
        "middleware_assembled": True,
    }
    assert list(local_app_data.iterdir()) == []


def test_storage_probe_uses_owned_root_and_removes_every_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_application_environment(monkeypatch)
    local_app_data = tmp_path / "LocalAppData"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))
    token = "a" * 32
    doctor_root = local_app_data / f"AIWebNovel-Doctor-{token}"
    formal_root = local_app_data / "AIWebNovel"

    result = run_storage_probe(token)

    assert result["ok"] is True
    assert result["storage"] is True
    assert result["database"] is True
    assert result["cleanup"] is True
    assert result["standard_directories"] == 12
    assert result["formal_content_accessed"] is False
    assert result["formal_root_exists"] is False
    assert result["formal_root_unchanged"] is True
    assert not doctor_root.exists()
    assert not formal_root.exists()


def test_existing_formal_root_is_not_enumerated_or_changed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_application_environment(monkeypatch)
    local_app_data = tmp_path / "LocalAppData"
    formal_root = local_app_data / "AIWebNovel"
    formal_root.mkdir(parents=True)
    marker = formal_root / "do-not-read-or-change.txt"
    marker.write_text("preserve", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))

    result = run_storage_probe("b" * 32)

    assert result["ok"] is True
    assert result["formal_root_exists"] is True
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_cleanup_failure_is_not_reported_as_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_application_environment(monkeypatch)
    local_app_data = tmp_path / "LocalAppData"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))
    token = "c" * 32
    doctor_root = local_app_data / f"AIWebNovel-Doctor-{token}"

    def fail_cleanup(root: Path, parent: Path, cleanup_token: str) -> None:
        del root, parent, cleanup_token
        raise OSError("controlled cleanup failure")

    result = run_storage_probe(token, cleanup_function=fail_cleanup)

    assert result["ok"] is False
    assert result["cleanup"] is False
    assert doctor_root.exists()

    cleanup = run_cleanup_probe(token)

    assert cleanup == {"ok": True, "cleanup": True, "root_exists": False}
    assert not doctor_root.exists()


def test_invalid_storage_probe_token_never_creates_a_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_application_environment(monkeypatch)
    local_app_data = tmp_path / "LocalAppData"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))

    result = run_storage_probe("not-a-safe-token")

    assert result["ok"] is False
    assert list(local_app_data.iterdir()) == []


def test_invalid_local_app_data_returns_a_safe_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_application_environment(monkeypatch)
    local_app_data = tmp_path / "not-a-directory"
    local_app_data.write_text("controlled", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))

    result = run_storage_probe("8" * 32)

    assert result["ok"] is False
    assert result["cleanup"] is False
    assert result["formal_root_unchanged"] is False


def test_preexisting_doctor_name_is_never_adopted_or_deleted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _isolate_application_environment(monkeypatch)
    local_app_data = tmp_path / "LocalAppData"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", os.fspath(local_app_data))
    token = "9" * 32
    preexisting = local_app_data / f"AIWebNovel-Doctor-{token}"
    preexisting.mkdir()
    marker = preexisting / "preserve.txt"
    marker.write_text("preserve", encoding="utf-8")

    result = run_storage_probe(token)

    assert result["ok"] is False
    assert result["cleanup"] is False
    assert marker.read_text(encoding="utf-8") == "preserve"

    cleanup = run_cleanup_probe(token)

    assert cleanup == {"ok": False, "cleanup": False, "root_exists": True}
    assert marker.read_text(encoding="utf-8") == "preserve"
    shutil.rmtree(preexisting)
