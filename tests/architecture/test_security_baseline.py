"""Controlled positive and negative tests for the tracked-source security gate."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SECURITY_SCRIPT = _REPOSITORY_ROOT / "scripts" / "check_security_baseline.ps1"
_SECURITY_AST_HELPER = _REPOSITORY_ROOT / "scripts" / "check_security_ast.py"
_QUALITY_GATE_SCRIPT = _REPOSITORY_ROOT / "scripts" / "quality_gate.ps1"


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


def _write(repository: Path, relative_path: str, content: str) -> None:
    target = repository / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _initialize_repository(repository: Path) -> None:
    repository.mkdir()
    initialization = _git(repository, "init", "--initial-branch=main")
    assert initialization.returncode == 0, initialization.stderr
    for key, value in (
        ("user.name", "AIWebNovel Security Test"),
        ("user.email", "security-test@invalid.example"),
    ):
        configuration = _git(repository, "config", key, value)
        assert configuration.returncode == 0, configuration.stderr


def _commit_all(repository: Path) -> None:
    staged = _git(repository, "add", "--all")
    assert staged.returncode == 0, staged.stderr
    committed = _git(repository, "commit", "-m", "controlled fixture")
    assert committed.returncode == 0, committed.stderr


def _install_script(repository: Path) -> Path:
    script = repository / "scripts" / _SECURITY_SCRIPT.name
    script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_SECURITY_SCRIPT, script)
    shutil.copy2(_SECURITY_AST_HELPER, script.parent / _SECURITY_AST_HELPER.name)
    return script


def _write_safe_security_wiring(repository: Path) -> None:
    _write(
        repository,
        "backend/src/aiwebnovel/core/config.py",
        "\n".join(
            (
                "class Settings:",
                '    trusted_hosts = ("127.0.0.1", "localhost")',
                "    max_request_body_bytes = 1048576",
                '    session_cookie_name = "aiwebnovel_session"',
                "    session_ttl_seconds = 28800",
                "    session_max_entries = 16",
                '    csrf_header_name = "X-CSRF-Token"',
                "    expose_api_docs = False",
                "    def apply_environment_security_defaults(self):",
                '        return self.environment in {"development", "test"}',
                "",
            )
        ),
    )
    _write(
        repository,
        "backend/src/aiwebnovel/main.py",
        "\n".join(
            (
                "def create_app(expose_api_docs):",
                '    api_prefix = "/api/v1"',
                "    application = FastAPI(",
                "        docs_url=None,",
                "        redoc_url=None,",
                '        openapi_url="/openapi.json" if expose_api_docs else None,',
                "    )",
                "    application.add_middleware(HostValidationMiddleware)",
                "    application.add_middleware(RequestLimitsMiddleware)",
                "    application.add_middleware(",
                "        CSRFMiddleware,",
                '        session_path=f"{api_prefix}/security/session",',
                "    )",
                "    application.add_middleware(SecurityHeadersMiddleware)",
                "    application.add_middleware(",
                "        CORSMiddleware,",
                '        allow_methods=["GET", "POST", "PUT", "OPTIONS"],',
                "        allow_headers=[",
                '            "Content-Type", "If-Match", "X-Request-ID", csrf_header_name,',
                "        ],",
                '        expose_headers=["X-Request-ID", "ETag", "Location"],',
                "    )",
                "    application.include_router(create_security_router())",
                "    application.state.proxy_headers_trusted = False",
                "    return application",
                "",
            )
        ),
    )
    _write(
        repository,
        "backend/src/aiwebnovel/security/csrf.py",
        'SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}\n'
        'UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}\n'
        "class CSRFMiddleware:\n    pass\n",
    )
    _write(
        repository,
        "backend/src/aiwebnovel/__main__.py",
        "\n".join(
            (
                "def main():",
                '    validate_loopback_bind_host("127.0.0.1")',
                "    uvicorn.run(",
                "        app,",
                "        proxy_headers=False,",
                "        server_header=False,",
                '        forwarded_allow_ips="",',
                "    )",
                "",
            )
        ),
    )
    _write(
        repository,
        "backend/src/aiwebnovel/safe_logging.py",
        'logger.info("csrf validation rejected")\n',
    )
    _write(
        repository,
        "backend/src/aiwebnovel/project/web/router.py",
        '@router.post("")\ndef create_project():\n    pass\n'
        '@router.put("/{project_id}")\ndef revise_project():\n    pass\n',
    )
    _write(
        repository,
        "backend/src/aiwebnovel/project/web/errors.py",
        'def safe_error(exc):\n    return {"message": "Project request failed"}\n',
    )
    _write(
        repository,
        "backend/src/aiwebnovel/project/web/dto.py",
        "class CreateProjectRequest:\n    title: str\n    description: str\n",
    )


def _run_security_script(
    repository: Path,
    *,
    script: Path,
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


def test_security_baseline_accepts_safe_tracked_wiring(tmp_path: Path) -> None:
    repository = tmp_path / "safe-security-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write_safe_security_wiring(repository)
    _commit_all(repository)

    result = _run_security_script(repository, script=script)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "[security-baseline] passed" in result.stdout


def test_security_baseline_ignores_untracked_source(tmp_path: Path) -> None:
    repository = tmp_path / "tracked-only-security-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write_safe_security_wiring(repository)
    _commit_all(repository)
    untracked_name = "backend/src/aiwebnovel/untracked_security_canary.py"
    _write(
        repository,
        untracked_name,
        'allow_origins = ["*"]\n',
    )

    result = _run_security_script(repository, script=script)
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert untracked_name not in output


def test_security_baseline_rejects_controlled_tracked_violations_without_leak(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "unsafe-security-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write_safe_security_wiring(repository)
    canary = "security" + "-canary-value-must-stay-hidden"
    _write(
        repository,
        "backend/src/aiwebnovel/unsafe_configuration.py",
        "\n".join(
            (
                "allow_origins = [",
                '    "http://localhost:5173",',
                '    "*",',
                "]",
                "allow_credentials = (",
                "    True",
                ")",
                "proxy_headers = (",
                "    True",
                ")",
                'host = "0.0.0.0"',
                f'access_token = "{canary}"',
                'trusted_hosts = ["localhost", "*"]',
                "",
            )
        ),
    )
    _write(
        repository,
        "frontend/src/unsafe-security.ts",
        "\n".join(
            (
                "localStorage.setItem(",
                '  "csrf_token",',
                "  csrfToken,",
                ");",
                "sessionStorage.csrf_token = csrfToken;",
                "console.log(",
                "  sessionCookie,",
                ");",
                "",
            )
        ),
    )
    _write(
        repository,
        "frontend/src/features/projects/api/unsafe-project-client.ts",
        "\n".join(
            (
                "console.log(requestBody);",
                "retry(() => postJson('projects', requestBody));",
                'const endpoint = "https://api.example.invalid/projects";',
                "",
            )
        ),
    )
    _write(
        repository,
        "frontend/src/features/projects/components/UnsafeProject.tsx",
        "\n".join(
            (
                "localStorage.setItem('project_cursor', cursor);",
                "const cookie = document.cookie;",
                "const header = 'X-CSRF-Token';",
                "const view = <div dangerouslySetInnerHTML={{__html: body}} />;",
                "",
            )
        ),
    )
    _write(
        repository,
        "scripts/unsafe-security.ps1",
        'Write-Output "Cookie=$sessionCookie"\n',
    )
    _commit_all(repository)

    result = _run_security_script(repository, script=script)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    for rule in (
        "wildcard-cors",
        "cors-credentials-enabled",
        "proxy-headers-trusted",
        "non-loopback-default-bind",
        "plaintext-secret",
        "csrf-browser-persistence",
        "project-cursor-browser-persistence",
        "project-request-body-log",
        "project-post-auto-retry",
        "external-frontend-api-address",
        "unsafe-project-html",
        "project-component-cookie-access",
        "project-component-hardcoded-csrf",
        "sensitive-security-log",
        "host-validation-disabled",
    ):
        assert f"type={rule}" in output
    assert canary not in output


def test_security_baseline_rejects_missing_required_wiring(tmp_path: Path) -> None:
    repository = tmp_path / "missing-security-wiring-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write(repository, "README.md", "# Controlled fixture\n")
    _commit_all(repository)

    result = _run_security_script(repository, script=script)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "type=required-security-file-not-tracked" in output
    assert "all requested local quality gates passed" not in output


def test_security_baseline_rejects_project_api_security_regressions(tmp_path: Path) -> None:
    repository = tmp_path / "unsafe-project-api-security-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write_safe_security_wiring(repository)

    csrf = repository / "backend/src/aiwebnovel/security/csrf.py"
    csrf.write_text(
        csrf.read_text(encoding="utf-8").replace(
            'SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}',
            'SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "POST"}',
        ),
        encoding="utf-8",
    )
    router = repository / "backend/src/aiwebnovel/project/web/router.py"
    router.write_text("import sqlalchemy\nCSRF_EXEMPT = 'csrf_exempt'\n", encoding="utf-8")
    _write(
        repository,
        "backend/src/aiwebnovel/project/web/errors.py",
        'def unsafe_error(exc):\n    return {"message": str(exc)}\n',
    )
    main = repository / "backend/src/aiwebnovel/main.py"
    main.write_text(
        main.read_text(encoding="utf-8").replace(
            'expose_headers=["X-Request-ID", "ETag", "Location"]',
            'expose_headers=["X-Request-ID", "Location"]',
        ),
        encoding="utf-8",
    )
    _commit_all(repository)

    result = _run_security_script(repository, script=script)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    for rule in (
        "project-write-csrf-exemption-detected",
        "project-router-direct-persistence-access",
        "project-error-exception-text-exposed",
        "project-cors-contract-missing",
    ):
        assert f"type={rule}" in output


def test_security_baseline_requires_actual_middleware_registration(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "unregistered-security-middleware-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write_safe_security_wiring(repository)
    _write(
        repository,
        "backend/src/aiwebnovel/main.py",
        "\n".join(
            (
                "def create_app():",
                "    # application.add_middleware(HostValidationMiddleware)",
                "    # application.add_middleware(RequestLimitsMiddleware)",
                "    # application.add_middleware(CSRFMiddleware)",
                "    # application.add_middleware(SecurityHeadersMiddleware)",
                '    marker = "application.include_router(create_security_router())"',
                '    proxy_marker = "application.state.proxy_headers_trusted = False"',
                '    docs_marker = "expose_api_docs docs_url redoc_url openapi_url"',
                "    return None",
                "",
            )
        ),
    )
    _commit_all(repository)

    result = _run_security_script(repository, script=script)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "type=security-middleware-not-registered" in output


def test_security_baseline_requires_production_document_default(tmp_path: Path) -> None:
    repository = tmp_path / "unsafe-document-default-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write_safe_security_wiring(repository)
    config = repository / "backend/src/aiwebnovel/core/config.py"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            'return self.environment in {"development", "test"}',
            'marker = \'self.environment in {"development", "test"}\'\n        return True',
        ),
        encoding="utf-8",
    )
    _commit_all(repository)

    result = _run_security_script(repository, script=script)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "type=production-api-docs-default-not-enforced" in output


def test_security_baseline_requires_actual_uvicorn_security_options(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "unsafe-uvicorn-options-repository"
    _initialize_repository(repository)
    script = _install_script(repository)
    _write_safe_security_wiring(repository)
    _write(
        repository,
        "backend/src/aiwebnovel/__main__.py",
        "\n".join(
            (
                "def main():",
                '    validate_loopback_bind_host("127.0.0.1")',
                "    # uvicorn.run(app, proxy_headers=False, server_header=False)",
                "    marker = 'forwarded_allow_ips=\"\"'",
                "",
            )
        ),
    )
    _commit_all(repository)

    result = _run_security_script(repository, script=script)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "type=uvicorn-security-options-not-enforced" in output


def test_default_quality_gate_runs_security_before_python_checks() -> None:
    source = _QUALITY_GATE_SCRIPT.read_text(encoding="utf-8")

    hygiene = source.index('-Name "Repository hygiene"')
    security = source.index('-Name "Security baseline"')
    ruff = source.index('-Name "Ruff format check"')
    audit = source.index("if ($IncludeDependencyAudit)")

    assert hygiene < security < ruff < audit
    assert "check_security_baseline.ps1" in source
