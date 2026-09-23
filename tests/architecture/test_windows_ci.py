"""Exercise CI orchestration failures with disposable command fixtures."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _powershell() -> str:
    executable = shutil.which("powershell.exe")
    assert executable is not None, "Windows PowerShell is required"
    return executable


def _stability_fixture(tmp_path: Path, scenario: str) -> subprocess.CompletedProcess[str]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    source = _REPOSITORY_ROOT / "scripts" / "run_ci_stability.ps1"
    shutil.copy2(source, scripts / source.name)
    vitest = tmp_path / "frontend" / "node_modules" / "vitest" / "vitest.mjs"
    vitest.parent.mkdir(parents=True)
    vitest.write_text("// Disposable command fixture, not the real test runner.\n")
    wrapper = tmp_path / "fixture.ps1"
    wrapper.write_text(
        r"""
$ErrorActionPreference = 'Stop'
$global:fixtureCalls = 0
function node {
    $global:fixtureCalls += 1
    $number = $global:fixtureCalls
    $filtered = $args -contains '--testNamePattern'
    $argumentsPath = Join-Path $env:CI_FIXTURE_ROOT 'invocations.jsonl'
    @{ number = $number; filtered = $filtered } | ConvertTo-Json -Compress |
        Add-Content -LiteralPath $argumentsPath
    $pathArgument = @($args | Where-Object { $_ -like '--outputFile.json=*' })[0]
    $jsonPath = $pathArgument.Substring('--outputFile.json='.Length)
    $passed = if ($filtered) { 8 } else { 17 }
    $pending = if ($filtered) { 9 } else { 0 }
    $global:LASTEXITCODE = 0
    if ($number -eq 2) {
        switch ($env:CI_FIXTURE_SCENARIO) {
            'native-failure' { $global:LASTEXITCODE = 23 }
            'underselected' { $passed = 1; $pending = 16 }
            'empty' { $passed = 0; $pending = 17 }
            'warning' { Write-Output 'Warning: controlled fixture diagnostic' }
            'missing-json' { return }
        }
    }
    if ($number -eq 21 -and $env:CI_FIXTURE_SCENARIO -eq 'file-skipped') {
        $passed = 16
        $pending = 1
    }
    @{
        success = $true
        numTotalTests = 17
        numPassedTests = $passed
        numPendingTests = $pending
        numFailedTests = 0
        numTodoTests = 0
    } | ConvertTo-Json | Set-Content -LiteralPath $jsonPath
    Write-Output 'Controlled command fixture completed.'
}
& (Join-Path $PSScriptRoot 'scripts/run_ci_stability.ps1') `
    -OutputDirectory (Join-Path $PSScriptRoot 'evidence')
""",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["CI_FIXTURE_ROOT"] = str(tmp_path)
    environment["CI_FIXTURE_SCENARIO"] = scenario
    return subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
        cwd=tmp_path,
        env=environment,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_stability_completes_exactly_twenty_targeted_and_five_full_runs(tmp_path: Path) -> None:
    result = _stability_fixture(tmp_path, "success")

    assert result.returncode == 0, result.stderr
    summary = json.loads((tmp_path / "evidence" / "result.json").read_text(encoding="utf-8-sig"))
    assert summary == {
        "status": "passed",
        "targeted_passes": 20,
        "file_passes": 5,
        "blocker": None,
    }
    invocations = [
        json.loads(line)
        for line in (tmp_path / "invocations.jsonl").read_text(encoding="utf-8-sig").splitlines()
    ]
    assert len(invocations) == 25
    assert [item["filtered"] for item in invocations] == [True] * 20 + [False] * 5


@pytest.mark.parametrize(
    ("scenario", "attempts", "targeted_passes"),
    [
        ("native-failure", 2, 1),
        ("underselected", 2, 1),
        ("empty", 2, 1),
        ("warning", 2, 1),
        ("missing-json", 2, 1),
        ("file-skipped", 21, 20),
    ],
)
def test_stability_stops_on_first_failed_attempt_without_retry(
    tmp_path: Path, scenario: str, attempts: int, targeted_passes: int
) -> None:
    result = _stability_fixture(tmp_path, scenario)

    assert result.returncode != 0
    summary = json.loads((tmp_path / "evidence" / "result.json").read_text(encoding="utf-8-sig"))
    assert summary["status"] == "failed"
    assert summary["targeted_passes"] == targeted_passes
    assert summary["file_passes"] == 0
    assert summary["blocker"]
    assert len((tmp_path / "invocations.jsonl").read_text().splitlines()) == attempts
    assert len(list((tmp_path / "evidence").glob("*.log"))) == attempts


@pytest.mark.parametrize("runner_environment", ["", "self-hosted"])
def test_ci_bootstrap_refuses_non_hosted_machine_before_any_setup(
    tmp_path: Path, runner_environment: str
) -> None:
    environment = os.environ.copy()
    environment.update(
        GITHUB_ACTIONS="true",
        RUNNER_ENVIRONMENT=runner_environment,
        RUNNER_OS="Windows",
        RUNNER_TEMP=str(tmp_path),
        CI_EVIDENCE_ROOT=str(tmp_path / "evidence"),
    )
    result = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_REPOSITORY_ROOT / "scripts" / "run_windows_ci.ps1"),
            "-Mode",
            "Default",
            "-ExpectedSha",
            "0" * 40,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert b"restricted to ephemeral GitHub-hosted Windows runners" in result.stderr
    assert list(tmp_path.iterdir()) == []
