[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WorkRoot,
    [ValidateSet("small", "full")]
    [string]$Scale = "small",
    [switch]$KeepData
)

# RF-16 long-form scale evaluation for one explicitly named work root.
# Wraps `.venv/Scripts/python.exe scripts/longform_eval.py`; its JSON summary line is
# passed through unchanged and its exit code is preserved
# (0 every threshold passed, 1 at least one FAIL, 2 invalid arguments or root).
# The work root must be an absolute new or empty folder outside the repository; the
# harness builds its own isolated data roots inside it and never touches author data.
# The default -Scale small is a quick smoke run; contract results come only from
# -Scale full (see docs/LONGFORM_EVALUATION.md).

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
. (Join-Path $PSScriptRoot "invoke_owned_process.ps1")

function Stop-LongformEvaluation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [int]$ExitCode = 2
    )

    [Console]::Error.WriteLine("[longform-eval] $Message")
    exit $ExitCode
}

function Assert-RepositoryRootInvocation {
    $currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
    if (-not $currentDirectory.TrimEnd("\", "/").Equals(
            $repositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-LongformEvaluation -Message "run this script from the repository root"
    }
}

Assert-RepositoryRootInvocation

if ([string]::IsNullOrWhiteSpace($WorkRoot)) {
    Stop-LongformEvaluation -Message "an explicit -WorkRoot is required"
}
if (-not (Test-FullyQualifiedWindowsPath -Value $WorkRoot)) {
    Stop-LongformEvaluation -Message "-WorkRoot must be an absolute Windows path"
}
$resolvedWorkRoot = [System.IO.Path]::GetFullPath($WorkRoot).TrimEnd("\", "/")
$repositoryPrefix = "$($repositoryRoot.TrimEnd('\', '/'))$([System.IO.Path]::DirectorySeparatorChar)"
if (
    $resolvedWorkRoot.Equals($repositoryRoot.TrimEnd("\", "/"), [System.StringComparison]::OrdinalIgnoreCase) -or
    $resolvedWorkRoot.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)
) {
    Stop-LongformEvaluation -Message "-WorkRoot must not be inside the source repository"
}

$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    Stop-LongformEvaluation -Message "root virtual environment is missing" -ExitCode 1
}
$evaluationScript = Join-Path $repositoryRoot "scripts/longform_eval.py"

$arguments = @($evaluationScript, "--work-root", $resolvedWorkRoot, "--scale", $Scale)
if ($KeepData) {
    $arguments += "--keep-data"
}

$global:LASTEXITCODE = 0
& $pythonExecutable @arguments
exit $LASTEXITCODE
