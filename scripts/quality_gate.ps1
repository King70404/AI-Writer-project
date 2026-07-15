[CmdletBinding()]
param(
    [switch]$IncludeDependencyAudit,
    [switch]$IncludeE2E
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-QualityGate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [int]$ExitCode = 1
    )

    [Console]::Error.WriteLine("[quality] $Message")
    exit $ExitCode
}

function Invoke-QualityGateStep {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host "[quality] running: $Name"
    $global:LASTEXITCODE = 0
    try {
        & $Action
        $exitCode = $LASTEXITCODE
    } catch {
        [Console]::Error.WriteLine("[quality] failed: $Name")
        exit 1
    }

    if ($exitCode -ne 0) {
        [Console]::Error.WriteLine(
            "[quality] failed: $Name (exit code $exitCode)"
        )
        exit $exitCode
    }

    Write-Host "[quality] passed: $Name"
}

function Assert-QualityGateEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,
        [Parameter(Mandatory = $true)]
        [string]$PythonExecutable
    )

    foreach ($command in @("git", "node", "npm.cmd", "powershell.exe")) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
            Stop-QualityGate -Message "required command is unavailable: $command"
        }
    }

    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
        Stop-QualityGate -Message "root virtual environment is missing"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot "frontend/node_modules") -PathType Container)) {
        Stop-QualityGate -Message "frontend dependencies are missing"
    }

    & $PythonExecutable -c (
        "import struct, sys; " +
        "raise SystemExit(0 if sys.version_info[:2] == (3, 12) " +
        "and struct.calcsize('P') * 8 == 64 else 1)"
    )
    if ($LASTEXITCODE -ne 0) {
        Stop-QualityGate -Message "the virtual environment must use 64-bit Python 3.12"
    }

    & node -e (
        "const major=Number(process.versions.node.split('.')[0]);" +
        "process.exit(major===24 && process.arch==='x64' ? 0 : 1);"
    )
    if ($LASTEXITCODE -ne 0) {
        Stop-QualityGate -Message "Node.js must be 64-bit major version 24"
    }
}

function Invoke-QualityGate {
    $repositoryRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot "..")
    )
    $currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
    if (-not $currentDirectory.TrimEnd("\", "/").Equals(
            $repositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-QualityGate -Message "run this script from the repository root"
    }

    $gitRootOutput = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0) {
        Stop-QualityGate -Message "current directory is not a Git repository"
    }
    $gitRoot = [System.IO.Path]::GetFullPath(
        ($gitRootOutput | Select-Object -First 1)
    )
    if (-not $gitRoot.TrimEnd("\", "/").Equals(
            $repositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-QualityGate -Message "current directory is not the expected repository root"
    }

    $pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
    Assert-QualityGateEnvironment `
        -RepositoryRoot $repositoryRoot `
        -PythonExecutable $pythonExecutable

    $pythonTargets = @(
        "backend/src",
        "tests/backend",
        "tests/architecture",
        "scripts/check_backend_coverage.py",
        "scripts/check_security_ast.py"
    )
    $backendConfig = "backend/pyproject.toml"
    $coverageReport = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) "aiwebnovel-backend-coverage-$PID-$([guid]::NewGuid().ToString('N')).json"
    $coverageData = "$coverageReport.data"

    Invoke-QualityGateStep -Name "Git difference whitespace check" -Action {
        & git diff --check HEAD --
    }

    Invoke-QualityGateStep -Name "Repository hygiene" -Action {
        & powershell.exe `
            -NoProfile `
            -ExecutionPolicy Bypass `
            -File (Join-Path $PSScriptRoot "check_repository_hygiene.ps1") `
            -RepositoryRoot $repositoryRoot
    }

    Invoke-QualityGateStep -Name "Security baseline" -Action {
        & powershell.exe `
            -NoProfile `
            -ExecutionPolicy Bypass `
            -File (Join-Path $PSScriptRoot "check_security_baseline.ps1") `
            -RepositoryRoot $repositoryRoot
    }

    Invoke-QualityGateStep -Name "Ruff format check" -Action {
        & $pythonExecutable -m ruff format --check `
            --config $backendConfig `
            @pythonTargets
    }

    Invoke-QualityGateStep -Name "Ruff static rules" -Action {
        & $pythonExecutable -m ruff check `
            --config $backendConfig `
            @pythonTargets
    }

    Invoke-QualityGateStep -Name "mypy" -Action {
        & $pythonExecutable -m mypy `
            --config-file $backendConfig `
            backend/src/aiwebnovel
    }

    Invoke-QualityGateStep -Name "Backend tests and coverage" -Action {
        $coverageExitCode = 0
        $previousCoverageFile = [Environment]::GetEnvironmentVariable(
            "COVERAGE_FILE",
            "Process"
        )
        try {
            [Environment]::SetEnvironmentVariable(
                "COVERAGE_FILE",
                $coverageData,
                "Process"
            )
            & $pythonExecutable -m pytest `
                tests/backend `
                tests/architecture `
                --cov=aiwebnovel `
                --cov-branch `
                --cov-config=$backendConfig `
                --cov-report=term-missing `
                --cov-report="json:$coverageReport" `
                --cov-fail-under=0
            $coverageExitCode = $LASTEXITCODE
            if ($coverageExitCode -eq 0) {
                & $pythonExecutable `
                    (Join-Path $PSScriptRoot "check_backend_coverage.py") `
                    $coverageReport
                $coverageExitCode = $LASTEXITCODE
            }
        } finally {
            Remove-Item -LiteralPath $coverageReport -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $coverageData -Force -ErrorAction SilentlyContinue
            [Environment]::SetEnvironmentVariable(
                "COVERAGE_FILE",
                $previousCoverageFile,
                "Process"
            )
        }
        $global:LASTEXITCODE = $coverageExitCode
    }

    Invoke-QualityGateStep -Name "Python dependency integrity" -Action {
        & $pythonExecutable -m pip check
    }

    Invoke-QualityGateStep -Name "Frontend quality" -Action {
        Push-Location (Join-Path $repositoryRoot "frontend")
        try {
            & npm.cmd run quality
        } finally {
            Pop-Location
        }
    }

    Invoke-QualityGateStep -Name "Frontend dependency integrity" -Action {
        Push-Location (Join-Path $repositoryRoot "frontend")
        try {
            & npm.cmd ls --depth=0
        } finally {
            Pop-Location
        }
    }

    if ($IncludeDependencyAudit) {
        Invoke-QualityGateStep -Name "Frontend production dependency audit" -Action {
            Push-Location (Join-Path $repositoryRoot "frontend")
            try {
                & npm.cmd audit --omit=dev
            } finally {
                Pop-Location
            }
        }
    }

    if ($IncludeE2E) {
        Invoke-QualityGateStep -Name "Playwright Chromium availability" -Action {
            Push-Location (Join-Path $repositoryRoot "frontend")
            try {
                & node -e (
                    "const fs=require('node:fs');" +
                    "const {chromium}=require('@playwright/test');" +
                    "process.exit(fs.existsSync(chromium.executablePath())?0:1);"
                )
                if ($LASTEXITCODE -ne 0) {
                    [Console]::Error.WriteLine(
                        "[quality] Playwright Chromium is missing; " +
                        "run 'Set-Location frontend; npm run e2e:install'"
                    )
                }
            } finally {
                Pop-Location
            }
        }

        Invoke-QualityGateStep -Name "Browser end-to-end tests" -Action {
            Push-Location (Join-Path $repositoryRoot "frontend")
            try {
                & npm.cmd run e2e
            } finally {
                Pop-Location
            }
        }

        Invoke-QualityGateStep -Name "E2E cleanup verification" -Action {
            & powershell.exe `
                -NoProfile `
                -ExecutionPolicy Bypass `
                -File (Join-Path $PSScriptRoot "check_e2e_cleanup.ps1")
        }
    }

    Write-Host "[quality] all requested local quality gates passed"
}

if ($MyInvocation.InvocationName -ne ".") {
    Invoke-QualityGate
}
