[CmdletBinding()]
param(
    [switch]$AllowFailureArtifacts
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
if (-not $currentDirectory.TrimEnd("\", "/").Equals(
        $repositoryRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    [Console]::Error.WriteLine("[e2e-cleanup] run this script from the repository root")
    exit 1
}

$runtimeRoot = Join-Path $repositoryRoot ".runtime/e2e"
$frontendRoot = Join-Path $repositoryRoot "frontend"
$artifactPaths = @(
    (Join-Path $frontendRoot "test-results"),
    (Join-Path $frontendRoot "playwright-results"),
    (Join-Path $frontendRoot "playwright-report")
)
function Test-E2ECleanupComplete {
    foreach ($port in @(14173, 18120, 18121, 18122)) {
        if (-not (Test-LoopbackPortAvailable -Port $port)) {
            return $false
        }
    }

    if (Test-Path -LiteralPath $runtimeRoot) {
        $remainingItems = @(Get-ChildItem -LiteralPath $runtimeRoot -Force)
        if ($remainingItems.Count -ne 0) {
            return $false
        }
    }
    if (-not $AllowFailureArtifacts) {
        foreach ($artifactPath in $artifactPaths) {
            if (Test-Path -LiteralPath $artifactPath) {
                return $false
            }
        }
    }
    return $true
}

$deadline = [DateTime]::UtcNow.AddSeconds(10)
do {
    if (Test-E2ECleanupComplete) {
        Write-Host "[e2e-cleanup] passed: owned ports are free and runtime data is absent"
        exit 0
    }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)

$issues = [System.Collections.Generic.List[string]]::new()
foreach ($port in @(14173, 18120, 18121, 18122)) {
    if (-not (Test-LoopbackPortAvailable -Port $port)) {
        $issues.Add("E2E port is still listening: $port")
    }
}
if (Test-Path -LiteralPath $runtimeRoot) {
    $remainingItems = @(Get-ChildItem -LiteralPath $runtimeRoot -Force)
    if ($remainingItems.Count -gt 0) {
        $issues.Add("E2E runtime directory still contains temporary items")
    }
}
if (-not $AllowFailureArtifacts) {
    foreach ($artifactPath in $artifactPaths) {
        if (Test-Path -LiteralPath $artifactPath) {
            $issues.Add("successful E2E artifacts were not removed")
            break
        }
    }
}

if ($issues.Count -gt 0) {
    foreach ($issue in $issues) {
        [Console]::Error.WriteLine("[e2e-cleanup] $issue")
    }
    exit 1
}

[Console]::Error.WriteLine("[e2e-cleanup] cleanup did not reach a stable empty state")
exit 1
