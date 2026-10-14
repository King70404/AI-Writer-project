"""Controlled tool, mode-policy, port, and build diagnostic tests."""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from aiwebnovel.diagnostics.checks import (
    CommandResult,
    DiagnosticContext,
    DiagnosticDependencies,
    check_frontend_build,
    check_operating_system,
    check_ports,
    check_quality_tools,
    check_storage_and_database,
    default_dependencies,
)
from aiwebnovel.diagnostics.models import (
    CheckStatus,
    DiagnosticCheck,
    DiagnosticMode,
    OverallStatus,
)
from aiwebnovel.diagnostics.runner import run_diagnostics

pytestmark = pytest.mark.unit

ResponseHandler = Callable[[tuple[str, ...], Path, Mapping[str, str] | None], CommandResult]


class ControlledRunner:
    """Record exact argv and return controlled command results."""

    def __init__(self, handler: ResponseHandler) -> None:
        self.handler = handler
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float = 15,
    ) -> CommandResult:
        del timeout_seconds
        normalized = tuple(argv)
        self.calls.append(normalized)
        return self.handler(normalized, cwd, env)


def _ok(stdout: str = "") -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr="")


def _failed() -> CommandResult:
    return CommandResult(returncode=1, stdout="", stderr="controlled failure")


def _create_repository(root: Path) -> None:
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"")
    (root / "backend" / "src" / "aiwebnovel").mkdir(parents=True)
    (root / "backend" / "src" / "aiwebnovel" / "__init__.py").write_text("", encoding="utf-8")
    frontend = root / "frontend"
    (frontend / "node_modules" / ".bin").mkdir(parents=True)
    (frontend / "package-lock.json").write_text("{}\n", encoding="utf-8")
    for command in ("eslint", "prettier", "vitest", "vite", "playwright"):
        (frontend / "node_modules" / ".bin" / f"{command}.cmd").write_text(
            "@exit /b 0\n", encoding="utf-8"
        )
    assets = frontend / "dist" / "assets"
    assets.mkdir(parents=True)
    (frontend / "dist" / "index.html").write_text(
        '<div id="root"></div><script src="/assets/app.js"></script>\n',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('safe');\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "check_repository_hygiene.ps1").write_text("exit 0\n", encoding="utf-8")


def _successful_handler(
    root: Path,
    failures: set[str] | None = None,
) -> ResponseHandler:
    controlled_failures = failures or set()
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    module_path = root / "backend" / "src" / "aiwebnovel" / "__init__.py"
    system_python = root.parent / "Python312" / "python.exe"

    def handle(
        argv: tuple[str, ...],
        cwd: Path,
        env: Mapping[str, str] | None,
    ) -> CommandResult:
        del cwd, env
        if argv[:2] == ("git", "--version"):
            return _failed() if "git" in controlled_failures else _ok("git version 2.50.1\n")
        if argv[:3] == ("git", "rev-parse", "--show-toplevel"):
            return _ok(f"{root}\n")
        if argv[:3] == ("git", "branch", "--show-current"):
            return _ok("main\n")
        if argv[:3] == ("git", "status", "--porcelain=v1"):
            return _ok(" M controlled.txt\0" if "dirty" in controlled_failures else "")
        if argv[:3] == ("git", "ls-files", "--others"):
            return _ok("")
        if argv[:3] == ("py", "-3.12", "--version"):
            version = "3.12.11" if "python-version" in controlled_failures else "3.12.10"
            return _ok(f"Python {version}\n")
        if argv[:3] == ("py", "-3.12", "-c"):
            version = "3.12.11" if "python-version" in controlled_failures else "3.12.10"
            return _ok(
                json.dumps({"version": version, "bits": 64, "executable": os.fspath(system_python)})
            )
        if argv[:5] == ("py", "-3.12", "-m", "pip", "--version"):
            return _ok("pip 25.1\n")
        if argv[:5] == ("py", "-3.12", "-m", "venv", "--help"):
            return _ok("venv help\n")
        if argv[0] == os.fspath(venv_python) and argv[1:3] == ("-c", argv[2]):
            return _ok(
                json.dumps(
                    {
                        "version": "3.12.10",
                        "bits": 64,
                        "executable": os.fspath(venv_python),
                        "prefix": os.fspath(root / ".venv"),
                        "base_prefix": os.fspath(root.parent / "Python312"),
                        "module": os.fspath(module_path),
                    }
                )
            )
        if argv[:4] == (os.fspath(venv_python), "-m", "pip", "check"):
            return (
                _failed() if "pip-check" in controlled_failures else _ok("No broken requirements\n")
            )
        if argv[:2] == ("node", "-p"):
            version = "v23.9.0" if "node-version" in controlled_failures else "v24.1.0"
            return _ok(
                json.dumps(
                    {
                        "version": version,
                        "arch": "x64",
                        "execPath": os.fspath(root.parent / "Node" / "node.exe"),
                    }
                )
            )
        if argv == ("npm.cmd", "--version"):
            return _ok("11.1.0\n")
        if argv == ("npm.cmd", "ls", "--depth=0", "--offline", "--no-update-notifier"):
            if "npm-timeout" in controlled_failures:
                return CommandResult(returncode=124, stdout="", stderr="")
            return _failed() if "npm-ls" in controlled_failures else _ok("ok\n")
        if argv[:2] == ("node", "-e"):
            if "playwright" in controlled_failures:
                return _failed()
            return _ok(
                json.dumps(
                    {
                        "available": True,
                        "path": os.fspath(root.parent / "playwright" / "chrome.exe"),
                    }
                )
            )
        if len(argv) >= 4 and argv[:3] == (
            os.fspath(venv_python),
            "-m",
            "aiwebnovel.diagnostics.probes",
        ):
            if argv[3] == "configuration":
                return _ok(
                    json.dumps(
                        {
                            "ok": True,
                            "default_loopback": True,
                            "proxy_headers_disabled": True,
                            "trusted_hosts_safe": True,
                            "cors_safe": True,
                            "production_docs_closed": True,
                            "request_limit_valid": True,
                            "middleware_assembled": True,
                        }
                    )
                )
            if argv[3] == "cleanup":
                if "cleanup-command" in controlled_failures:
                    return _failed()
                return _ok(json.dumps({"ok": True, "cleanup": True, "root_exists": False}))
            if "storage-timeout" in controlled_failures:
                return CommandResult(returncode=124, stdout="", stderr="")
            if "storage-runner-error" in controlled_failures:
                raise OSError("controlled runner failure")
            return _ok(
                json.dumps(
                    {
                        "ok": "storage-cleanup" not in controlled_failures,
                        "formal_content_accessed": False,
                        "formal_root_unchanged": True,
                        "formal_root_exists": False,
                        "storage": True,
                        "database": True,
                        "cleanup": "storage-cleanup" not in controlled_failures,
                        "standard_directories": 12,
                    }
                )
            )
        if argv[0] == os.fspath(venv_python) and argv[1] == "-m":
            return _ok("tool version\n")
        if argv[0] == "powershell.exe":
            if any("check_security_baseline.ps1" in argument for argument in argv):
                return (
                    _failed()
                    if "security-baseline" in controlled_failures
                    else _ok("[security-baseline] passed\n")
                )
            return _ok("[hygiene] passed\n")
        return _failed()

    return handle


def _dependencies(root: Path, failures: set[str] | None = None) -> DiagnosticDependencies:
    return DiagnosticDependencies(
        command_runner=ControlledRunner(_successful_handler(root, failures)),
        platform_name=lambda: "Windows",
        platform_summary=lambda: "Windows 11 build controlled",
        port_probe=lambda _port: "ports" not in (failures or set()),
        token_factory=lambda: "d" * 32,
        environment={"LOCALAPPDATA": os.fspath(root.parent / "LocalAppData")},
    )


def test_all_twelve_checks_pass_in_stable_order_with_controlled_tools(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    context = DiagnosticContext(root, DiagnosticMode.DEVELOPMENT)

    report = run_diagnostics(context, _dependencies(root), clock_ns=lambda: 0)

    assert [check.check_id for check in report.checks] == [
        f"ENV-{number:03d}" for number in range(1, 13)
    ]
    assert all(check.status is CheckStatus.PASS for check in report.checks)
    assert report.overall_status is OverallStatus.READY


@pytest.mark.parametrize(
    ("failure", "check_id"),
    (
        ("git", "ENV-002"),
        ("python-version", "ENV-003"),
        ("pip-check", "ENV-004"),
        ("node-version", "ENV-005"),
        ("npm-ls", "ENV-005"),
        ("npm-timeout", "ENV-005"),
        ("security-baseline", "ENV-007"),
        ("storage-cleanup", "ENV-008"),
        ("cleanup-command", "ENV-008"),
        ("storage-timeout", "ENV-008"),
        ("storage-runner-error", "ENV-008"),
    ),
)
def test_controlled_tool_failures_are_not_reported_as_pass(
    tmp_path: Path,
    failure: str,
    check_id: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)

    report = run_diagnostics(
        DiagnosticContext(root, DiagnosticMode.M0),
        _dependencies(root, {failure}),
        clock_ns=lambda: 0,
    )

    matching = next(check for check in report.checks if check.check_id == check_id)
    assert matching.status is CheckStatus.FAIL
    assert report.overall_status is OverallStatus.NOT_READY


def test_local_dependency_probe_is_offline_and_timeout_remains_a_failure(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    dependencies = _dependencies(root, {"npm-timeout"})
    report = run_diagnostics(
        DiagnosticContext(root, DiagnosticMode.INTEGRATED), dependencies, clock_ns=lambda: 0
    )
    runner = dependencies.command_runner
    assert isinstance(runner, ControlledRunner)
    tree_calls = [call for call in runner.calls if call[:2] == ("npm.cmd", "ls")]
    assert tree_calls == [("npm.cmd", "ls", "--depth=0", "--offline", "--no-update-notifier")]
    check = next(check for check in report.checks if check.check_id == "ENV-005")
    assert check.status is CheckStatus.FAIL
    assert "timed out" in check.summary
    assert "Install" not in check.remediation
    assert dict(check.details) == {
        "node_exit_code": 0,
        "npm_exit_code": 0,
        "dependency_tree_exit_code": 124,
    }
    assert report.overall_status is OverallStatus.NOT_READY


@pytest.mark.parametrize(
    "failure",
    ("storage-cleanup", "storage-timeout", "storage-runner-error"),
)
def test_storage_check_always_runs_public_cleanup_after_probe_failure(
    tmp_path: Path,
    failure: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    dependencies = _dependencies(root, {failure})

    report = run_diagnostics(
        DiagnosticContext(root, DiagnosticMode.M0),
        dependencies,
        clock_ns=lambda: 0,
    )

    runner = dependencies.command_runner
    assert isinstance(runner, ControlledRunner)
    probe_calls = [
        call
        for call in runner.calls
        if len(call) >= 4 and call[1:3] == ("-m", "aiwebnovel.diagnostics.probes")
    ]
    assert [call[3] for call in probe_calls if call[3] in {"storage", "cleanup"}] == [
        "storage",
        "cleanup",
    ]
    matching = next(check for check in report.checks if check.check_id == "ENV-008")
    assert matching.status is CheckStatus.FAIL


def test_git_dirty_and_playwright_missing_follow_mode_policy(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    dependencies = _dependencies(root, {"dirty", "playwright"})

    development = run_diagnostics(
        DiagnosticContext(root, DiagnosticMode.DEVELOPMENT), dependencies, clock_ns=lambda: 0
    )
    m0 = run_diagnostics(
        DiagnosticContext(root, DiagnosticMode.M0), dependencies, clock_ns=lambda: 0
    )

    development_by_id = {check.check_id: check for check in development.checks}
    m0_by_id = {check.check_id: check for check in m0.checks}
    assert development_by_id["ENV-002"].status is CheckStatus.WARNING
    assert development_by_id["ENV-006"].status is CheckStatus.WARNING
    assert m0_by_id["ENV-002"].status is CheckStatus.FAIL
    assert m0_by_id["ENV-006"].status is CheckStatus.FAIL


def test_non_windows_never_runs_the_storage_write_probe(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    runner = ControlledRunner(_successful_handler(root))
    dependencies = DiagnosticDependencies(
        command_runner=runner,
        platform_name=lambda: "Linux",
        platform_summary=lambda: "controlled",
        port_probe=lambda _port: True,
        token_factory=lambda: "e" * 32,
        environment={},
    )
    context = DiagnosticContext(root, DiagnosticMode.DEVELOPMENT)
    os_result = check_operating_system(context, dependencies, {})
    previous = {
        "ENV-001": DiagnosticCheck(
            "ENV-001",
            "Operating system",
            os_result.status,
            os_result.summary,
            os_result.details,
            os_result.remediation,
            os_result.required,
            0,
        ),
        "ENV-004": DiagnosticCheck(
            "ENV-004",
            "Virtual environment",
            CheckStatus.PASS,
            "Controlled pass.",
            (),
            "",
            True,
            0,
        ),
    }

    storage = check_storage_and_database(context, dependencies, previous)

    assert storage.status is CheckStatus.SKIPPED
    assert not any("aiwebnovel.diagnostics.probes" in call for call in runner.calls)


def test_port_occupancy_does_not_terminate_the_listener(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        occupied_port = int(listener.getsockname()[1])
        dependencies = default_dependencies()
        context = DiagnosticContext(
            root,
            DiagnosticMode.DEVELOPMENT,
            backend_port=occupied_port,
            frontend_port=occupied_port + 1,
        )

        result = check_ports(context, dependencies, {})

        assert result.status is CheckStatus.WARNING
        details = dict(result.details)
        assert details["backend_available"] is False
        assert details["backend_port"] == occupied_port
        assert details["frontend_available"] is True
        assert details["frontend_port"] == occupied_port + 1
        assert listener.getsockname()[1] == occupied_port


def test_integrated_mode_ignores_the_unused_frontend_port(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    checked: list[int] = []

    def record_port(port: int) -> bool:
        checked.append(port)
        return True

    dependencies = _dependencies(root)
    dependencies = DiagnosticDependencies(
        command_runner=dependencies.command_runner,
        platform_name=dependencies.platform_name,
        platform_summary=dependencies.platform_summary,
        port_probe=record_port,
        token_factory=dependencies.token_factory,
        environment=dependencies.environment,
    )

    result = check_ports(
        DiagnosticContext(
            root,
            DiagnosticMode.INTEGRATED,
            backend_port=8123,
            frontend_port=5173,
        ),
        dependencies,
        {},
    )

    assert result.status is CheckStatus.PASS
    assert checked == [8123]
    details = dict(result.details)
    assert details["backend_available"] is True
    assert details["backend_port"] == 8123
    assert details["frontend_available"] is None
    assert details["frontend_port"] is None


def test_build_and_quality_tool_requirements_are_mode_specific(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    (root / "frontend" / "dist" / "index.html").unlink()
    (root / "frontend" / "node_modules" / ".bin" / "vite.cmd").unlink()
    dependencies = _dependencies(root)

    dev_build = check_frontend_build(
        DiagnosticContext(root, DiagnosticMode.DEVELOPMENT), dependencies, {}
    )
    integrated_build = check_frontend_build(
        DiagnosticContext(root, DiagnosticMode.INTEGRATED), dependencies, {}
    )
    dev_tools = check_quality_tools(
        DiagnosticContext(root, DiagnosticMode.DEVELOPMENT), dependencies, {}
    )
    m0_tools = check_quality_tools(DiagnosticContext(root, DiagnosticMode.M0), dependencies, {})

    assert dev_build.status is CheckStatus.WARNING
    assert integrated_build.status is CheckStatus.FAIL
    assert dev_tools.status is CheckStatus.WARNING
    assert m0_tools.status is CheckStatus.FAIL


def test_frontend_build_rejects_an_obvious_credential(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    (root / "frontend" / "dist" / "assets" / "app.js").write_text(
        "const key = 'sk-" + "abcdefghijklmnopqrstuvwxyz123456';\n",
        encoding="utf-8",
    )

    result = check_frontend_build(
        DiagnosticContext(root, DiagnosticMode.INTEGRATED), _dependencies(root), {}
    )

    assert result.status is CheckStatus.FAIL


@pytest.mark.parametrize("relative_path", ("assets/nested/credential.js", "metadata.txt"))
def test_frontend_build_scans_nested_and_non_asset_files(
    tmp_path: Path,
    relative_path: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    target = root / "frontend" / "dist" / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "const key = 'sk-" + "nestedcredentialabcdefghijklmnopqrstuvwxyz';\n",
        encoding="utf-8",
    )

    result = check_frontend_build(
        DiagnosticContext(root, DiagnosticMode.INTEGRATED), _dependencies(root), {}
    )

    assert result.status is CheckStatus.FAIL


@pytest.mark.parametrize(
    "unsafe_content",
    (
        "const path = 'C:" + "\\private\\artifact.txt';\n",
        "const share = '" + "\\\\controlled-host\\private-share" + "';\n",
        "Author" + "ization: Bearer " + "a" * 32 + "\n",
        "client_" + "secret=" + "b" * 32 + "\n",
        "id_" + "token=" + "d" * 32 + "\n",
        "Cook" + "ie: sid=" + "c" * 32 + "\n",
    ),
)
def test_frontend_build_rejects_paths_and_credential_categories(
    tmp_path: Path,
    unsafe_content: str,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    _create_repository(root)
    (root / "frontend" / "dist" / "assets" / "app.js").write_text(
        unsafe_content,
        encoding="utf-8",
    )

    result = check_frontend_build(
        DiagnosticContext(root, DiagnosticMode.INTEGRATED), _dependencies(root), {}
    )

    assert result.status is CheckStatus.FAIL
