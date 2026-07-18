"""Deterministic architecture tests for M0 preflight reporting and ordering."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PREFLIGHT_SCRIPT = _REPOSITORY_ROOT / "scripts" / "m0_preflight.ps1"
_CHECKLIST = _REPOSITORY_ROOT / "docs" / "M0_ACCEPTANCE_CHECKLIST.md"
_SUCCESS_CONCLUSION = "M0预验收检查通过，等待正式阶段验收。"
_FAILURE_CONCLUSION = "M0预验收检查未通过\uff1b未形成正式阶段结论。"


def _powershell() -> str:
    executable = shutil.which("powershell.exe")
    assert executable is not None, "required command is unavailable: powershell.exe"
    return executable


def _quote_powershell(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=_REPOSITORY_ROOT,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def test_m0_preflight_is_ascii_and_parses_in_windows_powershell() -> None:
    source_bytes = _PREFLIGHT_SCRIPT.read_bytes()
    assert source_bytes.isascii()

    script = _quote_powershell(str(_PREFLIGHT_SCRIPT))
    command = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile({script}, "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -ne 0) { exit 17 }; "
        f". {script}; "
        "$expected='\"M0\\u9884\\u9a8c\\u6536\\u68c0\\u67e5\\u901a\\u8fc7"
        "\\uff0c\\u7b49\\u5f85\\u6b63\\u5f0f\\u9636\\u6bb5\\u9a8c"
        "\\u6536\\u3002\"'|ConvertFrom-Json; "
        "if ($script:M0SuccessConclusion -cne $expected) { exit 18 }; "
        "$gitRoot=@(& git rev-parse --show-toplevel 2>$null)[0]; "
        "$expectedRoot=(Resolve-Path '.').Path; "
        "if (-not (Test-PathEqual -Left $gitRoot -Right $expectedRoot)) { exit 19 }"
    )

    result = _run_powershell(command)

    assert result.returncode == 0, result.stdout + result.stderr


def test_m0_preflight_keeps_the_required_order_and_invocations() -> None:
    source = _PREFLIGHT_SCRIPT.read_text(encoding="ascii")
    ordered_names = (
        "M0 environment doctor",
        "Default quality gate",
        "Dependency audit and E2E quality gate",
        "Development startup smoke",
        "Integrated startup smoke",
        "Storage and security runtime smoke",
        "Cleanup verification",
        "Git worktree verification",
        "M0 preflight report generation",
    )

    plan_source = source[source.index("$steps = @(") :]
    offsets = [plan_source.index(name) for name in ordered_names]
    assert offsets == sorted(offsets)
    assert '"-Mode", "M0", "-Json"' in source
    assert '"-BackendPort", $doctorBackendPort.ToString()' in source
    assert '"-FrontendPort", $doctorFrontendPort.ToString()' in source
    assert source.count("Get-AvailableLoopbackPort") >= 5
    assert '"-IncludeDependencyAudit", "-IncludeE2E"' in source
    for scenario_id in (
        "E2E-DEV-001",
        "E2E-DEV-002",
        "E2E-DEV-003",
        "E2E-INT-001",
        "E2E-INT-002",
        "E2E-INT-003",
        "E2E-INT-004",
        "E2E-INT-005",
        "E2E-STARTUP-001",
    ):
        assert f'"{scenario_id}"' in source
    assert "-EvidenceStartedAtUtc $qualityEvidenceStartedAtUtc" in source
    assert '"-Mode", "Development"' in source
    assert '"-Mode", "Development", "-ExerciseChildFailure"' in source
    assert '"-Mode", "Integrated"' in source
    assert "check_windows_storage.ps1" in source
    assert "check_security_runtime.ps1" in source
    assert "check_e2e_cleanup.ps1" in source
    assert "if ($failed)" in source
    assert "break" in source
    assert '"-M0Preflight"' not in source
    assert "taskkill /IM" not in source
    assert "Stop-Process -Name" not in source
    sensitive_block = source[
        source.index("$sensitiveValues = @(") : source.index(
            "try {", source.index("$sensitiveValues = @(")
        )
    ]
    assert "$env:USERNAME" not in sensitive_block


def test_quality_evidence_accepts_real_pytest_warning_summary(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    coverage_directory = repository / "frontend" / "coverage"
    coverage_directory.mkdir(parents=True)
    coverage = {
        "total": {
            metric: {"pct": value}
            for metric, value in {
                "statements": 88.95,
                "branches": 82.11,
                "functions": 97.82,
                "lines": 88.82,
            }.items()
        }
    }
    (coverage_directory / "coverage-summary.json").write_text(
        json.dumps(coverage), encoding="utf-8"
    )
    stdout = tmp_path / "quality.stdout.txt"
    stderr = tmp_path / "quality.stderr.txt"
    scenarios = (
        "E2E-DEV-001",
        "E2E-DEV-002",
        "E2E-DEV-003",
        "E2E-INT-001",
        "E2E-INT-002",
        "E2E-INT-003",
        "E2E-INT-004",
        "E2E-INT-005",
        "E2E-STARTUP-001",
    )
    stdout.write_text(
        "369 passed, 1 warning in 12.34s\n"
        "[coverage] backend: statements=90.72% branches=82.12%\n"
        " Test Files 8 passed (8)\n"
        "      Tests 29 passed (29)\n"
        + "".join(f"[e2e] passed {scenario}\n" for scenario in scenarios),
        encoding="utf-8",
    )
    stderr.write_text("", encoding="utf-8")
    script = _quote_powershell(str(_PREFLIGHT_SCRIPT))
    repository_value = _quote_powershell(str(repository))
    stdout_value = _quote_powershell(str(stdout))
    stderr_value = _quote_powershell(str(stderr))
    command = (
        f". {script}; "
        f"$capture=[pscustomobject]@{{StdoutPath={stdout_value};StderrPath={stderr_value}}}; "
        f"$evidence=Get-QualityGateEvidence -Capture $capture "
        f"-RepositoryRoot {repository_value} "
        "-EvidenceStartedAtUtc ([DateTime]::UtcNow.AddMinutes(-1)); "
        "if ($null -eq $evidence) { exit 23 }; "
        "$evidence | ConvertTo-Json -Depth 4 -Compress"
    )

    result = _run_powershell(command)

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["backend_tests_passed"] == 369
    assert evidence["frontend_tests_passed"] == 29
    assert evidence["e2e_scenarios_passed"] == 9


def test_report_safety_does_not_treat_common_username_substrings_as_secrets() -> None:
    script = _quote_powershell(str(_PREFLIGHT_SCRIPT))
    command = (
        f". {script}; "
        "$content='Backend tests passed; Development startup passed'; "
        "Assert-M0ReportContentSafe -Content $content "
        "-SensitiveValues @('C:' + [char]92 + 'Users' + [char]92 + 'test')"
    )

    result = _run_powershell(command)

    assert result.returncode == 0, result.stdout + result.stderr


def test_controlled_report_writer_emits_utf8_json_and_markdown(
    tmp_path: Path,
) -> None:
    report_directory = tmp_path / "controlled-report"
    report_directory.mkdir()
    script = _quote_powershell(str(_PREFLIGHT_SCRIPT))
    directory = _quote_powershell(str(report_directory))
    command = (
        f". {script}; "
        "$payload=[ordered]@{schema_version='1.0';overall_status='fail';"
        "conclusion=$script:M0FailureConclusion}|ConvertTo-Json; "
        "$markdown='# Controlled report' + [Environment]::NewLine + "
        "'- Conclusion: ' + $script:M0FailureConclusion; "
        f"Write-AtomicM0ReportFiles -ReportDirectory {directory} "
        "-JsonContent $payload -MarkdownContent $markdown "
        "-SensitiveValues @('controlled-canary-not-in-report')"
    )

    result = _run_powershell(command)

    assert result.returncode == 0, result.stdout + result.stderr
    json_path = report_directory / "M0_PRECHECK_REPORT.json"
    markdown_path = report_directory / "M0_PRECHECK_REPORT.md"
    assert {path.name for path in report_directory.iterdir()} == {
        json_path.name,
        markdown_path.name,
    }
    assert not json_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not markdown_path.read_bytes().startswith(b"\xef\xbb\xbf")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["overall_status"] == "fail"
    assert payload["conclusion"] == _FAILURE_CONCLUSION
    assert _SUCCESS_CONCLUSION not in markdown
    assert "controlled-canary-not-in-report" not in markdown


def test_report_writer_removes_partial_publication(tmp_path: Path) -> None:
    report_directory = tmp_path / "partial-report"
    report_directory.mkdir()
    script = _quote_powershell(str(_PREFLIGHT_SCRIPT))
    directory = _quote_powershell(str(report_directory))
    command = (
        f". {script}; "
        "$payload=[ordered]@{schema_version='1.0';overall_status='pass';"
        "conclusion=$script:M0SuccessConclusion}|ConvertTo-Json; "
        "$markdown='# Controlled report'; $script:moveCount=0; "
        "function Move-Item { [CmdletBinding()] param("
        "[string]$LiteralPath,[string]$Destination,[switch]$Force); "
        "$script:moveCount += 1; if ($script:moveCount -eq 2) { "
        "throw 'controlled second publication failure' }; "
        "Microsoft.PowerShell.Management\\Move-Item @PSBoundParameters }; "
        "$rejected=$false; try { "
        f"Write-AtomicM0ReportFiles -ReportDirectory {directory} "
        "-JsonContent $payload -MarkdownContent $markdown "
        "-SensitiveValues @('controlled-canary-not-in-report') "
        "} catch { $rejected=$true }; if (-not $rejected) { exit 21 }; "
        f"if (@(Get-ChildItem -LiteralPath {directory} -Force).Count -ne 0) {{ exit 22 }}"
    )

    result = _run_powershell(command)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not list(report_directory.iterdir())


@pytest.mark.parametrize(
    ("json_expression", "markdown_expression"),
    [
        (
            "$payload=[ordered]@{overall_status='fail';"
            "conclusion=$script:M0SuccessConclusion}|ConvertTo-Json",
            "$markdown='# Controlled failure report'",
        ),
        (
            "$payload=[ordered]@{overall_status='fail';"
            "conclusion=$script:M0FailureConclusion}|ConvertTo-Json",
            "$markdown='# Report controlled-canary-secret'",
        ),
        (
            "$payload=[ordered]@{overall_status='fail';"
            "conclusion=$script:M0FailureConclusion}|ConvertTo-Json",
            "$markdown='# Report C:' + [char]92 + 'Users' + [char]92 + 'Canary'",
        ),
        (
            "$payload=[ordered]@{overall_status='fail';"
            "conclusion=$script:M0FailureConclusion}|ConvertTo-Json",
            "$markdown='# Report Cookie=session=controlled-value'",
        ),
    ],
)
def test_report_writer_rejects_false_success_and_protected_values(
    tmp_path: Path,
    json_expression: str,
    markdown_expression: str,
) -> None:
    report_directory = tmp_path / "rejected-report"
    report_directory.mkdir()
    script = _quote_powershell(str(_PREFLIGHT_SCRIPT))
    directory = _quote_powershell(str(report_directory))
    command = (
        f". {script}; {json_expression}; {markdown_expression}; "
        f"Write-AtomicM0ReportFiles -ReportDirectory {directory} "
        "-JsonContent $payload -MarkdownContent $markdown "
        "-SensitiveValues @('controlled-canary-secret')"
    )

    result = _run_powershell(command)

    assert result.returncode != 0
    assert not list(report_directory.iterdir())


def test_m0_acceptance_checklist_is_definition_only_and_complete() -> None:
    content = _CHECKLIST.read_text(encoding="utf-8")

    for section in ("工程", "质量", "存储", "安全", "启动", "范围真实性"):
        assert f"## {section}" in content
    for field in ("验收项", "验收方法", "预期结果", "证据来源", "失败处理"):
        assert field in content
    for required_item in (
        "仓库基线",
        "Python后端",
        "SQLite和Alembic",
        "React前端",
        "前后端集成",
        "Ruff",
        "mypy",
        "ESLint",
        "Prettier",
        "后端覆盖率",
        "前端覆盖率",
        "架构边界",
        "仓库卫生",
        "E2E",
        "LocalAppData路径",
        "测试隔离",
        "数据库不在仓库",
        "重解析点",
        "访问探针",
        "环回绑定",
        "Host",
        "CORS",
        "代理头",
        "请求限制",
        "内容类型",
        "会话",
        "CSRF",
        "CSP",
        "日志脱敏",
        "production文档关闭",
        "开发模式",
        "集成模式",
        "Ctrl+C清理",
        "端口释放",
        "无残留进程",
        "没有小说业务功能",
        "没有假数据",
        "没有Codex",
        "没有安装器",
        "没有远程服务",
        "M0只代表工程底座",
    ):
        assert required_item in content
    assert "[x]" not in content.lower()
    assert "[ ]" not in content
    assert "M0\u5df2\u901a\u8fc7" not in content
    table_rows = [
        line
        for line in content.splitlines()
        if line.startswith("| ") and not line.startswith("| ---")
    ]
    assert table_rows
    assert all(len(row.split("|")[1:-1]) == 5 for row in table_rows)
