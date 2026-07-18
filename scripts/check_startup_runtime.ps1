[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Development", "Integrated")]
    [string]$Mode,
    [Parameter(DontShow = $true)]
    [switch]$ExerciseChildFailure
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
. (Join-Path $PSScriptRoot "invoke_owned_process.ps1")

function Wait-OwnedCommandExit {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record,
        [int]$TimeoutSeconds = 60
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $Record.Process.Refresh()
        if ($Record.Process.HasExited) {
            Complete-OwnedProcessCapture -Record $Record
            return [int]($Record.Process.ExitCode)
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$($Record.Name) did not exit before the timeout"
}

function Set-StartupShutdownEvent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        try {
            $event = [System.Threading.EventWaitHandle]::OpenExisting($Name)
            try {
                $null = $event.Set()
                return
            } finally {
                $event.Dispose()
            }
        } catch [System.Threading.WaitHandleCannotBeOpenedException] {
            Start-Sleep -Milliseconds 100
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "startup shutdown event was not available"
}

function Assert-ProcessIdentityMismatchRejected {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record
    )

    $forgedRecord = [pscustomobject]@{
        Name = $Record.Name
        Process = $Record.Process
        ProcessId = $Record.ProcessId
        StartedAtUtcTicks = ([long]$Record.StartedAtUtcTicks + 1)
        Port = 0
        StdoutPath = $Record.StdoutPath
        StderrPath = $Record.StderrPath
    }
    $rejected = $false
    try {
        Stop-OwnedProcessTree -Record $forgedRecord
    } catch {
        if ($_.Exception.Message -match 'refusing to stop a reused process identifier') {
            $rejected = $true
        } else {
            throw
        }
    }
    if (-not $rejected -or -not (Test-OwnedProcessRunning -Record $Record)) {
        throw "PID reuse protection did not preserve the sentinel process"
    }
}

function Remove-ControlledSmokeDataRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedToken
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $localAppData = [System.IO.Path]::GetFullPath(
        [Environment]::GetEnvironmentVariable("LOCALAPPDATA", "Process")
    )
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $parent = [System.IO.Path]::GetFullPath((Split-Path -Parent $fullPath))
    $expectedLeaf = "AIWebNovel-Startup-Smoke-$ExpectedToken"
    if (
        -not $parent.Equals($localAppData, [System.StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Leaf $fullPath) -cne $expectedLeaf
    ) {
        throw "refusing to remove an unowned startup smoke data root"
    }

    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($fullPath)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "startup smoke data root contains a reparse point"
        }
        foreach ($child in Get-ChildItem -LiteralPath $current -Force) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "startup smoke data root contains a reparse point"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
            }
        }
    }
    Remove-Item -LiteralPath $fullPath -Recurse -Force
    if (Test-Path -LiteralPath $fullPath) {
        throw "startup smoke data root remains after cleanup"
    }
}

function Invoke-StartupBrowserCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$BackendUrl,
        [Parameter(Mandatory = $true)]
        [string]$LogDirectory,
        [Parameter(Mandatory = $true)]
        [string]$OutputDirectory,
        [Parameter(Mandatory = $true)]
        [string]$NodeExecutable
    )

    $frontendRoot = Join-Path $repositoryRoot "frontend"
    $playwrightExecutable = Join-Path $frontendRoot "node_modules/.bin/playwright.cmd"
    if (-not (Test-Path -LiteralPath $playwrightExecutable -PathType Leaf)) {
        throw "local Playwright CLI is unavailable"
    }
    $testPath = if ($Mode -eq "Development") {
        "../tests/e2e/development"
    } else {
        "../tests/e2e/integrated"
    }
    $configPath = if ($Mode -eq "Development") {
        "playwright.dev.config.ts"
    } else {
        "playwright.integrated.config.ts"
    }
    $grep = if ($Mode -eq "Development") {
        "^E2E-DEV-001"
    } else {
        "^E2E-INT-001"
    }
    $playwright = Start-OwnedProcess `
        -Name "startup-playwright" `
        -FilePath $playwrightExecutable `
        -ArgumentList @(
            "test",
            "--config=$configPath",
            $testPath,
            "--grep=$grep",
            "--reporter=line",
            "--output=$OutputDirectory"
        ) `
        -WorkingDirectory $frontendRoot `
        -LogDirectory $LogDirectory `
        -EnvironmentOverrides @{
            AIWEBNOVEL_E2E_BASE_URL = $BaseUrl
            AIWEBNOVEL_E2E_BACKEND_URL = $BackendUrl
            NODE_PATH = (Join-Path $frontendRoot "node_modules")
        }
    $script:OwnedProcesses.Add($playwright)
    $playwrightExitCode = Wait-OwnedCommandExit `
        -Record $playwright `
        -TimeoutSeconds 60
    if ($playwrightExitCode -ne 0) {
        throw "Playwright startup acceptance failed with exit code $playwrightExitCode"
    }
}

$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
if (-not $currentDirectory.TrimEnd("\", "/").Equals(
        $repositoryRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    [Console]::Error.WriteLine("[startup-smoke] run this script from the repository root")
    exit 1
}

$localAppDataValue = [Environment]::GetEnvironmentVariable("LOCALAPPDATA", "Process")
if ([string]::IsNullOrWhiteSpace($localAppDataValue)) {
    [Console]::Error.WriteLine("[startup-smoke] LOCALAPPDATA is unavailable")
    exit 1
}
$localAppData = [System.IO.Path]::GetFullPath($localAppDataValue)
$formalRoot = Join-Path $localAppData "AIWebNovel"
$formalRootExisted = Test-Path -LiteralPath $formalRoot
$runToken = [guid]::NewGuid().ToString("N")
$dataRoot = Join-Path $localAppData "AIWebNovel-Startup-Smoke-$runToken"
$shutdownEventName = "Local\AIWebNovel-Startup-$([guid]::NewGuid().ToString('N'))"
$backendPort = Get-TemporaryLoopbackPort
$frontendPort = if ($Mode -eq "Development") {
    do {
        $candidate = Get-TemporaryLoopbackPort
    } while ($candidate -eq $backendPort)
    $candidate
} else {
    0
}

$script:OwnedProcesses = [System.Collections.Generic.List[object]]::new()
$ownedPorts = [System.Collections.Generic.List[int]]::new()
$logDirectory = $null
$runFailure = $null
$cleanupFailure = $null
$browserReady = $false
$sentinelsProtected = $false
$controlledStopPassed = $false
$childFailureDetected = $false
$peerCleanupPassed = $false
$portsReleased = $false
$pythonSentinel = $null
$nodeSentinel = $null
$startupRecord = $null
$backendListenerRecord = $null
$frontendListenerRecord = $null

try {
    if ($ExerciseChildFailure -and $Mode -ne "Development") {
        throw "child failure acceptance is only available in Development mode"
    }
    if (Test-Path -LiteralPath $dataRoot) {
        throw "unique startup smoke data root already exists"
    }
    Assert-LoopbackPortAvailable -Port $backendPort
    if ($frontendPort -gt 0) {
        Assert-LoopbackPortAvailable -Port $frontendPort
    }

    $pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
    $nodeCommand = Get-Command "node.exe" -ErrorAction SilentlyContinue
    $powershellCommand = Get-Command "powershell.exe" -ErrorAction SilentlyContinue
    if (
        -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf) -or
        $null -eq $nodeCommand -or
        $null -eq $powershellCommand
    ) {
        throw "startup smoke prerequisites are unavailable"
    }

    $logDirectory = New-StartupLogDirectory
    $pythonSentinel = Start-OwnedProcess `
        -Name "python-sentinel" `
        -FilePath $pythonExecutable `
        -ArgumentList @("-c", "import time; time.sleep(120)") `
        -WorkingDirectory $repositoryRoot `
        -LogDirectory $logDirectory
    $script:OwnedProcesses.Add($pythonSentinel)
    $nodeSentinel = Start-OwnedProcess `
        -Name "node-sentinel" `
        -FilePath $nodeCommand.Source `
        -ArgumentList @("-e", "setTimeout(()=>{},120000)") `
        -WorkingDirectory $repositoryRoot `
        -LogDirectory $logDirectory
    $script:OwnedProcesses.Add($nodeSentinel)
    Assert-ProcessIdentityMismatchRejected -Record $pythonSentinel
    Assert-ProcessIdentityMismatchRejected -Record $nodeSentinel

    $startupScript = if ($Mode -eq "Development") {
        Join-Path $PSScriptRoot "start_development.ps1"
    } else {
        Join-Path $PSScriptRoot "start_integrated.ps1"
    }
    $startupArguments = @(
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $startupScript,
        "-DataRoot",
        $dataRoot,
        "-NoPreflight",
        "-ShutdownEventName",
        $shutdownEventName
    )
    if ($Mode -eq "Development") {
        $startupArguments += @(
            "-BackendPort",
            $backendPort.ToString(),
            "-FrontendPort",
            $frontendPort.ToString()
        )
    } else {
        $startupArguments += @("-Port", $backendPort.ToString())
    }
    $startupRecord = Start-OwnedProcess `
        -Name "$($Mode.ToLowerInvariant())-startup" `
        -FilePath $powershellCommand.Source `
        -ArgumentList $startupArguments `
        -WorkingDirectory $repositoryRoot `
        -LogDirectory $logDirectory `
        -Port $backendPort
    $script:OwnedProcesses.Add($startupRecord)
    $ownedPorts.Add($backendPort)
    if ($frontendPort -gt 0) {
        $ownedPorts.Add($frontendPort)
    }

    $backendUrl = "http://127.0.0.1:$backendPort"
    $readyContent = Wait-OwnedHttpResponse `
        -Record $startupRecord `
        -Uri ([uri]"$backendUrl/api/v1/health/ready") `
        -TimeoutSeconds 40
    $readyPayload = $readyContent | ConvertFrom-Json
    if ([string]$readyPayload.status -ne "ready") {
        throw "startup smoke backend did not report ready"
    }
    Assert-OwnedLoopbackListener -Record $startupRecord -Port $backendPort
    if ($ExerciseChildFailure) {
        $backendListenerRecord = Get-OwnedLoopbackListenerRecord `
            -Record $startupRecord `
            -Port $backendPort
        if ($backendListenerRecord.ProcessId -eq $startupRecord.ProcessId) {
            throw "development backend listener was not an owned child process"
        }
    }

    $baseUrl = if ($Mode -eq "Development") {
        "http://127.0.0.1:$frontendPort"
    } else {
        $backendUrl
    }
    $listenerPort = if ($Mode -eq "Development") { $frontendPort } else { $backendPort }
    $null = Wait-OwnedHttpResponse `
        -Record $startupRecord `
        -Uri ([uri]"$baseUrl/") `
        -AcceptMediaType "text/html" `
        -TimeoutSeconds 30
    Assert-OwnedLoopbackListener -Record $startupRecord -Port $listenerPort
    if ($ExerciseChildFailure) {
        $frontendListenerRecord = Get-OwnedLoopbackListenerRecord `
            -Record $startupRecord `
            -Port $frontendPort
        if ($frontendListenerRecord.ProcessId -eq $startupRecord.ProcessId) {
            throw "development frontend listener was not an owned child process"
        }
    }

    if ($Mode -eq "Integrated") {
        foreach ($documentationPath in @("/docs", "/redoc", "/openapi.json")) {
            $null = Wait-OwnedHttpResponse `
                -Record $startupRecord `
                -Uri ([uri]"$baseUrl$documentationPath") `
                -AcceptedStatusCodes @(404) `
                -TimeoutSeconds 10
        }
    }

    $playwrightOutput = Join-Path $logDirectory "playwright-results"
    Invoke-StartupBrowserCheck `
        -BaseUrl $baseUrl `
        -BackendUrl $backendUrl `
        -LogDirectory $logDirectory `
        -OutputDirectory $playwrightOutput `
        -NodeExecutable $nodeCommand.Source
    $browserReady = $true

    if ($ExerciseChildFailure) {
        Stop-OwnedProcessTree -Record $frontendListenerRecord
        $startupExitCode = Wait-OwnedCommandExit `
            -Record $startupRecord `
            -TimeoutSeconds 30
        if ($startupExitCode -eq 0) {
            throw "startup command returned success after an owned child process failed"
        }
        $childFailureDetected = $true
        if ((Get-OwnedProcessState -Record $backendListenerRecord) -ne "absent") {
            throw "startup command did not terminate its backend peer after child failure"
        }
        $peerCleanupPassed = $true
    } else {
        Set-StartupShutdownEvent -Name $shutdownEventName
        $startupExitCode = Wait-OwnedCommandExit `
            -Record $startupRecord `
            -TimeoutSeconds 30
        if ($startupExitCode -ne 0) {
            throw "startup command returned exit code $startupExitCode after controlled stop"
        }
        $controlledStopPassed = $true
    }
    foreach ($ownedPort in $ownedPorts) {
        Wait-LoopbackPortReleased -Port $ownedPort
    }
    $portsReleased = $true

    if (
        -not (Test-OwnedProcessRunning -Record $pythonSentinel) -or
        -not (Test-OwnedProcessRunning -Record $nodeSentinel)
    ) {
        throw "startup cleanup terminated an unrelated sentinel process"
    }
    $sentinelsProtected = $true
} catch {
    $runFailure = ConvertTo-StartupSafeText `
        -Value $_.Exception.Message `
        -ProtectedPaths @($repositoryRoot, $localAppData, $dataRoot, $logDirectory)
} finally {
    $cleanupIssues = [System.Collections.Generic.List[string]]::new()
    try {
        Stop-OwnedProcessGroup -Records $script:OwnedProcesses.ToArray()
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
    if (
        $cleanupIssues.Count -eq 0 -and
        $null -ne $runFailure -and
        $script:OwnedProcesses.Count -gt 0
    ) {
        try {
            Write-LimitedOwnedProcessDiagnostics `
                -Records $script:OwnedProcesses.ToArray() `
                -ProtectedPaths @($repositoryRoot, $localAppData, $dataRoot, $logDirectory)
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    if ($cleanupIssues.Count -eq 0) {
        try {
            Remove-ControlledSmokeDataRoot `
                -Path $dataRoot `
                -ExpectedToken $runToken
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    if ($cleanupIssues.Count -eq 0 -and $null -ne $logDirectory) {
        try {
            Remove-StartupLogDirectory -Path $logDirectory
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    if ((Test-Path -LiteralPath $formalRoot) -ne $formalRootExisted) {
        $cleanupIssues.Add("formal user data root existence changed")
    }
    if ($cleanupIssues.Count -gt 0) {
        $cleanupFailure = $cleanupIssues -join "; "
    }
}

if ($null -ne $runFailure) {
    [Console]::Error.WriteLine("[startup-smoke] failed: $runFailure")
}
if ($null -ne $cleanupFailure) {
    $safeCleanup = ConvertTo-StartupSafeText `
        -Value $cleanupFailure `
        -ProtectedPaths @($repositoryRoot, $localAppData, $dataRoot, $logDirectory)
    [Console]::Error.WriteLine("[startup-smoke] cleanup failed: $safeCleanup")
}
if ($null -ne $runFailure -or $null -ne $cleanupFailure) {
    exit 1
}

Write-Host "[startup-smoke] mode=$Mode"
Write-Host "[startup-smoke] browser_ready=$($browserReady.ToString().ToLowerInvariant())"
if ($ExerciseChildFailure) {
    Write-Host "[startup-smoke] scenario=child-failure"
    Write-Host (
        "[startup-smoke] child_failure_detected=" +
        $childFailureDetected.ToString().ToLowerInvariant()
    )
    Write-Host "[startup-smoke] peer_cleanup=$($peerCleanupPassed.ToString().ToLowerInvariant())"
} else {
    Write-Host (
        "[startup-smoke] controlled_stop=" +
        $controlledStopPassed.ToString().ToLowerInvariant()
    )
}
Write-Host "[startup-smoke] sentinel_protection=$($sentinelsProtected.ToString().ToLowerInvariant())"
Write-Host "[startup-smoke] ports_released=$($portsReleased.ToString().ToLowerInvariant())"
Write-Host "[startup-smoke] passed"
exit 0
