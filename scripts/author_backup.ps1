[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("create", "list", "verify", "restore")]
    [string]$Command,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [string]$BackupId = "",
    [string]$Target = ""
)

# Author backup command line for one explicitly named data root.
# Wraps `.venv/Scripts/python.exe -m aiwebnovel.backup`; the JSON document it
# prints is passed through unchanged and its exit code is preserved
# (0 success, 1 refused or failed, 2 invalid arguments, 3 damaged or incompatible).
# There is no default data root: tests, E2E and diagnostics must pass their own
# isolated root; an author passes their formal root explicitly.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
. (Join-Path $PSScriptRoot "invoke_owned_process.ps1")

function Stop-AuthorBackup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [int]$ExitCode = 2
    )

    [Console]::Error.WriteLine("[author-backup] $Message")
    exit $ExitCode
}

function Assert-RepositoryRootInvocation {
    $currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
    if (-not $currentDirectory.TrimEnd("\", "/").Equals(
            $repositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-AuthorBackup -Message "run this script from the repository root"
    }
}

Assert-RepositoryRootInvocation

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    Stop-AuthorBackup -Message "an explicit -DataRoot is required"
}
try {
    $resolvedDataRoot = Resolve-IsolatedDataRoot `
        -Candidate $DataRoot `
        -DefaultLeaf "AIWebNovel" `
        -RepositoryRoot $repositoryRoot `
        -AllowFormalRoot
} catch {
    Stop-AuthorBackup -Message "data root rejected: $($_.Exception.Message)"
}
if (-not (Test-Path -LiteralPath $resolvedDataRoot -PathType Container)) {
    Stop-AuthorBackup -Message "data root does not exist" -ExitCode 1
}

$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    Stop-AuthorBackup -Message "root virtual environment is missing" -ExitCode 1
}

$arguments = @("-m", "aiwebnovel.backup", $Command)
switch ($Command) {
    "create" {
        if (-not [string]::IsNullOrWhiteSpace($BackupId) -or -not [string]::IsNullOrWhiteSpace($Target)) {
            Stop-AuthorBackup -Message "create accepts no -BackupId or -Target"
        }
    }
    "list" {
        if (-not [string]::IsNullOrWhiteSpace($BackupId) -or -not [string]::IsNullOrWhiteSpace($Target)) {
            Stop-AuthorBackup -Message "list accepts no -BackupId or -Target"
        }
    }
    "verify" {
        if ([string]::IsNullOrWhiteSpace($BackupId)) {
            Stop-AuthorBackup -Message "verify requires -BackupId"
        }
        if (-not [string]::IsNullOrWhiteSpace($Target)) {
            Stop-AuthorBackup -Message "verify accepts no -Target"
        }
        $arguments += $BackupId
    }
    "restore" {
        if ([string]::IsNullOrWhiteSpace($BackupId)) {
            Stop-AuthorBackup -Message "restore requires -BackupId"
        }
        if ([string]::IsNullOrWhiteSpace($Target)) {
            Stop-AuthorBackup -Message "restore requires -Target (a new or empty folder)"
        }
        if (-not (Test-FullyQualifiedWindowsPath -Value $Target)) {
            Stop-AuthorBackup -Message "restore -Target must be an absolute Windows path"
        }
        $resolvedTarget = [System.IO.Path]::GetFullPath($Target).TrimEnd("\", "/")
        $repositoryPrefix = "$($repositoryRoot.TrimEnd('\', '/'))$([System.IO.Path]::DirectorySeparatorChar)"
        if (
            $resolvedTarget.Equals($repositoryRoot.TrimEnd("\", "/"), [System.StringComparison]::OrdinalIgnoreCase) -or
            $resolvedTarget.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)
        ) {
            Stop-AuthorBackup -Message "restore -Target must not be inside the source repository"
        }
        $arguments += @($BackupId, "--target", $resolvedTarget)
    }
}

$savedEnvironment = @{}
$childEnvironment = @{
    AIWEBNOVEL_DATA_ROOT = $resolvedDataRoot
    AIWEBNOVEL_DATABASE_URL = $null
}
foreach ($name in $childEnvironment.Keys) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    [Environment]::SetEnvironmentVariable($name, $childEnvironment[$name], "Process")
}
try {
    $global:LASTEXITCODE = 0
    & $pythonExecutable @arguments
    $exitCode = $LASTEXITCODE
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }
}
exit $exitCode
