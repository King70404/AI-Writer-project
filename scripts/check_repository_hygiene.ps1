[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Join-Path $PSScriptRoot "..")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-HygieneCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [int]$ExitCode = 1
    )

    [Console]::Error.WriteLine("[hygiene] $Message")
    exit $ExitCode
}

function Add-HygieneIssue {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Issues,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.HashSet[string]]$IssueKeys,
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [Parameter(Mandatory = $true)]
        [string]$Type
    )

    $key = "$Type`0$RelativePath"
    if ($IssueKeys.Add($key)) {
        $Issues.Add(
            [pscustomobject]@{
                Type = $Type
                Path = $RelativePath
            }
        )
    }
}

function Get-ProhibitedTrackedPathTypes {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $normalized = $RelativePath.Replace("\", "/")
    $segments = @($normalized.Split("/") | ForEach-Object { $_.ToLowerInvariant() })
    $name = $segments[-1]
    $types = [System.Collections.Generic.List[string]]::new()

    if ($name -match '^\.env($|\.)') {
        $types.Add("environment-file")
    }
    if ($segments -contains ".venv" -or $segments -contains "venv") {
        $types.Add("virtual-environment")
    }
    if ($segments -contains "node_modules") {
        $types.Add("node-dependencies")
    }
    if (
        $segments -contains "dist" -or
        $segments -contains "build" -or
        @($segments | Where-Object { $_ -like "*.egg-info" }).Count -gt 0
    ) {
        $types.Add("build-output")
    }
    if (
        $segments -contains "coverage" -or
        $segments -contains "htmlcov" -or
        $name -eq ".coverage" -or
        $name -like ".coverage.*"
    ) {
        $types.Add("coverage-output")
    }
    if (
        $segments -contains "test-results" -or
        $segments -contains "playwright-results" -or
        $segments -contains "playwright-report"
    ) {
        $types.Add("browser-test-output")
    }
    if (
        $segments -contains ".runtime" -or
        $segments -contains "runtime_data" -or
        $segments -contains "sandboxes" -or
        $segments -contains "task_sandboxes"
    ) {
        $types.Add("runtime-or-sandbox")
    }
    if ($segments -contains "local_models" -or $name -match '\.(gguf|safetensors|onnx)$') {
        $types.Add("local-model")
    }
    if (
        $segments -contains "backups" -or
        $segments -contains "exports" -or
        $name -match '\.(bak|backup)$'
    ) {
        $types.Add("backup-or-export")
    }
    if ($segments -contains "logs" -or $name -match '\.log$') {
        $types.Add("log-output")
    }
    if (
        $segments -contains ".idea" -or
        $segments -contains ".vscode" -or
        $name -match '\.(suo|user|userosscache|sln\.docstates)$'
    ) {
        $types.Add("ide-private-file")
    }
    if (
        $segments -contains "__pycache__" -or
        $segments -contains ".pytest_cache" -or
        $segments -contains ".mypy_cache" -or
        $segments -contains ".ruff_cache" -or
        $segments -contains ".vite" -or
        $name -match '\.(pyc|pyo)$' -or
        $name -eq ".eslintcache"
    ) {
        $types.Add("cache-output")
    }
    if ($name -match '\.(db|sqlite|sqlite3)(-(wal|shm|journal))?$') {
        $types.Add("database-artifact")
    }
    if ($name -in @(".ds_store", "thumbs.db", "desktop.ini")) {
        $types.Add("operating-system-metadata")
    }

    return $types.ToArray()
}

try {
    $resolvedRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
} catch {
    Stop-HygieneCheck -Message "repository root does not exist"
}

$gitRootOutput = & git -C $resolvedRoot rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) {
    Stop-HygieneCheck -Message "target directory is not a Git repository"
}

$gitRoot = [System.IO.Path]::GetFullPath(($gitRootOutput | Select-Object -First 1))
$expectedRoot = [System.IO.Path]::GetFullPath($resolvedRoot)
if (-not $gitRoot.TrimEnd("\", "/").Equals(
        $expectedRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    Stop-HygieneCheck -Message "target must be the Git repository root"
}

$trackedOutput = (& git -c core.quotepath=false -C $resolvedRoot ls-files -z) -join "`n"
if ($LASTEXITCODE -ne 0) {
    Stop-HygieneCheck -Message "git ls-files failed" -ExitCode $LASTEXITCODE
}

$trackedFiles = @($trackedOutput -split "`0" | Where-Object { $_.Length -gt 0 })
$issues = [System.Collections.Generic.List[object]]::new()
$issueKeys = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)

$contentPatterns = [System.Collections.Generic.List[object]]::new()
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "absolute-user-path"
        Regex = [regex]::new('(?i)\b[A-Z]:\\Users\\[^\\\r\n"''<>|]+')
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "absolute-user-path"
        Regex = [regex]::new('(?i)\b[A-Z]:\\UserData\\[^\r\n"''<>|]+')
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "private-key"
        Regex = [regex]::new('-----BEGIN(?:\s+[A-Z0-9]+)?\s+PRIVATE\s+KEY-----')
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "access-token"
        Regex = [regex]::new(
            '(?i)\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b'
        )
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "access-token"
        Regex = [regex]::new(
            '\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'
        )
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "password-or-secret-assignment"
        Regex = [regex]::new(
            '(?im)^\s*["'']?(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token)' +
            '["'']?\s*[:=]\s*["'']?[^\s"''(<{]{8,}'
        )
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "authorization-value"
        Regex = [regex]::new(
            '(?im)^\s*["'']?authorization["'']?\s*[:=]\s*["'']?' +
            '(?:bearer|basic)\s+[A-Za-z0-9+/_.=-]{8,}'
        )
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "cookie-value"
        Regex = [regex]::new(
            '(?im)^\s*["'']?(?:cookie|set-cookie)["'']?\s*[:=]\s*["'']?' +
            '[A-Za-z0-9_.-]{1,64}=[^;\r\n"'']{4,}'
        )
    }
)
$contentPatterns.Add(
    [pscustomobject]@{
        Type = "credential-bearing-url"
        Regex = [regex]::new(
            '(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@'
        )
    }
)

if (-not [string]::IsNullOrWhiteSpace($env:USERNAME)) {
    $escapedUsername = [regex]::Escape($env:USERNAME)
    $contentPatterns.Add(
        [pscustomobject]@{
            Type = "absolute-current-user-path"
            Regex = [regex]::new(
                "(?i)\b[A-Z]:\\(?:Users|UserData)\\$escapedUsername(?:\\|\b)"
            )
        }
    )
}

$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
foreach ($relativePath in $trackedFiles) {
    $normalizedPath = $relativePath.Replace("\", "/")
    foreach ($type in Get-ProhibitedTrackedPathTypes -RelativePath $normalizedPath) {
        Add-HygieneIssue `
            -Issues $issues `
            -IssueKeys $issueKeys `
            -RelativePath $normalizedPath `
            -Type $type
    }

    $platformPath = $normalizedPath.Replace(
        "/",
        [System.IO.Path]::DirectorySeparatorChar
    )
    $fullPath = Join-Path $resolvedRoot $platformPath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        continue
    }

    $item = Get-Item -LiteralPath $fullPath
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        continue
    }

    try {
        $bytes = [System.IO.File]::ReadAllBytes($fullPath)
    } catch {
        Add-HygieneIssue `
            -Issues $issues `
            -IssueKeys $issueKeys `
            -RelativePath $normalizedPath `
            -Type "tracked-file-unreadable"
        continue
    }

    if ($bytes -contains 0) {
        continue
    }

    try {
        $content = $utf8.GetString($bytes)
    } catch [System.Text.DecoderFallbackException] {
        continue
    }

    foreach ($pattern in $contentPatterns) {
        if ($pattern.Regex.IsMatch($content)) {
            Add-HygieneIssue `
                -Issues $issues `
                -IssueKeys $issueKeys `
                -RelativePath $normalizedPath `
                -Type $pattern.Type
        }
    }
}

if ($issues.Count -gt 0) {
    foreach ($issue in $issues | Sort-Object Type, Path) {
        [Console]::Error.WriteLine(
            "[hygiene] violation type=$($issue.Type) file=$($issue.Path)"
        )
    }
    [Console]::Error.WriteLine(
        "[hygiene] failed: $($issues.Count) tracked-file violation(s)"
    )
    exit 1
}

Write-Host "[hygiene] passed: $($trackedFiles.Count) tracked file(s) checked"
exit 0
