[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 18123
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-FullyQualifiedWindowsPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if (
        [string]::IsNullOrWhiteSpace($Value) -or
        $Value.IndexOf([char]0) -ge 0 -or
        $Value.StartsWith('\\?\') -or
        $Value.StartsWith('\\.\')
    ) {
        return $false
    }
    return (
        $Value -match '^[A-Za-z]:[\\/]' -or
        $Value -match '^\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)'
    )
}

function Test-LoopbackPortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidatePort
    )

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $CandidatePort
    )
    try {
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Wait-LoopbackPortReleased {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidatePort,
        [int]$TimeoutSeconds = 10
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (Test-LoopbackPortAvailable -CandidatePort $CandidatePort) {
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "owned smoke-test port was not released"
}

function Test-ProcessDescendsFrom {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidateProcessId,
        [Parameter(Mandatory = $true)]
        [int]$AncestorProcessId
    )

    for ($depth = 0; $depth -lt 32 -and $CandidateProcessId -gt 0; $depth++) {
        if ($CandidateProcessId -eq $AncestorProcessId) {
            return $true
        }
        $processRecord = Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId = $CandidateProcessId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $processRecord) {
            return $false
        }
        $CandidateProcessId = [int]$processRecord.ParentProcessId
    }
    return $false
}

function Get-OwnedListenerProcess {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidatePort,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Launcher
    )

    $listeners = @(
        Get-NetTCPConnection `
            -State Listen `
            -LocalAddress "127.0.0.1" `
            -LocalPort $CandidatePort `
            -ErrorAction SilentlyContinue
    )
    if ($listeners.Count -ne 1) {
        throw "smoke-test service does not own exactly one loopback listener"
    }

    $listenerProcessId = [int]$listeners[0].OwningProcess
    if (-not (Test-ProcessDescendsFrom `
            -CandidateProcessId $listenerProcessId `
            -AncestorProcessId $Launcher.Id)) {
        throw "loopback listener is not owned by the smoke-test process tree"
    }

    $listenerProcess = Get-Process `
        -Id $listenerProcessId `
        -ErrorAction Stop
    return [pscustomobject]@{
        ProcessId = $listenerProcessId
        StartedAtUtcTicks = $listenerProcess.StartTime.ToUniversalTime().Ticks
    }
}

function Stop-OwnedProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$OwnedProcessId,
        [Parameter(Mandatory = $true)]
        [long]$StartedAtUtcTicks
    )

    $current = Get-Process -Id $OwnedProcessId -ErrorAction SilentlyContinue
    if ($null -eq $current) {
        return
    }
    if ($current.StartTime.ToUniversalTime().Ticks -ne $StartedAtUtcTicks) {
        throw "refusing to stop a reused process identifier"
    }

    & taskkill.exe /PID $OwnedProcessId /T /F 2>$null | Out-Null
    $taskkillExitCode = $LASTEXITCODE
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        if ($null -eq (Get-Process -Id $OwnedProcessId -ErrorAction SilentlyContinue)) {
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "failed to stop an owned smoke-test process (exit code $taskkillExitCode)"
}

function Assert-DirectOwnedSmokeRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedParent,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedLeaf
    )

    if ($ExpectedLeaf -notmatch '^AIWebNovel-DEV-0\.8-[0-9a-f]{32}$') {
        throw "smoke-test root name is not recognized"
    }
    $fullCandidate = [System.IO.Path]::GetFullPath($Candidate).TrimEnd("\", "/")
    $fullParent = [System.IO.Path]::GetFullPath($ExpectedParent).TrimEnd("\", "/")
    $candidateParent = [System.IO.Path]::GetDirectoryName($fullCandidate)
    $candidateLeaf = [System.IO.Path]::GetFileName($fullCandidate)
    if (-not $candidateParent.Equals(
            $fullParent,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "smoke-test root must be a direct child of its controlled parent"
    }
    if (-not $candidateLeaf.Equals(
            $ExpectedLeaf,
            [System.StringComparison]::Ordinal
        )) {
        throw "smoke-test root identity changed"
    }
}

function Assert-NoReparsePointsInTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    if (-not (Test-Path -LiteralPath $Root)) {
        return
    }
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($Root)
    while ($pending.Count -gt 0) {
        $currentPath = $pending.Pop()
        $currentItem = Get-Item -LiteralPath $currentPath -Force
        if (($currentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "refusing to traverse or remove a reparse point"
        }
        if (-not $currentItem.PSIsContainer) {
            continue
        }
        foreach ($child in Get-ChildItem -LiteralPath $currentPath -Force) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "refusing to traverse or remove a reparse point"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
            }
        }
    }
}

function Assert-StandardStorageDirectories {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root
    )

    $relativeDirectories = @(
        "",
        "data",
        "assets",
        "runtime",
        "runtime/app",
        "runtime/temp",
        "runtime/locks",
        "models",
        "backups",
        "exports",
        "logs",
        "config"
    )
    foreach ($relativeDirectory in $relativeDirectories) {
        $candidate = if ([string]::IsNullOrEmpty($relativeDirectory)) {
            $Root
        } else {
            Join-Path $Root $relativeDirectory
        }
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            throw "one or more standard storage directories are missing"
        }
        $item = Get-Item -LiteralPath $candidate -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "a standard storage directory is a reparse point"
        }
    }
    return $relativeDirectories.Count
}

function Wait-SmokeEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Launcher,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $Launcher.Refresh()
        if ($Launcher.HasExited) {
            throw "smoke-test service exited before becoming ready"
        }
        try {
            $response = Invoke-WebRequest `
                -Uri $Url `
                -UseBasicParsing `
                -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return $response
            }
        } catch {
            # The service can refuse connections or return 503 during startup.
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "smoke-test endpoint did not become ready"
}

function ConvertTo-SafeDiagnostic {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Message,
        [Parameter(Mandatory = $true)]
        [string[]]$SensitivePaths
    )

    $safe = $Message
    foreach ($sensitivePath in $SensitivePaths) {
        if (-not [string]::IsNullOrWhiteSpace($sensitivePath)) {
            $safe = [regex]::Replace(
                $safe,
                [regex]::Escape($sensitivePath),
                "<local-path>",
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($env:USERNAME)) {
        $safe = [regex]::Replace(
            $safe,
            [regex]::Escape($env:USERNAME),
            "<user>",
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }
    $safe = [regex]::Replace($safe, '(?i)\b[A-Z]:[\\/][^\r\n]+', '<local-path>')
    if ($safe.Length -gt 500) {
        return $safe.Substring(0, 500) + "..."
    }
    return $safe
}

function Write-SafeServiceDiagnostics {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$CapturePaths,
        [Parameter(Mandatory = $true)]
        [string[]]$SensitivePaths
    )

    foreach ($capturePath in $CapturePaths) {
        if (-not (Test-Path -LiteralPath $capturePath -PathType Leaf)) {
            continue
        }
        foreach ($line in Get-Content -LiteralPath $capturePath -Tail 8 -ErrorAction SilentlyContinue) {
            $safeLine = ConvertTo-SafeDiagnostic `
                -Message $line `
                -SensitivePaths $SensitivePaths
            if (-not [string]::IsNullOrWhiteSpace($safeLine)) {
                [Console]::Error.WriteLine("[storage-smoke] service: $safeLine")
            }
        }
    }
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    [Console]::Error.WriteLine("[storage-smoke] failed: Windows is required")
    exit 1
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
if (-not $currentDirectory.TrimEnd("\", "/").Equals(
        $repositoryRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    [Console]::Error.WriteLine(
        "[storage-smoke] failed: run this script from the repository root"
    )
    exit 1
}

$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    [Console]::Error.WriteLine("[storage-smoke] failed: root virtual environment is missing")
    exit 1
}
if (-not (Test-LoopbackPortAvailable -CandidatePort $Port)) {
    [Console]::Error.WriteLine(
        "[storage-smoke] failed: the dedicated loopback port is already in use"
    )
    exit 1
}

$localAppDataValue = [Environment]::GetEnvironmentVariable("LOCALAPPDATA", "Process")
if (
    [string]::IsNullOrWhiteSpace($localAppDataValue) -or
    -not (Test-FullyQualifiedWindowsPath -Value $localAppDataValue)
) {
    [Console]::Error.WriteLine("[storage-smoke] failed: LOCALAPPDATA is unavailable or invalid")
    exit 1
}
try {
    $localAppData = [System.IO.Path]::GetFullPath($localAppDataValue).TrimEnd("\", "/")
} catch {
    [Console]::Error.WriteLine("[storage-smoke] failed: LOCALAPPDATA is invalid")
    exit 1
}
$localAppDataRoot = [System.IO.Path]::GetPathRoot($localAppData).TrimEnd("\", "/")
if (
    $localAppData.Equals($localAppDataRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    -not (Test-Path -LiteralPath $localAppData -PathType Container)
) {
    [Console]::Error.WriteLine("[storage-smoke] failed: LOCALAPPDATA is invalid")
    exit 1
}

$formalDefaultRoot = Join-Path $localAppData "AIWebNovel"
$formalDefaultRootExists = Test-Path -LiteralPath $formalDefaultRoot
$formalDefaultRootExistsAfter = $formalDefaultRootExists
$runToken = [guid]::NewGuid().ToString("N")
$smokeRootLeaf = "AIWebNovel-DEV-0.8-$runToken"
$smokeRoot = Join-Path $localAppData $smokeRootLeaf
try {
    Assert-DirectOwnedSmokeRoot `
        -Candidate $smokeRoot `
        -ExpectedParent $localAppData `
        -ExpectedLeaf $smokeRootLeaf
} catch {
    [Console]::Error.WriteLine("[storage-smoke] failed: unsafe test root")
    exit 1
}
if (Test-Path -LiteralPath $smokeRoot) {
    [Console]::Error.WriteLine("[storage-smoke] failed: unique test root already exists")
    exit 1
}

$captureRoot = [System.IO.Path]::GetTempPath()
$stdoutCapture = Join-Path $captureRoot "aiwebnovel-storage-smoke-$runToken.stdout.txt"
$stderrCapture = Join-Path $captureRoot "aiwebnovel-storage-smoke-$runToken.stderr.txt"
$capturePaths = @($stdoutCapture, $stderrCapture)
$sensitivePaths = @(
    $smokeRoot,
    $localAppData,
    $formalDefaultRoot,
    $repositoryRoot,
    $pythonExecutable,
    $stdoutCapture,
    $stderrCapture,
    $env:USERPROFILE
)

$launcher = $null
$launcherStartedAtUtcTicks = 0L
$serviceRecord = $null
$directoriesCreated = 0
$storageStatus = "not_checked"
$databaseStatus = "not_checked"
$failureMessage = $null
$cleanupFailure = $null

try {
    $environmentOverrides = [ordered]@{
        AIWEBNOVEL_APP_NAME = "AIWebNovel"
        AIWEBNOVEL_APP_VERSION = "0.0.0"
        AIWEBNOVEL_DATA_ROOT = $smokeRoot
        AIWEBNOVEL_DATABASE_URL = $null
        AIWEBNOVEL_ENVIRONMENT = "storage-smoke"
        AIWEBNOVEL_API_PREFIX = "/api/v1"
        AIWEBNOVEL_HOST = "127.0.0.1"
        AIWEBNOVEL_PORT = $Port.ToString()
        AIWEBNOVEL_LOG_LEVEL = "WARNING"
        AIWEBNOVEL_DATABASE_ECHO = "false"
        AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS = "5000"
        AIWEBNOVEL_SERVE_FRONTEND = "false"
        AIWEBNOVEL_FRONTEND_DIST_PATH = (Join-Path $repositoryRoot "frontend/dist")
        AIWEBNOVEL_CORS_ALLOWED_ORIGINS = ('["http://127.0.0.1:{0}"]' -f $Port)
    }
    $previousEnvironment = @{}
    foreach ($entry in $environmentOverrides.GetEnumerator()) {
        $previousEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable(
            $entry.Key,
            "Process"
        )
    }
    try {
        foreach ($entry in $environmentOverrides.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable(
                $entry.Key,
                $entry.Value,
                "Process"
            )
        }
        $launcher = Start-Process `
            -FilePath $pythonExecutable `
            -ArgumentList @("-m", "aiwebnovel") `
            -WorkingDirectory $repositoryRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutCapture `
            -RedirectStandardError $stderrCapture `
            -PassThru
        $launcherStartedAtUtcTicks = $launcher.StartTime.ToUniversalTime().Ticks
    } finally {
        foreach ($entry in $environmentOverrides.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable(
                $entry.Key,
                $previousEnvironment[$entry.Key],
                "Process"
            )
        }
    }

    $baseUrl = "http://127.0.0.1:$Port/api/v1/health"
    $liveResponse = Wait-SmokeEndpoint `
        -Url "$baseUrl/live" `
        -Launcher $launcher
    if ($liveResponse.StatusCode -ne 200) {
        throw "live endpoint did not return 200"
    }

    $serviceRecord = Get-OwnedListenerProcess `
        -CandidatePort $Port `
        -Launcher $launcher
    $readyResponse = Wait-SmokeEndpoint `
        -Url "$baseUrl/ready" `
        -Launcher $launcher
    if (
        $readyResponse.Content.IndexOf(
            $smokeRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0 -or
        $readyResponse.Content.IndexOf(
            $localAppData,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {
        throw "ready response exposed a local path"
    }
    $readyPayload = $readyResponse.Content | ConvertFrom-Json
    $storageStatus = [string]$readyPayload.checks.storage
    $databaseStatus = [string]$readyPayload.checks.database
    if ($readyPayload.status -ne "ready") {
        throw "ready endpoint did not report ready"
    }
    if ($storageStatus -ne "ok" -or $databaseStatus -ne "ok") {
        throw "storage or database readiness did not report ok"
    }

    Assert-DirectOwnedSmokeRoot `
        -Candidate $smokeRoot `
        -ExpectedParent $localAppData `
        -ExpectedLeaf $smokeRootLeaf
    $directoriesCreated = Assert-StandardStorageDirectories -Root $smokeRoot
    if ($directoriesCreated -ne 12) {
        throw "unexpected standard directory count"
    }
    $databaseFile = Join-Path $smokeRoot "data/aiwebnovel.sqlite3"
    if (-not (Test-Path -LiteralPath $databaseFile -PathType Leaf)) {
        throw "derived database file is missing"
    }
    $databaseItem = Get-Item -LiteralPath $databaseFile -Force
    if (($databaseItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "derived database file must not be a reparse point"
    }
} catch {
    $failureMessage = $_.Exception.Message
    Write-SafeServiceDiagnostics `
        -CapturePaths $capturePaths `
        -SensitivePaths $sensitivePaths
} finally {
    $cleanupIssues = [System.Collections.Generic.List[string]]::new()
    if ($null -ne $serviceRecord) {
        try {
            Stop-OwnedProcessTree `
                -OwnedProcessId $serviceRecord.ProcessId `
                -StartedAtUtcTicks $serviceRecord.StartedAtUtcTicks
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    if ($null -ne $launcher) {
        try {
            if ($null -eq $serviceRecord -or $launcher.Id -ne $serviceRecord.ProcessId) {
                Stop-OwnedProcessTree `
                    -OwnedProcessId $launcher.Id `
                    -StartedAtUtcTicks $launcherStartedAtUtcTicks
            }
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    try {
        Wait-LoopbackPortReleased -CandidatePort $Port
    } catch {
        $cleanupIssues.Add($_.Exception.Message)
    }

    if ($cleanupIssues.Count -eq 0) {
        try {
            Assert-DirectOwnedSmokeRoot `
                -Candidate $smokeRoot `
                -ExpectedParent $localAppData `
                -ExpectedLeaf $smokeRootLeaf
            Assert-NoReparsePointsInTree -Root $smokeRoot
            if (Test-Path -LiteralPath $smokeRoot) {
                Remove-Item -LiteralPath $smokeRoot -Recurse -Force
            }
            if (Test-Path -LiteralPath $smokeRoot) {
                throw "smoke-test root remains after cleanup"
            }
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }

    foreach ($capturePath in $capturePaths) {
        try {
            if (Test-Path -LiteralPath $capturePath) {
                Remove-Item -LiteralPath $capturePath -Force
            }
        } catch {
            $cleanupIssues.Add("temporary diagnostic cleanup failed")
        }
    }
    $formalDefaultRootExistsAfter = Test-Path -LiteralPath $formalDefaultRoot
    if ($formalDefaultRootExistsAfter -ne $formalDefaultRootExists) {
        $cleanupIssues.Add("formal default root existence changed during the smoke test")
    }
    if ($cleanupIssues.Count -gt 0) {
        $cleanupFailure = $cleanupIssues -join "; "
    }
}

Write-Host "[storage-smoke] test_root_name=$smokeRootLeaf"
Write-Host (
    "[storage-smoke] formal_default_root_exists=" +
    $formalDefaultRootExistsAfter.ToString().ToLowerInvariant() +
    " content_accessed=false"
)
Write-Host "[storage-smoke] directories_created=$directoriesCreated"
Write-Host "[storage-smoke] storage=$storageStatus"
Write-Host "[storage-smoke] database=$databaseStatus"

if ($null -ne $cleanupFailure) {
    $safeCleanupFailure = ConvertTo-SafeDiagnostic `
        -Message $cleanupFailure `
        -SensitivePaths $sensitivePaths
    [Console]::Error.WriteLine("[storage-smoke] cleanup=failed: $safeCleanupFailure")
    exit 1
}
Write-Host "[storage-smoke] cleanup=ok"

if ($null -ne $failureMessage) {
    $safeFailure = ConvertTo-SafeDiagnostic `
        -Message $failureMessage `
        -SensitivePaths $sensitivePaths
    [Console]::Error.WriteLine("[storage-smoke] failed: $safeFailure")
    exit 1
}

Write-Host "[storage-smoke] passed"
exit 0
