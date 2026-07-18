[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173,
    [string]$DataRoot = "",
    [switch]$NoPreflight,
    [Parameter(DontShow = $true)]
    [string]$ShutdownEventName = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
. (Join-Path $PSScriptRoot "invoke_owned_process.ps1")

function Assert-RepositoryRootInvocation {
    $currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
    if (-not $currentDirectory.TrimEnd("\", "/").Equals(
            $repositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "run this script from the repository root"
    }
    $gitPrefix = & git rev-parse --show-prefix 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "current directory is not a Git repository"
    }
    if (-not [string]::IsNullOrWhiteSpace(($gitPrefix -join ""))) {
        throw "current directory is not the expected repository root"
    }
}

function Assert-DevelopmentTools {
    $pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw "root virtual environment is unavailable"
    }
    & $pythonExecutable -c (
        "import struct, sys; " +
        "raise SystemExit(0 if sys.version_info[:3] == (3, 12, 10) " +
        "and struct.calcsize('P') * 8 == 64 else 1)"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "root virtual environment must use 64-bit Python 3.12.10"
    }

    $nodeCommand = Get-Command "node.exe" -ErrorAction SilentlyContinue
    if ($null -eq $nodeCommand) {
        throw "Node.js is unavailable"
    }
    & $nodeCommand.Source -e (
        "const major=Number(process.versions.node.split('.')[0]);" +
        "process.exit(major===24 && process.arch==='x64' ? 0 : 1);"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Node.js must be 64-bit major version 24"
    }

    $viteCli = Join-Path $repositoryRoot "frontend/node_modules/vite/bin/vite.js"
    if (-not (Test-Path -LiteralPath $viteCli -PathType Leaf)) {
        throw "local Vite is unavailable"
    }
    return [pscustomobject]@{
        Python = $pythonExecutable
        Node = $nodeCommand.Source
        Vite = $viteCli
    }
}

function Invoke-DevelopmentPreflight {
    if ($NoPreflight) {
        Write-Host "environment check: skipped by explicit -NoPreflight"
        return
    }
    $doctor = Join-Path $PSScriptRoot "environment_doctor.ps1"
    if (-not (Test-Path -LiteralPath $doctor -PathType Leaf)) {
        throw "environment diagnostics command is unavailable"
    }
    & powershell.exe `
        -NoProfile `
        -NonInteractive `
        -ExecutionPolicy Bypass `
        -File $doctor `
        -Mode Development `
        -BackendPort $BackendPort `
        -FrontendPort $FrontendPort
    $doctorExitCode = $LASTEXITCODE
    if ($doctorExitCode -ge 2) {
        throw "Development environment diagnostics did not pass required checks"
    }
    if ($doctorExitCode -eq 1) {
        Write-Host "environment check: passed with warnings"
    } else {
        Write-Host "environment check: passed"
    }
}

function Assert-ReadyPayload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    try {
        $payload = $Content | ConvertFrom-Json
    } catch {
        throw "backend readiness response was not valid JSON"
    }
    if (
        [string]$payload.status -ne "ready" -or
        [string]$payload.checks.storage -ne "ok" -or
        [string]$payload.checks.database -ne "ok" -or
        [string]$payload.checks.security -ne "ok"
    ) {
        throw "backend readiness checks did not pass"
    }
}

$ownedProcesses = [System.Collections.Generic.List[object]]::new()
$ownedPorts = [System.Collections.Generic.List[int]]::new()
$logDirectory = $null
$shutdownEvent = $null
$cancellationInstalled = $false
$servicesReady = $false
$runFailure = $null
$cleanupFailure = $null
$exitCode = 1
$resolvedDataRoot = $null

try {
    Assert-RepositoryRootInvocation
    if ($BackendPort -eq $FrontendPort) {
        throw "backend and frontend ports must be different"
    }
    $resolvedDataRoot = Resolve-IsolatedDataRoot `
        -Candidate $DataRoot `
        -DefaultLeaf "AIWebNovel-Development" `
        -RepositoryRoot $repositoryRoot
    $tools = Assert-DevelopmentTools
    Assert-LoopbackPortAvailable -Port $BackendPort
    Assert-LoopbackPortAvailable -Port $FrontendPort
    Invoke-DevelopmentPreflight

    $logDirectory = New-StartupLogDirectory
    Initialize-StartupCancellation
    $cancellationInstalled = $true
    $shutdownEvent = New-StartupShutdownEvent -Name $ShutdownEventName

    $backendEnvironment = @{
        AIWEBNOVEL_APP_NAME = "AIWebNovel"
        AIWEBNOVEL_APP_VERSION = "0.0.0"
        AIWEBNOVEL_ENVIRONMENT = "development"
        AIWEBNOVEL_API_PREFIX = "/api/v1"
        AIWEBNOVEL_HOST = "127.0.0.1"
        AIWEBNOVEL_PORT = $BackendPort.ToString()
        AIWEBNOVEL_LOG_LEVEL = "WARNING"
        AIWEBNOVEL_DATA_ROOT = $resolvedDataRoot
        AIWEBNOVEL_DATABASE_URL = $null
        AIWEBNOVEL_DATABASE_ECHO = "false"
        AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS = "5000"
        AIWEBNOVEL_SERVE_FRONTEND = "false"
        AIWEBNOVEL_FRONTEND_DIST_PATH = (Join-Path $repositoryRoot "frontend/dist")
        AIWEBNOVEL_CORS_ALLOWED_ORIGINS = (
            '["http://127.0.0.1:{0}"]' -f $FrontendPort
        )
        AIWEBNOVEL_TRUSTED_HOSTS = '["127.0.0.1","localhost"]'
        AIWEBNOVEL_EXPOSE_API_DOCS = "true"
        AIWEBNOVEL_MAX_REQUEST_BODY_BYTES = "1048576"
        AIWEBNOVEL_SESSION_COOKIE_NAME = "aiwebnovel_session"
        AIWEBNOVEL_SESSION_TTL_SECONDS = "28800"
        AIWEBNOVEL_SESSION_MAX_ENTRIES = "16"
        AIWEBNOVEL_CSRF_HEADER_NAME = "X-CSRF-Token"
    }
    $backend = Start-OwnedProcess `
        -Name "development-backend" `
        -FilePath $tools.Python `
        -ArgumentList @("-m", "aiwebnovel") `
        -WorkingDirectory $repositoryRoot `
        -LogDirectory $logDirectory `
        -EnvironmentOverrides $backendEnvironment `
        -Port $BackendPort
    $ownedProcesses.Add($backend)
    $ownedPorts.Add($BackendPort)
    $readyContent = Wait-OwnedHttpResponse `
        -Record $backend `
        -Uri ([uri]"http://127.0.0.1:$BackendPort/api/v1/health/ready")
    Assert-ReadyPayload -Content $readyContent
    Assert-OwnedLoopbackListener -Record $backend -Port $BackendPort
    Write-Host "backend: started"

    $frontendEnvironment = @{
        AIWEBNOVEL_DATA_ROOT = $null
        AIWEBNOVEL_DATABASE_URL = $null
        AIWEBNOVEL_VITE_BACKEND_URL = "http://127.0.0.1:$BackendPort"
        VITE_API_BASE_URL = "/api/v1"
        NODE_ENV = "development"
    }
    $frontendRoot = Join-Path $repositoryRoot "frontend"
    $vite = Start-OwnedProcess `
        -Name "development-vite" `
        -FilePath $tools.Node `
        -ArgumentList @(
            "node_modules/vite/bin/vite.js",
            "--host",
            "127.0.0.1",
            "--port",
            $FrontendPort.ToString(),
            "--strictPort"
        ) `
        -WorkingDirectory $frontendRoot `
        -LogDirectory $logDirectory `
        -EnvironmentOverrides $frontendEnvironment `
        -Port $FrontendPort
    $ownedProcesses.Add($vite)
    $ownedPorts.Add($FrontendPort)
    $null = Wait-OwnedHttpResponse `
        -Record $vite `
        -Uri ([uri]"http://127.0.0.1:$FrontendPort/") `
        -AcceptMediaType "text/html"
    Assert-OwnedLoopbackListener -Record $vite -Port $FrontendPort

    $servicesReady = $true
    Write-Host "frontend: started"
    Write-Host "readiness check: passed"
    Write-Host "address: http://127.0.0.1:$FrontendPort"
    Write-Host "press Ctrl+C to stop"

    while ($true) {
        if (Test-StartupCancellationRequested) {
            break
        }
        if ($null -ne $shutdownEvent -and $shutdownEvent.WaitOne(100)) {
            break
        }
        foreach ($record in $ownedProcesses) {
            $state = Get-OwnedProcessState -Record $record
            if ($state -ne "owned") {
                throw "$($record.Name) exited or lost its recorded identity"
            }
        }
        if ($null -eq $shutdownEvent) {
            Start-Sleep -Milliseconds 100
        }
    }
    $exitCode = 0
} catch [System.Management.Automation.PipelineStoppedException] {
    $runFailure = if ($servicesReady) {
        $null
    } else {
        "startup was interrupted before readiness"
    }
    if ($servicesReady) {
        $exitCode = 0
    }
} catch {
    $runFailure = ConvertTo-StartupSafeText `
        -Value $_.Exception.Message `
        -ProtectedPaths @($repositoryRoot, $resolvedDataRoot, $logDirectory)
} finally {
    $cleanupIssues = [System.Collections.Generic.List[string]]::new()
    try {
        Stop-OwnedProcessGroup -Records $ownedProcesses.ToArray()
    } catch {
        $cleanupIssues.Add($_.Exception.Message)
    }
    foreach ($port in $ownedPorts) {
        try {
            Wait-LoopbackPortReleased -Port $port
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    if ($null -ne $runFailure -and $ownedProcesses.Count -gt 0) {
        Write-LimitedOwnedProcessDiagnostics `
            -Records $ownedProcesses.ToArray() `
            -ProtectedPaths @($repositoryRoot, $resolvedDataRoot, $logDirectory)
    }
    if ($null -ne $shutdownEvent) {
        $shutdownEvent.Dispose()
    }
    if ($cancellationInstalled) {
        Close-StartupCancellation
    }
    if ($cleanupIssues.Count -eq 0 -and $null -ne $logDirectory) {
        try {
            Remove-StartupLogDirectory -Path $logDirectory
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    if ($cleanupIssues.Count -gt 0) {
        $cleanupFailure = $cleanupIssues -join "; "
        $exitCode = 1
    }
}

if ($null -ne $runFailure) {
    [Console]::Error.WriteLine("[startup] failed: $runFailure")
    $exitCode = 1
}
if ($null -ne $cleanupFailure) {
    $safeCleanup = ConvertTo-StartupSafeText `
        -Value $cleanupFailure `
        -ProtectedPaths @($repositoryRoot, $resolvedDataRoot, $logDirectory)
    [Console]::Error.WriteLine("[startup] cleanup failed: $safeCleanup")
}
exit $exitCode
