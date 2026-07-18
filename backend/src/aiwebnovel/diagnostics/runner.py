"""Environment diagnostic orchestration, rendering, and command entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Never

from aiwebnovel.diagnostics.checks import (
    DEFAULT_CHECKS,
    CheckDefinition,
    DiagnosticContext,
    DiagnosticDependencies,
    default_dependencies,
)
from aiwebnovel.diagnostics.models import (
    CheckStatus,
    DiagnosticCheck,
    DiagnosticExitCode,
    DiagnosticMode,
    DiagnosticReport,
    detail_items,
)
from aiwebnovel.diagnostics.redaction import DiagnosticRedactor

Clock = Callable[[], int]


class InvocationError(ValueError):
    """A safe command-usage failure."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise InvocationError("diagnostic invocation is invalid")


def run_diagnostics(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    *,
    checks: Sequence[CheckDefinition] = DEFAULT_CHECKS,
    clock_ns: Clock = time.perf_counter_ns,
) -> DiagnosticReport:
    """Run every check in order and convert individual exceptions to safe failures."""
    completed: dict[str, DiagnosticCheck] = {}
    outcomes: list[DiagnosticCheck] = []
    for definition in checks:
        started = clock_ns()
        try:
            result = definition.run(context, dependencies, completed)
        except Exception as exc:  # noqa: BLE001 - each check must fail independently.
            result = None
            error_type = type(exc).__name__
        finished = clock_ns()
        duration_ms = max(0, (finished - started) // 1_000_000)
        if result is None:
            outcome = DiagnosticCheck(
                check_id=definition.check_id,
                name=definition.name,
                status=CheckStatus.FAIL,
                summary="The diagnostic check failed safely.",
                details=detail_items(error_type=error_type),
                remediation="Resolve the reported environment category and rerun diagnostics.",
                required=True,
                duration_ms=duration_ms,
            )
        else:
            outcome = DiagnosticCheck(
                check_id=definition.check_id,
                name=definition.name,
                status=result.status,
                summary=result.summary,
                details=result.details,
                remediation=result.remediation,
                required=result.required,
                duration_ms=duration_ms,
            )
        completed[outcome.check_id] = outcome
        outcomes.append(outcome)
    return DiagnosticReport(mode=context.mode, checks=tuple(outcomes))


def _redact_value(value: object, redactor: DiagnosticRedactor) -> object:
    if isinstance(value, str):
        return redactor.redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item, redactor) for item in value]
    if isinstance(value, dict):
        return {
            redactor.redact_text(key): _redact_value(item, redactor) for key, item in value.items()
        }
    return value


def render_json(report: DiagnosticReport, redactor: DiagnosticRedactor) -> str:
    """Render one machine-readable UTF-8 JSON report."""
    safe = _redact_value(report.to_dict(), redactor)
    return json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def render_human(report: DiagnosticReport, redactor: DiagnosticRedactor) -> str:
    """Render one concise human-readable report through the same redactor."""
    lines = [
        "AIWebNovel environment diagnostics",
        f"mode: {report.mode.value}",
        f"overall_status: {report.overall_status.value}",
    ]
    for check in report.checks:
        lines.append(
            f"[{check.status.value.upper()}] {check.check_id} {redactor.redact_text(check.name)}"
        )
        lines.append(f"  {redactor.redact_text(check.summary)}")
        for key, value in check.details:
            lines.append(f"  {redactor.redact_text(key)}: {redactor.redact_text(value)}")
        if check.remediation:
            lines.append(f"  remediation: {redactor.redact_text(check.remediation)}")
        lines.append(f"  required: {str(check.required).lower()}")
        lines.append(f"  duration_ms: {check.duration_ms}")
    return "\n".join(lines) + "\n"


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _parse_mode(value: str) -> DiagnosticMode:
    normalized = value.strip().casefold()
    try:
        return DiagnosticMode(normalized)
    except ValueError as exc:
        raise InvocationError("diagnostic mode is invalid") from exc


def _parse_port(value: str) -> int:
    try:
        port = int(value, 10)
    except ValueError as exc:
        raise InvocationError("diagnostic port is invalid") from exc
    if port < 1 or port > 65_535:
        raise InvocationError("diagnostic port is invalid")
    return port


def _is_reparse_point(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(path_stat.st_mode):
        return True
    attributes = int(getattr(path_stat, "st_file_attributes", 0))
    return bool(attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def _is_inside(path: Path, container: Path) -> bool:
    try:
        common = os.path.commonpath((os.path.abspath(path), os.path.abspath(container)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(os.path.abspath(container))


def _validate_output_file(value: str, repository_root: Path) -> Path:
    if not value.strip():
        raise InvocationError("diagnostic output path is invalid")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = Path(os.path.abspath(candidate))
    parent = candidate.parent
    if not parent.is_dir():
        raise InvocationError("diagnostic output parent must already be a safe directory")
    current = parent
    while True:
        if _is_reparse_point(current):
            raise InvocationError("diagnostic output parent must already be a safe directory")
        if current.parent == current:
            break
        current = current.parent
    if candidate.exists() and (not candidate.is_file() or _is_reparse_point(candidate)):
        raise InvocationError("diagnostic output target is unsafe")
    if _is_inside(candidate, repository_root):
        runtime_root = repository_root / ".runtime"
        if not _is_inside(candidate, runtime_root):
            raise InvocationError("diagnostic output inside the repository must use .runtime")
    return candidate


def _build_redactor(repository_root: Path) -> DiagnosticRedactor:
    try:
        from aiwebnovel.core.config import resolve_local_app_data_root

        local_app_data = resolve_local_app_data_root()
    except Exception:  # noqa: BLE001 - rendering must survive unavailable app dependencies.
        local_app_data = None
    secret_values = tuple(
        value
        for key, value in os.environ.items()
        if len(value) >= 8
        and any(
            marker in key.casefold()
            for marker in (
                "password",
                "passwd",
                "secret",
                "token",
                "cookie",
                "csrf",
                "api_key",
                "authorization",
                "credential",
                "private_key",
            )
        )
    )
    return DiagnosticRedactor(
        repository_root=repository_root,
        virtual_environment=repository_root / ".venv",
        user_home=Path.home(),
        username=getpass.getuser(),
        local_app_data=local_app_data,
        sensitive_values=secret_values,
    )


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(add_help=True)
    parser.add_argument("--mode", default="development")
    parser.add_argument("--backend-port", default="8000")
    parser.add_argument("--frontend-port", default="5173")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output-file")
    return parser.parse_args(argv)


def _write_output(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _invocation_failure(as_json: bool) -> int:
    if as_json:
        print(
            json.dumps(
                {
                    "schema_version": "1",
                    "overall_status": "not_ready",
                    "error": "invocation_error",
                },
                ensure_ascii=False,
            )
        )
    else:
        print("Environment diagnostics could not start because the invocation is invalid.")
    return int(DiagnosticExitCode.INVOCATION_ERROR)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate invocation, execute diagnostics, render, and propagate readiness."""
    as_json = argv is not None and "--json" in argv
    try:
        arguments = _arguments(argv)
        as_json = bool(arguments.json)
        repository_root = _repository_root()
        if not Path.cwd().resolve().samefile(repository_root):
            raise InvocationError("diagnostics must run from the repository root")
        mode = _parse_mode(str(arguments.mode))
        backend_port = _parse_port(str(arguments.backend_port))
        frontend_port = _parse_port(str(arguments.frontend_port))
        if mode is not DiagnosticMode.INTEGRATED and backend_port == frontend_port:
            raise InvocationError("development ports must be distinct")
        output_file = (
            _validate_output_file(str(arguments.output_file), repository_root)
            if arguments.output_file is not None
            else None
        )
    except (InvocationError, OSError):
        return _invocation_failure(as_json)

    context = DiagnosticContext(
        repository_root=repository_root,
        mode=mode,
        backend_port=backend_port,
        frontend_port=frontend_port,
    )
    report = run_diagnostics(context, default_dependencies())
    redactor = _build_redactor(repository_root)
    rendered = render_json(report, redactor) if as_json else render_human(report, redactor)
    if output_file is not None:
        try:
            _write_output(output_file, rendered)
        except OSError:
            return _invocation_failure(as_json)
    sys.stdout.write(rendered)
    return int(report.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
