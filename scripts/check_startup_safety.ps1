[CmdletBinding()]
param(
    [string]$RepositoryRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-StartupSafetyCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [int]$ExitCode = 1
    )

    [Console]::Error.WriteLine("[startup-safety] $Message")
    exit $ExitCode
}

function Add-StartupViolation {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Violations,
        [Parameter(Mandatory = $true)]
        [string]$Rule,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $Violations.Add([pscustomobject]@{ Rule = $Rule; Path = $Path })
}

function Get-TrackedSource {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$TrackedPaths,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Violations
    )

    if ($TrackedPaths -notcontains $Path) {
        Add-StartupViolation `
            -Violations $Violations `
            -Rule "required-startup-file-not-tracked" `
            -Path $Path
        return $null
    }
    try {
        $rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd("\", "/")
        $sourcePath = [System.IO.Path]::GetFullPath(
            (Join-Path $rootPath $Path.Replace("/", "\"))
        )
        $rootPrefix = "$rootPath$([System.IO.Path]::DirectorySeparatorChar)"
        if (-not $sourcePath.StartsWith(
                $rootPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
            throw "tracked startup path escaped the repository"
        }
        $item = Get-Item -LiteralPath $sourcePath -Force -ErrorAction Stop
        if (
            $item.PSIsContainer -or
            ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $item.Length -gt 1048576
        ) {
            throw "tracked startup file is not an ordinary bounded file"
        }
        $encoding = [System.Text.UTF8Encoding]::new($false, $true)
        return [System.IO.File]::ReadAllText($sourcePath, $encoding)
    } catch {
        if ($null -eq ($Violations | Where-Object {
                    $_.Rule -eq "tracked-startup-file-unreadable" -and
                    $_.Path -eq $Path
                })) {
            Add-StartupViolation `
                -Violations $Violations `
                -Rule "tracked-startup-file-unreadable" `
                -Path $Path
        }
        return $null
    }
}

function Get-ParsedPowerShell {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Violations
    )

    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput(
        $Source,
        $Path,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if ($parseErrors.Count -gt 0) {
        Add-StartupViolation `
            -Violations $Violations `
            -Rule "startup-powershell-parse-error" `
            -Path $Path
    }
    return $ast
}

function Get-Commands {
    param(
        [Parameter(Mandatory = $true)]
        [System.Management.Automation.Language.Ast]$Ast
    )

    return @(
        $Ast.FindAll(
            {
                param($node)
                return $node -is [System.Management.Automation.Language.CommandAst]
            },
            $true
        )
    )
}

function Test-HasCommand {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Commands,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    foreach ($command in $Commands) {
        if ([string]$command.GetCommandName() -ieq $Name) {
            return $true
        }
    }
    return $false
}

function Test-HasStringConstant {
    param(
        [Parameter(Mandatory = $true)]
        [System.Management.Automation.Language.Ast]$Ast,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $matches = @(
        $Ast.FindAll(
            {
                param($node)
                return (
                    $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
                    $node.Value -ceq $Value
                )
            },
            $true
        )
    )
    return $matches.Count -gt 0
}

function Invoke-StartupSafetyCheck {
    $root = if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
        [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    } else {
        [System.IO.Path]::GetFullPath($RepositoryRoot)
    }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        Stop-StartupSafetyCheck -Message "repository root is unavailable"
    }

    Push-Location $root
    try {
        $gitRootOutput = & git rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -ne 0) {
            Stop-StartupSafetyCheck -Message "repository root is not a Git repository"
        }
        $gitRoot = [System.IO.Path]::GetFullPath(
            ($gitRootOutput | Select-Object -First 1)
        )
        if (-not $gitRoot.TrimEnd("\", "/").Equals(
                $root.TrimEnd("\", "/"),
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
            Stop-StartupSafetyCheck -Message "repository root does not match Git"
        }
        $trackedPaths = @(& git ls-files --)
        if ($LASTEXITCODE -ne 0) {
            Stop-StartupSafetyCheck -Message "Git tracked files could not be read"
        }
    } finally {
        Pop-Location
    }

    $requiredPaths = @(
        "scripts/invoke_owned_process.ps1",
        "scripts/start_development.ps1",
        "scripts/start_integrated.ps1",
        "scripts/check_startup_runtime.ps1"
    )
    $violations = [System.Collections.Generic.List[object]]::new()
    $sources = @{}
    $asts = @{}
    $commandsByPath = @{}
    foreach ($path in $requiredPaths) {
        $source = Get-TrackedSource `
            -Root $root `
            -Path $path `
            -TrackedPaths $trackedPaths `
            -Violations $violations
        if ($null -eq $source) {
            continue
        }
        $sources[$path] = $source
        $ast = Get-ParsedPowerShell `
            -Source $source `
            -Path $path `
            -Violations $violations
        $asts[$path] = $ast
        $commandsByPath[$path] = Get-Commands -Ast $ast
    }

    foreach ($path in $asts.Keys) {
        $commands = $commandsByPath[$path]
        foreach ($command in $commands) {
            $commandName = [string]$command.GetCommandName()
            $commandText = $command.Extent.Text
            if ($commandName -imatch '^(Stop-Process|Kill|pskill|wmic)$') {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "forbidden-process-name-or-ambiguous-kill" `
                    -Path $path
            }
            if (
                $commandName -imatch '^(taskkill|taskkill\.exe)$' -and
                $commandText -match '(?i)(?:^|\s)/IM(?:\s|$)'
            ) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "forbidden-image-name-kill" `
                    -Path $path
            }
            if ($commandName -imatch '^(winget|winget\.exe|choco|scoop)$') {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "forbidden-tool-installer" `
                    -Path $path
            }
            if ($commandName -imatch '^(Start-Service|New-Service|sc|sc\.exe)$') {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "forbidden-windows-service" `
                    -Path $path
            }
            if ($commandName -imatch '^(Invoke-Item|ii|Start)$') {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "forbidden-automatic-open" `
                    -Path $path
            }
            if (
                $commandName -imatch '^(npm|npm\.cmd|npx|npx\.cmd)$' -and
                $commandText -match '(?i)(?:^|\s)(install|ci)(?:\s|$)'
            ) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "forbidden-dependency-install" `
                    -Path $path
            }
            if (
                $commandName -ieq "Start-Process" -and
                $commandText -match '(?i)(https?://|chrome|msedge|firefox)'
            ) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "forbidden-browser-launch" `
                    -Path $path
            }
        }

        $strings = @(
            $asts[$path].FindAll(
                {
                    param($node)
                    return $node -is [System.Management.Automation.Language.StringConstantExpressionAst]
                },
                $true
            ) | ForEach-Object { [string]$_.Value }
        )
        if (@($strings | Where-Object { $_ -match '(?i)(?:^|[\\/])[^\\/]*\.pid$|process\.json|processmanifest' }).Count -gt 0) {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "forbidden-pid-or-process-manifest" `
                -Path $path
        }
    }

    $helperPath = "scripts/invoke_owned_process.ps1"
    if ($asts.ContainsKey($helperPath)) {
        $helperAst = $asts[$helperPath]
        $helperCommands = $commandsByPath[$helperPath]
        foreach ($requiredCommand in @("Get-Process", "taskkill.exe")) {
            if (-not (Test-HasCommand -Commands $helperCommands -Name $requiredCommand)) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "missing-owned-process-command-$requiredCommand" `
                    -Path $helperPath
            }
        }
        $stopFunctions = @(
            $helperAst.FindAll(
                {
                    param($node)
                    return (
                        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                        $node.Name -ceq "Stop-OwnedProcessTree"
                    )
                },
                $true
            )
        )
        if ($stopFunctions.Count -ne 1) {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "missing-owned-process-stop-function" `
                -Path $helperPath
        } else {
            $stopText = $stopFunctions[0].Extent.Text
            foreach ($requiredPattern in @(
                    'Get-OwnedProcessState',
                    'taskkill\.exe\s+/PID\s+\$Record\.ProcessId\s+/T\s+/F'
                )) {
                if ($stopText -notmatch $requiredPattern) {
                    Add-StartupViolation `
                        -Violations $violations `
                        -Rule "missing-pid-start-time-ownership-check" `
                        -Path $helperPath
                    break
                }
            }
            $stopStart = $stopFunctions[0].Extent.StartOffset
            $stopEnd = $stopFunctions[0].Extent.EndOffset
            foreach ($taskkillCommand in @(
                    $helperCommands | Where-Object {
                        [string]$_.GetCommandName() -imatch '^(taskkill|taskkill\.exe)$'
                    }
                )) {
                if (
                    $taskkillCommand.Extent.StartOffset -lt $stopStart -or
                    $taskkillCommand.Extent.EndOffset -gt $stopEnd
                ) {
                    Add-StartupViolation `
                        -Violations $violations `
                        -Rule "taskkill-outside-owned-stop" `
                        -Path $helperPath
                }
            }
        }
        foreach ($requiredPattern in @(
                'ProcessStartInfo',
                'RedirectStandardOutput\s*=\s*\$true',
                'RedirectStandardError\s*=\s*\$true',
                'CopyToAsync',
                '\$process\.Start\(\)',
                'Complete-OwnedProcessCapture'
            )) {
            if ($sources[$helperPath] -notmatch $requiredPattern) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "incomplete-owned-process-output-capture" `
                    -Path $helperPath
                break
            }
        }
        $identityFunctions = @(
            $helperAst.FindAll(
                {
                    param($node)
                    return (
                        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
                        $node.Name -ceq "Get-OwnedProcessState"
                    )
                },
                $true
            )
        )
        if (
            $identityFunctions.Count -ne 1 -or
            $identityFunctions[0].Extent.Text -notmatch 'StartedAtUtcTicks' -or
            $identityFunctions[0].Extent.Text -notmatch 'StartTime\.ToUniversalTime\(\)\.Ticks'
        ) {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "missing-pid-start-time-ownership-check" `
                -Path $helperPath
        }
        if ($sources[$helperPath] -notmatch '\[System\.IO\.Path\]::GetTempPath\(\)') {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "startup-logs-not-system-temp" `
                -Path $helperPath
        }
        if ($sources[$helperPath] -notmatch 'development startup must not use the formal user data root') {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "formal-data-root-not-rejected" `
                -Path $helperPath
        }
        foreach ($requiredPattern in @(
                'formalRoot\.StartsWith\(\$resolvedPrefix',
                'development data root must not overlap the source repository',
                'data root path must not traverse a reparse point'
            )) {
            if ($sources[$helperPath] -notmatch $requiredPattern) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "incomplete-data-root-boundary-check" `
                    -Path $helperPath
                break
            }
        }
    }

    $entryRequirements = @{
        "scripts/start_development.ps1" = @(
            "Start-OwnedProcess",
            "Stop-OwnedProcessGroup",
            "Assert-OwnedLoopbackListener",
            "Wait-LoopbackPortReleased",
            "Initialize-StartupCancellation",
            "Resolve-IsolatedDataRoot"
        )
        "scripts/start_integrated.ps1" = @(
            "Start-OwnedProcess",
            "Stop-OwnedProcessGroup",
            "Assert-OwnedLoopbackListener",
            "Wait-LoopbackPortReleased",
            "Initialize-StartupCancellation",
            "Resolve-IsolatedDataRoot"
        )
    }
    foreach ($entryPath in $entryRequirements.Keys) {
        if (-not $asts.ContainsKey($entryPath)) {
            continue
        }
        foreach ($requiredCommand in $entryRequirements[$entryPath]) {
            if (-not (Test-HasCommand `
                    -Commands $commandsByPath[$entryPath] `
                    -Name $requiredCommand)) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "missing-startup-orchestration-$requiredCommand" `
                    -Path $entryPath
            }
        }
    }

    $developmentPath = "scripts/start_development.ps1"
    if ($asts.ContainsKey($developmentPath)) {
        if (-not (Test-HasStringConstant `
                -Ast $asts[$developmentPath] `
                -Value "AIWebNovel-Development")) {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "missing-development-data-root" `
                -Path $developmentPath
        }
        if ($sources[$developmentPath] -match '(?i)BuildFrontend|npm\.cmd\s+run\s+build') {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "development-must-not-build-frontend" `
                -Path $developmentPath
        }
    }

    $integratedPath = "scripts/start_integrated.ps1"
    if ($asts.ContainsKey($integratedPath)) {
        if (-not (Test-HasStringConstant `
                -Ast $asts[$integratedPath] `
                -Value "AIWebNovel")) {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "missing-integrated-data-root" `
                -Path $integratedPath
        }
        $buildBranches = @(
            $asts[$integratedPath].FindAll(
                {
                    param($node)
                    return (
                        $node -is [System.Management.Automation.Language.IfStatementAst] -and
                        $node.Extent.Text -match '\$BuildFrontend' -and
                        $node.Extent.Text -match 'Start-OwnedProcess' -and
                        $node.Extent.Text -match (
                            'ArgumentList\s+@\(\s*"run"\s*,\s*"build"\s*,\s*' +
                            '"--"\s*,\s*"--"\s*,\s*"--emptyOutDir"\s*,\s*"false"\s*\)'
                        )
                    )
                },
                $true
            )
        )
        if ($buildBranches.Count -eq 0) {
            Add-StartupViolation `
                -Violations $violations `
                -Rule "integrated-build-not-explicitly-gated" `
                -Path $integratedPath
        }
        foreach ($requiredValue in @("production", "true", "false")) {
            if (-not (Test-HasStringConstant -Ast $asts[$integratedPath] -Value $requiredValue)) {
                Add-StartupViolation `
                    -Violations $violations `
                    -Rule "missing-integrated-production-setting" `
                    -Path $integratedPath
                break
            }
        }
    }

    if ($violations.Count -gt 0) {
        foreach ($violation in $violations) {
            [Console]::Error.WriteLine(
                "[startup-safety] rule=$($violation.Rule) file=$($violation.Path)"
            )
        }
        exit 1
    }

    Write-Host "[startup-safety] passed: deterministic startup safeguards are present"
    exit 0
}

Invoke-StartupSafetyCheck
