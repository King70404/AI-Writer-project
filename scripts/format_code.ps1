[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-Formatter {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [int]$ExitCode = 1
    )

    [Console]::Error.WriteLine("[format] $Message")
    exit $ExitCode
}

function Invoke-FormatterStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host "[format] running: $Name"
    $global:LASTEXITCODE = 0
    try {
        & $Action
        $exitCode = $LASTEXITCODE
    } catch {
        [Console]::Error.WriteLine("[format] failed: $Name")
        exit 1
    }
    if ($exitCode -ne 0) {
        [Console]::Error.WriteLine(
            "[format] failed: $Name (exit code $exitCode)"
        )
        exit $exitCode
    }
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
if (-not $currentDirectory.TrimEnd("\", "/").Equals(
        $repositoryRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    Stop-Formatter -Message "run this script from the repository root"
}

$gitRootOutput = & git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) {
    Stop-Formatter -Message "current directory is not a Git repository"
}
$gitRoot = [System.IO.Path]::GetFullPath(($gitRootOutput | Select-Object -First 1))
if (-not $gitRoot.TrimEnd("\", "/").Equals(
        $repositoryRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    Stop-Formatter -Message "current directory is not the expected repository root"
}

$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    Stop-Formatter -Message "root virtual environment is missing"
}
if (-not (Test-Path -LiteralPath "frontend/node_modules" -PathType Container)) {
    Stop-Formatter -Message "frontend dependencies are missing"
}
if ($null -eq (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Stop-Formatter -Message "npm.cmd is unavailable"
}

Write-Warning (
    "This command modifies source and test files. " +
    "Review git diff before staging or committing."
)

$pythonTargets = @(
    "backend/src",
    "tests/backend",
    "tests/architecture",
    "scripts/check_backend_coverage.py"
)
$backendConfig = "backend/pyproject.toml"

Invoke-FormatterStep -Name "Ruff formatting" -Action {
    & $pythonExecutable -m ruff format `
        --config $backendConfig `
        @pythonTargets
}

Invoke-FormatterStep -Name "Ruff safe fixes" -Action {
    & $pythonExecutable -m ruff check `
        --fix `
        --config $backendConfig `
        @pythonTargets
}

Invoke-FormatterStep -Name "Prettier formatting" -Action {
    Push-Location (Join-Path $repositoryRoot "frontend")
    try {
        & npm.cmd run format
    } finally {
        Pop-Location
    }
}

Write-Host "[format] formatting finished; no files were staged or committed"
Write-Host "[format] review git diff, then run .\scripts\quality_gate.ps1"
