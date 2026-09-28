"""Exercise the E2E runner's real process capture and Windows file lifetime."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _quote(value: str | Path) -> str:
    return str(value).replace("'", "''")


@pytest.mark.parametrize("already_exited", [False, True], ids=["terminated", "natural-exit"])
def test_e2e_service_cleanup_drains_output_and_releases_log_files(
    tmp_path: Path, already_exited: bool
) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    run_directory = tmp_path / "isolated run with spaces"
    run_directory.mkdir()
    launcher = run_directory / "controlled service.ps1"
    launcher.write_text(
        """param([string]$Service, [int]$Port, [string]$ProcessManifestPath, [string]$DataRoot)
$ErrorActionPreference = 'Stop'
$release = [System.Threading.EventWaitHandle]::OpenExisting("Local\\AIWebNovel-E2ECapture-$Port")
try {
    [Console]::Out.Write(('o' * 131072) + 'stdout-complete')
    [Console]::Error.Write(('e' * 131072) + 'stderr-complete')
    $process = Get-Process -Id $PID
    @{
        process_id = $PID
        started_at_utc_ticks = $process.StartTime.ToUniversalTime().Ticks
        data_root = $DataRoot
    } | ConvertTo-Json | Set-Content -LiteralPath $ProcessManifestPath -Encoding UTF8
    if (-not $release.WaitOne(30000)) { throw 'controlled service was not stopped' }
} finally { $release.Dispose() }
""",
        encoding="utf-8",
    )
    command = f"""
$ErrorActionPreference = 'Stop'
. '{_quote(_REPOSITORY_ROOT / "scripts/invoke_owned_process.ps1")}'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '{_quote(_REPOSITORY_ROOT / "scripts/run_e2e.ps1")}', [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) {{ throw 'E2E runner has parse errors' }}
# Load production function bodies without invoking the full browser suite.
foreach ($name in @('Assert-PortAvailable', 'Start-OwnedService', 'Stop-OwnedServiceTree')) {{
    $definition = $ast.Find({{
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $name
    }}, $false)
    if ($null -eq $definition) {{ throw 'production function is missing' }}
    . ([scriptblock]::Create($definition.Extent.Text))
}}
$script:RepositoryRoot = '{_quote(_REPOSITORY_ROOT)}'
$script:ServiceLauncher = '{_quote(launcher)}'
$script:OwnedProcesses = [System.Collections.Generic.List[object]]::new()
$script:OwnedPorts = [System.Collections.Generic.HashSet[int]]::new()
$port = Get-TemporaryLoopbackPort
$release = [System.Threading.EventWaitHandle]::new(
    $false, [System.Threading.EventResetMode]::ManualReset, "Local\\AIWebNovel-E2ECapture-$port")
$record = $null
try {{
    $record = Start-OwnedService -Service Backend -Name capture-regression -Port $port `
        -RunDirectory '{_quote(run_directory)}' -DataRoot '{_quote(run_directory / "data root")}'
    $manifest = Get-Content -LiteralPath $record.ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.data_root -ne '{_quote(run_directory / "data root")}') {{
        throw 'space-containing service arguments did not round-trip'
    }}
    if (${str(already_exited).lower()}) {{
        $null = $release.Set()
        if (-not $record.Process.WaitForExit(5000)) {{ throw 'controlled service did not exit' }}
    }}
    Stop-OwnedServiceTree -Record $record
    if (-not $record.Capture.CaptureCompleted) {{ throw 'output capture was not finalized' }}
    if ((Get-OwnedProcessState -Record $record.Capture) -ne 'absent') {{
        throw 'owned service is still running'
    }}
    foreach ($stream in @(
        @{{ Path = $record.StdoutPath; Expected = ('o' * 131072) + 'stdout-complete' }},
        @{{ Path = $record.StderrPath; Expected = ('e' * 131072) + 'stderr-complete' }}
    )) {{
        if ([System.IO.File]::ReadAllText($stream.Path) -ne $stream.Expected) {{
            throw 'captured output was truncated'
        }}
        # A single immediate exclusive open and removal exposes live capture handles.
        $exclusive = [System.IO.File]::Open(
            $stream.Path, [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        $exclusive.Dispose()
        [System.IO.File]::Delete($stream.Path)
        if (Test-Path -LiteralPath $stream.Path) {{ throw 'captured log could not be removed' }}
    }}
    Write-Output 'captured-output-released'
}} finally {{
    $null = $release.Set()
    foreach ($owned in $script:OwnedProcesses) {{ Stop-OwnedServiceTree -Record $owned }}
    $release.Dispose()
}}
"""
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    assert "captured-output-released" in result.stdout
