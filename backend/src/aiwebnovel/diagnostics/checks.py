"""Deterministic ENV-001 through ENV-012 checks with injectable side effects."""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import stat
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aiwebnovel.diagnostics.models import (
    CheckResult,
    CheckStatus,
    DiagnosticCheck,
    DiagnosticMode,
    detail_items,
)

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_NODE_VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_PROHIBITED_BUILD_CONTENT = (
    re.compile(r"(?i)\b[A-Z]:[\\/]"),
    re.compile(
        r"(?i)(?<![\\/])\\\\[A-Z0-9][A-Z0-9._-]*[\\/]"
        r"[A-Z0-9$][A-Z0-9$._-]*(?=[\\/\s\"'])"
    ),
    re.compile(r"-----BEGIN(?:\s+[A-Z0-9]+)?\s+PRIVATE\s+KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\bauthorization\b[\"']?\s*[:=]\s*[\"']?(?:bearer|basic)\s+"
        r"[A-Za-z0-9+/_.=-]{8,}"
    ),
    re.compile(
        r"(?i)\b(?:cookie|set-cookie)\b[\"']?\s*[:=]\s*[\"']?"
        r"[A-Za-z0-9_.-]{1,64}=[^;\r\n\"']{4,}"
    ),
    re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|client[_-]?secret|api[_-]?key|"
        r"access[_-]?token|refresh[_-]?token|id[_-]?token)\b[\"']?\s*[:=]\s*"
        r"(?:[\"'][^\"'\r\n]{8,}[\"']|[A-Za-z0-9._~+/=-]{8,})"
    ),
)
_MAX_COMMAND_OUTPUT = 1_048_576
_MAX_BUILD_FILE_BYTES = 2_097_152
_MAX_BUILD_TOTAL_BYTES = 16_777_216
_MAX_BUILD_FILES = 100
_MAX_BUILD_DIRECTORIES = 50


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bounded output from one non-shell command."""

    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    """Injectable command execution boundary."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float = 15,
    ) -> CommandResult: ...


class SystemCommandRunner:
    """Run local commands without a shell or unbounded diagnostic output."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float = 15,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                list(argv),
                cwd=cwd,
                env=dict(env) if env is not None else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(returncode=124, stdout="", stderr="")
        except OSError:
            return CommandResult(returncode=127, stdout="", stderr="")
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout[:_MAX_COMMAND_OUTPUT],
            stderr=completed.stderr[:_MAX_COMMAND_OUTPUT],
        )


class PortProbe(Protocol):
    """Injectable loopback port availability boundary."""

    def __call__(self, port: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class DiagnosticContext:
    """One immutable diagnostic invocation."""

    repository_root: Path
    mode: DiagnosticMode
    backend_port: int = 8000
    frontend_port: int = 5173


@dataclass(frozen=True, slots=True)
class DiagnosticDependencies:
    """Side effects used by checks and replaced in unit tests."""

    command_runner: CommandRunner
    platform_name: Callable[[], str]
    platform_summary: Callable[[], str]
    port_probe: PortProbe
    token_factory: Callable[[], str]
    environment: Mapping[str, str]


CheckFunction = Callable[
    [DiagnosticContext, DiagnosticDependencies, Mapping[str, DiagnosticCheck]], CheckResult
]


@dataclass(frozen=True, slots=True)
class CheckDefinition:
    """Stable ID, name, and implementation for one check."""

    check_id: str
    name: str
    run: CheckFunction


def _loopback_port_available(port: int) -> bool:
    if port < 1 or port > 65_535:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            candidate.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def default_dependencies() -> DiagnosticDependencies:
    """Build production dependencies without performing checks."""
    return DiagnosticDependencies(
        command_runner=SystemCommandRunner(),
        platform_name=platform.system,
        platform_summary=lambda: f"{platform.release()} {platform.version()}".strip(),
        port_probe=_loopback_port_available,
        token_factory=lambda: uuid.uuid4().hex,
        environment=dict(os.environ),
    )


def _combined_output(result: CommandResult) -> str:
    return f"{result.stdout}\n{result.stderr}".strip()


def _safe_version(output: str) -> str | None:
    match = _VERSION_PATTERN.search(output)
    if match is None:
        return None
    return ".".join(match.groups())


def _json_object(result: CommandResult) -> dict[str, object] | None:
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def _inside(path: Path, container: Path) -> bool:
    try:
        common = os.path.commonpath((os.path.abspath(path), os.path.abspath(container)))
    except ValueError:
        return False
    return os.path.normcase(common) == os.path.normcase(os.path.abspath(container))


def _dependency_passed(previous: Mapping[str, DiagnosticCheck], check_id: str) -> bool:
    outcome = previous.get(check_id)
    return outcome is not None and outcome.status is CheckStatus.PASS


def check_operating_system(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-001: require Windows without an administrator probe."""
    del context, previous
    if dependencies.platform_name().casefold() != "windows":
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="Windows is required for this local application.",
            remediation="Run the development environment on supported Windows 11.",
        )
    summary = dependencies.platform_summary().strip()
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Windows is available without an administrator requirement.",
        details=detail_items(version_summary=summary or "available"),
    )


def check_git(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-002: verify Git, repository identity, branch, and readable status."""
    del previous
    runner = dependencies.command_runner
    version_result = runner.run(("git", "--version"), cwd=context.repository_root)
    root_result = runner.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=context.repository_root,
    )
    branch_result = runner.run(
        ("git", "branch", "--show-current"),
        cwd=context.repository_root,
    )
    status_result = runner.run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all", "-z"),
        cwd=context.repository_root,
    )
    if any(
        result.returncode != 0
        for result in (version_result, root_result, branch_result, status_result)
    ):
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="Git or repository state could not be read.",
            remediation="Install Git and run the doctor from the repository root.",
        )
    reported_root = Path(root_result.stdout.strip())
    if not _same_path(reported_root, context.repository_root):
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="The current directory is not the expected repository root.",
            remediation="Run the doctor from the AIWebNovel repository root.",
        )
    branch = branch_result.stdout.strip() or "detached"
    changes = len([item for item in status_result.stdout.split("\0") if item])
    details = detail_items(
        branch=branch,
        changes=changes,
        version=_safe_version(_combined_output(version_result)) or "available",
    )
    if changes:
        return CheckResult(
            status=CheckStatus.FAIL if context.mode is DiagnosticMode.M0 else CheckStatus.WARNING,
            summary="The Git working tree contains local changes.",
            details=details,
            remediation="Review the working tree manually; diagnostics never clean it.",
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Git repository state is readable and clean.",
        details=details,
    )


def check_python(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-003: require the exact system Python launcher target."""
    del previous
    runner = dependencies.command_runner
    version_result = runner.run(("py", "-3.12", "--version"), cwd=context.repository_root)
    probe_script = (
        "import json,struct,sys;"
        "print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),"
        "'bits':struct.calcsize('P')*8,'executable':sys.executable}))"
    )
    probe_result = runner.run(
        ("py", "-3.12", "-c", probe_script),
        cwd=context.repository_root,
    )
    pip_result = runner.run(
        ("py", "-3.12", "-m", "pip", "--version"),
        cwd=context.repository_root,
    )
    venv_result = runner.run(
        ("py", "-3.12", "-m", "venv", "--help"),
        cwd=context.repository_root,
    )
    payload = _json_object(probe_result)
    version = _safe_version(_combined_output(version_result))
    valid = (
        version_result.returncode == 0
        and version == "3.12.10"
        and payload is not None
        and payload.get("version") == "3.12.10"
        and payload.get("bits") == 64
        and isinstance(payload.get("executable"), str)
        and not _inside(Path(str(payload["executable"])), context.repository_root)
        and pip_result.returncode == 0
        and venv_result.returncode == 0
    )
    if not valid:
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="Python 3.12.10 x64 with py, pip, and venv is unavailable.",
            remediation="Install the official Python 3.12.10 x64 user distribution.",
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Python 3.12.10 x64, pip, venv, and the launcher are available.",
        details=detail_items(bits=64, interpreter="<python>", version="3.12.10"),
    )


def check_virtual_environment(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-004: verify the repository virtual environment and dependency integrity."""
    del previous
    virtual_environment = context.repository_root / ".venv"
    python = virtual_environment / "Scripts" / "python.exe"
    if not python.is_file():
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="The repository virtual environment is missing.",
            remediation="Create the documented root virtual environment manually.",
        )
    probe_script = (
        "import aiwebnovel,json,struct,sys;"
        "print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),"
        "'bits':struct.calcsize('P')*8,'executable':sys.executable,'prefix':sys.prefix,"
        "'base_prefix':sys.base_prefix,'module':aiwebnovel.__file__}))"
    )
    runner = dependencies.command_runner
    probe_result = runner.run((str(python), "-c", probe_script), cwd=context.repository_root)
    pip_result = runner.run(
        (str(python), "-m", "pip", "check"),
        cwd=context.repository_root,
    )
    payload = _json_object(probe_result)
    source_root = context.repository_root / "backend" / "src"
    valid = False
    if payload is not None and pip_result.returncode == 0:
        executable = Path(str(payload.get("executable", "")))
        prefix = Path(str(payload.get("prefix", "")))
        base_prefix = Path(str(payload.get("base_prefix", "")))
        module = Path(str(payload.get("module", "")))
        valid = (
            payload.get("version") == "3.12.10"
            and payload.get("bits") == 64
            and _same_path(executable, python)
            and _same_path(prefix, virtual_environment)
            and not _same_path(prefix, base_prefix)
            and _inside(module, source_root)
        )
    if not valid:
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="The repository virtual environment is invalid or inconsistent.",
            remediation="Recreate the virtual environment using the documented dependency lock.",
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="The repository virtual environment and installed dependencies are valid.",
        details=detail_items(interpreter="<venv>\\Scripts\\python.exe", pip_check=True),
    )


def check_node(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-005: verify Node.js, npm, lockfile, and installed dependency tree."""
    del previous
    frontend = context.repository_root / "frontend"
    runner = dependencies.command_runner
    node_result = runner.run(
        (
            "node",
            "-p",
            "JSON.stringify({version:process.version,arch:process.arch,execPath:process.execPath})",
        ),
        cwd=context.repository_root,
    )
    npm_result = runner.run(("npm.cmd", "--version"), cwd=frontend)
    # Inspect the installed tree without npm's unrelated registry update probe.
    # Keep the normal command deadline and report actual dependency failures.
    npm_tree_result = runner.run(
        ("npm.cmd", "ls", "--depth=0", "--offline", "--no-update-notifier"), cwd=frontend
    )
    payload = _json_object(node_result)
    version_value = str(payload.get("version", "")) if payload is not None else ""
    version_match = _NODE_VERSION_PATTERN.fullmatch(version_value)
    valid = (
        payload is not None
        and version_match is not None
        and int(version_match.group(1)) == 24
        and payload.get("arch") == "x64"
        and isinstance(payload.get("execPath"), str)
        and not _inside(Path(str(payload["execPath"])), context.repository_root)
        and npm_result.returncode == 0
        and npm_tree_result.returncode == 0
        and (frontend / "package-lock.json").is_file()
        and (frontend / "node_modules").is_dir()
    )
    if not valid:
        timed_out = any(
            result.returncode == 124 for result in (node_result, npm_result, npm_tree_result)
        )
        return CheckResult(
            status=CheckStatus.FAIL,
            summary=(
                "A local Node.js or npm diagnostic command timed out."
                if timed_out
                else "Node.js 24 x64, npm, or frontend dependencies are unavailable."
            ),
            details=detail_items(
                node_exit_code=node_result.returncode,
                npm_exit_code=npm_result.returncode,
                dependency_tree_exit_code=npm_tree_result.returncode,
            ),
            remediation=(
                "Check local tool responsiveness and system load before repeating diagnostics."
                if timed_out
                else "Install Node.js 24 LTS and restore frontend dependencies manually."
            ),
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Node.js 24 x64, npm, and the locked dependency tree are available.",
        details=detail_items(
            architecture="x64",
            node=version_value,
            npm=_safe_version(_combined_output(npm_result)) or "available",
        ),
    )


def check_playwright(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-006: verify Playwright and its external Chromium binary."""
    del previous
    frontend = context.repository_root / "frontend"
    script = (
        "const fs=require('node:fs');"
        "try{const {chromium}=require('@playwright/test');const p=chromium.executablePath();"
        "console.log(JSON.stringify({available:fs.existsSync(p),path:p}));}"
        "catch(_error){console.log(JSON.stringify({available:false,path:''}));process.exitCode=1;}"
    )
    result = dependencies.command_runner.run(("node", "-e", script), cwd=frontend)
    payload = _json_object(result)
    valid = (
        payload is not None
        and payload.get("available") is True
        and isinstance(payload.get("path"), str)
        and not _inside(Path(str(payload["path"])), context.repository_root)
    )
    required = context.mode is DiagnosticMode.M0
    if not valid:
        return CheckResult(
            status=CheckStatus.FAIL if required else CheckStatus.WARNING,
            summary="Playwright Chromium is unavailable.",
            remediation="Install only the documented Playwright Chromium browser manually.",
            required=required,
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Playwright and its external Chromium binary are available.",
        details=detail_items(browser_cache_in_repository=False),
        required=required,
    )


def _application_probe_environment(dependencies: DiagnosticDependencies) -> dict[str, str]:
    return {
        key: value
        for key, value in dependencies.environment.items()
        if not key.upper().startswith("AIWEBNOVEL_")
    }


def check_security_configuration(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-007: construct isolated defaults and the public security baseline."""
    if not _dependency_passed(previous, "ENV-004"):
        return CheckResult(
            status=CheckStatus.SKIPPED,
            summary="Security configuration was not probed because the virtual environment failed.",
            remediation="Repair the virtual environment, then rerun diagnostics.",
        )
    python = context.repository_root / ".venv" / "Scripts" / "python.exe"
    result = dependencies.command_runner.run(
        (str(python), "-m", "aiwebnovel.diagnostics.probes", "configuration"),
        cwd=context.repository_root,
        env=_application_probe_environment(dependencies),
    )
    baseline = dependencies.command_runner.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(context.repository_root / "scripts" / "check_security_baseline.ps1"),
            "-RepositoryRoot",
            str(context.repository_root),
        ),
        cwd=context.repository_root,
        timeout_seconds=30,
    )
    payload = _json_object(result)
    required_flags = (
        "default_loopback",
        "proxy_headers_disabled",
        "trusted_hosts_safe",
        "cors_safe",
        "production_docs_closed",
        "request_limit_valid",
        "middleware_assembled",
    )
    valid = (
        baseline.returncode == 0
        and payload is not None
        and payload.get("ok") is True
        and all(payload.get(flag) is True for flag in required_flags)
    )
    if not valid:
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="The configuration or local security baseline is invalid.",
            remediation="Review AIWebNovel security configuration and rerun the baseline checks.",
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Configuration defaults and the local security baseline are valid.",
        details=detail_items(
            bind_host="127.0.0.1",
            production_docs=False,
            proxy_headers=False,
        ),
    )


def check_storage_and_database(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-008: run storage and SQLite probes only in an owned temporary root."""
    if not _dependency_passed(previous, "ENV-001") or not _dependency_passed(previous, "ENV-004"):
        return CheckResult(
            status=CheckStatus.SKIPPED,
            summary="Storage diagnostics were skipped because a required platform failed.",
            remediation="Repair Windows and the virtual environment, then rerun diagnostics.",
        )
    token = dependencies.token_factory()
    if re.fullmatch(r"[0-9a-f]{32}", token) is None:
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="A safe diagnostic storage identity could not be generated.",
            remediation="Rerun diagnostics; no formal data was accessed.",
        )
    python = context.repository_root / ".venv" / "Scripts" / "python.exe"
    probe_environment = _application_probe_environment(dependencies)
    try:
        result = dependencies.command_runner.run(
            (
                str(python),
                "-m",
                "aiwebnovel.diagnostics.probes",
                "storage",
                "--token",
                token,
            ),
            cwd=context.repository_root,
            env=probe_environment,
            timeout_seconds=30,
        )
    except Exception:  # noqa: BLE001 - diagnostics convert runner faults into failure.
        result = CommandResult(returncode=127, stdout="", stderr="")
    try:
        cleanup_result = dependencies.command_runner.run(
            (
                str(python),
                "-m",
                "aiwebnovel.diagnostics.probes",
                "cleanup",
                "--token",
                token,
            ),
            cwd=context.repository_root,
            env=probe_environment,
            timeout_seconds=15,
        )
    except Exception:  # noqa: BLE001 - diagnostics convert runner faults into failure.
        cleanup_result = CommandResult(returncode=127, stdout="", stderr="")
    payload = _json_object(result)
    cleanup_payload = _json_object(cleanup_result)
    valid = (
        payload is not None
        and cleanup_payload is not None
        and payload.get("ok") is True
        and payload.get("formal_content_accessed") is False
        and payload.get("formal_root_unchanged") is True
        and payload.get("storage") is True
        and payload.get("database") is True
        and payload.get("cleanup") is True
        and payload.get("standard_directories") == 12
        and cleanup_payload.get("ok") is True
        and cleanup_payload.get("cleanup") is True
        and cleanup_payload.get("root_exists") is False
    )
    if not valid:
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="Isolated storage, database, or cleanup diagnostics failed.",
            remediation="Review LocalAppData access and remove only verified doctor residue.",
        )
    assert payload is not None
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Isolated storage, SQLite, and cleanup probes passed.",
        details=detail_items(
            cleanup=True,
            database=True,
            formal_content_accessed=False,
            formal_root_exists=bool(payload["formal_root_exists"]),
            root="<temp-data-root>",
            storage=True,
        ),
    )


def check_ports(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-009: briefly bind requested loopback ports without inspecting owners."""
    del previous
    ports = (
        (context.backend_port,)
        if context.mode is DiagnosticMode.INTEGRATED
        else (context.backend_port, context.frontend_port)
    )
    if any(port < 1 or port > 65_535 for port in ports) or len(set(ports)) != len(ports):
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="Diagnostic ports are invalid or conflict with each other.",
            remediation="Choose distinct loopback ports between 1 and 65535.",
        )
    backend_available = dependencies.port_probe(context.backend_port)
    frontend_available = (
        None
        if context.mode is DiagnosticMode.INTEGRATED
        else dependencies.port_probe(context.frontend_port)
    )
    unavailable = int(not backend_available) + int(frontend_available is False)
    details = detail_items(
        backend_available=backend_available,
        backend_port=context.backend_port,
        checked=len(ports),
        frontend_available=frontend_available,
        frontend_port=(
            None if context.mode is DiagnosticMode.INTEGRATED else context.frontend_port
        ),
        unavailable=unavailable,
    )
    if unavailable:
        status = (
            CheckStatus.WARNING if context.mode is DiagnosticMode.DEVELOPMENT else CheckStatus.FAIL
        )
        return CheckResult(
            status=status,
            summary="One or more requested loopback ports are occupied.",
            details=details,
            remediation="Stop the owning service manually or select another port.",
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Requested loopback ports can be bound and were immediately released.",
        details=details,
    )


def _is_reparse_point(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(path_stat.st_mode):
        return True
    attributes = int(getattr(path_stat, "st_file_attributes", 0))
    return bool(attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def _valid_frontend_build(repository_root: Path) -> bool:
    dist = repository_root / "frontend" / "dist"
    index = dist / "index.html"
    assets = dist / "assets"
    if not dist.is_dir() or not index.is_file() or not assets.is_dir():
        return False
    if any(_is_reparse_point(path) for path in (dist, index, assets)):
        return False
    files: list[Path] = []
    pending = [dist]
    directory_count = 0
    total_bytes = 0
    while pending:
        directory = pending.pop()
        directory_count += 1
        if directory_count > _MAX_BUILD_DIRECTORIES or _is_reparse_point(directory):
            return False
        try:
            children = sorted(directory.iterdir(), key=lambda path: os.fspath(path).casefold())
        except OSError:
            return False
        for child in children:
            if _is_reparse_point(child):
                return False
            try:
                if child.is_dir():
                    pending.append(child)
                    continue
                if not child.is_file():
                    return False
                size = child.stat().st_size
            except OSError:
                return False
            if size > _MAX_BUILD_FILE_BYTES:
                return False
            total_bytes += size
            files.append(child)
            if len(files) > _MAX_BUILD_FILES or total_bytes > _MAX_BUILD_TOTAL_BYTES:
                return False

    if index not in files or not any(
        path.suffix.casefold() == ".js" and path.is_relative_to(assets) for path in files
    ):
        return False
    for path in files:
        try:
            content = path.read_bytes().decode("utf-8", errors="ignore")
        except OSError:
            return False
        if _is_reparse_point(path) or any(
            pattern.search(content) for pattern in _PROHIBITED_BUILD_CONTENT
        ):
            return False
    return True


def check_frontend_build(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-010: validate an existing frontend build without creating it."""
    del dependencies, previous
    required = context.mode in {DiagnosticMode.INTEGRATED, DiagnosticMode.M0}
    valid = _valid_frontend_build(context.repository_root)
    if not valid:
        return CheckResult(
            status=CheckStatus.FAIL if required else CheckStatus.WARNING,
            summary="The frontend production build is missing or invalid.",
            remediation="Run the documented frontend build explicitly, then rerun diagnostics.",
            required=required,
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="The frontend production build has a valid local asset structure.",
        details=detail_items(path="<repo>\\frontend\\dist"),
        required=required,
    )


def check_quality_tools(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-011: verify local quality-tool entry points without running full tests."""
    del previous
    python = context.repository_root / ".venv" / "Scripts" / "python.exe"
    frontend_bin = context.repository_root / "frontend" / "node_modules" / ".bin"
    missing = 0
    for module in ("ruff", "mypy", "pytest"):
        if not python.is_file():
            missing += 1
            continue
        result = dependencies.command_runner.run(
            (str(python), "-m", module, "--version"),
            cwd=context.repository_root,
        )
        if result.returncode != 0:
            missing += 1
    for command in ("eslint", "prettier", "vitest", "vite", "playwright"):
        if not (frontend_bin / f"{command}.cmd").is_file():
            missing += 1
    required = context.mode is DiagnosticMode.M0
    if missing:
        return CheckResult(
            status=CheckStatus.FAIL if required else CheckStatus.WARNING,
            summary="One or more local quality-tool entry points are unavailable.",
            details=detail_items(available=8 - missing, missing=missing),
            remediation="Restore the documented development dependencies without using diagnostics.",
            required=required,
        )
    return CheckResult(
        status=CheckStatus.PASS,
        summary="All required local quality-tool entry points are available.",
        details=detail_items(available=8, missing=0),
        required=required,
    )


def check_repository_hygiene(
    context: DiagnosticContext,
    dependencies: DiagnosticDependencies,
    previous: Mapping[str, DiagnosticCheck],
) -> CheckResult:
    """ENV-012: reuse tracked-file hygiene without deleting untracked artifacts."""
    del previous
    script = context.repository_root / "scripts" / "check_repository_hygiene.ps1"
    hygiene_result = dependencies.command_runner.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RepositoryRoot",
            str(context.repository_root),
        ),
        cwd=context.repository_root,
        timeout_seconds=30,
    )
    untracked_result = dependencies.command_runner.run(
        ("git", "ls-files", "--others", "--exclude-standard", "-z"),
        cwd=context.repository_root,
    )
    if hygiene_result.returncode != 0 or untracked_result.returncode != 0:
        return CheckResult(
            status=CheckStatus.FAIL,
            summary="Repository hygiene could not be verified.",
            remediation="Run the repository hygiene gate and review violations manually.",
        )
    untracked = len([item for item in untracked_result.stdout.split("\0") if item])
    return CheckResult(
        status=CheckStatus.PASS,
        summary="Tracked-file hygiene passed without deleting local artifacts.",
        details=detail_items(untracked_not_inspected=untracked),
    )


DEFAULT_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition("ENV-001", "Operating system", check_operating_system),
    CheckDefinition("ENV-002", "Git repository", check_git),
    CheckDefinition("ENV-003", "Python", check_python),
    CheckDefinition("ENV-004", "Virtual environment", check_virtual_environment),
    CheckDefinition("ENV-005", "Node.js and npm", check_node),
    CheckDefinition("ENV-006", "Playwright Chromium", check_playwright),
    CheckDefinition("ENV-007", "Configuration and security", check_security_configuration),
    CheckDefinition("ENV-008", "Storage and database", check_storage_and_database),
    CheckDefinition("ENV-009", "Loopback ports", check_ports),
    CheckDefinition("ENV-010", "Frontend build", check_frontend_build),
    CheckDefinition("ENV-011", "Quality tools", check_quality_tools),
    CheckDefinition("ENV-012", "Repository hygiene", check_repository_hygiene),
)
