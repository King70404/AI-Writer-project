[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [ValidateRange(5, 180)]
    [int]$TimeoutSeconds = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$readyUri = "http://127.0.0.1:$Port/api/v1/health/ready"
$appUri = "http://127.0.0.1:$Port/"
$deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)

while ([DateTimeOffset]::UtcNow -lt $deadline) {
    try {
        $response = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri $readyUri `
            -Method Get `
            -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $payload = $response.Content | ConvertFrom-Json
            if ([string]$payload.status -eq "ready") {
                Start-Process $appUri
                exit 0
            }
        }
    } catch {
        # The integrated launcher may still be starting; keep waiting until the bounded deadline.
    }
    Start-Sleep -Milliseconds 250
}

exit 1
