[CmdletBinding()]
param(
    [ValidateSet("Development", "Integrated", "All")]
    [string]$Mode = "All",
    [string]$Scenario = "",
    [switch]$Headed,
    [ValidateRange(0, 65535)]
    [int]$ProxyBackendPort = 0,
    [switch]$SimulateStartupInterruption
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$script:FrontendRoot = Join-Path $script:RepositoryRoot "frontend"
$script:RuntimeRoot = Join-Path $script:RepositoryRoot ".runtime/e2e"
$script:ServiceLauncher = Join-Path $PSScriptRoot "run_e2e_service.ps1"
$script:PlaywrightExecutable = Join-Path (
    $script:FrontendRoot
) "node_modules/.bin/playwright.cmd"

function Assert-SafeContainedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$Container,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $fullCandidate = [System.IO.Path]::GetFullPath($Candidate)
    $fullContainer = [System.IO.Path]::GetFullPath($Container).TrimEnd("\", "/")
    if (Test-Path -LiteralPath $fullContainer) {
        $containerItem = Get-Item -LiteralPath $fullContainer -Force
        if (($containerItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Description controlled root must not be a reparse point"
        }
    }
    $requiredPrefix = "$fullContainer$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not $fullCandidate.StartsWith(
            $requiredPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "$Description must stay inside its controlled root"
    }

    $relativePath = $fullCandidate.Substring($requiredPrefix.Length)
    $currentPath = $fullContainer
    foreach ($segment in $relativePath.Split(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.StringSplitOptions]::RemoveEmptyEntries
        )) {
        $currentPath = Join-Path $currentPath $segment
        if (-not (Test-Path -LiteralPath $currentPath)) {
            continue
        }
        $item = Get-Item -LiteralPath $currentPath -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Description must not traverse a reparse point"
        }
    }
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

function Assert-PortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    if (-not (Test-LoopbackPortAvailable -Port $Port)) {
        throw "E2E port $Port is already in use; existing services are never reused"
    }
}

function Wait-PortReleased {
    param(
        [Parameter(Mandatory = $true)]
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

    throw "owned E2E port $Port was not released"
}

function Assert-ServiceOwnsPort {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ServiceRecord
    )

    $listeners = @(
        Get-NetTCPConnection `
            -State Listen `
            -LocalAddress "127.0.0.1" `
            -LocalPort $ServiceRecord.Port `
            -ErrorAction SilentlyContinue
    )
    $ownerIsRecordedDescendant = $false
    if ($listeners.Count -eq 1) {
        $candidateProcessId = [int]$listeners[0].OwningProcess
        for ($depth = 0; $depth -lt 32 -and $candidateProcessId -gt 0; $depth++) {
            if ($candidateProcessId -eq $ServiceRecord.ServiceProcessId) {
                $ownerIsRecordedDescendant = $true
                break
            }
            $candidate = Get-CimInstance `
                -ClassName Win32_Process `
                -Filter "ProcessId = $candidateProcessId" `
                -ErrorAction SilentlyContinue
            if ($null -eq $candidate) {
                break
            }
            $candidateProcessId = [int]$candidate.ParentProcessId
        }
    }
    if (
        $listeners.Count -ne 1 -or
        -not $ownerIsRecordedDescendant
    ) {
        $observedOwners = @($listeners | Select-Object -ExpandProperty OwningProcess) -join ","
        throw (
            "$($ServiceRecord.Name) does not own its expected loopback port " +
            "(expected PID $($ServiceRecord.ServiceProcessId), observed $observedOwners)"
        )
    }
}

function ConvertTo-QuotedArgument {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value.Contains('"')) {
        throw "service argument contains an unsupported quote character"
    }
    return '"{0}"' -f $Value
}

function Start-OwnedService {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("Backend", "Vite")]
        [string]$Service,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory,
        [int]$BackendPort = 0,
        [int]$CorsPort = 0,
        [string]$DatabasePath = "",
        [switch]$ServeFrontend,
        [string]$FrontendDistPath = ""
    )

    Assert-PortAvailable -Port $Port
    $stdoutPath = Join-Path $RunDirectory "$Name.stdout.log"
    $stderrPath = Join-Path $RunDirectory "$Name.stderr.log"
    $manifestPath = Join-Path $RunDirectory "$Name.process.json"
    $arguments = @(
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (ConvertTo-QuotedArgument -Value $script:ServiceLauncher),
        "-Service",
        $Service,
        "-Port",
        $Port.ToString(),
        "-ProcessManifestPath",
        (ConvertTo-QuotedArgument -Value $manifestPath)
    )
    if ($BackendPort -gt 0) {
        $arguments += @("-BackendPort", $BackendPort.ToString())
    }
    if ($CorsPort -gt 0) {
        $arguments += @("-CorsPort", $CorsPort.ToString())
    }
    if (-not [string]::IsNullOrWhiteSpace($DatabasePath)) {
        $arguments += @(
            "-DatabasePath",
            (ConvertTo-QuotedArgument -Value $DatabasePath)
        )
    }
    if ($ServeFrontend) {
        $arguments += "-ServeFrontend"
        $arguments += @(
            "-FrontendDistPath",
            (ConvertTo-QuotedArgument -Value $FrontendDistPath)
        )
    }

    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $arguments `
        -WorkingDirectory $script:RepositoryRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $record = [pscustomobject]@{
        Name = $Name
        Port = $Port
        Process = $process
        StartedAt = $process.StartTime.ToUniversalTime()
        ServiceProcessId = 0
        ServiceStartedAt = $null
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
        ManifestPath = $manifestPath
    }
    $script:OwnedProcesses.Add($record)
    $null = $script:OwnedPorts.Add($Port)

    $manifestDeadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $process.Refresh()
        if ($process.HasExited) {
            throw "$Name launcher exited before recording its service process"
        }
        if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
            try {
                $manifest = Get-Content `
                    -LiteralPath $manifestPath `
                    -Raw `
                    -Encoding UTF8 | ConvertFrom-Json
                $serviceProcessId = [int]$manifest.process_id
                $serviceStartedAt = [DateTime]::new(
                    [long]$manifest.started_at_utc_ticks,
                    [DateTimeKind]::Utc
                )
                $serviceProcess = Get-Process `
                    -Id $serviceProcessId `
                    -ErrorAction SilentlyContinue
                if (
                    $null -ne $serviceProcess -and
                    $serviceProcess.StartTime.ToUniversalTime() -eq $serviceStartedAt
                ) {
                    $record.ServiceProcessId = $serviceProcessId
                    $record.ServiceStartedAt = $serviceStartedAt
                    break
                }
            } catch {
                # The launcher may still be completing its atomic-sized manifest write.
            }
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $manifestDeadline)

    if ($record.ServiceProcessId -le 0) {
        throw "$Name did not record a valid owned service process"
    }
    return $record
}

function Get-ResponseStatusCode {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest `
            -Uri $Url `
            -Method Get `
            -Headers @{ Accept = "application/json, text/html" } `
            -UseBasicParsing `
            -TimeoutSec 2
        return [int]$response.StatusCode
    } catch {
        $errorResponse = $_.Exception.Response
        if ($null -ne $errorResponse -and $null -ne $errorResponse.StatusCode) {
            return [int]$errorResponse.StatusCode
        }
        return 0
    }
}

function Wait-ServiceUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int[]]$AcceptedStatusCodes,
        [Parameter(Mandatory = $true)]
        [object]$ServiceRecord,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $ServiceRecord.Process.Refresh()
        if ($ServiceRecord.Process.HasExited) {
            throw "$Name exited before its readiness URL became available"
        }
        $statusCode = Get-ResponseStatusCode -Url $Url
        if ($AcceptedStatusCodes -contains $statusCode) {
            Assert-ServiceOwnsPort -ServiceRecord $ServiceRecord
            return
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "$Name did not become ready before the startup timeout"
}

function Write-LimitedServiceDiagnostics {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory
    )

    foreach ($record in $script:OwnedProcesses) {
        foreach ($stream in @(
                @{ Label = "stdout"; Path = $record.StdoutPath },
                @{ Label = "stderr"; Path = $record.StderrPath }
            )) {
            if (-not (Test-Path -LiteralPath $stream.Path -PathType Leaf)) {
                continue
            }
            $lines = @(
                Get-Content `
                    -LiteralPath $stream.Path `
                    -Tail 20 `
                    -Encoding UTF8 `
                    -ErrorAction SilentlyContinue
            )
            if ($lines.Count -eq 0) {
                continue
            }
            [Console]::Error.WriteLine(
                "[e2e] limited $($record.Name) $($stream.Label) diagnostics:"
            )
            foreach ($line in $lines) {
                $sanitized = [string]$line
                foreach ($replacement in @(
                        @($script:RepositoryRoot, "<repository>"),
                        @($script:RepositoryRoot.Replace("\", "/"), "<repository>"),
                        @($RunDirectory, "<e2e-runtime>"),
                        @($RunDirectory.Replace("\", "/"), "<e2e-runtime>")
                    )) {
                    $sanitized = [regex]::Replace(
                        $sanitized,
                        [regex]::Escape($replacement[0]),
                        $replacement[1],
                        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                    )
                }
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(https?://[^\s?]+)\?[^\s]+',
                    '$1?<redacted>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)file:///[A-Z]:/[^\s"''<>|]*',
                    'file:///<local-path>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)\b[A-Z]:[\\/][^\s"''<>|]*',
                    '<local-path>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)\\\\[^\s"''<>|]+',
                    '<local-path>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    '(?i)\b(authorization|cookie|set-cookie|token|api[_-]?key)' +
                    '\s*[:=]\s*[^\s,;]+',
                    '$1=<redacted>'
                )
                $sanitized = [regex]::Replace(
                    $sanitized,
                    ([char]27 + '\[[0-?]*[ -/]*[@-~]'),
                    ''
                )
                if ($sanitized.Length -gt 500) {
                    $sanitized = $sanitized.Substring(0, 500) + "..."
                }
                [Console]::Error.WriteLine("[e2e] $sanitized")
            }
        }
    }
}

function Stop-OwnedServiceTree {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Record
    )

    if ($Record.ServiceProcessId -gt 0) {
        $serviceProcess = Get-Process `
            -Id $Record.ServiceProcessId `
            -ErrorAction SilentlyContinue
        if ($null -ne $serviceProcess) {
            if ($serviceProcess.StartTime.ToUniversalTime() -ne $Record.ServiceStartedAt) {
                throw "refusing to stop a reused service process identifier"
            }
            try {
                & taskkill.exe /PID $Record.ServiceProcessId /T /F 2>$null | Out-Null
                $serviceTaskkillExitCode = $LASTEXITCODE
            } catch {
                $serviceTaskkillExitCode = 1
            }
            $serviceProcess.WaitForExit(5000) | Out-Null
            $serviceProcess.Refresh()
            if (-not $serviceProcess.HasExited) {
                throw (
                    "failed to stop owned service process: $($Record.Name) " +
                    "(taskkill exit code $serviceTaskkillExitCode)"
                )
            }
        }
    }

    $Record.Process.Refresh()
    if ($Record.Process.HasExited) {
        return
    }
    $currentProcess = Get-Process -Id $Record.Process.Id -ErrorAction SilentlyContinue
    if ($null -eq $currentProcess) {
        return
    }
    $currentStartedAt = $currentProcess.StartTime.ToUniversalTime()
    if ($currentStartedAt -ne $Record.StartedAt) {
        throw "refusing to stop a reused process identifier"
    }

    try {
        & taskkill.exe /PID $Record.Process.Id /T /F 2>$null | Out-Null
        $taskkillExitCode = $LASTEXITCODE
    } catch {
        $taskkillExitCode = 1
    }
    $Record.Process.WaitForExit(5000) | Out-Null
    $Record.Process.Refresh()
    if (-not $Record.Process.HasExited) {
        throw (
            "failed to stop owned service tree: $($Record.Name) " +
            "(taskkill exit code $taskkillExitCode)"
        )
    }
}

function Remove-ValidatedRunDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RunDirectory
    )

    Assert-SafeContainedPath `
        -Candidate $RunDirectory `
        -Container $script:RepositoryRoot `
        -Description "E2E run directory"
    Assert-SafeContainedPath `
        -Candidate $RunDirectory `
        -Container $script:RuntimeRoot `
        -Description "E2E run directory"
    $fullRunDirectory = [System.IO.Path]::GetFullPath($RunDirectory)
    if (Test-Path -LiteralPath $fullRunDirectory) {
        Remove-Item -LiteralPath $fullRunDirectory -Recurse -Force
    }
    if (Test-Path -LiteralPath $script:RuntimeRoot -PathType Container) {
        $remaining = @(Get-ChildItem -LiteralPath $script:RuntimeRoot -Force)
        if ($remaining.Count -eq 0) {
            Remove-Item -LiteralPath $script:RuntimeRoot -Force
        }
    }
}

function Remove-SuccessArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("development", "integrated")]
        [string]$ModeName
    )

    foreach ($relativePath in @(
            "playwright-results/$ModeName",
            "playwright-report/$ModeName"
        )) {
        $candidate = Join-Path $script:FrontendRoot $relativePath
        $fullCandidate = [System.IO.Path]::GetFullPath($candidate)
        $frontendPrefix = (
            [System.IO.Path]::GetFullPath($script:FrontendRoot).TrimEnd("\", "/") +
            [System.IO.Path]::DirectorySeparatorChar
        )
        if (-not $fullCandidate.StartsWith(
                $frontendPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
            throw "refusing to remove Playwright artifacts outside frontend"
        }
        Assert-SafeContainedPath `
            -Candidate $fullCandidate `
            -Container $script:FrontendRoot `
            -Description "Playwright artifact directory"
        if (Test-Path -LiteralPath $fullCandidate) {
            Remove-Item -LiteralPath $fullCandidate -Recurse -Force
        }
    }
    foreach ($relativeParent in @("playwright-results", "playwright-report")) {
        $parentPath = Join-Path $script:FrontendRoot $relativeParent
        Assert-SafeContainedPath `
            -Candidate $parentPath `
            -Container $script:FrontendRoot `
            -Description "Playwright artifact root"
        if (
            (Test-Path -LiteralPath $parentPath -PathType Container) -and
            @(Get-ChildItem -LiteralPath $parentPath -Force).Count -eq 0
        ) {
            Remove-Item -LiteralPath $parentPath -Force
        }
    }
}

function Invoke-Playwright {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigFile,
        [Parameter(Mandatory = $true)]
        [hashtable]$Environment,
        [string[]]$TestPaths = @(),
        [string]$GrepPattern = ""
    )

    $Environment["NODE_PATH"] = Join-Path $script:FrontendRoot "node_modules"
    $previousValues = @{}
    foreach ($name in $Environment.Keys) {
        $previousValues[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $Environment[$name], "Process")
    }

    try {
        Push-Location $script:FrontendRoot
        try {
            $arguments = @("test", "--config=$ConfigFile") + $TestPaths
            if (-not [string]::IsNullOrWhiteSpace($GrepPattern)) {
                $arguments += "--grep=$GrepPattern"
            }
            if ($Headed) {
                $arguments += "--headed"
            }
            & $script:PlaywrightExecutable @arguments | Out-Host
            $playwrightExitCode = $LASTEXITCODE
            return [int]$playwrightExitCode
        } finally {
            Pop-Location
        }
    } finally {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable(
                $name,
                $previousValues[$name],
                "Process"
            )
        }
    }
}

function Assert-ChromiumInstalled {
    if (-not (Test-Path -LiteralPath $script:PlaywrightExecutable -PathType Leaf)) {
        throw "Playwright is not installed in frontend/node_modules"
    }

    Push-Location $script:FrontendRoot
    try {
        & node -e (
            "const fs=require('node:fs');" +
            "const {chromium}=require('@playwright/test');" +
            "process.exit(fs.existsSync(chromium.executablePath())?0:1);"
        )
        $probeExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($probeExitCode -ne 0) {
        throw "Playwright Chromium is missing; run 'Set-Location frontend; npm run e2e:install'"
    }
}

function Assert-E2EEnvironment {
    foreach ($command in @(
            "git",
            "node",
            "npm.cmd",
            "powershell.exe",
            "taskkill.exe"
        )) {
        if ($null -eq (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "required E2E command is unavailable: $command"
        }
    }

    $pythonExecutable = Join-Path $script:RepositoryRoot ".venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw "root virtual environment is missing"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $script:FrontendRoot "node_modules") -PathType Container)) {
        throw "frontend dependencies are missing"
    }

    $gitRootOutput = & git -C $script:RepositoryRoot rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "repository root is not a Git work tree"
    }
    $gitRoot = [System.IO.Path]::GetFullPath(
        ($gitRootOutput | Select-Object -First 1)
    )
    if (-not $gitRoot.TrimEnd("\", "/").Equals(
            $script:RepositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "E2E runner resolved an unexpected Git repository"
    }

    & $pythonExecutable -c (
        "import struct, sys; " +
        "raise SystemExit(0 if sys.version_info[:3] == (3, 12, 10) " +
        "and struct.calcsize('P') * 8 == 64 else 1)"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "E2E requires 64-bit Python 3.12.10 in the root virtual environment"
    }

    & node -e (
        "const major=Number(process.versions.node.split('.')[0]);" +
        "process.exit(major===24 && process.arch==='x64' ? 0 : 1);"
    )
    if ($LASTEXITCODE -ne 0) {
        throw "E2E requires 64-bit Node.js major version 24"
    }
}

function Invoke-FrontendBuild {
    $previousApiBaseUrl = [Environment]::GetEnvironmentVariable(
        "VITE_API_BASE_URL",
        "Process"
    )
    try {
        [Environment]::SetEnvironmentVariable(
            "VITE_API_BASE_URL",
            "/api/v1",
            "Process"
        )
        Push-Location $script:FrontendRoot
        try {
            & npm.cmd run build
            $buildExitCode = $LASTEXITCODE
        } finally {
            Pop-Location
        }
    } finally {
        [Environment]::SetEnvironmentVariable(
            "VITE_API_BASE_URL",
            $previousApiBaseUrl,
            "Process"
        )
    }
    if ($buildExitCode -ne 0) {
        throw "frontend production build failed with exit code $buildExitCode"
    }
}

function Invoke-E2EScenario {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet(
            "E2E-DEV-001",
            "E2E-DEV-002",
            "E2E-DEV-003",
            "E2E-INT-001",
            "E2E-INT-002",
            "E2E-INT-003",
            "E2E-INT-004",
            "E2E-STARTUP-001"
        )]
        [string]$SelectedScenario
    )

    $script:OwnedProcesses = [System.Collections.Generic.List[object]]::new()
    $script:OwnedPorts = [System.Collections.Generic.HashSet[int]]::new()
    $isDevelopment = $SelectedScenario.StartsWith(
        "E2E-DEV-",
        [System.StringComparison]::Ordinal
    )
    $isMissingBuild = $SelectedScenario -eq "E2E-STARTUP-001"
    $modeName = if ($isDevelopment) { "development" } else { "integrated" }
    $scenarioName = $SelectedScenario.ToLowerInvariant()
    $runId = "{0}-{1}-{2}" -f $scenarioName, $PID, ([guid]::NewGuid().ToString("N"))
    $runDirectory = Join-Path $script:RuntimeRoot $runId
    Assert-SafeContainedPath `
        -Candidate $runDirectory `
        -Container $script:RepositoryRoot `
        -Description "E2E run directory"
    Assert-SafeContainedPath `
        -Candidate $runDirectory `
        -Container $script:RuntimeRoot `
        -Description "E2E run directory"
    foreach ($artifactPath in @(
            (Join-Path $script:FrontendRoot "playwright-results/$modeName"),
            (Join-Path $script:FrontendRoot "playwright-report/$modeName")
        )) {
        Assert-SafeContainedPath `
            -Candidate $artifactPath `
            -Container $script:FrontendRoot `
            -Description "Playwright artifact directory"
    }
    New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null

    $runSucceeded = $false
    $runFailure = $null
    $cleanupFailure = $null
    try {
        if ($isDevelopment) {
            $backendPort = 18120
            $vitePort = 14173
            $selectedProxyPort = if ($ProxyBackendPort -gt 0) {
                $ProxyBackendPort
            } else {
                $backendPort
            }
            if ($selectedProxyPort -ne $backendPort) {
                Assert-PortAvailable -Port $selectedProxyPort
            }

            $backendDatabase = Join-Path $runDirectory "$scenarioName.sqlite3"
            $backend = Start-OwnedService `
                -Service Backend `
                -Name "development-backend" `
                -Port $backendPort `
                -RunDirectory $runDirectory `
                -DatabasePath $backendDatabase `
                -CorsPort $vitePort
            Wait-ServiceUrl `
                -Name "development backend" `
                -Url "http://127.0.0.1:$backendPort/api/v1/health/ready" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $backend

            $vite = Start-OwnedService `
                -Service Vite `
                -Name "development-vite" `
                -Port $vitePort `
                -RunDirectory $runDirectory `
                -BackendPort $selectedProxyPort
            Wait-ServiceUrl `
                -Name "development Vite" `
                -Url "http://127.0.0.1:$vitePort/" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $vite

            if ($SimulateStartupInterruption) {
                throw "controlled startup interruption requested"
            }

            $playwrightExitCode = Invoke-Playwright `
                -ConfigFile "playwright.dev.config.ts" `
                -Environment @{
                    AIWEBNOVEL_E2E_BASE_URL = "http://127.0.0.1:$vitePort"
                    AIWEBNOVEL_E2E_BACKEND_URL = "http://127.0.0.1:$backendPort"
                } `
                -TestPaths @("../tests/e2e/development") `
                -GrepPattern "^$SelectedScenario"
        } elseif ($isMissingBuild) {
            $missingBuildPort = 18122
            $missingBuildDatabase = Join-Path $runDirectory "$scenarioName.sqlite3"
            $missingBuildDist = Join-Path $runDirectory "missing-build-dist"
            New-Item -ItemType Directory -Path $missingBuildDist -Force | Out-Null

            $missingBuild = Start-OwnedService `
                -Service Backend `
                -Name "missing-build-backend" `
                -Port $missingBuildPort `
                -RunDirectory $runDirectory `
                -DatabasePath $missingBuildDatabase `
                -ServeFrontend `
                -FrontendDistPath $missingBuildDist
            Wait-ServiceUrl `
                -Name "missing-build live endpoint" `
                -Url "http://127.0.0.1:$missingBuildPort/api/v1/health/live" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $missingBuild
            Wait-ServiceUrl `
                -Name "missing-build readiness endpoint" `
                -Url "http://127.0.0.1:$missingBuildPort/api/v1/health/ready" `
                -AcceptedStatusCodes @(503) `
                -ServiceRecord $missingBuild
            Wait-ServiceUrl `
                -Name "missing-build root endpoint" `
                -Url "http://127.0.0.1:$missingBuildPort/" `
                -AcceptedStatusCodes @(503) `
                -ServiceRecord $missingBuild

            if ($SimulateStartupInterruption) {
                throw "controlled startup interruption requested"
            }

            $playwrightExitCode = Invoke-Playwright `
                -ConfigFile "playwright.integrated.config.ts" `
                -Environment @{
                    AIWEBNOVEL_E2E_BASE_URL = "http://127.0.0.1:$missingBuildPort"
                    AIWEBNOVEL_E2E_BACKEND_URL = "http://127.0.0.1:$missingBuildPort"
                    AIWEBNOVEL_E2E_MISSING_BUILD_BASE_URL = (
                        "http://127.0.0.1:$missingBuildPort"
                    )
                } `
                -TestPaths @("../tests/e2e/startup-failure") `
                -GrepPattern "^$SelectedScenario"
        } else {
            $integratedPort = 18121
            $integratedDatabase = Join-Path $runDirectory "$scenarioName.sqlite3"
            $frontendDist = Join-Path $script:FrontendRoot "dist"

            $integrated = Start-OwnedService `
                -Service Backend `
                -Name "integrated-backend" `
                -Port $integratedPort `
                -RunDirectory $runDirectory `
                -DatabasePath $integratedDatabase `
                -ServeFrontend `
                -FrontendDistPath $frontendDist
            Wait-ServiceUrl `
                -Name "integrated backend" `
                -Url "http://127.0.0.1:$integratedPort/api/v1/health/ready" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $integrated
            Wait-ServiceUrl `
                -Name "integrated frontend" `
                -Url "http://127.0.0.1:$integratedPort/" `
                -AcceptedStatusCodes @(200) `
                -ServiceRecord $integrated

            if ($SimulateStartupInterruption) {
                throw "controlled startup interruption requested"
            }

            $playwrightExitCode = Invoke-Playwright `
                -ConfigFile "playwright.integrated.config.ts" `
                -Environment @{
                    AIWEBNOVEL_E2E_BASE_URL = "http://127.0.0.1:$integratedPort"
                    AIWEBNOVEL_E2E_BACKEND_URL = "http://127.0.0.1:$integratedPort"
                } `
                -TestPaths @("../tests/e2e/integrated") `
                -GrepPattern "^$SelectedScenario"
        }

        if ($playwrightExitCode -ne 0) {
            throw "Playwright $modeName tests failed with exit code $playwrightExitCode"
        }
        $runSucceeded = $true
    } catch {
        $runFailure = $_.Exception.Message
        Write-LimitedServiceDiagnostics -RunDirectory $runDirectory
    } finally {
        $cleanupIssues = [System.Collections.Generic.List[string]]::new()
        $processesToStop = $script:OwnedProcesses.ToArray()
        [array]::Reverse($processesToStop)
        foreach ($record in $processesToStop) {
            try {
                Stop-OwnedServiceTree -Record $record
            } catch {
                $cleanupIssues.Add($_.Exception.Message)
            }
        }
        foreach ($port in $script:OwnedPorts) {
            try {
                Wait-PortReleased -Port $port
            } catch {
                $cleanupIssues.Add($_.Exception.Message)
            }
        }
        if ($cleanupIssues.Count -eq 0) {
            try {
                Remove-ValidatedRunDirectory -RunDirectory $runDirectory
                if ($runSucceeded) {
                    Remove-SuccessArtifacts -ModeName $modeName
                }
            } catch {
                $cleanupIssues.Add($_.Exception.Message)
            }
        }
        if ($cleanupIssues.Count -gt 0) {
            $cleanupFailure = $cleanupIssues -join "; "
        }
    }

    if ($null -ne $cleanupFailure) {
        throw "E2E cleanup failed: $cleanupFailure"
    }
    if ($null -ne $runFailure) {
        throw $runFailure
    }
}

$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
$allowedDirectories = @(
    $script:RepositoryRoot.TrimEnd("\", "/"),
    $script:FrontendRoot.TrimEnd("\", "/")
)
if (-not ($allowedDirectories -contains $currentDirectory.TrimEnd("\", "/"))) {
    [Console]::Error.WriteLine(
        "[e2e] run from the repository root or through the frontend package scripts"
    )
    exit 1
}
if (-not (Test-Path -LiteralPath $script:ServiceLauncher -PathType Leaf)) {
    [Console]::Error.WriteLine("[e2e] service launcher is missing")
    exit 1
}
if ($Mode -ne "Development" -and $ProxyBackendPort -gt 0) {
    [Console]::Error.WriteLine("[e2e] ProxyBackendPort is limited to Development mode")
    exit 1
}
if ($Mode -eq "All" -and $SimulateStartupInterruption -and [string]::IsNullOrWhiteSpace($Scenario)) {
    [Console]::Error.WriteLine(
        "[e2e] SimulateStartupInterruption requires one explicit mode"
    )
    exit 1
}

try {
    Assert-E2EEnvironment
    Assert-ChromiumInstalled
    $scenarioModes = @{
        "E2E-DEV-001" = "Development"
        "E2E-DEV-002" = "Development"
        "E2E-DEV-003" = "Development"
        "E2E-INT-001" = "Integrated"
        "E2E-INT-002" = "Integrated"
        "E2E-INT-003" = "Integrated"
        "E2E-INT-004" = "Integrated"
        "E2E-STARTUP-001" = "Integrated"
    }
    $developmentScenarios = @("E2E-DEV-001", "E2E-DEV-002", "E2E-DEV-003")
    $integratedScenarios = @(
        "E2E-INT-001",
        "E2E-INT-002",
        "E2E-INT-003",
        "E2E-INT-004",
        "E2E-STARTUP-001"
    )

    if (-not [string]::IsNullOrWhiteSpace($Scenario)) {
        if (-not $scenarioModes.ContainsKey($Scenario)) {
            throw "unknown E2E scenario: $Scenario"
        }
        $scenarioMode = $scenarioModes[$Scenario]
        if ($Mode -ne "All" -and $Mode -ne $scenarioMode) {
            throw "scenario $Scenario does not belong to $Mode mode"
        }
        $selectedScenarios = @($Scenario)
    } elseif ($Mode -eq "Development") {
        $selectedScenarios = $developmentScenarios
    } elseif ($Mode -eq "Integrated") {
        $selectedScenarios = $integratedScenarios
    } else {
        $selectedScenarios = $developmentScenarios + $integratedScenarios
    }

    $needsProductionBuild = @(
        $selectedScenarios | Where-Object { $_ -like "E2E-INT-*" }
    ).Count -gt 0
    if ($needsProductionBuild) {
        Invoke-FrontendBuild
    }

    foreach ($selectedScenario in $selectedScenarios) {
        Write-Host "[e2e] running $selectedScenario"
        Invoke-E2EScenario -SelectedScenario $selectedScenario
        Write-Host "[e2e] passed $selectedScenario"
    }
    Write-Host "[e2e] all requested browser acceptance tests passed"
    exit 0
} catch {
    [Console]::Error.WriteLine("[e2e] failed: $($_.Exception.Message)")
    exit 1
}
