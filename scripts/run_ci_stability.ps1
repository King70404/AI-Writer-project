[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$frontendRoot = Join-Path $repositoryRoot "frontend"
$vitest = Join-Path $frontendRoot "node_modules/vitest/vitest.mjs"
if (-not (Test-Path -LiteralPath $vitest -PathType Leaf)) {
    throw "Install the locked frontend dependencies before stability checks."
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputRoot) {
    throw "Use a new stability output directory; existing failure evidence is never overwritten."
}
$null = New-Item -ItemType Directory -Path $outputRoot
$summaryPath = Join-Path $outputRoot "result.json"
$summary = [ordered]@{ status = "running"; targeted_passes = 0; file_passes = 0; blocker = $null }

function Invoke-StabilityRun {
    param(
        [string]$Name,
        [int]$ExpectedPassedTests,
        [int]$ExpectedPendingTests,
        [string]$Filter = ""
    )

    $logPath = Join-Path $outputRoot "$Name.log"
    $jsonPath = Join-Path $outputRoot "$Name.json"
    $null = New-Item -ItemType File -Path $logPath
    $arguments = @(
        $vitest, "run", "../tests/frontend/novel-structure-workspace.test.tsx",
        "--reporter=default", "--reporter=json", "--outputFile.json=$jsonPath"
    )
    if ($Filter) {
        $arguments += @("--testNamePattern", $Filter)
    }
    Write-Host "[stability] $Name"
    # Capture stderr without turning native diagnostic output into a PowerShell exception.
    # Its content is audited below, and the original native exit code is always checked.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & node @arguments 2>&1 | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode; see $Name.log."
    }
    $logText = [System.IO.File]::ReadAllText($logPath)
    $plainLog = [regex]::Replace($logText, '\x1B\[[0-?]*[ -/]*[@-~]', '')
    if ($plainLog -match '(?im)^stderr\s*\||Warning:|React does not recognize|not wrapped in act|Received NaN') {
        throw "$Name emitted unexpected diagnostics; see $Name.log."
    }
    $report = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
    if (
        -not $report.success -or
        $report.numFailedTests -ne 0 -or
        $report.numTodoTests -ne 0 -or
        $report.numPassedTests -ne $ExpectedPassedTests -or
        $report.numPendingTests -ne $ExpectedPendingTests -or
        $report.numTotalTests -ne ($ExpectedPassedTests + $ExpectedPendingTests)
    ) {
        throw "$Name did not report the required $ExpectedPassedTests passing tests and $ExpectedPendingTests unselected tests."
    }
    Write-Host "[stability] $Name passed: $($report.numPassedTests) tests"
}

Push-Location $frontendRoot
try {
    $summary | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    for ($iteration = 1; $iteration -le 20; $iteration++) {
        Invoke-StabilityRun -Name ("targeted-{0:D2}" -f $iteration) `
            -ExpectedPassedTests 8 -ExpectedPendingTests 9 `
            -Filter "creation behaviors|keeps a cleared position"
        $summary.targeted_passes = $iteration
        $summary | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    }
    for ($iteration = 1; $iteration -le 5; $iteration++) {
        Invoke-StabilityRun -Name ("file-{0:D2}" -f $iteration) `
            -ExpectedPassedTests 17 -ExpectedPendingTests 0
        $summary.file_passes = $iteration
        $summary | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    }
    $summary.status = "passed"
} catch {
    $summary.status = "failed"
    $summary.blocker = $_.Exception.Message
    throw
} finally {
    $summary | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    Pop-Location
}
