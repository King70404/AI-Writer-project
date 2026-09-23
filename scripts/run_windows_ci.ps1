[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Default", "Full", "Stability")]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$ExpectedSha
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# This bootstrap registers the runner's interpreter. Never run it on an author's machine.
if ($env:GITHUB_ACTIONS -ne "true" -or $env:RUNNER_ENVIRONMENT -ne "github-hosted" -or $env:RUNNER_OS -ne "Windows") {
    throw "Windows CI bootstrap is restricted to ephemeral GitHub-hosted Windows runners."
}
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $repositoryRoot
$actualSha = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualSha -ne $ExpectedSha) {
    throw "Checkout does not match the exact requested candidate SHA."
}
$runnerTemp = [System.IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd("\", "/")
$evidenceRoot = [System.IO.Path]::GetFullPath($env:CI_EVIDENCE_ROOT)
if (-not $evidenceRoot.StartsWith("$runnerTemp\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "CI evidence must stay inside RUNNER_TEMP."
}
if (Test-Path -LiteralPath $evidenceRoot) {
    throw "Existing CI evidence must not be overwritten."
}
$null = New-Item -ItemType Directory -Path $evidenceRoot
$ownedRoot = Join-Path $runnerTemp ("aiwebnovel-ci-owned-" + [guid]::NewGuid().ToString("N"))
$null = New-Item -ItemType Directory -Path $ownedRoot
foreach ($directory in @("temp", "local-app-data", "browser-cache")) {
    $null = New-Item -ItemType Directory -Path (Join-Path $ownedRoot $directory)
}
$env:TEMP = Join-Path $ownedRoot "temp"
$env:TMP = $env:TEMP
$env:LOCALAPPDATA = Join-Path $ownedRoot "local-app-data"
$env:AIWEBNOVEL_DATA_ROOT = Join-Path $ownedRoot "application-data"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $ownedRoot "browser-cache"
$env:NO_COLOR = "1"
$env:CI = "true"
$metadata = [ordered]@{
    candidate_sha = $actualSha
    mode = $Mode
    event = $env:GITHUB_EVENT_NAME
    run_id = $env:GITHUB_RUN_ID
    run_attempt = $env:GITHUB_RUN_ATTEMPT
    status = "running"
    passed_steps = @()
    blocker = $null
}
$metadataPath = Join-Path $evidenceRoot "run.json"
$activeStep = "bootstrap"

function Invoke-CIStep {
    param([string]$Name, [scriptblock]$Action)
    $script:activeStep = $Name
    Write-Host "[ci] running: $Name"
    $global:LASTEXITCODE = 0
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
    $metadata.passed_steps += $Name
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metadataPath -Encoding UTF8
}

Start-Transcript -Path (Join-Path $evidenceRoot "windows-ci.log") | Out-Null
try {
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metadataPath -Encoding UTF8
    $pythonExecutable = Join-Path $env:pythonLocation "python.exe"
    Invoke-CIStep "Pinned Python interpreter" {
        & $pythonExecutable -c "import struct,sys; print(sys.version); assert sys.version_info[:3] == (3,12,10) and struct.calcsize('P') == 8"
    }
    # setup-python changes PATH, whereas environment_doctor intentionally probes py -3.12.
    # PEP 514's current-user registration makes the real launcher select the same interpreter.
    $pythonKey = "HKCU:\Software\Python\PythonCore\3.12"
    $installKey = "$pythonKey\InstallPath"
    $null = New-Item -Path $installKey -Force
    Set-Item -LiteralPath $installKey -Value $env:pythonLocation
    $null = New-ItemProperty -Path $installKey -Name ExecutablePath -Value $pythonExecutable -PropertyType String -Force
    $null = New-ItemProperty -Path $pythonKey -Name SysVersion -Value "3.12" -PropertyType String -Force
    $null = New-ItemProperty -Path $pythonKey -Name SysArchitecture -Value "64bit" -PropertyType String -Force
    Invoke-CIStep "Python launcher" {
        & py -3.12 -c "import os,struct,sys; print(sys.version); assert sys.version_info[:3] == (3,12,10) and struct.calcsize('P') == 8; assert os.path.samefile(sys.executable, sys.argv[1])" $pythonExecutable
    }
    Invoke-CIStep "Node.js 24 x64" {
        & node -e "console.log(process.version); if(process.versions.node.split('.')[0] !== '24' || process.arch !== 'x64') process.exit(1)"
    }
    Invoke-CIStep "Create repository virtual environment" { & $pythonExecutable -m venv .venv }
    $venvPython = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
    Invoke-CIStep "Install backend development dependencies" { & $venvPython -m pip install -e "./backend[dev]" }
    Push-Location (Join-Path $repositoryRoot "frontend")
    try {
        Invoke-CIStep "Install locked frontend dependencies" { & npm.cmd ci }
        if ($Mode -eq "Full") {
            Invoke-CIStep "Install Chromium" { & npm.cmd run e2e:install }
        }
    } finally {
        Pop-Location
    }

    if ($Mode -eq "Stability") {
        Invoke-CIStep "Structure stability 20+5" {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
                (Join-Path $PSScriptRoot "run_ci_stability.ps1") `
                -OutputDirectory (Join-Path $evidenceRoot "stability")
        }
    } else {
        $gateArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/quality_gate.ps1")
        if ($Mode -eq "Full") { $gateArguments += "-IncludeE2E" }
        Invoke-CIStep "$Mode quality gate" { & powershell.exe @gateArguments }
        $doctorMode = if ($Mode -eq "Full") { "M0" } else { "Development" }
        Invoke-CIStep "Environment diagnostics" {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/environment_doctor.ps1 `
                -Mode $doctorMode -Json -OutputFile (Join-Path $evidenceRoot "environment.json")
        }
    }
    Invoke-CIStep "Tracked worktree unchanged" {
        & git diff --exit-code HEAD --
    }
    if ((& git rev-parse HEAD).Trim() -ne $ExpectedSha -or $LASTEXITCODE -ne 0) {
        throw "Candidate SHA changed during CI."
    }
    $metadata.status = "passed"
} catch {
    $metadata.status = "failed"
    $metadata.blocker = "$activeStep`: $($_.Exception.Message)"
    throw
} finally {
    $metadata | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metadataPath -Encoding UTF8
    Stop-Transcript | Out-Null
    # The hosted VM owns and disposes this job's isolated data. No broad filesystem cleanup.
}
