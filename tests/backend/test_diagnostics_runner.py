"""Runner isolation, rendering, invocation, and output-file tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from aiwebnovel.diagnostics.checks import (
    CheckDefinition,
    CommandResult,
    DiagnosticContext,
    DiagnosticDependencies,
)
from aiwebnovel.diagnostics.models import (
    CheckResult,
    CheckStatus,
    DiagnosticCheck,
    DiagnosticExitCode,
    DiagnosticMode,
    DiagnosticReport,
    detail_items,
)
from aiwebnovel.diagnostics.redaction import DiagnosticRedactor
from aiwebnovel.diagnostics.runner import _build_redactor, main, render_json, run_diagnostics

pytestmark = pytest.mark.unit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class UnusedRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float = 15,
    ) -> CommandResult:
        del argv, cwd, env, timeout_seconds
        raise AssertionError("controlled runner must not execute a command")


def _dependencies() -> DiagnosticDependencies:
    return DiagnosticDependencies(
        command_runner=UnusedRunner(),
        platform_name=lambda: "Windows",
        platform_summary=lambda: "controlled",
        port_probe=lambda _port: True,
        token_factory=lambda: "f" * 32,
        environment={},
    )


def _pass(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    del context, dependencies, previous
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Controlled pass.",
        details=detail_items(value=True),
    )


def _raise_with_secret(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    del context, dependencies, previous
    raise RuntimeError("Authorization: Bearer controlled-secret-that-must-not-leak")


def test_runner_converts_one_exception_and_continues_in_order(tmp_path: Path) -> None:
    ticks = iter((0, 2_000_000, 3_000_000, 7_000_000))
    report = run_diagnostics(
        DiagnosticContext(tmp_path, DiagnosticMode.DEVELOPMENT),
        _dependencies(),
        checks=(
            CheckDefinition("ENV-001", "Failure", _raise_with_secret),
            CheckDefinition("ENV-002", "Pass", _pass),
        ),
        clock_ns=lambda: next(ticks),
    )

    assert [check.check_id for check in report.checks] == ["ENV-001", "ENV-002"]
    assert report.checks[0].status is CheckStatus.FAIL
    assert report.checks[0].details == (("error_type", "RuntimeError"),)
    assert report.checks[0].duration_ms == 2
    assert report.checks[1].status is CheckStatus.PASS
    assert report.checks[1].duration_ms == 4
    assert "controlled-secret" not in str(report.to_dict())


def test_json_report_is_parseable_and_has_stable_check_order(tmp_path: Path) -> None:
    report = run_diagnostics(
        DiagnosticContext(tmp_path, DiagnosticMode.DEVELOPMENT),
        _dependencies(),
        checks=(
            CheckDefinition("ENV-001", "First", _pass),
            CheckDefinition("ENV-002", "Second", _pass),
        ),
        clock_ns=lambda: 0,
    )
    redactor = DiagnosticRedactor(
        repository_root=tmp_path,
        virtual_environment=tmp_path / ".venv",
    )

    payload = json.loads(render_json(report, redactor))

    assert payload["schema_version"] == "1"
    assert payload["overall_status"] == "ready"
    assert [item["check_id"] for item in payload["checks"]] == ["ENV-001", "ENV-002"]


def test_runtime_redactor_uses_the_public_local_app_data_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    redactor = _build_redactor(tmp_path / "repository")
    rendered = redactor.redact_text(local_app_data / "AIWebNovel")

    assert rendered == "<localappdata>\\AIWebNovel"


def _ready_report() -> DiagnosticReport:
    return DiagnosticReport(
        mode=DiagnosticMode.DEVELOPMENT,
        checks=(
            DiagnosticCheck(
                "ENV-001",
                "Controlled",
                CheckStatus.PASS,
                "Controlled pass.",
                (),
                "",
                True,
                0,
            ),
        ),
    )


def test_main_returns_three_for_invalid_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(("--mode", "invalid", "--json"))

    assert exit_code == DiagnosticExitCode.INVOCATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "invocation_error"


@pytest.mark.parametrize(
    "arguments",
    (
        ("-Json", "-UnknownOption"),
        ("-OutputFile", "-Json"),
        ("-Json", "-Mode"),
    ),
)
def test_powershell_wrapper_safely_reports_invocation_errors(
    arguments: tuple[str, ...],
) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    script = _REPOSITORY_ROOT / "scripts" / "environment_doctor.ps1"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            os.fspath(script),
            *arguments,
        ],
        cwd=_REPOSITORY_ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )

    assert result.returncode == DiagnosticExitCode.INVOCATION_ERROR
    assert json.loads(result.stdout)["error"] == "invocation_error"
    assert not result.stderr
    assert os.fspath(_REPOSITORY_ROOT).casefold() not in (result.stdout + result.stderr).casefold()


def test_main_writes_utf8_json_only_to_an_existing_explicit_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    output_parent = tmp_path / "reports"
    repository.mkdir()
    output_parent.mkdir()
    output_file = output_parent / "doctor.json"
    monkeypatch.chdir(repository)
    monkeypatch.setattr("aiwebnovel.diagnostics.runner._repository_root", lambda: repository)
    monkeypatch.setattr(
        "aiwebnovel.diagnostics.runner.run_diagnostics",
        lambda context, dependencies: _ready_report(),
    )

    exit_code = main(("--json", "--output-file", str(output_file)))

    assert exit_code == DiagnosticExitCode.READY
    disk_payload = json.loads(output_file.read_text(encoding="utf-8"))
    stdout_payload = json.loads(capsys.readouterr().out)
    assert disk_payload == stdout_payload


def test_main_refuses_missing_output_parent_and_repository_code_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.chdir(repository)
    monkeypatch.setattr("aiwebnovel.diagnostics.runner._repository_root", lambda: repository)

    missing_parent = main(("--output-file", str(tmp_path / "missing" / "doctor.json")))
    code_target = main(("--output-file", str(repository / "README.md")))

    assert missing_parent == DiagnosticExitCode.INVOCATION_ERROR
    assert code_target == DiagnosticExitCode.INVOCATION_ERROR


def test_output_inside_existing_runtime_directory_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    runtime = repository / ".runtime"
    runtime.mkdir(parents=True)
    monkeypatch.chdir(repository)
    monkeypatch.setattr("aiwebnovel.diagnostics.runner._repository_root", lambda: repository)
    monkeypatch.setattr(
        "aiwebnovel.diagnostics.runner.run_diagnostics",
        lambda context, dependencies: _ready_report(),
    )

    exit_code = main(("--json", "--output-file", str(runtime / "doctor.json")))

    assert exit_code == DiagnosticExitCode.READY
    assert (runtime / "doctor.json").is_file()


def test_powershell_bootstrap_failure_emits_one_parseable_report(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    repository = tmp_path / "bootstrap-repository"
    scripts = repository / "scripts"
    output_parent = tmp_path / "reports"
    empty_path = tmp_path / "empty-path"
    scripts.mkdir(parents=True)
    output_parent.mkdir()
    empty_path.mkdir()
    shutil.copy2(
        _REPOSITORY_ROOT / "scripts" / "environment_doctor.ps1",
        scripts / "environment_doctor.ps1",
    )
    output_file = output_parent / "bootstrap.json"
    environment = os.environ.copy()
    environment["PATH"] = os.fspath(empty_path)

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            os.fspath(scripts / "environment_doctor.ps1"),
            "-Mode",
            "Development",
            "-Json",
            "-OutputFile",
            os.fspath(output_file),
        ],
        cwd=repository,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )

    assert result.returncode == DiagnosticExitCode.NOT_READY
    stdout_payload = json.loads(result.stdout)
    disk_payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert stdout_payload == disk_payload
    assert stdout_payload["overall_status"] == "not_ready"
    assert len(stdout_payload["checks"]) == 12
    required_by_id = {item["check_id"]: item["required"] for item in stdout_payload["checks"]}
    assert required_by_id["ENV-006"] is False
    assert required_by_id["ENV-010"] is False
    assert required_by_id["ENV-011"] is False
    assert all(
        required_by_id[check_id] is True
        for check_id in required_by_id
        if check_id not in {"ENV-006", "ENV-010", "ENV-011"}
    )


def test_powershell_wrapper_contains_catastrophic_runner_failure(
    tmp_path: Path,
) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    repository = tmp_path / "failure-repository"
    scripts = repository / "scripts"
    package = repository / "backend" / "src" / "aiwebnovel" / "diagnostics"
    output_parent = tmp_path / "failure-reports"
    scripts.mkdir(parents=True)
    package.mkdir(parents=True)
    output_parent.mkdir()
    shutil.copy2(
        _REPOSITORY_ROOT / "scripts" / "environment_doctor.ps1",
        scripts / "environment_doctor.ps1",
    )
    (package.parent / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    canary = "controlled-runner-canary-987654321"
    (package / "runner.py").write_text(
        "import sys\n"
        f"sys.stderr.write({canary!r} + ' at ' + __file__ + '\\n')\n"
        "raise SystemExit(99)\n",
        encoding="utf-8",
    )
    output_file = output_parent / "doctor.json"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            os.fspath(scripts / "environment_doctor.ps1"),
            "-Json",
            "-OutputFile",
            os.fspath(output_file),
        ],
        cwd=repository,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )

    assert result.returncode == DiagnosticExitCode.NOT_READY
    stdout_payload = json.loads(result.stdout)
    disk_payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert stdout_payload == disk_payload
    assert stdout_payload["error"] == "diagnostic_failure"
    assert not result.stderr
    combined = result.stdout + result.stderr + output_file.read_text(encoding="utf-8")
    assert canary not in combined
    assert os.fspath(repository).casefold() not in combined.casefold()
