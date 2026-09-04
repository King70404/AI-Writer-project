[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Backend", "Vite")]
    [string]$Service,
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 65535)]
    [int]$Port,
    [ValidateRange(0, 65535)]
    [int]$BackendPort = 0,
    [ValidateRange(0, 65535)]
    [int]$CorsPort = 0,
    [ValidateRange(0, 65535)]
    [int]$AIProviderPort = 0,
    [string]$DataRoot = "",
    [switch]$ServeFrontend,
    [switch]$MigrateDatabase,
    [string]$FrontendDistPath = "",
    [Parameter(Mandatory = $true)]
    [string]$ProcessManifestPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-ServiceLauncher {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    [Console]::Error.WriteLine("[e2e-service] $Message")
    exit 1
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

function Get-ValidatedContainedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$Container,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        Stop-ServiceLauncher -Message "$Description is required"
    }
    if (-not (Test-FullyQualifiedWindowsPath -Value $Candidate)) {
        Stop-ServiceLauncher -Message "$Description must be an absolute path"
    }

    $fullCandidate = [System.IO.Path]::GetFullPath($Candidate)
    $fullContainer = [System.IO.Path]::GetFullPath($Container).TrimEnd("\", "/")
    if (Test-Path -LiteralPath $fullContainer) {
        $containerItem = Get-Item -LiteralPath $fullContainer -Force
        if (($containerItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Stop-ServiceLauncher -Message "$Description root must not be a reparse point"
        }
    }
    $containerPrefix = "$fullContainer$([System.IO.Path]::DirectorySeparatorChar)"
    if (-not $fullCandidate.StartsWith(
            $containerPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-ServiceLauncher -Message "$Description must stay inside its controlled root"
    }

    $relativePath = $fullCandidate.Substring($containerPrefix.Length)
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
            Stop-ServiceLauncher -Message "$Description must not traverse a reparse point"
        }
    }

    return $fullCandidate
}

function ConvertTo-SafeProcessArgument {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if ($Value.Contains('"')) {
        Stop-ServiceLauncher -Message "process argument contains an unsupported quote"
    }
    if ($Value -match '\s') {
        return '"{0}"' -f $Value
    }
    return $Value
}

function Invoke-ManagedServiceProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$ManifestPath
    )

    $safeArguments = @(
        $ArgumentList | ForEach-Object { ConvertTo-SafeProcessArgument -Value $_ }
    )
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $safeArguments `
        -WorkingDirectory $WorkingDirectory `
        -NoNewWindow `
        -PassThru
    $startedAtUtcTicks = $process.StartTime.ToUniversalTime().Ticks
    try {
        $manifest = [ordered]@{
            process_id = $process.Id
            started_at_utc_ticks = $startedAtUtcTicks
            executable_name = [System.IO.Path]::GetFileName($FilePath)
        } | ConvertTo-Json -Compress
        [System.IO.File]::WriteAllText(
            $ManifestPath,
            $manifest + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    } catch {
        $current = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
        if ($null -ne $current) {
            if ($current.StartTime.ToUniversalTime().Ticks -ne $startedAtUtcTicks) {
                throw "service manifest failed and the process identifier was reused"
            }
            & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            $process.WaitForExit(10000)
            $process.Refresh()
            if (-not $process.HasExited) {
                throw "service manifest failed and the owned process tree could not be stopped"
            }
        }
        throw "service process registration failed; the owned process tree was stopped"
    }
    $process.WaitForExit()
    exit $process.ExitCode
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runtimeRoot = Join-Path $repositoryRoot ".runtime/e2e"
$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
$frontendRoot = Join-Path $repositoryRoot "frontend"
$manifestFullPath = Get-ValidatedContainedPath `
    -Candidate $ProcessManifestPath `
    -Container $runtimeRoot `
    -Description "service process manifest path"
$manifestParent = Split-Path -Parent $manifestFullPath
if (-not (Test-Path -LiteralPath $manifestParent -PathType Container)) {
    Stop-ServiceLauncher -Message "service process manifest directory is missing"
}
$manifestParentParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $manifestParent))
if (-not $manifestParentParent.Equals(
        [System.IO.Path]::GetFullPath($runtimeRoot),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    Stop-ServiceLauncher -Message "service process manifest must belong to one E2E run"
}
$runDirectoryName = Split-Path -Leaf $manifestParent
if ($runDirectoryName -notmatch '^e2e-(?:dev|int|startup)-\d{3}-\d+-[0-9a-f]{32}$') {
    Stop-ServiceLauncher -Message "service process manifest run lacks its ownership marker"
}
if ($Service -eq "Vite" -and -not [string]::IsNullOrWhiteSpace($DataRoot)) {
    Stop-ServiceLauncher -Message "Vite must not receive an application data root"
}

if ($Service -eq "Backend") {
    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        Stop-ServiceLauncher -Message "root virtual environment is missing"
    }

    $dataRootFullPath = Get-ValidatedContainedPath `
        -Candidate $DataRoot `
        -Container $manifestParent `
        -Description "E2E data root"
    $dataRootParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $dataRootFullPath))
    if (-not $dataRootParent.Equals(
            [System.IO.Path]::GetFullPath($manifestParent),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-ServiceLauncher -Message "E2E data root must be a direct child of its run directory"
    }
    $dataRootName = Split-Path -Leaf $dataRootFullPath
    if ($dataRootName -notmatch '^AIWebNovel-E2E-DataRoot-[0-9a-f]{32}$') {
        Stop-ServiceLauncher -Message "E2E data root must carry its exact ownership marker"
    }
    if (Test-Path -LiteralPath $dataRootFullPath) {
        Stop-ServiceLauncher -Message "E2E data root must be created by storage initialization"
    }

    $env:AIWEBNOVEL_APP_NAME = "AIWebNovel"
    $env:AIWEBNOVEL_APP_VERSION = "0.0.0"
    $env:AIWEBNOVEL_ENVIRONMENT = if ($ServeFrontend) {
        "production"
    } else {
        "development"
    }
    $env:AIWEBNOVEL_API_PREFIX = "/api/v1"
    $env:AIWEBNOVEL_HOST = "127.0.0.1"
    $env:AIWEBNOVEL_PORT = $Port.ToString()
    $env:AIWEBNOVEL_LOG_LEVEL = "WARNING"
    if ($AIProviderPort -gt 0) {
        $env:AIWEBNOVEL_AI_BASE_URL = "http://127.0.0.1:$AIProviderPort"
        $env:AIWEBNOVEL_AI_MODEL = "e2e-ai-model"
    } else {
        [Environment]::SetEnvironmentVariable("AIWEBNOVEL_AI_BASE_URL", $null, "Process")
        [Environment]::SetEnvironmentVariable("AIWEBNOVEL_AI_MODEL", $null, "Process")
    }
    $env:AIWEBNOVEL_DATA_ROOT = $dataRootFullPath
    [Environment]::SetEnvironmentVariable(
        "AIWEBNOVEL_DATABASE_URL",
        $null,
        "Process"
    )
    $env:AIWEBNOVEL_DATABASE_ECHO = "false"
    $env:AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS = "5000"
    $env:AIWEBNOVEL_SERVE_FRONTEND = if ($ServeFrontend) { "true" } else { "false" }
    $env:AIWEBNOVEL_EXPOSE_API_DOCS = if ($ServeFrontend) { "false" } else { "true" }

    if ($CorsPort -gt 0) {
        $env:AIWEBNOVEL_CORS_ALLOWED_ORIGINS = (
            '["http://127.0.0.1:{0}"]' -f $CorsPort
        )
    } else {
        $env:AIWEBNOVEL_CORS_ALLOWED_ORIGINS = (
            '["http://127.0.0.1:{0}"]' -f $Port
        )
    }

    if ($ServeFrontend) {
        $frontendFullPath = Get-ValidatedContainedPath `
            -Candidate $FrontendDistPath `
            -Container $repositoryRoot `
            -Description "frontend build path"
        $env:AIWEBNOVEL_FRONTEND_DIST_PATH = $frontendFullPath
    } else {
        $env:AIWEBNOVEL_FRONTEND_DIST_PATH = Join-Path $frontendRoot "dist"
    }

    if ($MigrateDatabase) {
        Set-Location $repositoryRoot
        & $pythonExecutable -m alembic -c backend/alembic.ini upgrade head
        if ($LASTEXITCODE -ne 0) {
            Stop-ServiceLauncher -Message "explicit E2E database migration failed"
        }
    }

    Set-Location $repositoryRoot
    Invoke-ManagedServiceProcess `
        -FilePath $pythonExecutable `
        -ArgumentList @("-m", "aiwebnovel") `
        -WorkingDirectory $repositoryRoot `
        -ManifestPath $manifestFullPath
}

if ($BackendPort -eq 0) {
    Stop-ServiceLauncher -Message "Vite requires a loopback backend port"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules") -PathType Container)) {
    Stop-ServiceLauncher -Message "frontend dependencies are missing"
}
if ($null -eq (Get-Command "npm.cmd" -ErrorAction SilentlyContinue)) {
    Stop-ServiceLauncher -Message "npm.cmd is unavailable"
}
$nodeCommand = Get-Command "node.exe" -ErrorAction SilentlyContinue
if ($null -eq $nodeCommand) {
    Stop-ServiceLauncher -Message "node.exe is unavailable"
}
$viteCli = Join-Path $frontendRoot "node_modules/vite/bin/vite.js"
if (-not (Test-Path -LiteralPath $viteCli -PathType Leaf)) {
    Stop-ServiceLauncher -Message "local Vite CLI is missing"
}

[Environment]::SetEnvironmentVariable("AIWEBNOVEL_DATA_ROOT", $null, "Process")
[Environment]::SetEnvironmentVariable("AIWEBNOVEL_DATABASE_URL", $null, "Process")
$env:AIWEBNOVEL_VITE_BACKEND_URL = "http://127.0.0.1:$BackendPort"
$env:AIWEBNOVEL_E2E_DISABLE_HMR = "1"
$env:VITE_API_BASE_URL = "/api/v1"
$env:NODE_ENV = "development"
Set-Location $frontendRoot
Invoke-ManagedServiceProcess `
    -FilePath $nodeCommand.Source `
    -ArgumentList @(
        $viteCli,
        "--host",
        "127.0.0.1",
        "--port",
        $Port.ToString(),
        "--strictPort"
    ) `
    -WorkingDirectory $frontendRoot `
    -ManifestPath $manifestFullPath
