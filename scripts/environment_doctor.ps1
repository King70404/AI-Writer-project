[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyCollection()]
    [object[]]$RawArguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-Invocation {
    param([switch]$AsJson)

    if ($AsJson) {
        [Console]::Out.WriteLine(
            '{"schema_version":"1","overall_status":"not_ready","error":"invocation_error"}'
        )
    } else {
        [Console]::Out.WriteLine(
            "Environment diagnostics could not start because the invocation is invalid."
        )
    }
    exit 3
}

$Mode = "Development"
$BackendPort = "8000"
$FrontendPort = "5173"
$OutputFile = ""
$Json = @($RawArguments | Where-Object { [string]$_ -ieq "-Json" }).Count -gt 0
$seenArguments = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
$valueArguments = @("-Mode", "-BackendPort", "-FrontendPort", "-OutputFile")
for ($argumentIndex = 0; $argumentIndex -lt $RawArguments.Count; $argumentIndex++) {
    $argument = [string]$RawArguments[$argumentIndex]
    switch ($argument) {
        "-Json" {
            if (-not $seenArguments.Add("Json")) {
                Stop-Invocation -AsJson:$Json
            }
        }
        { $_ -in $valueArguments } {
            $argumentName = $argument.TrimStart("-")
            if (-not $seenArguments.Add($argumentName)) {
                Stop-Invocation -AsJson:$Json
            }
            $argumentIndex += 1
            if ($argumentIndex -ge $RawArguments.Count) {
                Stop-Invocation -AsJson:$Json
            }
            $argumentValue = [string]$RawArguments[$argumentIndex]
            if ($argumentValue -in @($valueArguments + "-Json")) {
                Stop-Invocation -AsJson:$Json
            }
            switch ($argumentName) {
                "Mode" { $Mode = $argumentValue }
                "BackendPort" { $BackendPort = $argumentValue }
                "FrontendPort" { $FrontendPort = $argumentValue }
                "OutputFile" { $OutputFile = $argumentValue }
            }
        }
        default {
            Stop-Invocation -AsJson:$Json
        }
    }
}

function ConvertTo-BootstrapReport {
    param(
        [switch]$AsJson,
        [Parameter(Mandatory = $true)]
        [string]$NormalizedMode
    )

    $definitions = @(
        @("ENV-001", "Operating system", "skipped"),
        @("ENV-002", "Git repository", "skipped"),
        @("ENV-003", "Python", "fail"),
        @("ENV-004", "Virtual environment", "fail"),
        @("ENV-005", "Node.js and npm", "skipped"),
        @("ENV-006", "Playwright Chromium", "skipped"),
        @("ENV-007", "Configuration and security", "skipped"),
        @("ENV-008", "Storage and database", "skipped"),
        @("ENV-009", "Loopback ports", "skipped"),
        @("ENV-010", "Frontend build", "skipped"),
        @("ENV-011", "Quality tools", "skipped"),
        @("ENV-012", "Repository hygiene", "skipped")
    )
    $optionalCheckIds = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::Ordinal
    )
    if ($NormalizedMode -eq "development") {
        foreach ($checkId in @("ENV-006", "ENV-010", "ENV-011")) {
            $null = $optionalCheckIds.Add($checkId)
        }
    } elseif ($NormalizedMode -eq "integrated") {
        foreach ($checkId in @("ENV-006", "ENV-011")) {
            $null = $optionalCheckIds.Add($checkId)
        }
    }
    $checks = @(
        foreach ($definition in $definitions) {
            [ordered]@{
                check_id = $definition[0]
                name = $definition[1]
                status = $definition[2]
                summary = "A supported Python bootstrap interpreter is unavailable."
                details = [ordered]@{}
                remediation = "Install Python 3.12.10 or repair the repository virtual environment."
                required = -not $optionalCheckIds.Contains($definition[0])
                duration_ms = 0
            }
        }
    )
    $report = [ordered]@{
        schema_version = "1"
        mode = $NormalizedMode
        overall_status = "not_ready"
        checks = $checks
    }
    if ($AsJson) {
        return ($report | ConvertTo-Json -Depth 6)
    }
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("AIWebNovel environment diagnostics")
    $lines.Add("mode: $NormalizedMode")
    $lines.Add("overall_status: not_ready")
    foreach ($check in $checks) {
        $lines.Add("[$($check.status.ToUpperInvariant())] $($check.check_id) $($check.name)")
        $lines.Add("  $($check.summary)")
    }
    return ($lines -join [Environment]::NewLine)
}

function Write-ExplicitDiagnosticOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Content,
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot,
        [switch]$AsJson
    )

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return
    }
    try {
        $resolvedOutput = [System.IO.Path]::GetFullPath($Candidate)
        $outputParent = [System.IO.Path]::GetDirectoryName($resolvedOutput)
        if (-not (Test-Path -LiteralPath $outputParent -PathType Container)) {
            throw "diagnostic output parent is unavailable"
        }
        $currentPath = $outputParent
        while (-not [string]::IsNullOrWhiteSpace($currentPath)) {
            $currentItem = Get-Item -LiteralPath $currentPath -Force
            if (($currentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "diagnostic output path is unsafe"
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
        if (Test-Path -LiteralPath $resolvedOutput) {
            $targetItem = Get-Item -LiteralPath $resolvedOutput -Force
            if (
                $targetItem.PSIsContainer -or
                ($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            ) {
                throw "diagnostic output target is unsafe"
            }
        }
        $repositoryPrefix = "$($RepositoryRoot.TrimEnd('\', '/'))$([System.IO.Path]::DirectorySeparatorChar)"
        $runtimeRoot = [System.IO.Path]::GetFullPath(
            (Join-Path $RepositoryRoot ".runtime")
        ).TrimEnd("\", "/")
        $runtimePrefix = "$runtimeRoot$([System.IO.Path]::DirectorySeparatorChar)"
        if (
            $resolvedOutput.StartsWith(
                $repositoryPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -and
            -not $resolvedOutput.StartsWith(
                $runtimePrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        ) {
            throw "diagnostic output inside the repository must use .runtime"
        }
        [System.IO.File]::WriteAllText(
            $resolvedOutput,
            $Content.Replace("`r`n", "`n") + "`n",
            [System.Text.UTF8Encoding]::new($false)
        )
    } catch {
        Stop-Invocation -AsJson:$AsJson
    }
}

function Stop-DiagnosticFailure {
    param(
        [switch]$AsJson,
        [Parameter(Mandatory = $true)]
        [string]$NormalizedMode,
        [string]$OutputFile = "",
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $rendered = if ($AsJson) {
        (
            '{"schema_version":"1","mode":"' + $NormalizedMode +
            '","overall_status":"not_ready","error":"diagnostic_failure"}'
        )
    } else {
        "Environment diagnostics could not complete safely."
    }
    Write-ExplicitDiagnosticOutput `
        -Content $rendered `
        -Candidate $OutputFile `
        -RepositoryRoot $RepositoryRoot `
        -AsJson:$AsJson
    [Console]::Out.WriteLine($rendered)
    exit 2
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
if (-not $currentDirectory.TrimEnd("\", "/").Equals(
        $repositoryRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    Stop-Invocation -AsJson:$Json
}

$normalizedMode = $Mode.Trim().ToLowerInvariant()
if ($normalizedMode -notin @("development", "integrated", "m0")) {
    Stop-Invocation -AsJson:$Json
}
$parsedBackendPort = 0
$parsedFrontendPort = 0
if (
    -not [int]::TryParse($BackendPort, [ref]$parsedBackendPort) -or
    -not [int]::TryParse($FrontendPort, [ref]$parsedFrontendPort) -or
    $parsedBackendPort -lt 1 -or $parsedBackendPort -gt 65535 -or
    $parsedFrontendPort -lt 1 -or $parsedFrontendPort -gt 65535 -or
    ($normalizedMode -ne "integrated" -and $parsedBackendPort -eq $parsedFrontendPort)
) {
    Stop-Invocation -AsJson:$Json
}

$bootstrapExecutable = $null
$bootstrapPrefix = @()
$venvPython = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    & $venvPython -c "raise SystemExit(0)" 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        $bootstrapExecutable = $venvPython
    }
}
if ($null -eq $bootstrapExecutable -and $null -ne (Get-Command py -ErrorAction SilentlyContinue)) {
    & py -3.12 -c "raise SystemExit(0)" 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        $bootstrapExecutable = "py"
        $bootstrapPrefix = @("-3.12")
    }
}

if ($null -eq $bootstrapExecutable) {
    $rendered = ConvertTo-BootstrapReport `
        -AsJson:$Json `
        -NormalizedMode $normalizedMode
    Write-ExplicitDiagnosticOutput `
        -Content $rendered `
        -Candidate $OutputFile `
        -RepositoryRoot $repositoryRoot `
        -AsJson:$Json
    [Console]::Out.WriteLine($rendered)
    exit 2
}

$arguments = [System.Collections.Generic.List[string]]::new()
foreach ($prefixArgument in $bootstrapPrefix) {
    $arguments.Add($prefixArgument)
}
$arguments.Add("-m")
$arguments.Add("aiwebnovel.diagnostics.runner")
$arguments.Add("--mode")
$arguments.Add($normalizedMode)
$arguments.Add("--backend-port")
$arguments.Add($parsedBackendPort.ToString())
$arguments.Add("--frontend-port")
$arguments.Add($parsedFrontendPort.ToString())
if ($Json) {
    $arguments.Add("--json")
}
if (-not [string]::IsNullOrWhiteSpace($OutputFile)) {
    $arguments.Add("--output-file")
    $arguments.Add($OutputFile)
}

$sourceRoot = Join-Path $repositoryRoot "backend/src"
$previousPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
$previousErrorActionPreference = $ErrorActionPreference
$diagnosticOutput = @()
$diagnosticExitCode = 2
try {
    $diagnosticPythonPath = if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
        $sourceRoot
    } else {
        "$sourceRoot$([System.IO.Path]::PathSeparator)$previousPythonPath"
    }
    [Environment]::SetEnvironmentVariable("PYTHONPATH", $diagnosticPythonPath, "Process")
    $ErrorActionPreference = "Continue"
    $diagnosticOutput = @(& $bootstrapExecutable @arguments 2>$null | ForEach-Object {
            $_.ToString()
        })
    $diagnosticExitCode = $LASTEXITCODE
} catch {
    $diagnosticOutput = @()
    $diagnosticExitCode = 2
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
    [Environment]::SetEnvironmentVariable("PYTHONPATH", $previousPythonPath, "Process")
}

if ($diagnosticExitCode -notin @(0, 1, 2, 3) -or $diagnosticOutput.Count -eq 0) {
    Stop-DiagnosticFailure `
        -AsJson:$Json `
        -NormalizedMode $normalizedMode `
        -OutputFile $OutputFile `
        -RepositoryRoot $repositoryRoot
}
if ($Json) {
    try {
        $payload = ($diagnosticOutput -join "`n") | ConvertFrom-Json -ErrorAction Stop
        if ($payload.overall_status -notin @("ready", "ready_with_warnings", "not_ready")) {
            throw "invalid diagnostic status"
        }
    } catch {
        Stop-DiagnosticFailure `
            -AsJson:$Json `
            -NormalizedMode $normalizedMode `
            -OutputFile $OutputFile `
            -RepositoryRoot $repositoryRoot
    }
} elseif (
    -not $diagnosticOutput[0].StartsWith("AIWebNovel environment diagnostics") -and
    -not $diagnosticOutput[0].StartsWith("Environment diagnostics could not start")
) {
    Stop-DiagnosticFailure `
        -AsJson:$Json `
        -NormalizedMode $normalizedMode `
        -OutputFile $OutputFile `
        -RepositoryRoot $repositoryRoot
}
foreach ($line in $diagnosticOutput) {
    [Console]::Out.WriteLine($line)
}
exit $diagnosticExitCode
