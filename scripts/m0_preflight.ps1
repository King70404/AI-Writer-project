[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:M0Utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $script:M0Utf8
$OutputEncoding = $script:M0Utf8

$script:M0SuccessConclusion = (
    '"M0\u9884\u9a8c\u6536\u68c0\u67e5\u901a\u8fc7' +
    '\uff0c\u7b49\u5f85\u6b63\u5f0f\u9636\u6bb5\u9a8c\u6536\u3002"' |
        ConvertFrom-Json
)
$script:M0FailureConclusion = (
    '"M0\u9884\u9a8c\u6536\u68c0\u67e5\u672a\u901a\u8fc7' +
    '\uff1b\u672a\u5f62\u6210\u6b63\u5f0f\u9636\u6bb5\u7ed3\u8bba\u3002"' |
        ConvertFrom-Json
)
$script:M0ForbiddenConclusion = '"M0\u5df2\u901a\u8fc7"' | ConvertFrom-Json
$script:M0JsonReportName = "M0_PRECHECK_REPORT.json"
$script:M0MarkdownReportName = "M0_PRECHECK_REPORT.md"

function Test-PathEqual {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Left,
        [Parameter(Mandatory = $true)]
        [string]$Right
    )

    return [System.IO.Path]::GetFullPath($Left).TrimEnd("\", "/").Equals(
        [System.IO.Path]::GetFullPath($Right).TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Assert-OrdinaryDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Description is missing or is not a directory"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Description must not be a reparse point"
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
        $current = $pending.Pop()
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "controlled directory contains a reparse point"
        }
        if (-not $item.PSIsContainer) {
            continue
        }
        foreach ($child in Get-ChildItem -LiteralPath $current -Force) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "controlled directory contains a reparse point"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
            }
        }
    }
}

function Initialize-M0ReportDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $runtimeRoot = Join-Path $RepositoryRoot ".runtime"
    $reportRoot = Join-Path $runtimeRoot "m0-preflight"
    foreach ($directory in @($runtimeRoot, $reportRoot)) {
        if (Test-Path -LiteralPath $directory) {
            Assert-OrdinaryDirectory `
                -Path $directory `
                -Description "M0 report directory"
        } else {
            New-Item -ItemType Directory -Path $directory | Out-Null
            Assert-OrdinaryDirectory `
                -Path $directory `
                -Description "M0 report directory"
        }
    }

    foreach ($name in @($script:M0JsonReportName, $script:M0MarkdownReportName)) {
        $target = Join-Path $reportRoot $name
        if (-not (Test-Path -LiteralPath $target)) {
            continue
        }
        $item = Get-Item -LiteralPath $target -Force
        if (
            $item.PSIsContainer -or
            ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            throw "an existing M0 report target is not an ordinary file"
        }
        Remove-Item -LiteralPath $target -Force
    }
    return $reportRoot
}

function New-M0CaptureDirectory {
    $parent = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $leaf = "AIWebNovel-M0-$([guid]::NewGuid().ToString('N'))"
    $captureRoot = Join-Path $parent $leaf
    New-Item -ItemType Directory -Path $captureRoot | Out-Null
    Assert-OrdinaryDirectory `
        -Path $captureRoot `
        -Description "M0 capture directory"
    return $captureRoot
}

function Remove-M0CaptureDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CaptureRoot
    )

    if (-not (Test-Path -LiteralPath $CaptureRoot)) {
        return
    }
    $fullPath = [System.IO.Path]::GetFullPath($CaptureRoot).TrimEnd("\", "/")
    $expectedParent = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::GetTempPath()
    ).TrimEnd("\", "/")
    $actualParent = [System.IO.Path]::GetDirectoryName($fullPath).TrimEnd("\", "/")
    $leaf = [System.IO.Path]::GetFileName($fullPath)
    if (
        -not $actualParent.Equals(
            $expectedParent,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        $leaf -notmatch '^AIWebNovel-M0-[0-9a-f]{32}$'
    ) {
        throw "refusing to remove an unrecognized M0 capture directory"
    }
    Assert-NoReparsePointsInTree -Root $fullPath
    Remove-Item -LiteralPath $fullPath -Recurse -Force
    if (Test-Path -LiteralPath $fullPath) {
        throw "M0 capture directory cleanup did not complete"
    }
}

function Invoke-M0CapturedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$CaptureRoot,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Z0-9-]+$')]
        [string]$CaptureName
    )

    $stdoutPath = Join-Path $CaptureRoot "$CaptureName.stdout.txt"
    $stderrPath = Join-Path $CaptureRoot "$CaptureName.stderr.txt"
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $exitCode = 1
    Push-Location $WorkingDirectory
    try {
        $global:LASTEXITCODE = 0
        & $FilePath @ArgumentList 1> $stdoutPath 2> $stderrPath
        $exitCode = if ($null -eq $LASTEXITCODE) {
            0
        } else {
            [int]$LASTEXITCODE
        }
    } catch {
        $exitCode = 1
    } finally {
        Pop-Location
        $stopwatch.Stop()
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        DurationMs = [math]::Max(0, [int64]$stopwatch.ElapsedMilliseconds)
        StdoutPath = $stdoutPath
        StderrPath = $stderrPath
    }
}

function Get-M0CapturedText {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Capture
    )

    $parts = [System.Collections.Generic.List[string]]::new()
    foreach ($path in @($Capture.StdoutPath, $Capture.StderrPath)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $parts.Add([System.IO.File]::ReadAllText($path))
        }
    }
    $text = $parts -join "`n"
    $escape = [regex]::Escape([string][char]27)
    return [regex]::Replace($text, "$escape\[[0-?]*[ -/]*[@-~]", "")
}

function Test-M0DoctorEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Capture
    )

    if (-not (Test-Path -LiteralPath $Capture.StdoutPath -PathType Leaf)) {
        return $false
    }
    try {
        $payload = [System.IO.File]::ReadAllText($Capture.StdoutPath) |
            ConvertFrom-Json -ErrorAction Stop
        if (
            $payload.schema_version -ne "1" -or
            $payload.mode -ne "m0" -or
            $payload.overall_status -ne "ready"
        ) {
            return $false
        }
        $actualIds = @($payload.checks | ForEach-Object { $_.check_id })
        $expectedIds = @(1..12 | ForEach-Object { "ENV-{0:D3}" -f $_ })
        if ($actualIds.Count -ne $expectedIds.Count) {
            return $false
        }
        for ($index = 0; $index -lt $expectedIds.Count; $index++) {
            if ($actualIds[$index] -ne $expectedIds[$index]) {
                return $false
            }
        }
        return $true
    } catch {
        return $false
    }
}

function Get-FrontendCoverageEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,
        [Parameter(Mandatory = $true)]
        [DateTime]$NotOlderThanUtc
    )

    $summaryPath = Join-Path $RepositoryRoot "frontend/coverage/coverage-summary.json"
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        return $null
    }
    try {
        $summaryItem = Get-Item -LiteralPath $summaryPath -Force
        if (
            ($summaryItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $summaryItem.LastWriteTimeUtc -lt $NotOlderThanUtc
        ) {
            return $null
        }
        $payload = Get-Content -LiteralPath $summaryPath -Encoding UTF8 -Raw |
            ConvertFrom-Json -ErrorAction Stop
        $values = [ordered]@{}
        foreach ($metric in @("statements", "branches", "functions", "lines")) {
            $value = [double]$payload.total.$metric.pct
            if ([double]::IsNaN($value) -or $value -lt 0 -or $value -gt 100) {
                return $null
            }
            $values[$metric] = [math]::Round($value, 2)
        }
        return $values
    } catch {
        return $null
    }
}

function Get-QualityGateEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Capture,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,
        [Parameter(Mandatory = $true)]
        [DateTime]$EvidenceStartedAtUtc
    )

    $text = Get-M0CapturedText -Capture $Capture
    $backendTests = [regex]::Matches(
        $text,
        '(?im)(?<passed>\d+)\s+passed' +
        '(?:,\s*\d+\s+(?:warnings?|skipped|deselected))*\s+in\s+[0-9.]+'
    )
    $frontendTests = [regex]::Matches(
        $text,
        '(?im)^\s*Tests\s+(?<passed>\d+)\s+passed\s+\(\d+\)'
    )
    $backendCoverage = [regex]::Matches(
        $text,
        '(?im)^\[coverage\] backend: statements=(?<statements>\d+(?:\.\d+)?)% branches=(?<branches>\d+(?:\.\d+)?)%\s*$'
    )
    $e2eScenarios = [regex]::Matches(
        $text,
        '(?im)^\[e2e\]\s+passed\s+(?<id>E2E-(?:DEV|INT|STARTUP)-\d+)\s*$'
    )
    $expectedE2EScenarios = @(
        "E2E-DEV-001",
        "E2E-DEV-002",
        "E2E-DEV-003",
        "E2E-INT-001",
        "E2E-INT-002",
        "E2E-INT-003",
        "E2E-INT-004",
        "E2E-INT-005",
        "E2E-STARTUP-001"
    )
    $actualE2EScenarios = @(
        $e2eScenarios |
            ForEach-Object { $_.Groups["id"].Value } |
            Sort-Object -Unique
    )
    $frontendCoverage = Get-FrontendCoverageEvidence `
        -RepositoryRoot $RepositoryRoot `
        -NotOlderThanUtc $EvidenceStartedAtUtc
    $e2eEvidenceMatches = $actualE2EScenarios.Count -eq $expectedE2EScenarios.Count
    if ($e2eEvidenceMatches) {
        for ($index = 0; $index -lt $expectedE2EScenarios.Count; $index++) {
            if ($actualE2EScenarios[$index] -cne $expectedE2EScenarios[$index]) {
                $e2eEvidenceMatches = $false
                break
            }
        }
    }

    if (
        $backendTests.Count -lt 1 -or
        $frontendTests.Count -lt 1 -or
        $backendCoverage.Count -lt 1 -or
        -not $e2eEvidenceMatches -or
        $null -eq $frontendCoverage
    ) {
        return $null
    }

    $backendTestMatch = $backendTests[$backendTests.Count - 1]
    $frontendTestMatch = $frontendTests[$frontendTests.Count - 1]
    $backendCoverageMatch = $backendCoverage[$backendCoverage.Count - 1]
    return [ordered]@{
        backend_tests_passed = [int]$backendTestMatch.Groups["passed"].Value
        frontend_tests_passed = [int]$frontendTestMatch.Groups["passed"].Value
        backend_statement_percent = [double]$backendCoverageMatch.Groups["statements"].Value
        backend_branch_percent = [double]$backendCoverageMatch.Groups["branches"].Value
        frontend_coverage = $frontendCoverage
        e2e_scenarios_passed = [int]$actualE2EScenarios.Count
    }
}

function Invoke-M0VersionCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    Push-Location $WorkingDirectory
    try {
        $global:LASTEXITCODE = 0
        $output = @(& $FilePath @ArgumentList 2>$null)
        if ($LASTEXITCODE -ne 0 -or $output.Count -lt 1) {
            return "unavailable"
        }
        $candidate = (($output | ForEach-Object { $_.ToString().Trim() }) -join " ").Trim()
        if (
            $candidate.Length -lt 1 -or
            $candidate.Length -gt 120 -or
            $candidate -notmatch '^[A-Za-z0-9][A-Za-z0-9 ._()+:-]*$'
        ) {
            return "unavailable"
        }
        return $candidate
    } catch {
        return "unavailable"
    } finally {
        Pop-Location
    }
}

function Get-M0ToolVersions {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $python = Join-Path $RepositoryRoot ".venv/Scripts/python.exe"
    $versions = [ordered]@{
        powershell = $PSVersionTable.PSVersion.ToString()
        git = Invoke-M0VersionCommand `
            -FilePath "git" `
            -ArgumentList @("--version") `
            -WorkingDirectory $RepositoryRoot
        python = Invoke-M0VersionCommand `
            -FilePath "py" `
            -ArgumentList @("-3.12", "--version") `
            -WorkingDirectory $RepositoryRoot
        node = Invoke-M0VersionCommand `
            -FilePath "node" `
            -ArgumentList @("--version") `
            -WorkingDirectory $RepositoryRoot
        npm = Invoke-M0VersionCommand `
            -FilePath "npm.cmd" `
            -ArgumentList @("--version") `
            -WorkingDirectory $RepositoryRoot
        ruff = Invoke-M0VersionCommand `
            -FilePath $python `
            -ArgumentList @("-m", "ruff", "--version") `
            -WorkingDirectory $RepositoryRoot
        mypy = Invoke-M0VersionCommand `
            -FilePath $python `
            -ArgumentList @("-m", "mypy", "--version") `
            -WorkingDirectory $RepositoryRoot
        pytest = Invoke-M0VersionCommand `
            -FilePath $python `
            -ArgumentList @("-m", "pytest", "--version") `
            -WorkingDirectory $RepositoryRoot
        sqlite = Invoke-M0VersionCommand `
            -FilePath $python `
            -ArgumentList @("-c", "import sqlite3; print(sqlite3.sqlite_version)") `
            -WorkingDirectory $RepositoryRoot
        playwright = Invoke-M0VersionCommand `
            -FilePath "node" `
            -ArgumentList @(
                "-e",
                "console.log(require('./frontend/node_modules/@playwright/test/package.json').version)"
            ) `
            -WorkingDirectory $RepositoryRoot
    }
    return $versions
}

function Get-M0GitEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    Push-Location $RepositoryRoot
    try {
        $commitOutput = @(& git rev-parse HEAD 2>$null)
        $commit = if (
            $LASTEXITCODE -eq 0 -and
            $commitOutput.Count -ge 1 -and
            $commitOutput[0].Trim() -match '^[0-9a-f]{40}$'
        ) {
            $commitOutput[0].Trim()
        } else {
            "unavailable"
        }
        $branchOutput = @(& git branch --show-current 2>$null)
        $branch = if (
            $LASTEXITCODE -eq 0 -and
            $branchOutput.Count -ge 1 -and
            $branchOutput[0].Trim() -eq "main"
        ) {
            "main"
        } else {
            "other"
        }
        $statusOutput = @(& git status --porcelain=v1 --untracked-files=all 2>$null)
        $isClean = $LASTEXITCODE -eq 0 -and $statusOutput.Count -eq 0
        $remoteOutput = @(& git remote 2>$null)
        $hasRemote = $LASTEXITCODE -ne 0 -or $remoteOutput.Count -gt 0
        return [ordered]@{
            commit = $commit
            branch = $branch
            clean = [bool]$isClean
            remote_configured = [bool]$hasRemote
        }
    } catch {
        return [ordered]@{
            commit = "unavailable"
            branch = "other"
            clean = $false
            remote_configured = $true
        }
    } finally {
        Pop-Location
    }
}

function Test-M0GitReady {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$GitEvidence
    )

    return (
        $GitEvidence.commit -match '^[0-9a-f]{40}$' -and
        $GitEvidence.branch -eq "main" -and
        $GitEvidence.clean -and
        -not $GitEvidence.remote_configured
    )
}

function Get-AvailableLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    try {
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return [int]([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function New-M0Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Id,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    return [pscustomobject][ordered]@{
        check_id = $Id
        name = $Name
        status = "skipped"
        exit_code = $null
        duration_ms = 0
        summary = "Not executed"
    }
}

function Set-M0StepResult {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Step,
        [Parameter(Mandatory = $true)]
        [int]$ExitCode,
        [Parameter(Mandatory = $true)]
        [long]$DurationMs
    )

    $Step.exit_code = $ExitCode
    $Step.duration_ms = [math]::Max(0, $DurationMs)
    if ($ExitCode -eq 0) {
        $Step.status = "pass"
        $Step.summary = "Check passed"
    } else {
        $Step.status = "fail"
        $Step.summary = "Check failed; later validation stopped"
    }
}

function Assert-M0ReportContentSafe {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Content,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$SensitiveValues
    )

    if ($Content.Contains($script:M0ForbiddenConclusion)) {
        throw "M0 report contains a forbidden formal-stage conclusion"
    }
    if ($Content -match '(?i)\b[A-Z]:[\\/]' -or $Content -match '\\\\[^\\/]+[\\/]') {
        throw "M0 report contains an absolute local path"
    }
    if (
        $Content -match '(?i)(?:cookie|authorization|password|private[_ -]?key)\s*[:=]\s*[^\s,;]+' -or
        $Content -match '(?i)(?:csrf|token)\s*[:=]\s*[A-Za-z0-9_./+=-]{8,}' -or
        $Content -match '-----BEGIN [A-Z ]*PRIVATE KEY-----'
    ) {
        throw "M0 report contains a protected value pattern"
    }
    foreach ($value in $SensitiveValues) {
        if (
            -not [string]::IsNullOrWhiteSpace($value) -and
            $Content.IndexOf($value, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        ) {
            throw "M0 report contains a protected local value"
        }
    }
}

function Write-Utf8NoBomFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Content
    )

    [System.IO.File]::WriteAllText(
        $Path,
        $Content.Replace("`r`n", "`n") + $(if ($Content.EndsWith("`n")) { "" } else { "`n" }),
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Write-AtomicM0ReportFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReportDirectory,
        [Parameter(Mandatory = $true)]
        [string]$JsonContent,
        [Parameter(Mandatory = $true)]
        [string]$MarkdownContent,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$SensitiveValues
    )

    Assert-OrdinaryDirectory `
        -Path $ReportDirectory `
        -Description "M0 report directory"
    Assert-M0ReportContentSafe `
        -Content $JsonContent `
        -SensitiveValues $SensitiveValues
    Assert-M0ReportContentSafe `
        -Content $MarkdownContent `
        -SensitiveValues $SensitiveValues
    try {
        $parsed = $JsonContent | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "M0 JSON report is not parseable"
    }
    if (
        $parsed.overall_status -eq "pass" -and
        $parsed.conclusion -ne $script:M0SuccessConclusion
    ) {
        throw "successful M0 preflight report has an invalid conclusion"
    }
    if (
        $parsed.overall_status -ne "pass" -and
        $parsed.conclusion -eq $script:M0SuccessConclusion
    ) {
        throw "failed M0 preflight report contains the success conclusion"
    }

    $token = [guid]::NewGuid().ToString("N")
    $jsonTemporary = Join-Path $ReportDirectory ".$($script:M0JsonReportName).$token.tmp"
    $markdownTemporary = Join-Path $ReportDirectory ".$($script:M0MarkdownReportName).$token.tmp"
    $jsonTarget = Join-Path $ReportDirectory $script:M0JsonReportName
    $markdownTarget = Join-Path $ReportDirectory $script:M0MarkdownReportName
    $published = $false
    try {
        Write-Utf8NoBomFile -Path $jsonTemporary -Content $JsonContent
        Write-Utf8NoBomFile -Path $markdownTemporary -Content $MarkdownContent
        Move-Item -LiteralPath $jsonTemporary -Destination $jsonTarget -Force
        Move-Item -LiteralPath $markdownTemporary -Destination $markdownTarget -Force
        $published = $true
    } finally {
        Remove-Item -LiteralPath $jsonTemporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $markdownTemporary -Force -ErrorAction SilentlyContinue
        if (-not $published) {
            foreach ($target in @($jsonTarget, $markdownTarget)) {
                if (-not (Test-Path -LiteralPath $target)) {
                    continue
                }
                $targetItem = Get-Item -LiteralPath $target -Force
                if (
                    $targetItem.PSIsContainer -or
                    ($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
                ) {
                    throw "partial M0 report publication could not be safely removed"
                }
                Remove-Item -LiteralPath $target -Force
            }
        }
    }
}

function ConvertTo-M0MarkdownReport {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$Report
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("# M0 preflight report")
    $lines.Add("")
    $lines.Add("> This report records Stage 0 preflight evidence only; it is not formal acceptance.")
    $lines.Add("")
    $lines.Add("- Status: $($Report.overall_status)")
    $lines.Add("- Generated at (UTC): $($Report.generated_at_utc)")
    $lines.Add("- Git commit: $($Report.git.commit)")
    $lines.Add("- Conclusion: $($Report.conclusion)")
    $lines.Add("")
    $lines.Add("## Ordered checks")
    $lines.Add("")
    $lines.Add("| Check ID | Check | Status | Exit code | Duration (ms) | Summary |")
    $lines.Add("| --- | --- | --- | ---: | ---: | --- |")
    foreach ($step in $Report.steps) {
        $exitCode = if ($null -eq $step.exit_code) { "-" } else { $step.exit_code }
        $lines.Add(
            "| $($step.check_id) | $($step.name) | $($step.status) | " +
            "$exitCode | $($step.duration_ms) | $($step.summary) |"
        )
    }
    $lines.Add("")
    $lines.Add("## Tool versions")
    $lines.Add("")
    $lines.Add("| Tool | Version |")
    $lines.Add("| --- | --- |")
    foreach ($entry in $Report.tool_versions.GetEnumerator()) {
        $lines.Add("| $($entry.Key) | $($entry.Value) |")
    }
    $lines.Add("")
    $lines.Add("## Quality evidence")
    $lines.Add("")
    $lines.Add("- Default quality gate: $($Report.quality_gates.default)")
    $lines.Add("- Dependency audit and E2E gate: $($Report.quality_gates.audit_and_e2e)")
    $lines.Add("- Backend tests passed: $($Report.tests.backend_passed)")
    $lines.Add("- Frontend tests passed: $($Report.tests.frontend_passed)")
    $lines.Add("- Backend statement coverage: $($Report.coverage.backend_statements_percent)")
    $lines.Add("- Backend branch coverage: $($Report.coverage.backend_branches_percent)")
    $lines.Add("- Frontend statement coverage: $($Report.coverage.frontend.statements)")
    $lines.Add("- Frontend branch coverage: $($Report.coverage.frontend.branches)")
    $lines.Add("- Frontend function coverage: $($Report.coverage.frontend.functions)")
    $lines.Add("- Frontend line coverage: $($Report.coverage.frontend.lines)")
    $lines.Add("- E2E scenarios passed: $($Report.e2e.scenarios_passed)")
    $lines.Add("")
    $lines.Add("## Runtime evidence")
    $lines.Add("")
    $lines.Add("- Development startup smoke: $($Report.startup.development)")
    $lines.Add("- Integrated startup smoke: $($Report.startup.integrated)")
    $lines.Add("- Storage runtime smoke: $($Report.storage.status)")
    $lines.Add("- Security runtime smoke: $($Report.security.status)")
    $lines.Add("- Cleanup verification: $($Report.cleanup.status)")
    $lines.Add("")
    $lines.Add("## Incomplete checks")
    $lines.Add("")
    if ($Report.incomplete_items.Count -eq 0) {
        $lines.Add("- None")
    } else {
        foreach ($item in $Report.incomplete_items) {
            $lines.Add("- $item")
        }
    }
    $lines.Add("")
    $lines.Add("## Known risks")
    $lines.Add("")
    if ($Report.risks.Count -eq 0) {
        $lines.Add("- No additional preflight risk recorded")
    } else {
        foreach ($risk in $Report.risks) {
            $lines.Add("- $risk")
        }
    }
    return $lines -join "`n"
}

function New-M0Report {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Steps,
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$Components,
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$GitEvidence,
        [Parameter(Mandatory = $true)]
        [System.Collections.IDictionary]$ToolVersions,
        [AllowNull()]
        [System.Collections.IDictionary]$QualityEvidence,
        [Parameter(Mandatory = $true)]
        [bool]$Succeeded,
        [Parameter(Mandatory = $true)]
        [bool]$InternalCleanupSucceeded
    )

    $incompleteItems = @(
        foreach ($step in $Steps) {
            if ($step.status -ne "pass") {
                "$($step.check_id): $($step.name) ($($step.status))"
            }
        }
    )
    $risks = [System.Collections.Generic.List[string]]::new()
    if (-not $Succeeded) {
        $risks.Add("One or more preflight checks failed or were not executed.")
    }
    if (-not $InternalCleanupSucceeded) {
        $risks.Add("Temporary preflight capture cleanup could not be confirmed.")
    }

    $backendPassed = $null
    $frontendPassed = $null
    $backendStatements = $null
    $backendBranches = $null
    $frontendCoverage = [ordered]@{
        statements = $null
        branches = $null
        functions = $null
        lines = $null
    }
    $e2ePassed = $null
    if ($null -ne $QualityEvidence) {
        $backendPassed = $QualityEvidence.backend_tests_passed
        $frontendPassed = $QualityEvidence.frontend_tests_passed
        $backendStatements = $QualityEvidence.backend_statement_percent
        $backendBranches = $QualityEvidence.backend_branch_percent
        $frontendCoverage = $QualityEvidence.frontend_coverage
        $e2ePassed = $QualityEvidence.e2e_scenarios_passed
    }

    return [ordered]@{
        schema_version = "1.0"
        report_type = "m0_preflight"
        generated_at_utc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
        overall_status = if ($Succeeded) { "pass" } else { "fail" }
        conclusion = if ($Succeeded) {
            $script:M0SuccessConclusion
        } else {
            $script:M0FailureConclusion
        }
        git = $GitEvidence
        tool_versions = $ToolVersions
        steps = @($Steps)
        quality_gates = [ordered]@{
            default = $Components.default_gate
            audit_and_e2e = $Components.audit_and_e2e_gate
        }
        tests = [ordered]@{
            backend_passed = $backendPassed
            frontend_passed = $frontendPassed
        }
        coverage = [ordered]@{
            backend_statements_percent = $backendStatements
            backend_branches_percent = $backendBranches
            frontend = $frontendCoverage
        }
        e2e = [ordered]@{
            status = $Components.audit_and_e2e_gate
            scenarios_passed = $e2ePassed
        }
        startup = [ordered]@{
            development = $Components.development_startup
            integrated = $Components.integrated_startup
        }
        storage = [ordered]@{ status = $Components.storage }
        security = [ordered]@{ status = $Components.security }
        cleanup = [ordered]@{
            status = $Components.cleanup
            internal_capture_cleanup = if ($InternalCleanupSucceeded) { "pass" } else { "fail" }
        }
        incomplete_items = @($incompleteItems)
        risks = @($risks)
    }
}

function Invoke-M0Preflight {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        [Console]::Error.WriteLine("[m0-preflight] failed: Windows is required")
        return 1
    }

    $repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    $currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
    if (-not (Test-PathEqual -Left $currentDirectory -Right $repositoryRoot)) {
        [Console]::Error.WriteLine(
            "[m0-preflight] failed: run this script from the repository root"
        )
        return 1
    }
    $gitRootOutput = @(& git rev-parse --show-toplevel 2>$null)
    if (
        $LASTEXITCODE -ne 0 -or
        $gitRootOutput.Count -lt 1 -or
        -not (Test-PathEqual -Left $gitRootOutput[0] -Right $repositoryRoot)
    ) {
        [Console]::Error.WriteLine(
            "[m0-preflight] failed: current directory is not the expected Git repository"
        )
        return 1
    }

    try {
        $reportRoot = Initialize-M0ReportDirectory -RepositoryRoot $repositoryRoot
        $captureRoot = New-M0CaptureDirectory
    } catch {
        [Console]::Error.WriteLine(
            "[m0-preflight] failed: controlled report storage could not be prepared"
        )
        return 1
    }

    $steps = @(
        (New-M0Step -Id "M0-001" -Name "M0 environment doctor"),
        (New-M0Step -Id "M0-002" -Name "Default quality gate"),
        (New-M0Step -Id "M0-003" -Name "Dependency audit and E2E quality gate"),
        (New-M0Step -Id "M0-004" -Name "Development startup smoke"),
        (New-M0Step -Id "M0-005" -Name "Integrated startup smoke"),
        (New-M0Step -Id "M0-006" -Name "Storage and security runtime smoke"),
        (New-M0Step -Id "M0-007" -Name "Cleanup verification"),
        (New-M0Step -Id "M0-008" -Name "Git worktree verification"),
        (New-M0Step -Id "M0-009" -Name "M0 preflight report generation")
    )
    $components = [ordered]@{
        environment_doctor = "skipped"
        default_gate = "skipped"
        audit_and_e2e_gate = "skipped"
        development_startup = "skipped"
        integrated_startup = "skipped"
        storage = "skipped"
        security = "skipped"
        cleanup = "skipped"
        git = "skipped"
    }
    $qualityEvidence = $null
    $gitEvidence = Get-M0GitEvidence -RepositoryRoot $repositoryRoot
    $toolVersions = Get-M0ToolVersions -RepositoryRoot $repositoryRoot
    $failed = $false
    $internalCleanupSucceeded = $true
    $powershell = "powershell.exe"

    for ($index = 0; $index -lt 8; $index++) {
        if ($failed) {
            break
        }
        $step = $steps[$index]
        Write-Host "[m0-preflight] running: $($step.name)"
        $result = $null
        try {
            switch ($step.check_id) {
                "M0-001" {
                    $doctorBackendPort = Get-AvailableLoopbackPort
                    do {
                        $doctorFrontendPort = Get-AvailableLoopbackPort
                    } while ($doctorFrontendPort -eq $doctorBackendPort)
                    $result = Invoke-M0CapturedCommand `
                        -FilePath $powershell `
                        -ArgumentList @(
                            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            (Join-Path $PSScriptRoot "environment_doctor.ps1"),
                            "-Mode", "M0", "-Json",
                            "-BackendPort", $doctorBackendPort.ToString(),
                            "-FrontendPort", $doctorFrontendPort.ToString()
                        ) `
                        -WorkingDirectory $repositoryRoot `
                        -CaptureRoot $captureRoot `
                        -CaptureName "M0-001"
                    if (
                        $result.ExitCode -eq 0 -and
                        -not (Test-M0DoctorEvidence -Capture $result)
                    ) {
                        $result.ExitCode = 1
                    }
                    $components.environment_doctor = if ($result.ExitCode -eq 0) {
                        "pass"
                    } else {
                        "fail"
                    }
                }
                "M0-002" {
                    $result = Invoke-M0CapturedCommand `
                        -FilePath $powershell `
                        -ArgumentList @(
                            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            (Join-Path $PSScriptRoot "quality_gate.ps1")
                        ) `
                        -WorkingDirectory $repositoryRoot `
                        -CaptureRoot $captureRoot `
                        -CaptureName "M0-002"
                    $components.default_gate = if ($result.ExitCode -eq 0) {
                        "pass"
                    } else {
                        "fail"
                    }
                }
                "M0-003" {
                    $qualityEvidenceStartedAtUtc = [DateTime]::UtcNow
                    $result = Invoke-M0CapturedCommand `
                        -FilePath $powershell `
                        -ArgumentList @(
                            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            (Join-Path $PSScriptRoot "quality_gate.ps1"),
                            "-IncludeDependencyAudit", "-IncludeE2E"
                        ) `
                        -WorkingDirectory $repositoryRoot `
                        -CaptureRoot $captureRoot `
                        -CaptureName "M0-003"
                    if ($result.ExitCode -eq 0) {
                        $qualityEvidence = Get-QualityGateEvidence `
                            -Capture $result `
                            -RepositoryRoot $repositoryRoot `
                            -EvidenceStartedAtUtc $qualityEvidenceStartedAtUtc
                        if ($null -eq $qualityEvidence) {
                            $result.ExitCode = 1
                        }
                    }
                    $components.audit_and_e2e_gate = if ($result.ExitCode -eq 0) {
                        "pass"
                    } else {
                        "fail"
                    }
                }
                "M0-004" {
                    $normalStartupResult = Invoke-M0CapturedCommand `
                        -FilePath $powershell `
                        -ArgumentList @(
                            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            (Join-Path $PSScriptRoot "check_startup_runtime.ps1"),
                            "-Mode", "Development"
                        ) `
                        -WorkingDirectory $repositoryRoot `
                        -CaptureRoot $captureRoot `
                        -CaptureName "M0-004-NORMAL"
                    $childFailureExitCode = 1
                    $childFailureDurationMs = 0
                    if ($normalStartupResult.ExitCode -eq 0) {
                        $childFailureResult = Invoke-M0CapturedCommand `
                            -FilePath $powershell `
                            -ArgumentList @(
                                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                (Join-Path $PSScriptRoot "check_startup_runtime.ps1"),
                                "-Mode", "Development", "-ExerciseChildFailure"
                            ) `
                            -WorkingDirectory $repositoryRoot `
                            -CaptureRoot $captureRoot `
                            -CaptureName "M0-004-CHILD-FAILURE"
                        $childFailureExitCode = $childFailureResult.ExitCode
                        $childFailureDurationMs = $childFailureResult.DurationMs
                    }
                    $result = [pscustomobject]@{
                        ExitCode = if ($normalStartupResult.ExitCode -ne 0) {
                            $normalStartupResult.ExitCode
                        } else {
                            $childFailureExitCode
                        }
                        DurationMs = (
                            [int64]$normalStartupResult.DurationMs +
                            [int64]$childFailureDurationMs
                        )
                    }
                    $components.development_startup = if ($result.ExitCode -eq 0) {
                        "pass"
                    } else {
                        "fail"
                    }
                }
                "M0-005" {
                    $result = Invoke-M0CapturedCommand `
                        -FilePath $powershell `
                        -ArgumentList @(
                            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            (Join-Path $PSScriptRoot "check_startup_runtime.ps1"),
                            "-Mode", "Integrated"
                        ) `
                        -WorkingDirectory $repositoryRoot `
                        -CaptureRoot $captureRoot `
                        -CaptureName "M0-005"
                    $components.integrated_startup = if ($result.ExitCode -eq 0) {
                        "pass"
                    } else {
                        "fail"
                    }
                }
                "M0-006" {
                    $stepTimer = [System.Diagnostics.Stopwatch]::StartNew()
                    $storagePort = Get-AvailableLoopbackPort
                    $storageResult = Invoke-M0CapturedCommand `
                        -FilePath $powershell `
                        -ArgumentList @(
                            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            (Join-Path $PSScriptRoot "check_windows_storage.ps1"),
                            "-Port", $storagePort.ToString()
                        ) `
                        -WorkingDirectory $repositoryRoot `
                        -CaptureRoot $captureRoot `
                        -CaptureName "M0-006-STORAGE"
                    $components.storage = if ($storageResult.ExitCode -eq 0) {
                        "pass"
                    } else {
                        "fail"
                    }
                    $securityExitCode = 1
                    if ($storageResult.ExitCode -eq 0) {
                        $securityPort = Get-AvailableLoopbackPort
                        $securityResult = Invoke-M0CapturedCommand `
                            -FilePath $powershell `
                            -ArgumentList @(
                                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                (Join-Path $PSScriptRoot "check_security_runtime.ps1"),
                                "-Port", $securityPort.ToString()
                            ) `
                            -WorkingDirectory $repositoryRoot `
                            -CaptureRoot $captureRoot `
                            -CaptureName "M0-006-SECURITY"
                        $securityExitCode = $securityResult.ExitCode
                        $components.security = if ($securityExitCode -eq 0) {
                            "pass"
                        } else {
                            "fail"
                        }
                    }
                    $stepTimer.Stop()
                    $result = [pscustomobject]@{
                        ExitCode = if ($storageResult.ExitCode -ne 0) {
                            $storageResult.ExitCode
                        } else {
                            $securityExitCode
                        }
                        DurationMs = [int64]$stepTimer.ElapsedMilliseconds
                    }
                }
                "M0-007" {
                    $cleanupTimer = [System.Diagnostics.Stopwatch]::StartNew()
                    $cleanupResult = Invoke-M0CapturedCommand `
                        -FilePath $powershell `
                        -ArgumentList @(
                            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            (Join-Path $PSScriptRoot "check_e2e_cleanup.ps1")
                        ) `
                        -WorkingDirectory $repositoryRoot `
                        -CaptureRoot $captureRoot `
                        -CaptureName "M0-007"
                    $cleanupExitCode = $cleanupResult.ExitCode
                    try {
                        Remove-M0CaptureDirectory -CaptureRoot $captureRoot
                    } catch {
                        $cleanupExitCode = 1
                        $internalCleanupSucceeded = $false
                    }
                    $cleanupTimer.Stop()
                    $result = [pscustomobject]@{
                        ExitCode = $cleanupExitCode
                        DurationMs = [int64]$cleanupTimer.ElapsedMilliseconds
                    }
                    $components.cleanup = if ($cleanupExitCode -eq 0) {
                        "pass"
                    } else {
                        "fail"
                    }
                }
                "M0-008" {
                    $gitTimer = [System.Diagnostics.Stopwatch]::StartNew()
                    $gitEvidence = Get-M0GitEvidence -RepositoryRoot $repositoryRoot
                    $gitExitCode = if (Test-M0GitReady -GitEvidence $gitEvidence) {
                        0
                    } else {
                        1
                    }
                    $gitTimer.Stop()
                    $result = [pscustomobject]@{
                        ExitCode = $gitExitCode
                        DurationMs = [int64]$gitTimer.ElapsedMilliseconds
                    }
                    $components.git = if ($gitExitCode -eq 0) { "pass" } else { "fail" }
                }
            }
        } catch {
            $result = [pscustomobject]@{
                ExitCode = 1
                DurationMs = 0
            }
        }

        Set-M0StepResult `
            -Step $step `
            -ExitCode ([int]$result.ExitCode) `
            -DurationMs ([long]$result.DurationMs)
        if ($result.ExitCode -ne 0) {
            $failed = $true
            [Console]::Error.WriteLine("[m0-preflight] failed: $($step.name)")
        } else {
            Write-Host "[m0-preflight] passed: $($step.name)"
        }
    }

    if (Test-Path -LiteralPath $captureRoot) {
        try {
            Remove-M0CaptureDirectory -CaptureRoot $captureRoot
        } catch {
            $internalCleanupSucceeded = $false
            $failed = $true
            if ($steps[6].status -eq "skipped") {
                $components.cleanup = "fail"
            }
        }
    }
    if (-not $internalCleanupSucceeded -and $steps[6].status -eq "pass") {
        Set-M0StepResult -Step $steps[6] -ExitCode 1 -DurationMs $steps[6].duration_ms
        $components.cleanup = "fail"
    }

    $reportStep = $steps[8]
    Write-Host "[m0-preflight] running: $($reportStep.name)"
    $reportTimer = [System.Diagnostics.Stopwatch]::StartNew()
    if (-not $failed -and $null -eq $qualityEvidence) {
        $failed = $true
    }
    Set-M0StepResult `
        -Step $reportStep `
        -ExitCode $(if ($failed -and $steps[0..7].status -notcontains "fail") { 1 } else { 0 }) `
        -DurationMs 0
    $validationSucceeded = -not $failed
    $report = New-M0Report `
        -Steps $steps `
        -Components $components `
        -GitEvidence $gitEvidence `
        -ToolVersions $toolVersions `
        -QualityEvidence $qualityEvidence `
        -Succeeded $validationSucceeded `
        -InternalCleanupSucceeded $internalCleanupSucceeded
    $jsonContent = $report | ConvertTo-Json -Depth 10
    $markdownContent = ConvertTo-M0MarkdownReport -Report $report
    $sensitiveValues = @(
        $repositoryRoot,
        $env:USERPROFILE,
        $env:LOCALAPPDATA,
        [System.IO.Path]::GetTempPath()
    )
    try {
        Write-AtomicM0ReportFiles `
            -ReportDirectory $reportRoot `
            -JsonContent $jsonContent `
            -MarkdownContent $markdownContent `
            -SensitiveValues $sensitiveValues
        $reportTimer.Stop()
        $reportStep.duration_ms = [int64]$reportTimer.ElapsedMilliseconds
        if ($reportStep.status -ne "fail") {
            Write-Host "[m0-preflight] passed: $($reportStep.name)"
        }
    } catch {
        $reportTimer.Stop()
        Set-M0StepResult `
            -Step $reportStep `
            -ExitCode 1 `
            -DurationMs ([int64]$reportTimer.ElapsedMilliseconds)
        [Console]::Error.WriteLine(
            "[m0-preflight] failed: safe M0 reports could not be generated"
        )
        return 1
    }

    if (-not $validationSucceeded) {
        [Console]::Error.WriteLine("[m0-preflight] $($script:M0FailureConclusion)")
        return 1
    }

    Write-Host "[m0-preflight] $($script:M0SuccessConclusion)"
    return 0
}

if ($MyInvocation.InvocationName -ne ".") {
    exit (Invoke-M0Preflight)
}
