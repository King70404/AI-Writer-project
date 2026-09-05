[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$DataRoot = "",
    [switch]$BuildFrontend,
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

function Assert-IntegratedTools {
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
    $npmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $nodeCommand -or $null -eq $npmCommand) {
        throw "Node.js or npm is unavailable"
    }
    & $nodeCommand.Source -e (
        "const major=Number(process.versions.node.split('.')[0]);" +
        "process.exit(major===24 && process.arch==='x64' ? 0 : 1);"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Node.js must be 64-bit major version 24"
    }
    return [pscustomobject]@{
        Python = $pythonExecutable
        Node = $nodeCommand.Source
        Npm = $npmCommand.Source
    }
}

function Invoke-IntegratedPreflight {
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
        -Mode Integrated `
        -BackendPort $Port
    $doctorExitCode = $LASTEXITCODE
    if ($doctorExitCode -ge 2) {
        throw "Integrated environment diagnostics did not pass required checks"
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
        [string]$payload.checks.security -ne "ok" -or
        [string]$payload.checks.frontend -ne "ok"
    ) {
        throw (
            "integrated readiness checks did not pass " +
            "(configuration=$($payload.checks.configuration), " +
            "application=$($payload.checks.application), " +
            "storage=$($payload.checks.storage), " +
            "database=$($payload.checks.database), " +
            "security=$($payload.checks.security), " +
            "frontend=$($payload.checks.frontend))"
        )
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
    $resolvedDataRoot = Resolve-IsolatedDataRoot `
        -Candidate $DataRoot `
        -DefaultLeaf "AIWebNovel" `
        -RepositoryRoot $repositoryRoot `
        -AllowFormalRoot
    $tools = Assert-IntegratedTools
    Assert-LoopbackPortAvailable -Port $Port
    $logDirectory = New-StartupLogDirectory
    Initialize-StartupCancellation
    $cancellationInstalled = $true

    $frontendRoot = Join-Path $repositoryRoot "frontend"
    $frontendDist = Join-Path $frontendRoot "dist"
    Assert-FrontendBuildBoundary `
        -DistPath $frontendDist `
        -RepositoryRoot $repositoryRoot
    if ($BuildFrontend) {
        $build = Start-OwnedProcess `
            -Name "integrated-build" `
            -FilePath $tools.Npm `
            -ArgumentList @("run", "build", "--", "--", "--emptyOutDir", "false") `
            -WorkingDirectory $frontendRoot `
            -LogDirectory $logDirectory
        $ownedProcesses.Add($build)
        while ($true) {
            if (Test-StartupCancellationRequested) {
                throw "frontend build was interrupted"
            }
            $build.Process.Refresh()
            if ($build.Process.HasExited) {
                break
            }
            Start-Sleep -Milliseconds 100
        }
        Complete-OwnedProcessCapture -Record $build
        if ($build.Process.ExitCode -ne 0) {
            throw "frontend build failed with exit code $($build.Process.ExitCode)"
        }
        $null = $ownedProcesses.Remove($build)
        Write-Host "frontend build: passed"
    }
    Assert-FrontendBuild `
        -DistPath $frontendDist `
        -RepositoryRoot $repositoryRoot
    Invoke-IntegratedPreflight
    $shutdownEvent = New-StartupShutdownEvent -Name $ShutdownEventName

    $backendEnvironment = @{
        AIWEBNOVEL_APP_NAME = "AIWebNovel"
        AIWEBNOVEL_APP_VERSION = "0.0.0"
        AIWEBNOVEL_ENVIRONMENT = "production"
        AIWEBNOVEL_API_PREFIX = "/api/v1"
        AIWEBNOVEL_HOST = "127.0.0.1"
        AIWEBNOVEL_PORT = $Port.ToString()
        AIWEBNOVEL_LOG_LEVEL = "WARNING"
        AIWEBNOVEL_DATA_ROOT = $resolvedDataRoot
        AIWEBNOVEL_DATABASE_URL = $null
        AIWEBNOVEL_DATABASE_ECHO = "false"
        AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS = "5000"
        AIWEBNOVEL_SERVE_FRONTEND = "true"
        AIWEBNOVEL_FRONTEND_DIST_PATH = $frontendDist
        AIWEBNOVEL_CORS_ALLOWED_ORIGINS = ('["http://127.0.0.1:{0}"]' -f $Port)
        AIWEBNOVEL_TRUSTED_HOSTS = '["127.0.0.1","localhost"]'
        AIWEBNOVEL_EXPOSE_API_DOCS = "false"
        AIWEBNOVEL_MAX_REQUEST_BODY_BYTES = "1048576"
        AIWEBNOVEL_SESSION_COOKIE_NAME = "aiwebnovel_session"
        AIWEBNOVEL_SESSION_TTL_SECONDS = "28800"
        AIWEBNOVEL_SESSION_MAX_ENTRIES = "16"
        AIWEBNOVEL_CSRF_HEADER_NAME = "X-CSRF-Token"
    }
    $databaseSetup = Start-OwnedProcess `
        -Name "integrated-database-initialization" `
        -FilePath $tools.Python `
        -ArgumentList @("scripts/initialize_integrated_database.py") `
        -WorkingDirectory $repositoryRoot `
        -LogDirectory $logDirectory `
        -EnvironmentOverrides $backendEnvironment
    $ownedProcesses.Add($databaseSetup)
    while (-not $databaseSetup.Process.HasExited) {
        if (Test-StartupCancellationRequested) {
            throw "database initialization was interrupted"
        }
        Start-Sleep -Milliseconds 100
        $databaseSetup.Process.Refresh()
    }
    Complete-OwnedProcessCapture -Record $databaseSetup
    if ($databaseSetup.Process.ExitCode -ne 0) {
        throw "database initialization failed; existing data was not reset"
    }
    $null = $ownedProcesses.Remove($databaseSetup)

    $backend = Start-OwnedProcess `
        -Name "integrated-backend" `
        -FilePath $tools.Python `
        -ArgumentList @("-m", "aiwebnovel") `
        -WorkingDirectory $repositoryRoot `
        -LogDirectory $logDirectory `
        -EnvironmentOverrides $backendEnvironment `
        -Port $Port
    $ownedProcesses.Add($backend)
    $ownedPorts.Add($Port)
    $readyContent = Wait-OwnedHttpResponse `
        -Record $backend `
        -Uri ([uri]"http://127.0.0.1:$Port/api/v1/health/ready") `
        -AcceptedStatusCodes @(200, 503)
    Assert-ReadyPayload -Content $readyContent
    $null = Wait-OwnedHttpResponse `
        -Record $backend `
        -Uri ([uri]"http://127.0.0.1:$Port/") `
        -AcceptMediaType "text/html"
    Assert-OwnedLoopbackListener -Record $backend -Port $Port

    $servicesReady = $true
    Write-Host "backend: started"
    Write-Host "frontend: served by backend"
    Write-Host "readiness check: passed"
    Write-Host "address: http://127.0.0.1:$Port"
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
    foreach ($ownedPort in $ownedPorts) {
        try {
            Wait-LoopbackPortReleased -Port $ownedPort
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
