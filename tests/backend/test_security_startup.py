"""Uvicorn entry-point tests for loopback-only and proxy-header policy."""

from pathlib import Path
from typing import Any

import pytest

import aiwebnovel.__main__ as entrypoint
from aiwebnovel.core.config import Settings

pytestmark = pytest.mark.unit


def test_non_loopback_environment_fails_before_settings_or_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("AIWEBNOVEL_HOST", "0.0.0.0")
    monkeypatch.setattr(
        entrypoint,
        "get_settings",
        lambda: calls.append("settings") or Settings(),
    )
    monkeypatch.setattr(
        entrypoint.uvicorn,
        "run",
        lambda *args, **kwargs: calls.append("uvicorn"),
    )

    with pytest.raises(SystemExit, match="explicit loopback"):
        entrypoint.main()

    assert calls == []


def test_uvicorn_explicitly_disables_proxy_and_server_headers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = Settings(environment="test", data_root=tmp_path / "startup-data")
    captured: dict[str, Any] = {}

    def capture_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setenv("AIWEBNOVEL_HOST", "127.0.0.1")
    monkeypatch.setattr(entrypoint, "get_settings", lambda: settings)
    monkeypatch.setattr(entrypoint.uvicorn, "run", capture_run)

    entrypoint.main()

    assert captured["app"] == "aiwebnovel.main:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["proxy_headers"] is False
    assert captured["forwarded_allow_ips"] == ""
    assert captured["server_header"] is False
    assert captured["access_log"] is False
    assert not (tmp_path / "startup-data").exists()
