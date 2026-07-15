[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$frontendRoot = Join-Path $repositoryRoot "frontend"
$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
$allowedDirectories = @(
    $repositoryRoot.TrimEnd("\", "/"),
    $frontendRoot.TrimEnd("\", "/")
)
if (-not ($allowedDirectories -contains $currentDirectory.TrimEnd("\", "/"))) {
    [Console]::Error.WriteLine(
        "[e2e-report] run from the repository root or through the frontend package script"
    )
    exit 1
}

$playwrightExecutable = Join-Path $frontendRoot "node_modules/.bin/playwright.cmd"
if (-not (Test-Path -LiteralPath $playwrightExecutable -PathType Leaf)) {
    [Console]::Error.WriteLine("[e2e-report] local Playwright is not installed")
    exit 1
}

$reportRoot = Join-Path $frontendRoot "playwright-report"
$candidates = @(
    foreach ($modeName in @("development", "integrated")) {
        $indexPath = Join-Path $reportRoot "$modeName/index.html"
        if (Test-Path -LiteralPath $indexPath -PathType Leaf) {
            Get-Item -LiteralPath $indexPath
        }
    }
)
if ($candidates.Count -eq 0) {
    [Console]::Error.WriteLine(
        "[e2e-report] no retained report is available; run a failing E2E test first"
    )
    exit 1
}

$selectedIndex = $candidates |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$selectedReport = Split-Path -Parent $selectedIndex.FullName
Push-Location $frontendRoot
try {
    & $playwrightExecutable show-report $selectedReport
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
