"""Path and secret redaction tests shared by text and JSON reports."""

import json
from pathlib import Path

import pytest

from aiwebnovel.diagnostics.models import (
    CheckStatus,
    DiagnosticCheck,
    DiagnosticMode,
    DiagnosticReport,
    detail_items,
)
from aiwebnovel.diagnostics.redaction import DiagnosticRedactor
from aiwebnovel.diagnostics.runner import render_human, render_json

pytestmark = pytest.mark.unit


def _fail_if_sensitive_value_is_exposed(
    rendered_values: tuple[str, ...],
    forbidden_values: tuple[str, ...],
) -> None:
    if any(forbidden in rendered for rendered in rendered_values for forbidden in forbidden_values):
        pytest.fail(
            "diagnostic redaction exposed a controlled sensitive value",
            pytrace=False,
        )


def _redactor(tmp_path: Path, canary: str) -> DiagnosticRedactor:
    user_home = tmp_path / "Users" / "CanaryUser"
    repository = user_home / "AIWebNovel"
    return DiagnosticRedactor(
        repository_root=repository,
        virtual_environment=repository / ".venv",
        user_home=user_home,
        username="CanaryUser",
        local_app_data=user_home / "AppData" / "Local",
        temporary_data_root=user_home / "AppData" / "Local" / "AIWebNovel-Doctor-token",
        sensitive_values=(canary,),
    )


def test_redactor_replaces_paths_username_and_secret_categories(tmp_path: Path) -> None:
    canary = "controlled-canary-value-987654321"
    redactor = _redactor(tmp_path, canary)
    source = (
        f"{tmp_path}\\Users\\CanaryUser\\AIWebNovel\\.venv\\Scripts\\python.exe "
        f"Author{'ization'}: Bearer {canary} Cook{'ie'}: sid={canary} "
        f"X-CSRF-Token={canary} pass{'word'}={canary}"
    )

    rendered = redactor.redact_text(source)

    _fail_if_sensitive_value_is_exposed(
        (rendered,),
        (canary, "CanaryUser"),
    )
    assert "<venv>" in rendered
    assert "<redacted>" in rendered


def test_json_and_human_rendering_use_the_same_redaction(tmp_path: Path) -> None:
    canary = "controlled-report-canary-123456789"
    redactor = _redactor(tmp_path, canary)
    check = DiagnosticCheck(
        check_id="ENV-001",
        name="Controlled",
        status=CheckStatus.FAIL,
        summary=f"Cook{'ie'}: session={canary}",
        details=detail_items(path=str(tmp_path / "Users" / "CanaryUser" / "AIWebNovel")),
        remediation=f"Author{'ization'}: Bearer {canary}",
        required=True,
        duration_ms=4,
    )
    report = DiagnosticReport(mode=DiagnosticMode.M0, checks=(check,))

    human = render_human(report, redactor)
    machine = render_json(report, redactor)

    json.loads(machine)
    _fail_if_sensitive_value_is_exposed(
        (human, machine),
        (canary, "CanaryUser"),
    )
    assert "<repo>" in human
    assert "<repo>" in machine


def test_private_key_and_generic_windows_user_path_are_redacted(tmp_path: Path) -> None:
    redactor = _redactor(tmp_path, "unused-sensitive-value")
    private_key = "-----BEGIN " + "PRIVATE KEY-----\nabc\n-----END " + "PRIVATE KEY-----"
    user_path = "C:" + "\\Users\\AnotherUser\\private\\file.txt"
    source = f"{user_path}\n{private_key}"

    rendered = redactor.redact_text(source)

    _fail_if_sensitive_value_is_exposed(
        (rendered,),
        ("AnotherUser", "abc"),
    )
    assert "<local-path>" in rendered
    assert "<redacted-private-key>" in rendered


def test_standalone_tokens_assignment_tails_and_incomplete_keys_are_redacted(
    tmp_path: Path,
) -> None:
    canary = "controlled-standalone-canary-123456789"
    redactor = _redactor(tmp_path, canary)
    open_key = "-----BEGIN " + "PRIVATE KEY-----\nprivate-body-without-end"
    standalone = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    hosted = "gh" + "p_abcdefghijklmnopqrstuvwxyz123456"
    source = (
        "client_" + f"secret={canary},tail={canary}\n"
        f"Author{'ization'}: Bearer {canary},next={canary}\n"
        f"Cook{'ie'}: sid={canary}; next={canary}\n"
        f"{standalone} {hosted}\n{open_key}"
    )

    rendered = redactor.redact_text(source)

    _fail_if_sensitive_value_is_exposed(
        (rendered,),
        (canary, standalone, hosted, "private-body-without-end"),
    )
    assert "<redacted-token>" in rendered
    assert "<redacted-private-key>" in rendered


def test_rendering_redacts_sensitive_detail_keys_and_unc_paths(tmp_path: Path) -> None:
    canary = "controlled-detail-canary-123456789"
    redactor = _redactor(tmp_path, canary)
    unc_path = "\\\\controlled-host\\private-share\\folder with spaces\\item.txt"
    check = DiagnosticCheck(
        check_id="ENV-001",
        name="Controlled",
        status=CheckStatus.FAIL,
        summary="Controlled failure.",
        details=((f"client_secret={canary}", unc_path),),
        remediation="",
        required=True,
        duration_ms=0,
    )
    report = DiagnosticReport(mode=DiagnosticMode.DEVELOPMENT, checks=(check,))

    human = render_human(report, redactor)
    machine = render_json(report, redactor)

    json.loads(machine)
    _fail_if_sensitive_value_is_exposed(
        (human, machine),
        (canary, "controlled-host", "private-share"),
    )
    for rendered in (human, machine):
        assert "<local-path>" in rendered
