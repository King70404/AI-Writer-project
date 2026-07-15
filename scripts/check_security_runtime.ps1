[CmdletBinding()]
param(
    [ValidateRange(0, 65535)]
    [int]$Port = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

function Test-LoopbackPortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$CandidatePort
    )

    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        $CandidatePort
    )
    try {
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Get-TemporaryLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    try {
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function Wait-LoopbackPortReleased {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidatePort,
        [int]$TimeoutSeconds = 10
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (Test-LoopbackPortAvailable -CandidatePort $CandidatePort) {
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "owned security smoke-test port was not released"
}

function Test-ProcessDescendsFrom {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidateProcessId,
        [Parameter(Mandatory = $true)]
        [int]$AncestorProcessId
    )

    for ($depth = 0; $depth -lt 32 -and $CandidateProcessId -gt 0; $depth++) {
        if ($CandidateProcessId -eq $AncestorProcessId) {
            return $true
        }
        $processRecord = Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId = $CandidateProcessId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $processRecord) {
            return $false
        }
        $CandidateProcessId = [int]$processRecord.ParentProcessId
    }
    return $false
}

function Get-OwnedLoopbackListener {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidatePort,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Launcher
    )

    $listeners = @(
        Get-NetTCPConnection `
            -State Listen `
            -LocalPort $CandidatePort `
            -ErrorAction SilentlyContinue
    )
    if ($listeners.Count -ne 1) {
        throw "service must own exactly one listener on the temporary port"
    }
    if ([string]$listeners[0].LocalAddress -ne "127.0.0.1") {
        throw "service listener is not restricted to the IPv4 loopback address"
    }
    $listenerProcessId = [int]$listeners[0].OwningProcess
    if (-not (Test-ProcessDescendsFrom `
            -CandidateProcessId $listenerProcessId `
            -AncestorProcessId $Launcher.Id)) {
        throw "loopback listener does not belong to the owned process tree"
    }
    $listenerProcess = Get-Process -Id $listenerProcessId -ErrorAction Stop
    return [pscustomobject]@{
        ProcessId = $listenerProcessId
        StartedAtUtcTicks = $listenerProcess.StartTime.ToUniversalTime().Ticks
    }
}

function Stop-OwnedProcessTree {
    param(
        [Parameter(Mandatory = $true)]
        [int]$OwnedProcessId,
        [Parameter(Mandatory = $true)]
        [long]$StartedAtUtcTicks
    )

    $current = Get-Process -Id $OwnedProcessId -ErrorAction SilentlyContinue
    if ($null -eq $current) {
        return
    }
    if ($current.StartTime.ToUniversalTime().Ticks -ne $StartedAtUtcTicks) {
        throw "refusing to stop a reused process identifier"
    }
    & taskkill.exe /PID $OwnedProcessId /T /F 2>$null | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        if ($null -eq (Get-Process -Id $OwnedProcessId -ErrorAction SilentlyContinue)) {
            return
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "owned security smoke-test process did not stop"
}

function Assert-OrdinaryDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Description is not an existing directory"
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Description must not be a reparse point"
    }
}

function Assert-DirectOwnedRunDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedParent,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedLeaf
    )

    if ($ExpectedLeaf -notmatch '^security-smoke-\d+-[0-9a-f]{32}$') {
        throw "security smoke-test run name is not recognized"
    }
    $fullCandidate = [System.IO.Path]::GetFullPath($Candidate).TrimEnd("\", "/")
    $fullParent = [System.IO.Path]::GetFullPath($ExpectedParent).TrimEnd("\", "/")
    if (-not [System.IO.Path]::GetDirectoryName($fullCandidate).Equals(
            $fullParent,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "security smoke-test run must be a direct child of its controlled root"
    }
    if (-not [System.IO.Path]::GetFileName($fullCandidate).Equals(
            $ExpectedLeaf,
            [System.StringComparison]::Ordinal
        )) {
        throw "security smoke-test run identity changed"
    }
}

function Assert-DirectOwnedDataRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedParent,
        [Parameter(Mandatory = $true)]
        [string]$ExpectedToken
    )

    $expectedLeaf = "AIWebNovel-Security-DataRoot-$ExpectedToken"
    if ($ExpectedToken -notmatch '^[0-9a-f]{32}$') {
        throw "security smoke-test data token is invalid"
    }
    $fullCandidate = [System.IO.Path]::GetFullPath($Candidate).TrimEnd("\", "/")
    $fullParent = [System.IO.Path]::GetFullPath($ExpectedParent).TrimEnd("\", "/")
    if (-not [System.IO.Path]::GetDirectoryName($fullCandidate).Equals(
            $fullParent,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "security smoke-test data root must be a direct child of its run"
    }
    if (-not [System.IO.Path]::GetFileName($fullCandidate).Equals(
            $expectedLeaf,
            [System.StringComparison]::Ordinal
        )) {
        throw "security smoke-test data root identity changed"
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
        $currentPath = $pending.Pop()
        $currentItem = Get-Item -LiteralPath $currentPath -Force
        if (($currentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "refusing to traverse or remove a reparse point"
        }
        if (-not $currentItem.PSIsContainer) {
            continue
        }
        foreach ($child in Get-ChildItem -LiteralPath $currentPath -Force) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "refusing to traverse or remove a reparse point"
            }
            if ($child.PSIsContainer) {
                $pending.Push($child.FullName)
            }
        }
    }
}

function New-LocalHttpClient {
    param(
        [Parameter(Mandatory = $true)]
        [uri]$BaseUri
    )

    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseCookies = $true
    $handler.CookieContainer = [System.Net.CookieContainer]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler, $true)
    $client.BaseAddress = $BaseUri
    $client.Timeout = [TimeSpan]::FromSeconds(10)
    return [pscustomobject]@{
        Client = $client
        Handler = $handler
    }
}

function Invoke-LocalRequest {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpClient]$Client,
        [Parameter(Mandatory = $true)]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [hashtable]$Headers = @{},
        [AllowNull()]
        [string]$Body = $null,
        [string]$ContentType = "application/json",
        [string]$HostHeader = ""
    )

    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::new($Method),
        $Path
    )
    try {
        if (-not [string]::IsNullOrWhiteSpace($HostHeader)) {
            $request.Headers.Host = $HostHeader
        }
        foreach ($entry in $Headers.GetEnumerator()) {
            if (-not $request.Headers.TryAddWithoutValidation(
                    [string]$entry.Key,
                    [string]$entry.Value
                )) {
                throw "a smoke-test request header was rejected locally"
            }
        }
        if ($PSBoundParameters.ContainsKey("Body")) {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
            $request.Content = [System.Net.Http.ByteArrayContent]::new($bytes)
            $request.Content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse(
                $ContentType
            )
        }
        $response = $Client.SendAsync($request).GetAwaiter().GetResult()
        $request.Dispose()
        return $response
    } catch {
        $request.Dispose()
        throw
    }
}

function Get-ResponseHeader {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpResponseMessage]$Response,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    try {
        if ($Response.Headers.Contains($Name)) {
            return [string]::Join(", ", @($Response.Headers.GetValues($Name)))
        }
    } catch {
        # .NET rejects content-header names against the general header collection.
    }
    try {
        if ($Response.Content.Headers.Contains($Name)) {
            return [string]::Join(", ", @($Response.Content.Headers.GetValues($Name)))
        }
    } catch {
        # .NET rejects general-header names against the content header collection.
    }
    return ""
}

function Read-ResponseText {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpResponseMessage]$Response
    )
    return $Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
}

function Assert-ApiSecurityHeaders {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpResponseMessage]$Response,
        [switch]$AllowCache
    )

    $expected = [ordered]@{
        "X-Content-Type-Options" = "nosniff"
        "Referrer-Policy" = "no-referrer"
        "X-Frame-Options" = "DENY"
        "Cross-Origin-Opener-Policy" = "same-origin"
    }
    foreach ($entry in $expected.GetEnumerator()) {
        if ((Get-ResponseHeader -Response $Response -Name $entry.Key) -ne $entry.Value) {
            throw "an API security response header is missing or invalid"
        }
    }
    $permissionsPolicy = Get-ResponseHeader -Response $Response -Name "Permissions-Policy"
    foreach ($directive in @(
            "camera=()",
            "microphone=()",
            "geolocation=()",
            "payment=()",
            "usb=()"
        )) {
        if (-not $permissionsPolicy.Contains($directive)) {
            throw "the API Permissions-Policy is incomplete"
        }
    }
    if (
        -not $AllowCache -and
        -not (Get-ResponseHeader -Response $Response -Name "Cache-Control").Contains("no-store")
    ) {
        throw "API responses must disable caching"
    }
    if (-not [string]::IsNullOrWhiteSpace(
            (Get-ResponseHeader -Response $Response -Name "Server")
        )) {
        throw "API responses expose a server header"
    }
}

function Assert-HtmlContentSecurityPolicy {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpResponseMessage]$Response
    )

    $csp = Get-ResponseHeader -Response $Response -Name "Content-Security-Policy"
    foreach ($directive in @(
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'"
        )) {
        if (-not $csp.Contains($directive)) {
            throw "the production HTML Content-Security-Policy is incomplete"
        }
    }
    if (
        $csp.Contains("unsafe-eval") -or
        $csp.Contains("unsafe-inline") -or
        $csp -match '(?:^|[;\s])\*(?:[;\s]|$)'
    ) {
        throw "the production HTML Content-Security-Policy is unsafe"
    }
}

function Get-JsonPayload {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpResponseMessage]$Response
    )

    try {
        return (Read-ResponseText -Response $Response) | ConvertFrom-Json
    } catch {
        throw "a security smoke-test response was not valid JSON"
    }
}

function Wait-ReadyResponse {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpClient]$Client,
        [Parameter(Mandatory = $true)]
        [System.Diagnostics.Process]$Launcher,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastStatus = 0
    $transportFailures = 0
    $lastTransportError = "none"
    do {
        $Launcher.Refresh()
        if ($Launcher.HasExited) {
            throw "security smoke-test service exited before becoming ready"
        }
        try {
            $response = Invoke-LocalRequest `
                -Client $Client `
                -Method "GET" `
                -Path "/api/v1/health/ready" `
                -Headers @{ Accept = "application/json" }
            if ([int]$response.StatusCode -eq 200) {
                return $response
            }
            $lastStatus = [int]$response.StatusCode
            $response.Dispose()
        } catch {
            # The owned service can refuse connections while it starts.
            $transportFailures += 1
            $lastTransportError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw (
        "security smoke-test service did not become ready " +
        "(last_status=$lastStatus transport_failures=$transportFailures " +
        "last_transport_error=$lastTransportError)"
    )
}

function Invoke-ChunkedOversizeRequest {
    param(
        [Parameter(Mandatory = $true)]
        [int]$CandidatePort,
        [Parameter(Mandatory = $true)]
        [string]$SessionValue,
        [Parameter(Mandatory = $true)]
        [string]$CsrfToken
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect("127.0.0.1", $CandidatePort)
        $stream = $client.GetStream()
        $stream.ReadTimeout = 10000
        $stream.WriteTimeout = 10000
        $sessionCookieHeader = "Cookie: " + "aiwebnovel_session=$SessionValue"
        $headerText = (
            "POST /api/v1/missing HTTP/1.1`r`n" +
            "Host: 127.0.0.1:$CandidatePort`r`n" +
            "Accept: application/json`r`n" +
            "Content-Type: application/json`r`n" +
            "Transfer-Encoding: chunked`r`n" +
            "Origin: http://127.0.0.1:$CandidatePort`r`n" +
            "$sessionCookieHeader`r`n" +
            "X-CSRF-Token: $CsrfToken`r`n" +
            "Connection: close`r`n`r`n"
        )
        $headerBytes = [System.Text.Encoding]::ASCII.GetBytes($headerText)
        $stream.Write($headerBytes, 0, $headerBytes.Length)
        $chunkData = [byte[]]::new(65536)
        $chunkPrefix = [System.Text.Encoding]::ASCII.GetBytes("10000`r`n")
        $chunkSuffix = [System.Text.Encoding]::ASCII.GetBytes("`r`n")
        try {
            for ($index = 0; $index -lt 17; $index++) {
                $stream.Write($chunkPrefix, 0, $chunkPrefix.Length)
                $stream.Write($chunkData, 0, $chunkData.Length)
                $stream.Write($chunkSuffix, 0, $chunkSuffix.Length)
                $stream.Flush()
            }
            $terminator = [System.Text.Encoding]::ASCII.GetBytes("0`r`n`r`n")
            $stream.Write($terminator, 0, $terminator.Length)
            $stream.Flush()
        } catch [System.IO.IOException] {
            # The server may stop accepting body bytes immediately after the limit.
        }

        $buffer = [byte[]]::new(8192)
        $capture = [System.IO.MemoryStream]::new()
        try {
            while ($capture.Length -lt 65536) {
                $read = $stream.Read($buffer, 0, $buffer.Length)
                if ($read -le 0) {
                    break
                }
                $capture.Write($buffer, 0, $read)
            }
            $responseText = [System.Text.Encoding]::UTF8.GetString($capture.ToArray())
        } finally {
            $capture.Dispose()
        }
        if ($responseText -notmatch '^HTTP/1\.[01] 413\b') {
            throw "chunked oversized request did not return HTTP 413"
        }
        if (-not $responseText.Contains("REQUEST_TOO_LARGE")) {
            throw "chunked oversized request did not return the expected safe error code"
        }
    } finally {
        $client.Dispose()
    }
}

function ConvertTo-SafeDiagnostic {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Message,
        [Parameter(Mandatory = $true)]
        [string[]]$SensitivePaths,
        [string[]]$SensitiveValues = @()
    )

    $safe = $Message
    foreach ($value in $SensitivePaths + $SensitiveValues) {
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $safe = [regex]::Replace(
                $safe,
                [regex]::Escape($value),
                "<redacted>",
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($env:USERNAME)) {
        $safe = [regex]::Replace(
            $safe,
            [regex]::Escape($env:USERNAME),
            "<user>",
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }
    $safe = [regex]::Replace($safe, '(?i)\b[A-Z]:[\\/][^\r\n]+', '<local-path>')
    $safe = [regex]::Replace(
        $safe,
        '(?i)(authorization|cookie|set-cookie|x-csrf-token)\s*[:=]\s*[^\s,;]+',
        '$1=<redacted>'
    )
    if ($safe.Length -gt 500) {
        return $safe.Substring(0, 500) + "..."
    }
    return $safe
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    [Console]::Error.WriteLine("[security-smoke] failed: Windows is required")
    exit 1
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$currentDirectory = [System.IO.Path]::GetFullPath((Get-Location).ProviderPath)
if (-not $currentDirectory.TrimEnd("\", "/").Equals(
        $repositoryRoot.TrimEnd("\", "/"),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    [Console]::Error.WriteLine(
        "[security-smoke] failed: run this script from the repository root"
    )
    exit 1
}

$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
$frontendDist = Join-Path $repositoryRoot "frontend/dist"
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    [Console]::Error.WriteLine("[security-smoke] failed: root virtual environment is missing")
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendDist "index.html") -PathType Leaf)) {
    [Console]::Error.WriteLine("[security-smoke] failed: production frontend build is missing")
    exit 1
}

if ($Port -eq 0) {
    $Port = Get-TemporaryLoopbackPort
}
if (-not (Test-LoopbackPortAvailable -CandidatePort $Port)) {
    [Console]::Error.WriteLine("[security-smoke] failed: temporary port is unavailable")
    exit 1
}

$temporaryParent = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd("\", "/")
$controlledRoot = Join-Path $temporaryParent "AIWebNovel-Security-Smoke"
$controlledRootCreated = $false
try {
    Assert-OrdinaryDirectory -Path $temporaryParent -Description "system temporary root"
    if (Test-Path -LiteralPath $controlledRoot) {
        Assert-OrdinaryDirectory -Path $controlledRoot -Description "security smoke controlled root"
    } else {
        New-Item -ItemType Directory -Path $controlledRoot | Out-Null
        $controlledRootCreated = $true
        Assert-OrdinaryDirectory -Path $controlledRoot -Description "security smoke controlled root"
    }
} catch {
    [Console]::Error.WriteLine("[security-smoke] failed: unsafe temporary root")
    exit 1
}

$token = [guid]::NewGuid().ToString("N")
$runLeaf = "security-smoke-$PID-$token"
$runDirectory = Join-Path $controlledRoot $runLeaf
$dataRoot = Join-Path $runDirectory "AIWebNovel-Security-DataRoot-$token"
try {
    Assert-DirectOwnedRunDirectory `
        -Candidate $runDirectory `
        -ExpectedParent $controlledRoot `
        -ExpectedLeaf $runLeaf
    Assert-DirectOwnedDataRoot `
        -Candidate $dataRoot `
        -ExpectedParent $runDirectory `
        -ExpectedToken $token
    if (Test-Path -LiteralPath $runDirectory) {
        throw "unique security smoke-test run already exists"
    }
    New-Item -ItemType Directory -Path $runDirectory | Out-Null
    Assert-OrdinaryDirectory -Path $runDirectory -Description "security smoke-test run"
} catch {
    if (
        $controlledRootCreated -and
        (Test-Path -LiteralPath $controlledRoot -PathType Container) -and
        @(Get-ChildItem -LiteralPath $controlledRoot -Force).Count -eq 0
    ) {
        Remove-Item -LiteralPath $controlledRoot -Force -ErrorAction SilentlyContinue
    }
    [Console]::Error.WriteLine("[security-smoke] failed: unsafe owned run directory")
    exit 1
}

$stdoutCapture = Join-Path $runDirectory "service.stdout.log"
$stderrCapture = Join-Path $runDirectory "service.stderr.log"
$formalDefaultRoot = if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    $null
} else {
    Join-Path $env:LOCALAPPDATA "AIWebNovel"
}
$formalRootExistsBefore = if ($null -eq $formalDefaultRoot) {
    $false
} else {
    Test-Path -LiteralPath $formalDefaultRoot
}
$formalRootExistsAfter = $formalRootExistsBefore
$sensitivePaths = @(
    $repositoryRoot,
    $pythonExecutable,
    $frontendDist,
    $temporaryParent,
    $controlledRoot,
    $runDirectory,
    $dataRoot,
    $stdoutCapture,
    $stderrCapture,
    $env:USERPROFILE
)
$sensitiveValues = [System.Collections.Generic.List[string]]::new()
$launcher = $null
$launcherStartedAtUtcTicks = 0L
$listenerRecord = $null
$httpResources = $null
$failureMessage = $null
$cleanupFailure = $null
$listenerResult = "not_checked"
$normalHostResult = "not_checked"
$logResult = "not_checked"
$readySecurity = "not_checked"
$invalidHostResult = "not_checked"
$requestLimitResult = "not_checked"
$contentTypeResult = "not_checked"
$documentResult = "not_checked"
$sessionResult = "not_checked"
$proxyHeaderResult = "not_checked"
$htmlResult = "not_checked"

try {
    $environmentOverrides = [ordered]@{
        AIWEBNOVEL_APP_NAME = "AIWebNovel"
        AIWEBNOVEL_APP_VERSION = "0.0.0"
        AIWEBNOVEL_ENVIRONMENT = "production"
        AIWEBNOVEL_API_PREFIX = "/api/v1"
        AIWEBNOVEL_HOST = "127.0.0.1"
        AIWEBNOVEL_PORT = $Port.ToString()
        AIWEBNOVEL_LOG_LEVEL = "WARNING"
        AIWEBNOVEL_DATA_ROOT = $dataRoot
        AIWEBNOVEL_DATABASE_URL = $null
        AIWEBNOVEL_DATABASE_ECHO = "false"
        AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS = "5000"
        AIWEBNOVEL_SERVE_FRONTEND = "true"
        AIWEBNOVEL_FRONTEND_DIST_PATH = $frontendDist
        AIWEBNOVEL_CORS_ALLOWED_ORIGINS = ('["http://127.0.0.1:{0}"]' -f $Port)
        AIWEBNOVEL_TRUSTED_HOSTS = '["127.0.0.1","localhost"]'
        AIWEBNOVEL_EXPOSE_API_DOCS = "false"
        AIWEBNOVEL_MAX_REQUEST_BODY_BYTES = "1048576"
    }
    $previousEnvironment = @{}
    foreach ($entry in $environmentOverrides.GetEnumerator()) {
        $previousEnvironment[$entry.Key] = [Environment]::GetEnvironmentVariable(
            $entry.Key,
            "Process"
        )
    }
    try {
        foreach ($entry in $environmentOverrides.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable(
                $entry.Key,
                $entry.Value,
                "Process"
            )
        }
        $launcher = Start-Process `
            -FilePath $pythonExecutable `
            -ArgumentList @("-m", "aiwebnovel") `
            -WorkingDirectory $repositoryRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutCapture `
            -RedirectStandardError $stderrCapture `
            -PassThru
        $launcherStartedAtUtcTicks = $launcher.StartTime.ToUniversalTime().Ticks
    } finally {
        foreach ($entry in $environmentOverrides.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable(
                $entry.Key,
                $previousEnvironment[$entry.Key],
                "Process"
            )
        }
    }

    $baseUri = [uri]"http://127.0.0.1:$Port/"
    $httpResources = New-LocalHttpClient -BaseUri $baseUri
    $readyResponse = Wait-ReadyResponse `
        -Client $httpResources.Client `
        -Launcher $launcher
    try {
        if ([int]$readyResponse.StatusCode -ne 200) {
            throw "ready endpoint did not return HTTP 200"
        }
        Assert-ApiSecurityHeaders -Response $readyResponse
        $readyPayload = Get-JsonPayload -Response $readyResponse
        if ($readyPayload.status -ne "ready" -or $readyPayload.checks.security -ne "ok") {
            throw "ready endpoint did not report security ok"
        }
        $readySecurity = "ok"
    } finally {
        $readyResponse.Dispose()
    }

    $listenerRecord = Get-OwnedLoopbackListener `
        -CandidatePort $Port `
        -Launcher $launcher
    $listenerResult = "127.0.0.1-only"

    $liveResponse = Invoke-LocalRequest `
        -Client $httpResources.Client `
        -Method "GET" `
        -Path "/api/v1/health/live" `
        -Headers @{ Accept = "application/json" }
    try {
        if ([int]$liveResponse.StatusCode -ne 200) {
            throw "normal Host request did not succeed"
        }
        Assert-ApiSecurityHeaders -Response $liveResponse
        $normalHostResult = "ok"
    } finally {
        $liveResponse.Dispose()
    }

    $forwardedResponse = Invoke-LocalRequest `
        -Client $httpResources.Client `
        -Method "GET" `
        -Path "/api/v1/health/live" `
        -Headers @{
            Accept = "application/json"
            "X-Forwarded-Host" = "untrusted.invalid"
            "X-Forwarded-Proto" = "https"
            "X-Forwarded-For" = "203.0.113.9"
            Forwarded = "for=203.0.113.9;host=untrusted.invalid;proto=https"
        }
    try {
        if ([int]$forwardedResponse.StatusCode -ne 200) {
            throw "forged forwarding headers changed the normal Host result"
        }
        $proxyHeaderResult = "ignored"
    } finally {
        $forwardedResponse.Dispose()
    }

    $invalidHostResponse = Invoke-LocalRequest `
        -Client $httpResources.Client `
        -Method "GET" `
        -Path "/api/v1/health/live" `
        -Headers @{ Accept = "application/json" } `
        -HostHeader "untrusted.invalid"
    try {
        if ([int]$invalidHostResponse.StatusCode -ne 400) {
            throw "invalid Host did not return HTTP 400"
        }
        Assert-ApiSecurityHeaders -Response $invalidHostResponse
        $invalidHostPayload = Get-JsonPayload -Response $invalidHostResponse
        if ($invalidHostPayload.error.code -ne "INVALID_HOST") {
            throw "invalid Host did not return the expected safe error code"
        }
        if ((Read-ResponseText -Response $invalidHostResponse).Contains("untrusted.invalid")) {
            throw "invalid Host response reflected the rejected value"
        }
        $invalidHostResult = "400/INVALID_HOST"
    } finally {
        $invalidHostResponse.Dispose()
    }

    $rootResponse = Invoke-LocalRequest `
        -Client $httpResources.Client `
        -Method "GET" `
        -Path "/" `
        -Headers @{ Accept = "text/html" }
    try {
        if ([int]$rootResponse.StatusCode -ne 200) {
            throw "production HTML root did not return HTTP 200"
        }
        Assert-HtmlContentSecurityPolicy -Response $rootResponse
        if (-not (Get-ResponseHeader -Response $rootResponse -Name "Content-Type").Contains("text/html")) {
            throw "production root did not return HTML"
        }
        $htmlResult = "csp_ok"
    } finally {
        $rootResponse.Dispose()
    }

    foreach ($documentPath in @("/docs", "/redoc", "/openapi.json")) {
        $documentResponse = Invoke-LocalRequest `
            -Client $httpResources.Client `
            -Method "GET" `
            -Path $documentPath `
            -Headers @{ Accept = "application/json" }
        try {
            if ([int]$documentResponse.StatusCode -ne 404) {
                throw "a production API documentation path remained exposed"
            }
            if ((Get-ResponseHeader -Response $documentResponse -Name "Content-Type").Contains("text/html")) {
                throw "a disabled API documentation path entered the SPA fallback"
            }
            Assert-ApiSecurityHeaders -Response $documentResponse -AllowCache
        } finally {
            $documentResponse.Dispose()
        }
    }
    $documentResult = "closed"

    $sessionResponse = Invoke-LocalRequest `
        -Client $httpResources.Client `
        -Method "GET" `
        -Path "/api/v1/security/session" `
        -Headers @{
            Accept = "application/json"
            Origin = "http://127.0.0.1:$Port"
        }
    try {
        if ([int]$sessionResponse.StatusCode -ne 200) {
            throw "local session endpoint did not return HTTP 200"
        }
        Assert-ApiSecurityHeaders -Response $sessionResponse
        $sessionPayload = Get-JsonPayload -Response $sessionResponse
        $csrfToken = [string]$sessionPayload.csrf_token
        if (
            $csrfToken -notmatch '^[A-Za-z0-9_-]{32,512}$' -or
            [int]$sessionPayload.expires_in_seconds -ne 28800
        ) {
            throw "local session response is invalid"
        }
        $sensitiveValues.Add($csrfToken)
        $sessionCookieUri = [uri]::new($baseUri, "/api/v1/security/session")
        $sessionCookie = $httpResources.Handler.CookieContainer.GetCookies(
            $sessionCookieUri
        )["aiwebnovel_session"]
        if ($null -eq $sessionCookie -or [string]::IsNullOrWhiteSpace($sessionCookie.Value)) {
            throw "local session Cookie was not stored by the HTTP client"
        }
        $sensitiveValues.Add($sessionCookie.Value)
        $setCookieHeader = Get-ResponseHeader -Response $sessionResponse -Name "Set-Cookie"
        $cookieSegments = @($setCookieHeader.Split(";") | ForEach-Object { $_.Trim() })
        $safeCookieAttributes = @($cookieSegments | Select-Object -Skip 1)
        if (
            $cookieSegments.Count -lt 2 -or
            -not $cookieSegments[0].StartsWith("aiwebnovel_session=") -or
            -not ($safeCookieAttributes -contains "HttpOnly") -or
            -not ($safeCookieAttributes -contains "SameSite=Strict") -or
            -not ($safeCookieAttributes -contains "Path=/api") -or
            @($safeCookieAttributes | Where-Object { $_ -like "Max-Age=*" }).Count -ne 1 -or
            @($safeCookieAttributes | Where-Object { $_ -like "Domain=*" }).Count -ne 0 -or
            ($safeCookieAttributes -contains "Secure")
        ) {
            throw "local session Cookie attributes are invalid"
        }
        if (
            -not $sessionCookie.HttpOnly -or
            $sessionCookie.Secure -or
            $sessionCookie.Path -ne "/api"
        ) {
            throw "local session Cookie metadata is invalid"
        }
        $sessionResult = "cookie_ok"
    } finally {
        $sessionResponse.Dispose()
    }

    $unsupportedResponse = Invoke-LocalRequest `
        -Client $httpResources.Client `
        -Method "POST" `
        -Path "/api/v1/missing" `
        -Headers @{
            Accept = "application/json"
            Origin = "http://127.0.0.1:$Port"
            "X-CSRF-Token" = $csrfToken
        } `
        -Body "{}" `
        -ContentType "text/plain"
    try {
        if ([int]$unsupportedResponse.StatusCode -ne 415) {
            throw "unsupported API content type did not return HTTP 415"
        }
        $unsupportedPayload = Get-JsonPayload -Response $unsupportedResponse
        if ($unsupportedPayload.error.code -ne "UNSUPPORTED_MEDIA_TYPE") {
            throw "unsupported API content type returned an unexpected error code"
        }
        $contentTypeResult = "415/UNSUPPORTED_MEDIA_TYPE"
    } finally {
        $unsupportedResponse.Dispose()
    }

    Invoke-ChunkedOversizeRequest `
        -CandidatePort $Port `
        -SessionValue $sessionCookie.Value `
        -CsrfToken $csrfToken
    $requestLimitResult = "413/REQUEST_TOO_LARGE"

    Assert-DirectOwnedDataRoot `
        -Candidate $dataRoot `
        -ExpectedParent $runDirectory `
        -ExpectedToken $token
    Assert-NoReparsePointsInTree -Root $dataRoot
    $databaseFile = Join-Path $dataRoot "data/aiwebnovel.sqlite3"
    if (-not (Test-Path -LiteralPath $databaseFile -PathType Leaf)) {
        throw "security smoke-test database was not created in its isolated data root"
    }
} catch {
    $failureMessage = $_.Exception.Message
} finally {
    $cleanupIssues = [System.Collections.Generic.List[string]]::new()
    if ($null -ne $httpResources) {
        try {
            $httpResources.Client.Dispose()
        } catch {
            $cleanupIssues.Add("HTTP client cleanup failed")
        }
    }
    if ($null -ne $listenerRecord) {
        try {
            Stop-OwnedProcessTree `
                -OwnedProcessId $listenerRecord.ProcessId `
                -StartedAtUtcTicks $listenerRecord.StartedAtUtcTicks
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    if ($null -ne $launcher) {
        try {
            if ($null -eq $listenerRecord -or $launcher.Id -ne $listenerRecord.ProcessId) {
                Stop-OwnedProcessTree `
                    -OwnedProcessId $launcher.Id `
                    -StartedAtUtcTicks $launcherStartedAtUtcTicks
            }
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }
    try {
        Wait-LoopbackPortReleased -CandidatePort $Port
    } catch {
        $cleanupIssues.Add($_.Exception.Message)
    }

    if ($cleanupIssues.Count -eq 0) {
        try {
            $capturedLogs = ""
            foreach ($capturePath in @($stdoutCapture, $stderrCapture)) {
                if (Test-Path -LiteralPath $capturePath -PathType Leaf) {
                    $capturedLogs += [System.IO.File]::ReadAllText($capturePath)
                }
            }
            foreach ($secretValue in $sensitiveValues) {
                if (
                    -not [string]::IsNullOrWhiteSpace($secretValue) -and
                    $capturedLogs.Contains($secretValue)
                ) {
                    throw "service logs contain a protected session value"
                }
            }
            $logResult = "absent"
        } catch {
            if ($null -eq $failureMessage) {
                $failureMessage = $_.Exception.Message
            }
        }
    }

    if ($cleanupIssues.Count -eq 0) {
        try {
            Assert-DirectOwnedRunDirectory `
                -Candidate $runDirectory `
                -ExpectedParent $controlledRoot `
                -ExpectedLeaf $runLeaf
            Assert-NoReparsePointsInTree -Root $runDirectory
            if (Test-Path -LiteralPath $runDirectory) {
                Remove-Item -LiteralPath $runDirectory -Recurse -Force
            }
            if (Test-Path -LiteralPath $runDirectory) {
                throw "security smoke-test run remains after controlled cleanup"
            }
            if (
                $controlledRootCreated -and
                (Test-Path -LiteralPath $controlledRoot -PathType Container) -and
                @(Get-ChildItem -LiteralPath $controlledRoot -Force).Count -eq 0
            ) {
                Assert-OrdinaryDirectory `
                    -Path $controlledRoot `
                    -Description "security smoke controlled root"
                Remove-Item -LiteralPath $controlledRoot -Force
            }
        } catch {
            $cleanupIssues.Add($_.Exception.Message)
        }
    }

    $formalRootExistsAfter = if ($null -eq $formalDefaultRoot) {
        $false
    } else {
        Test-Path -LiteralPath $formalDefaultRoot
    }
    if ($formalRootExistsAfter -ne $formalRootExistsBefore) {
        $cleanupIssues.Add("formal default data root existence changed")
    }
    if ($cleanupIssues.Count -gt 0) {
        $cleanupFailure = $cleanupIssues -join "; "
    }
}

Write-Host "[security-smoke] test_run_name=$runLeaf"
Write-Host "[security-smoke] listener=$listenerResult"
Write-Host "[security-smoke] normal_host=$normalHostResult"
Write-Host "[security-smoke] invalid_host=$invalidHostResult"
Write-Host "[security-smoke] ready_security=$readySecurity"
Write-Host "[security-smoke] proxy_headers=$proxyHeaderResult"
Write-Host "[security-smoke] html=$htmlResult"
Write-Host "[security-smoke] api_docs=$documentResult"
Write-Host "[security-smoke] session=$sessionResult"
Write-Host "[security-smoke] request_limit=$requestLimitResult"
Write-Host "[security-smoke] content_type=$contentTypeResult"
Write-Host "[security-smoke] protected_values_in_logs=$logResult"
Write-Host (
    "[security-smoke] formal_default_root_exists=" +
    $formalRootExistsAfter.ToString().ToLowerInvariant() +
    " content_accessed=false"
)

if ($null -ne $cleanupFailure) {
    $safeCleanupFailure = ConvertTo-SafeDiagnostic `
        -Message $cleanupFailure `
        -SensitivePaths $sensitivePaths `
        -SensitiveValues $sensitiveValues.ToArray()
    [Console]::Error.WriteLine("[security-smoke] cleanup=failed: $safeCleanupFailure")
    exit 1
}
Write-Host "[security-smoke] cleanup=ok"

if ($null -ne $failureMessage) {
    $safeFailureMessage = ConvertTo-SafeDiagnostic `
        -Message $failureMessage `
        -SensitivePaths $sensitivePaths `
        -SensitiveValues $sensitiveValues.ToArray()
    [Console]::Error.WriteLine("[security-smoke] failed: $safeFailureMessage")
    exit 1
}

Write-Host "[security-smoke] passed"
exit 0
