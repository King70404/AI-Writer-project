[CmdletBinding()]
param(
    [string]$RepositoryRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot "..")
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-SecurityBaseline {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [int]$ExitCode = 1
    )

    [Console]::Error.WriteLine("[security-baseline] $Message")
    exit $ExitCode
}

function ConvertTo-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalized = $Path.Replace("\", "/")
    while ($normalized.StartsWith("./", [System.StringComparison]::Ordinal)) {
        $normalized = $normalized.Substring(2)
    }
    return $normalized
}

function Test-IsSecuritySource {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $normalized = ConvertTo-RepositoryPath -Path $Path
    if ($normalized -match '^backend/src/.+\.py$') {
        return $true
    }
    if ($normalized -match '^frontend/src/.+\.(?:js|jsx|ts|tsx)$') {
        return $true
    }
    if ($normalized -match '^frontend/(?:[^/]+\.(?:js|ts)|package\.json)$') {
        return $true
    }
    if ($normalized -eq "backend/pyproject.toml") {
        return $true
    }
    return (
        $normalized -match '^scripts/.+\.ps1$' -and
        $normalized -ne "scripts/check_security_baseline.ps1"
    )
}

function Add-SecurityViolation {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Violations,
        [Parameter(Mandatory = $true)]
        [string]$Rule,
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $Violations.Add(
        [pscustomobject]@{
            Rule = $Rule
            Path = ConvertTo-RepositoryPath -Path $Path
        }
    )
}

function Get-TrackedText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [System.Collections.Generic.HashSet[string]]$TrackedFiles,
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Violations
    )

    $normalized = ConvertTo-RepositoryPath -Path $Path
    if (-not $TrackedFiles.Contains($normalized)) {
        Add-SecurityViolation `
            -Violations $Violations `
            -Rule "required-security-file-not-tracked" `
            -Path $normalized
        return $null
    }

    $absolutePath = [System.IO.Path]::GetFullPath(
        (Join-Path $Root $normalized)
    )
    $rootPrefix = $Root.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    if (-not $absolutePath.StartsWith(
            $rootPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-SecurityBaseline -Message "tracked path escaped repository boundary"
    }
    if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
        Add-SecurityViolation `
            -Violations $Violations `
            -Rule "tracked-security-file-missing" `
            -Path $normalized
        return $null
    }
    $parentPath = [System.IO.Path]::GetDirectoryName($absolutePath)
    while (
        -not [string]::IsNullOrWhiteSpace($parentPath) -and
        -not $parentPath.TrimEnd("\", "/").Equals(
            $Root.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        try {
            $parentAttributes = [System.IO.File]::GetAttributes($parentPath)
        } catch {
            Add-SecurityViolation `
                -Violations $Violations `
                -Rule "tracked-security-file-unreadable" `
                -Path $normalized
            return $null
        }
        if (
            ($parentAttributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
        ) {
            Add-SecurityViolation `
                -Violations $Violations `
                -Rule "tracked-security-path-is-reparse-point" `
                -Path $normalized
            return $null
        }
        $parentPath = [System.IO.Path]::GetDirectoryName($parentPath)
    }
    try {
        $attributes = [System.IO.File]::GetAttributes($absolutePath)
    } catch {
        Add-SecurityViolation `
            -Violations $Violations `
            -Rule "tracked-security-file-unreadable" `
            -Path $normalized
        return $null
    }
    if (
        ($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
    ) {
        Add-SecurityViolation `
            -Violations $Violations `
            -Rule "tracked-security-path-is-reparse-point" `
            -Path $normalized
        return $null
    }

    try {
        $strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)
        return [System.IO.File]::ReadAllText($absolutePath, $strictUtf8)
    } catch {
        Add-SecurityViolation `
            -Violations $Violations `
            -Rule "security-source-not-valid-utf8" `
            -Path $normalized
        return $null
    }
}

function Invoke-SecurityAstCheck {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.Generic.HashSet[string]]$TrackedFiles,
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Violations
    )

    $helperPath = "scripts/check_security_ast.py"
    $requiredAstInputs = @(
        $helperPath,
        "backend/src/aiwebnovel/main.py",
        "backend/src/aiwebnovel/core/config.py",
        "backend/src/aiwebnovel/security/csrf.py",
        "backend/src/aiwebnovel/__main__.py",
        "backend/src/aiwebnovel/project/web/router.py",
        "backend/src/aiwebnovel/project/web/errors.py",
        "backend/src/aiwebnovel/project/web/dto.py"
    )
    $allInputsReady = $true
    foreach ($requiredPath in $requiredAstInputs) {
        $requiredText = Get-TrackedText `
            -Path $requiredPath `
            -TrackedFiles $TrackedFiles `
            -Root $Root `
            -Violations $Violations
        if ($null -eq $requiredText) {
            $allInputsReady = $false
        }
    }
    if (-not $allInputsReady) {
        return
    }

    $helperAbsolutePath = Join-Path $Root $helperPath
    $virtualEnvironmentPython = Join-Path $Root ".venv/Scripts/python.exe"
    if (Test-Path -LiteralPath $virtualEnvironmentPython -PathType Leaf) {
        $pythonCommand = $virtualEnvironmentPython
        $pythonArguments = @($helperAbsolutePath, $Root)
    } elseif ($null -ne (Get-Command py -ErrorAction SilentlyContinue)) {
        $pythonCommand = "py"
        $pythonArguments = @("-3.12", $helperAbsolutePath, $Root)
    } elseif ($null -ne (Get-Command python -ErrorAction SilentlyContinue)) {
        $pythonCommand = "python"
        $pythonArguments = @($helperAbsolutePath, $Root)
    } else {
        Add-SecurityViolation `
            -Violations $Violations `
            -Rule "security-ast-check-python-unavailable" `
            -Path $helperPath
        return
    }

    $astOutput = @(& $pythonCommand @pythonArguments 2>$null)
    $astExitCode = $LASTEXITCODE
    $parsedViolationCount = 0
    foreach ($line in $astOutput) {
        if ($line -match '^(?<rule>[a-z0-9-]+)\t(?<path>[A-Za-z0-9_./-]+)$') {
            Add-SecurityViolation `
                -Violations $Violations `
                -Rule $Matches.rule `
                -Path $Matches.path
            $parsedViolationCount += 1
        } elseif (-not [string]::IsNullOrWhiteSpace($line)) {
            Add-SecurityViolation `
                -Violations $Violations `
                -Rule "security-ast-check-invalid-output" `
                -Path $helperPath
        }
    }
    if ($astExitCode -ne 0 -and $parsedViolationCount -eq 0) {
        Add-SecurityViolation `
            -Violations $Violations `
            -Rule "security-ast-check-failed" `
            -Path $helperPath
    }
}

function Invoke-SecurityBaselineCheck {
    $repositoryRoot = [System.IO.Path]::GetFullPath($RepositoryRoot)
    $currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
    if (-not $currentDirectory.TrimEnd("\", "/").Equals(
            $repositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-SecurityBaseline -Message "run this script from the repository root"
    }

    $gitRootOutput = & git -C $repositoryRoot rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0) {
        Stop-SecurityBaseline -Message "repository root is not a Git repository"
    }
    $gitRoot = [System.IO.Path]::GetFullPath(
        ($gitRootOutput | Select-Object -First 1)
    )
    if (-not $gitRoot.TrimEnd("\", "/").Equals(
            $repositoryRoot.TrimEnd("\", "/"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        Stop-SecurityBaseline -Message "repository root does not match the Git work tree"
    }

    $trackedOutput = (
        & git -c core.quotepath=false -C $repositoryRoot ls-files -z --
    ) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        Stop-SecurityBaseline -Message "unable to enumerate Git tracked files"
    }
    $trackedFiles = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::Ordinal
    )
    foreach ($path in @($trackedOutput -split "`0" | Where-Object { $_.Length -gt 0 })) {
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            $null = $trackedFiles.Add((ConvertTo-RepositoryPath -Path $path))
        }
    }

    $violations = [System.Collections.Generic.List[object]]::new()
    $rules = @(
        [pscustomobject]@{
            Name = "wildcard-cors"
            Pattern = '(?is)(?:\ballow_origins\s*=|["'']allow_origins["'']\s*:|\ballowOrigins\s*:)\s*(?:["'']\*["'']|[\[(][^\])]{0,2048}["'']\*["''][^\])]{0,2048}[\])])'
        },
        [pscustomobject]@{
            Name = "cors-credentials-enabled"
            Pattern = '(?is)(?:\ballow_credentials\s*=|["'']allow_credentials["'']\s*:|\ballowCredentials\s*:)\s*(?:\(\s*)?(?:True|true)\b'
        },
        [pscustomobject]@{
            Name = "proxy-headers-trusted"
            Pattern = '(?is)(?:\bproxy_headers\s*=|["'']proxy_headers["'']\s*:|\bproxyHeaders\s*:)\s*(?:\(\s*)?(?:True|true)\b'
        },
        [pscustomobject]@{
            Name = "non-loopback-default-bind"
            Pattern = '(?im)(?:\b(?:host|bind_host|listen_host)\s*(?<![=!<>])=|["''](?:host|bind_host|listen_host)["'']\s*:|\b(?:host|bindHost|listenHost)\s*:)\s*["''](?:0\.0\.0\.0|::)["'']'
        },
        [pscustomobject]@{
            Name = "plaintext-secret"
            Pattern = '(?im)["'']?\b(?:access_token|refresh_token|password|api_key|client_secret|authorization)\b["'']?\s*[:=]\s*["''](?!\[?REDACTED\]?|<redacted>|replace-me)[^"''\r\n]{8,}["'']'
        },
        [pscustomobject]@{
            Name = "csrf-browser-persistence"
            Pattern = '(?is)(?:localStorage|sessionStorage)\s*(?:\.\s*setItem\s*\([^)]{0,1024}(?:csrf|token)|\.\s*[A-Za-z_$][\w$]*(?:csrf|token)[\w$]*\s*=|\[\s*["''][^"'']{0,256}(?:csrf|token)[^"'']{0,256}["'']\s*\]\s*=)'
        },
        [pscustomobject]@{
            Name = "sensitive-security-log"
            Pattern = '(?is)(?:(?:\b(?:logger|logging|console)\s*\.\s*\w+|\bprint)\s*\([^)]{0,1024}(?<!["''])\b(?:csrf_token|session_id|session_cookie|cookie_value|csrfToken|sessionId|sessionCookie|cookieValue)\b(?!["''])|\bWrite-(?:Host|Output|Verbose|Debug|Information)\b(?:\s*\(|\s+)[^\r\n)]{0,1024}\$(?:csrfToken|csrf_token|sessionId|session_id|sessionCookie|session_cookie|cookieValue|cookie_value)\b)'
        },
        [pscustomobject]@{
            Name = "host-validation-disabled"
            Pattern = '(?is)(?:(?:trusted_hosts|allowed_hosts)\s*[:=]\s*(?:["'']\*["'']|[\[(][^\])]{0,2048}["'']\*["''][^\])]{0,2048}[\])])|host_validation_(?:enabled\s*[:=]\s*(?:\(\s*)?(?:False|false)|disabled\s*[:=]\s*(?:\(\s*)?(?:True|true)))'
        }
    )

    $scannedCount = 0
    foreach ($relativePath in ($trackedFiles | Sort-Object)) {
        if (-not (Test-IsSecuritySource -Path $relativePath)) {
            continue
        }
        $scannedCount += 1
        $text = Get-TrackedText `
            -Path $relativePath `
            -TrackedFiles $trackedFiles `
            -Root $repositoryRoot `
            -Violations $violations
        if ($null -eq $text) {
            continue
        }
        foreach ($rule in $rules) {
            if ([System.Text.RegularExpressions.Regex]::IsMatch($text, $rule.Pattern)) {
                Add-SecurityViolation `
                    -Violations $violations `
                    -Rule $rule.Name `
                    -Path $relativePath
            }
        }
    }

    Invoke-SecurityAstCheck `
        -TrackedFiles $trackedFiles `
        -Root $repositoryRoot `
        -Violations $violations

    $uniqueViolations = @(
        $violations |
            Sort-Object Rule, Path -Unique
    )
    if ($uniqueViolations.Count -gt 0) {
        foreach ($violation in $uniqueViolations) {
            [Console]::Error.WriteLine(
                "[security-baseline] violation type=$($violation.Rule) file=$($violation.Path)"
            )
        }
        Stop-SecurityBaseline -Message (
            "failed with $($uniqueViolations.Count) tracked-source violation(s)"
        )
    }

    Write-Host (
        "[security-baseline] passed: scanned $scannedCount Git tracked code/config file(s)"
    )
}

if ($MyInvocation.InvocationName -ne ".") {
    Invoke-SecurityBaselineCheck
}
