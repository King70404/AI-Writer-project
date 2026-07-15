"""Repository-hygiene and local quality-script regression tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_HYGIENE_SCRIPT = _REPOSITORY_ROOT / "scripts" / "check_repository_hygiene.ps1"
_QUALITY_GATE_SCRIPT = _REPOSITORY_ROOT / "scripts" / "quality_gate.ps1"
_COVERAGE_CHECKER = _REPOSITORY_ROOT / "scripts" / "check_backend_coverage.py"


def _require_command(name: str) -> str:
    executable = shutil.which(name)
    assert executable is not None, f"required command is unavailable: {name}"
    return executable


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return _run([_require_command("git"), *arguments], cwd=repository)


def _initialize_repository(repository: Path) -> None:
    repository.mkdir()
    initialization = _git(repository, "init", "--initial-branch=main")
    assert initialization.returncode == 0, initialization.stderr
    for key, value in (
        ("user.name", "AIWebNovel Hygiene Test"),
        ("user.email", "hygiene-test@invalid.example"),
    ):
        configuration = _git(repository, "config", key, value)
        assert configuration.returncode == 0, configuration.stderr


def _commit_all(repository: Path) -> None:
    staged = _git(repository, "add", "--all")
    assert staged.returncode == 0, staged.stderr
    committed = _git(repository, "commit", "-m", "test fixture")
    assert committed.returncode == 0, committed.stderr


def _run_hygiene_script(
    repository: Path,
    *,
    script: Path = _HYGIENE_SCRIPT,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            _require_command("powershell.exe"),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RepositoryRoot",
            str(repository),
        ],
        cwd=repository,
    )


def _coverage_result(
    tmp_path: Path,
    *,
    covered_statements: int,
    covered_branches: int,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    report_path = tmp_path / "controlled-coverage.json"
    report = {
        "totals": {
            "num_statements": 100,
            "covered_lines": covered_statements,
            "num_branches": 100,
            "covered_branches": covered_branches,
        }
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    result = _run(
        [sys.executable, str(_COVERAGE_CHECKER), str(report_path)],
        cwd=_REPOSITORY_ROOT,
    )
    return result, report_path


def test_hygiene_check_accepts_a_safe_tracked_repository(tmp_path: Path) -> None:
    repository = tmp_path / "safe-repository"
    _initialize_repository(repository)
    script_directory = repository / "scripts"
    script_directory.mkdir()
    copied_script = script_directory / _HYGIENE_SCRIPT.name
    shutil.copy2(_HYGIENE_SCRIPT, copied_script)
    (repository / "README.md").write_text("# Safe fixture\n", encoding="utf-8")
    _commit_all(repository)

    result = _run_hygiene_script(repository, script=copied_script)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "[hygiene] passed" in result.stdout


def test_hygiene_check_rejects_tracked_artifacts_without_leaking_values(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "unsafe-repository"
    _initialize_repository(repository)
    sensitive_value = "fixture-value-that-must-not-be-printed"
    sensitive_user = "FixtureUserThatMustNotBePrinted"
    (repository / ".env").write_text(
        "PASS" + "WORD=" + sensitive_value + "\n",
        encoding="utf-8",
    )
    (repository / "data.sqlite3").write_bytes(b"SQLite fixture")
    (repository / "data.sqlite3-wal").write_bytes(b"SQLite WAL fixture")
    (repository / "data.sqlite3-shm").write_bytes(b"SQLite SHM fixture")
    runtime_directory = repository / ".runtime"
    runtime_directory.mkdir()
    (runtime_directory / "state.json").write_text("{}\n", encoding="utf-8")
    backups_directory = repository / "backups"
    backups_directory.mkdir()
    (backups_directory / "snapshot.zip").write_bytes(b"backup fixture")
    exports_directory = repository / "exports"
    exports_directory.mkdir()
    (exports_directory / "export.txt").write_text("export\n", encoding="utf-8")
    models_directory = repository / "local_models"
    models_directory.mkdir()
    (models_directory / "detector.bin").write_bytes(b"model fixture")
    (repository / "service.log").write_text("diagnostic\n", encoding="utf-8")
    (repository / "local-path.txt").write_text(
        "C:" + "\\Users\\" + sensitive_user + "\\draft.txt\n",
        encoding="utf-8",
    )
    (repository / "key-material.txt").write_text(
        "-----BEGIN " + "PRIVATE KEY-----\n" + sensitive_value + "\n",
        encoding="utf-8",
    )
    _commit_all(repository)

    untracked_name = "untracked-canary.txt"
    (repository / untracked_name).write_text(
        "Author" + "ization: Bearer " + sensitive_value,
        encoding="utf-8",
    )
    result = _run_hygiene_script(repository)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "type=environment-file file=.env" in output
    assert "type=database-artifact file=data.sqlite3" in output
    assert "type=database-artifact file=data.sqlite3-wal" in output
    assert "type=database-artifact file=data.sqlite3-shm" in output
    assert "type=runtime-or-sandbox file=.runtime/state.json" in output
    assert "type=backup-or-export file=backups/snapshot.zip" in output
    assert "type=backup-or-export file=exports/export.txt" in output
    assert "type=local-model file=local_models/detector.bin" in output
    assert "type=log-output file=service.log" in output
    assert "type=absolute-user-path file=local-path.txt" in output
    assert "type=private-key file=key-material.txt" in output
    assert sensitive_value not in output
    assert sensitive_user not in output
    assert untracked_name not in output


def test_quality_gate_step_propagates_failure_and_stops_success_reporting() -> None:
    quoted_script = str(_QUALITY_GATE_SCRIPT).replace("'", "''")
    command = (
        f". '{quoted_script}'; "
        "Invoke-QualityGateStep -Name 'controlled failure' "
        "-Action { & powershell.exe -NoProfile -Command 'exit 23' }; "
        "Write-Output 'UNREACHABLE_SUCCESS'"
    )

    result = _run(
        [
            _require_command("powershell.exe"),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=_REPOSITORY_ROOT,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 23
    assert "[quality] running: controlled failure" in output
    assert "[quality] failed: controlled failure (exit code 23)" in output
    assert "UNREACHABLE_SUCCESS" not in output
    assert "all requested local quality gates passed" not in output


def test_backend_coverage_checker_accepts_both_thresholds(tmp_path: Path) -> None:
    result, report_path = _coverage_result(
        tmp_path,
        covered_statements=80,
        covered_branches=75,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "statements=80.00% branches=75.00%" in result.stdout
    assert str(report_path) not in result.stdout + result.stderr


def test_backend_coverage_checker_rejects_low_statement_coverage(
    tmp_path: Path,
) -> None:
    result, report_path = _coverage_result(
        tmp_path,
        covered_statements=79,
        covered_branches=100,
    )

    assert result.returncode != 0
    assert "statement coverage below threshold" in result.stdout
    assert "branch coverage below threshold" not in result.stdout
    assert str(report_path) not in result.stdout + result.stderr


def test_backend_coverage_checker_rejects_low_branch_coverage(tmp_path: Path) -> None:
    result, report_path = _coverage_result(
        tmp_path,
        covered_statements=100,
        covered_branches=74,
    )

    assert result.returncode != 0
    assert "branch coverage below threshold" in result.stdout
    assert "statement coverage below threshold" not in result.stdout
    assert str(report_path) not in result.stdout + result.stderr
