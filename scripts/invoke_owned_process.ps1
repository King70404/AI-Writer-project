Set-StrictMode -Version Latest

function ConvertTo-NativeProcessArgument {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    if ($Value.IndexOf([char]0) -ge 0 -or $Value.Contains('"')) {
        throw "process argument contains an unsupported character"
    }
    if ($Value.Length -eq 0) {
        return '""'
    }
    if ($Value -notmatch '\s') {
        return $Value
    }

    $quotedValue = [regex]::Replace($Value, '(\\+)$', '$1$1')
    return '"{0}"' -f $quotedValue
}

function ConvertTo-StartupSafeText {
    param(
        [AllowNull()]
        [string]$Value,
        [string[]]$ProtectedPaths = @()
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "operation failed"
    }

    $safeValue = $Value
    foreach ($protectedPath in $ProtectedPaths) {
        if ([string]::IsNullOrWhiteSpace($protectedPath)) {
            continue
        }
        $safeValue = [regex]::Replace(
            $safeValue,
            [regex]::Escape($protectedPath),
            "<local-path>",
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
        $safeValue = [regex]::Replace(
            $safeValue,
            [regex]::Escape($protectedPath.Replace("\", "/")),
            "<local-path>",
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }
    $safeValue = [regex]::Replace(
        $safeValue,
        '(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+',
        'Bearer <redacted>'
    )
    $safeValue = [regex]::Replace(
        $safeValue,
        '(?i)\b(authorization|cookie|set-cookie|x[-_]?csrf[-_]?token|' +
        'csrf(?:[-_]?token)?|password|passwd|secret|client[-_]?secret|' +
        'access[-_]?token|refresh[-_]?token|id[-_]?token|token|' +
        'api[-_]?key)\b\s*[:=]\s*[^\r\n]*',
        '$1=<redacted>'
    )
    $safeValue = [regex]::Replace(
        $safeValue,
        '(?is)-----BEGIN(?:\s+[A-Z0-9]+)?\s+PRIVATE\s+KEY-----.*?' +
        '(?:-----END(?:\s+[A-Z0-9]+)?\s+PRIVATE\s+KEY-----|\z)',
        '<redacted-private-key>'
    )
    $safeValue = [regex]::Replace(
        $safeValue,
        '(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|' +
        'AKIA[0-9A-Z]{16})\b',
        '<redacted-token>'
    )
    $safeValue = [regex]::Replace(
        $safeValue,
        '(?i)file:///[A-Z]:/[^\r\n"''<>|]*',
        'file:///<local-path>'
    )
    $safeValue = [regex]::Replace(
        $safeValue,
        '(?i)\b[A-Z]:[\\/][^\r\n"''<>|]*',
        '<local-path>'
    )
    $safeValue = [regex]::Replace(
        $safeValue,
        '(?i)\\\\[^\r\n"''<>|]+',
        '<local-path>'
    )
    $safeValue = [regex]::Replace(
        $safeValue,
        ([char]27 + '\[[0-?]*[ -/]*[@-~]'),
        ''
    )
    if ($safeValue.Length -gt 500) {
        $safeValue = $safeValue.Substring(0, 500) + "..."
    }
    return $safeValue
}

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

function Resolve-IsolatedDataRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$DefaultLeaf,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $localAppData = [Environment]::GetEnvironmentVariable("LOCALAPPDATA", "Process")
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        throw "LOCALAPPDATA is unavailable"
    }
    try {
        $localAppData = [System.IO.Path]::GetFullPath($localAppData)
    } catch {
        throw "LOCALAPPDATA could not be normalized"
    }
    $selected = if ([string]::IsNullOrWhiteSpace($Candidate)) {
        Join-Path $localAppData $DefaultLeaf
    } else {
        $Candidate
    }
    if (-not (Test-FullyQualifiedWindowsPath -Value $selected)) {
        throw "data root must be an absolute Windows path"
    }

    try {
        $resolved = [System.IO.Path]::GetFullPath($selected).TrimEnd("\", "/")
    } catch {
        throw "data root could not be normalized"
    }
    $pathRoot = [System.IO.Path]::GetPathRoot($resolved).TrimEnd("\", "/")
    if ($resolved.Equals($pathRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "data root must not be a filesystem root"
    }

    $formalRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $localAppData "AIWebNovel")
    ).TrimEnd("\", "/")
    $formalPrefix = "$formalRoot$([System.IO.Path]::DirectorySeparatorChar)"
    $resolvedPrefix = "$resolved$([System.IO.Path]::DirectorySeparatorChar)"
    if (
        $resolved.Equals($formalRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $resolved.StartsWith($formalPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        $formalRoot.StartsWith($resolvedPrefix, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "development startup must not use the formal user data root"
    }

    try {
        $repository = [System.IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\", "/")
    } catch {
        throw "repository root could not be normalized for data isolation"
    }
    $repositoryPrefix = "$repository$([System.IO.Path]::DirectorySeparatorChar)"
    if (
        $resolved.Equals($repository, [System.StringComparison]::OrdinalIgnoreCase) -or
        $resolved.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        $repository.StartsWith($resolvedPrefix, [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "development data root must not overlap the source repository"
    }

    $currentPath = $resolved
    while (-not [string]::IsNullOrWhiteSpace($currentPath)) {
        if (Test-Path -LiteralPath $currentPath) {
            $item = Get-Item -LiteralPath $currentPath -Force
            if ($currentPath -eq $resolved -and -not $item.PSIsContainer) {
                throw "data root must be a directory"
            }
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "data root path must not traverse a reparse point"
            }
        }
        $parentPath = Split-Path -Parent $currentPath
        if (
            [string]::IsNullOrWhiteSpace($parentPath) -or
            $parentPath.Equals($currentPath, [System.StringComparison]::OrdinalIgnoreCase)
        ) {
            break
        }
        $currentPath = $parentPath
    }
    return $resolved
}

function Test-LoopbackPortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$Port
    )

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $Port
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

function Get-TemporaryLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    try {
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function Assert-LoopbackPortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$Port
    )

    if (-not (Test-LoopbackPortAvailable -Port $Port)) {
        throw "loopback port $Port is already in use; specify another port"
    }
}

function Wait-LoopbackPortReleased {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (Test-LoopbackPortAvailable -Port $Port) {
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "owned loopback port $Port was not released"
}

function New-StartupLogDirectory {
    $temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $leaf = "AIWebNovel-Startup-$PID-$([guid]::NewGuid().ToString('N'))"
    $candidate = Join-Path $temporaryRoot $leaf
    if (Test-Path -LiteralPath $candidate) {
        throw "unique startup log directory already exists"
    }
    New-Item -ItemType Directory -Path $candidate | Out-Null
    return $candidate
}

function Start-OwnedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9-]+$')]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$LogDirectory,
        [hashtable]$EnvironmentOverrides = @{},
        [ValidateRange(0, 65535)]
        [int]$Port = 0
    )

    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "owned process executable is unavailable"
    }
    if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
        throw "owned process working directory is unavailable"
    }
    if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
        throw "owned process log directory is unavailable"
    }

    $safeArguments = @(
        $ArgumentList | ForEach-Object { ConvertTo-NativeProcessArgument -Value $_ }
    )
    $stdoutPath = Join-Path $LogDirectory "$Name.stdout.log"
    $stderrPath = Join-Path $LogDirectory "$Name.stderr.log"
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $safeArguments -join " "
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($entry in $EnvironmentOverrides.GetEnumerator()) {
        $environmentName = [string]$entry.Key
        if (
            [string]::IsNullOrWhiteSpace($environmentName) -or
            $environmentName.Contains("=") -or
            $environmentName.IndexOf([char]0) -ge 0
        ) {
            throw "child environment override has an invalid name"
        }
        if ($null -eq $entry.Value) {
            $startInfo.EnvironmentVariables.Remove($environmentName)
        } else {
            $startInfo.EnvironmentVariables[$environmentName] = [string]$entry.Value
        }
    }

    $stdoutStream = $null
    $stderrStream = $null
    $stdoutCaptureTask = $null
    $stderrCaptureTask = $null
    $processStarted = $false
    $startedAtUtcTicks = $null
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        $stdoutStream = [System.IO.File]::Open(
            $stdoutPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::Read
        )
        $stderrStream = [System.IO.File]::Open(
            $stderrPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::Read
        )
        if (-not $process.Start()) {
            throw "owned process did not start"
        }
        $processStarted = $true
        $startedAtUtcTicks = $process.StartTime.ToUniversalTime().Ticks
        $stdoutCaptureTask = $process.StandardOutput.BaseStream.CopyToAsync($stdoutStream)
        $stderrCaptureTask = $process.StandardError.BaseStream.CopyToAsync($stderrStream)
    } catch {
        $cleanupIssue = $null
        $cleanupRecord = $null
        if ($processStarted -and $null -ne $startedAtUtcTicks) {
            $cleanupRecord = [pscustomobject]@{
                Name = $Name
                Process = $process
                ProcessId = $process.Id
                StartedAtUtcTicks = $startedAtUtcTicks
                Port = $Port
                StdoutPath = $stdoutPath
                StderrPath = $stderrPath
                StdoutCaptureTask = $stdoutCaptureTask
                StderrCaptureTask = $stderrCaptureTask
                StdoutCaptureStream = $stdoutStream
                StderrCaptureStream = $stderrStream
                CaptureCompleted = $false
            }
            try {
                Stop-OwnedProcessTree -Record $cleanupRecord
            } catch {
                $cleanupIssue = $_.Exception.Message
            }
        } elseif ($processStarted) {
            $cleanupIssue = (
                "process identity could not be verified; refusing unverified cleanup " +
                "(pid=$($process.Id))"
            )
        }
        if ($null -eq $cleanupRecord -or -not $cleanupRecord.CaptureCompleted) {
            foreach ($stream in @($stdoutStream, $stderrStream)) {
                if ($null -ne $stream) {
                    $stream.Dispose()
                }
            }
        }
        if ($null -ne $cleanupIssue) {
            throw "owned process registration failed; $cleanupIssue"
        }
        throw "owned process could not be started and captured"
    }

    return [pscustomobject]@{
        Name = $Name
        Process = $process
        ProcessId = $process.Id
        StartedAtUtcTicks = $startedAtUtcTicks
        Port = $Port
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
        StdoutCaptureTask = $stdoutCaptureTask
        StderrCaptureTask = $stderrCaptureTask
        StdoutCaptureStream = $stdoutStream
        StderrCaptureStream = $stderrStream
        CaptureCompleted = $false
    }
}

function Complete-OwnedProcessCapture {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record,
        [ValidateRange(1, 60)]
        [int]$TimeoutSeconds = 5
    )

    if (
        $Record.PSObject.Properties.Name -notcontains "CaptureCompleted" -or
        $Record.CaptureCompleted
    ) {
        return
    }
    $issues = [System.Collections.Generic.List[string]]::new()
    $tasks = @(
        $Record.StdoutCaptureTask,
        $Record.StderrCaptureTask
    ) | Where-Object { $null -ne $_ }
    $completedInTime = $true
    if ($tasks.Count -gt 0) {
        try {
            $completedInTime = [System.Threading.Tasks.Task]::WaitAll(
                [System.Threading.Tasks.Task[]]$tasks,
                [TimeSpan]::FromSeconds($TimeoutSeconds)
            )
        } catch {
            $issues.Add("owned process output capture did not complete")
        }
    }
    if (-not $completedInTime) {
        $issues.Add("owned process output capture exceeded its bounded timeout")
    }
    if ($completedInTime -and $issues.Count -eq 0) {
        foreach ($task in $tasks) {
            try {
                $null = $task.GetAwaiter().GetResult()
            } catch {
                $issues.Add("owned process output capture did not complete")
            }
        }
    }
    try {
        if (-not $completedInTime -and $null -ne $Record.Process) {
            $Record.Process.StandardOutput.Dispose()
            $Record.Process.StandardError.Dispose()
        }
    } catch {
        $issues.Add("owned process output capture could not be closed")
    } finally {
        foreach ($stream in @($Record.StdoutCaptureStream, $Record.StderrCaptureStream)) {
            if ($null -ne $stream) {
                $stream.Dispose()
            }
        }
        $Record.CaptureCompleted = $true
    }
    if ($issues.Count -gt 0) {
        throw ($issues -join "; ")
    }
}

function Get-OwnedProcessState {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record
    )

    $current = Get-Process -Id $Record.ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $current) {
        return "absent"
    }
    try {
        $currentTicks = $current.StartTime.ToUniversalTime().Ticks
    } catch {
        return "unverifiable"
    }
    if ($currentTicks -ne [long]$Record.StartedAtUtcTicks) {
        return "mismatch"
    }
    return "owned"
}

function Test-OwnedProcessRunning {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record
    )

    return (Get-OwnedProcessState -Record $Record) -eq "owned"
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
            -Query (
                "SELECT ProcessId, ParentProcessId FROM Win32_Process " +
                "WHERE ProcessId = $CandidateProcessId"
            ) `
            -ErrorAction SilentlyContinue
        if ($null -eq $processRecord) {
            return $false
        }
        $CandidateProcessId = [int]$processRecord.ParentProcessId
    }
    return $false
}

function Get-OwnedLoopbackListenerRecord {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record,
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$Port
    )

    if ((Get-OwnedProcessState -Record $Record) -ne "owned") {
        throw "$($Record.Name) process identity is no longer owned"
    }
    $initialListeners = @(
        Get-NetTCPConnection `
            -State Listen `
            -LocalAddress "127.0.0.1" `
            -LocalPort $Port `
            -ErrorAction SilentlyContinue
    )
    if ($initialListeners.Count -ne 1) {
        throw "$($Record.Name) must own exactly one expected loopback listener"
    }
    $listenerProcessId = [int]$initialListeners[0].OwningProcess
    if (-not (Test-ProcessDescendsFrom `
            -CandidateProcessId $listenerProcessId `
            -AncestorProcessId $Record.ProcessId)) {
        throw "$($Record.Name) does not own its expected loopback listener"
    }

    $listenerProcess = Get-Process -Id $listenerProcessId -ErrorAction SilentlyContinue
    if ($null -eq $listenerProcess) {
        throw "$($Record.Name) loopback listener exited during identity capture"
    }
    try {
        $listenerStartedAtUtcTicks = $listenerProcess.StartTime.ToUniversalTime().Ticks
    } catch {
        throw "$($Record.Name) loopback listener identity could not be recorded"
    }

    $confirmedListeners = @(
        Get-NetTCPConnection `
            -State Listen `
            -LocalAddress "127.0.0.1" `
            -LocalPort $Port `
            -ErrorAction SilentlyContinue
    )
    if (
        $confirmedListeners.Count -ne 1 -or
        [int]$confirmedListeners[0].OwningProcess -ne $listenerProcessId -or
        (Get-OwnedProcessState -Record $Record) -ne "owned" -or
        -not (Test-ProcessDescendsFrom `
            -CandidateProcessId $listenerProcessId `
            -AncestorProcessId $Record.ProcessId)
    ) {
        throw "$($Record.Name) loopback listener identity changed during capture"
    }

    return [pscustomobject]@{
        Name = "$($Record.Name)-listener"
        Process = $listenerProcess
        ProcessId = $listenerProcessId
        StartedAtUtcTicks = $listenerStartedAtUtcTicks
        Port = $Port
        StdoutPath = $Record.StdoutPath
        StderrPath = $Record.StderrPath
    }
}

function Assert-OwnedLoopbackListener {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record,
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$Port
    )

    $null = Get-OwnedLoopbackListenerRecord -Record $Record -Port $Port
}

function Stop-OwnedProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record,
        [int]$TimeoutSeconds = 10
    )

    $state = Get-OwnedProcessState -Record $Record
    if ($state -eq "absent") {
        Complete-OwnedProcessCapture -Record $Record
        return
    }
    if ($state -eq "mismatch") {
        throw "refusing to stop a reused process identifier (pid=$($Record.ProcessId))"
    }
    if ($state -ne "owned") {
        throw "refusing to stop a process whose identity cannot be verified (pid=$($Record.ProcessId))"
    }

    & taskkill.exe /PID $Record.ProcessId /T /F 2>$null | Out-Null
    $taskkillExitCode = $LASTEXITCODE
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-OwnedProcessState -Record $Record) -eq "absent") {
            Complete-OwnedProcessCapture -Record $Record
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw (
        "owned process tree did not stop (pid=$($Record.ProcessId), " +
        "exit_code=$taskkillExitCode)"
    )
}

function Stop-OwnedProcessGroup {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Records
    )

    $issues = [System.Collections.Generic.List[string]]::new()
    $ordered = @($Records)
    [array]::Reverse($ordered)
    foreach ($record in $ordered) {
        try {
            Stop-OwnedProcessTree -Record $record
        } catch {
            $issues.Add($_.Exception.Message)
        }
    }
    if ($issues.Count -gt 0) {
        throw ($issues -join "; ")
    }
}

function Wait-OwnedHttpResponse {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record,
        [Parameter(Mandatory = $true)]
        [uri]$Uri,
        [ValidateSet("application/json", "text/html")]
        [string]$AcceptMediaType = "application/json",
        [int[]]$AcceptedStatusCodes = @(200),
        [int]$TimeoutSeconds = 30
    )

    if ($null -eq ("System.Net.Http.HttpClientHandler" -as [type])) {
        Add-Type -AssemblyName System.Net.Http
    }
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    $client.DefaultRequestHeaders.Accept.ParseAdd($AcceptMediaType)
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        $lastOutcome = "no response"
        do {
            if (
                $null -ne ("AIWebNovel.DevTools.StartupCancellation" -as [type]) -and
                [AIWebNovel.DevTools.StartupCancellation]::Requested
            ) {
                throw "startup cancellation requested before readiness"
            }
            if (-not (Test-OwnedProcessRunning -Record $Record)) {
                throw "$($Record.Name) exited before becoming ready"
            }
            try {
                $response = $client.GetAsync($Uri).GetAwaiter().GetResult()
                try {
                    $statusCode = [int]$response.StatusCode
                    $lastOutcome = "HTTP status $statusCode for $($Uri.AbsolutePath)"
                    if ($AcceptedStatusCodes -contains $statusCode) {
                        return $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                    }
                } finally {
                    $response.Dispose()
                }
            } catch [System.Net.Http.HttpRequestException] {
                # The listener may not yet be accepting requests.
                $lastOutcome = "HTTP request unavailable"
            } catch [System.Threading.Tasks.TaskCanceledException] {
                # A bounded request timed out while the service was starting.
                $lastOutcome = "HTTP request timed out"
            }
            Start-Sleep -Milliseconds 200
        } while ([DateTime]::UtcNow -lt $deadline)
    } finally {
        $client.Dispose()
        $handler.Dispose()
    }
    throw "$($Record.Name) did not become ready before the startup timeout ($lastOutcome)"
}

function Write-LimitedOwnedProcessDiagnostics {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Records,
        [string[]]$ProtectedPaths = @()
    )

    foreach ($record in $Records) {
        foreach ($path in @($record.StdoutPath, $record.StderrPath)) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                continue
            }
            $lines = @(
                Get-Content `
                    -LiteralPath $path `
                    -Tail 12 `
                    -Encoding UTF8 `
                    -ErrorAction SilentlyContinue
            )
            if ($lines.Count -eq 0) {
                continue
            }
            $safeBlock = ConvertTo-StartupSafeText `
                -Value ($lines -join "`n") `
                -ProtectedPaths $ProtectedPaths
            foreach ($safeLine in [regex]::Split($safeBlock, '\r?\n')) {
                if (-not [string]::IsNullOrWhiteSpace($safeLine)) {
                    [Console]::Error.WriteLine("[startup] $safeLine")
                }
            }
        }
    }
}

function Assert-FrontendBuildBoundary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DistPath,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $resolvedDist = [System.IO.Path]::GetFullPath($DistPath).TrimEnd("\", "/")
    $resolvedRepository = [System.IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\", "/")
    $repositoryPrefix = "$resolvedRepository$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not $resolvedDist.StartsWith(
            $repositoryPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "frontend production build must remain inside the repository"
    }

    $current = $resolvedDist
    while ($true) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "frontend production build must not traverse a reparse point"
            }
            if ($current -eq $resolvedDist -and -not $item.PSIsContainer) {
                throw "frontend production build path must be a directory"
            }
        }
        if ($current.Equals(
                $resolvedRepository,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
            break
        }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) {
            throw "frontend production build path is outside the repository"
        }
        $current = $parent
    }

    if (-not (Test-Path -LiteralPath $resolvedDist -PathType Container)) {
        return
    }
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($resolvedDist)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        foreach ($child in Get-ChildItem -LiteralPath $directory -Force) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "frontend production build must not contain a reparse point"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
            }
        }
    }
}

function Assert-FrontendBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DistPath,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    Assert-FrontendBuildBoundary `
        -DistPath $DistPath `
        -RepositoryRoot $RepositoryRoot
    if (-not (Test-Path -LiteralPath $DistPath -PathType Container)) {
        throw "frontend production build is missing or invalid; use -BuildFrontend explicitly"
    }

    $resolvedDist = [System.IO.Path]::GetFullPath($DistPath).TrimEnd("\", "/")
    $indexPath = Join-Path $resolvedDist "index.html"
    $assetsPath = Join-Path $resolvedDist "assets"
    if (
        -not (Test-Path -LiteralPath $indexPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $assetsPath -PathType Container)
    ) {
        throw "frontend production build is missing or invalid; use -BuildFrontend explicitly"
    }

    $files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($resolvedDist)
    $directoryCount = 0
    [long]$totalBytes = 0
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        $directoryCount += 1
        if ($directoryCount -gt 50) {
            throw "frontend production build exceeds its validation bounds"
        }
        foreach ($child in Get-ChildItem -LiteralPath $directory -Force) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "frontend production build must not contain a reparse point"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
                continue
            }
            if ($child -isnot [System.IO.FileInfo] -or $child.Length -gt 2097152) {
                throw "frontend production build exceeds its validation bounds"
            }
            $files.Add($child)
            $totalBytes += $child.Length
            if ($files.Count -gt 100 -or $totalBytes -gt 16777216) {
                throw "frontend production build exceeds its validation bounds"
            }
        }
    }

    $hasIndex = $false
    $hasJavaScriptAsset = $false
    $assetPrefix = "$([System.IO.Path]::GetFullPath($assetsPath).TrimEnd('\', '/'))$([System.IO.Path]::DirectorySeparatorChar)"
    $prohibitedContent = @(
        '(?i)\b[A-Z]:[\\/]',
        '(?i)(?<![\\/])(?:\\\\){1,2}(?!u[0-9A-F]{4}(?:[\\/]{1,2}|-))[A-Z0-9][A-Z0-9._-]*[\\/]{1,2}[A-Z0-9$][A-Z0-9$._-]*(?=[\\/]{1,2}|\s|["''])',
        '-----BEGIN(?:\s+[A-Z0-9]+)?\s+PRIVATE\s+KEY-----',
        '\bsk-[A-Za-z0-9_-]{20,}\b',
        '\bgh[pousr]_[A-Za-z0-9]{20,}\b',
        '\bAKIA[0-9A-Z]{16}\b',
        '(?i)\bauthorization\b["'']?\s*[:=]\s*["'']?(?:bearer|basic)\s+[A-Za-z0-9+/_.=-]{8,}',
        '(?i)\b(?:cookie|set-cookie)\b["'']?\s*[:=]\s*["'']?[A-Za-z0-9_.-]{1,64}=[^;\r\n"'']{4,}',
        '(?i)\b(?:password|passwd|pwd|secret|client[_-]?secret|api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token)\b["'']?\s*[:=]\s*["'']?[A-Za-z0-9._~+/=-]{8,}'
    )
    foreach ($file in $files) {
        $fullName = [System.IO.Path]::GetFullPath($file.FullName)
        if ($fullName.Equals($indexPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            $hasIndex = $true
        }
        if (
            $file.Extension.Equals(".js", [System.StringComparison]::OrdinalIgnoreCase) -and
            $fullName.StartsWith($assetPrefix, [System.StringComparison]::OrdinalIgnoreCase)
        ) {
            $hasJavaScriptAsset = $true
        }
        $content = [System.Text.Encoding]::UTF8.GetString(
            [System.IO.File]::ReadAllBytes($fullName)
        )
        foreach ($pattern in $prohibitedContent) {
            if ($content -match $pattern) {
                throw "frontend production build contains prohibited local or credential content"
            }
        }
    }
    if (-not $hasIndex -or -not $hasJavaScriptAsset) {
        throw "frontend production build is missing or invalid; use -BuildFrontend explicitly"
    }
}

function Remove-StartupLogDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $temporaryRoot = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::GetTempPath()
    ).TrimEnd("\", "/")
    $parent = [System.IO.Path]::GetFullPath((Split-Path -Parent $fullPath))
    $leaf = Split-Path -Leaf $fullPath
    if (
        -not $parent.Equals($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $leaf -notmatch '^AIWebNovel-Startup-\d+-[0-9a-f]{32}$'
    ) {
        throw "refusing to remove an unowned startup log directory"
    }
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($fullPath)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "refusing to remove a startup log directory containing a reparse point"
        }
        if ($item.PSIsContainer) {
            foreach ($child in Get-ChildItem -LiteralPath $current -Force) {
                if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "refusing to remove a startup log directory containing a reparse point"
                }
                if ($child.PSIsContainer) {
                    $pending.Push($child.FullName)
                }
            }
        }
    }
    Remove-Item -LiteralPath $fullPath -Recurse -Force
}

function Initialize-StartupCancellation {
    if ($null -eq ("AIWebNovel.DevTools.StartupCancellation" -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Threading;

namespace AIWebNovel.DevTools
{
    public static class StartupCancellation
    {
        private static int installed;
        private static readonly ConsoleCancelEventHandler handler = HandleCancel;
        public static volatile bool Requested;

        private static void HandleCancel(object sender, ConsoleCancelEventArgs args)
        {
            args.Cancel = true;
            Requested = true;
        }

        public static void Install()
        {
            Requested = false;
            if (Interlocked.Exchange(ref installed, 1) == 0)
            {
                Console.CancelKeyPress += handler;
            }
        }

        public static void Uninstall()
        {
            if (Interlocked.Exchange(ref installed, 0) == 1)
            {
                Console.CancelKeyPress -= handler;
            }
            Requested = false;
        }
    }
}
'@
    }
    [AIWebNovel.DevTools.StartupCancellation]::Install()
}

function Test-StartupCancellationRequested {
    return [AIWebNovel.DevTools.StartupCancellation]::Requested
}

function Close-StartupCancellation {
    if ($null -ne ("AIWebNovel.DevTools.StartupCancellation" -as [type])) {
        [AIWebNovel.DevTools.StartupCancellation]::Uninstall()
    }
}

function New-StartupShutdownEvent {
    param(
        [string]$Name
    )

    if ([string]::IsNullOrWhiteSpace($Name)) {
        return $null
    }
    if ($Name -notmatch '^Local\\AIWebNovel-Startup-[0-9a-f]{32}$') {
        throw "shutdown event name is invalid"
    }
    $created = $false
    $event = [System.Threading.EventWaitHandle]::new(
        $false,
        [System.Threading.EventResetMode]::ManualReset,
        $Name,
        [ref]$created
    )
    if (-not $created) {
        $event.Dispose()
        throw "shutdown event already exists"
    }
    return $event
}
