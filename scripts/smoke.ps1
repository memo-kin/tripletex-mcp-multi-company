<#
.SYNOPSIS
    End-to-end smoke test of the deployed Tripletex MCP server.

.DESCRIPTION
    Runs the standard MCP handshake (initialize, notifications/initialized,
    tools/list) plus a live tools/call against `whoami` for the specified
    company. Returns exit code 0 if everything passes, nonzero otherwise.

    Intended to be run after deploying a new revision but BEFORE promoting
    traffic to it, to catch container-boot, secret-mount, and Tripletex-auth
    regressions in <10 seconds.

.PARAMETER Url
    Base URL of the deployed service (no trailing /mcp). Pass your Cloud Run
    service or revision URL — the default is a placeholder.

.PARAMETER Company
    Tripletex company key to use for the whoami probe. Must exist in the
    TRIPLETEX_COMPANIES secret. Defaults to "default" (single-company setups).

.PARAMETER Audience
    Optional ID-token audience override. Leave unset for default behavior.

.EXAMPLE
    pwsh ./scripts/smoke.ps1 -Url https://tripletex-mcp-multi-xxxxxxxx-ew.a.run.app
    pwsh ./scripts/smoke.ps1 -Url https://rev-v0-1-0---tripletex-mcp-multi-xxxxxxxx-ew.a.run.app -Company company_a
#>
[CmdletBinding()]
param(
    [string]$Url = "https://<YOUR_CLOUD_RUN_SERVICE_URL>",
    [string]$Company = "default",
    [string]$Audience
)

$ErrorActionPreference = "Stop"
$mcpUrl = "$Url/mcp"

# ---------- locate gcloud ----------
$gcloud = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (-not $gcloud) { $gcloud = (Get-Command gcloud -ErrorAction SilentlyContinue).Source }
if (-not $gcloud) {
    Write-Error "gcloud not found on PATH. Install the Google Cloud SDK."
    exit 2
}

# ---------- mint ID token ----------
$tokenArgs = @("auth", "print-identity-token")
if ($Audience) { $tokenArgs += "--audiences=$Audience" }
$token = & $gcloud @tokenArgs 2>$null
if (-not $token) {
    Write-Error "Failed to mint ID token. Run 'gcloud auth login' first."
    exit 2
}

# ---------- helpers ----------
$failures = @()

function Invoke-McpRequest {
    param(
        [string]$Body,
        [string]$SessionId,
        [string]$OutputFile = "$env:TEMP\smoke-response.body",
        [string]$HeaderFile = "$env:TEMP\smoke-response.headers"
    )
    $payloadFile = "$env:TEMP\smoke-payload.json"
    $Body | Out-File -FilePath $payloadFile -Encoding ascii -NoNewline

    $curlArgs = @(
        "-s", "-D", $HeaderFile, "-o", $OutputFile, "-w", "%{http_code}",
        "-X", "POST",
        "-H", "Authorization: Bearer $token",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json, text/event-stream"
    )
    if ($SessionId) { $curlArgs += @("-H", "mcp-session-id: $SessionId") }
    $curlArgs += @("--data-binary", "@$payloadFile", $mcpUrl)

    $code = & curl.exe @curlArgs
    Remove-Item $payloadFile -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        StatusCode = [int]$code
        Body       = (Get-Content $OutputFile -Raw -ErrorAction SilentlyContinue)
        Headers    = (Get-Content $HeaderFile -Raw -ErrorAction SilentlyContinue)
    }
}

function Get-McpResultJson {
    param([string]$ResponseBody)
    # FastMCP streamable-http frames responses as "event: message\ndata: {...}\n\n"
    $line = ($ResponseBody -split "`n" | Where-Object { $_ -match '^data:\s*' } | Select-Object -First 1)
    if (-not $line) { return $null }
    return ($line -replace '^data:\s*', '') | ConvertFrom-Json
}

function Assert {
    param([bool]$Condition, [string]$Message)
    if ($Condition) {
        Write-Host "  OK   $Message"
    } else {
        Write-Host "  FAIL $Message" -ForegroundColor Red
        $script:failures += $Message
    }
}

# ---------- 1) unauth check ----------
Write-Host "[1/4] IAM gate (expect 401/403 without token)"
$noAuth = & curl.exe -s -o NUL -w "%{http_code}" $mcpUrl
Assert ([int]$noAuth -in 401,403) "unauth GET returned $noAuth"

# ---------- 2) initialize ----------
Write-Host "[2/4] initialize handshake"
$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}'
$init = Invoke-McpRequest -Body $initBody
Assert ($init.StatusCode -eq 200) "initialize HTTP $($init.StatusCode)"
$sid = $null
if ($init.Headers -match '(?im)^mcp-session-id:\s*(.+?)\s*$') {
    $sid = $Matches[1]
}
Assert ($null -ne $sid) "received mcp-session-id"

$initResult = Get-McpResultJson -ResponseBody $init.Body
Assert ($null -ne $initResult.result.serverInfo.name) "server identified itself"

# ---------- 3) tools/list ----------
Write-Host "[3/4] tools/list (expect >=23 tools)"
$noteBody = '{"jsonrpc":"2.0","method":"notifications/initialized"}'
$null = Invoke-McpRequest -Body $noteBody -SessionId $sid

$listBody = '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
$list = Invoke-McpRequest -Body $listBody -SessionId $sid
Assert ($list.StatusCode -eq 200) "tools/list HTTP $($list.StatusCode)"
$listResult = Get-McpResultJson -ResponseBody $list.Body
$toolCount = ($listResult.result.tools | Measure-Object).Count
Assert ($toolCount -ge 23) "tools registered: $toolCount"

# ---------- 4) whoami live ----------
Write-Host "[4/4] whoami live against Tripletex (company=$Company)"
$callBody = '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"whoami","arguments":{"company":"' + $Company + '"}}}'
$call = Invoke-McpRequest -Body $callBody -SessionId $sid
Assert ($call.StatusCode -eq 200) "tools/call HTTP $($call.StatusCode)"
$callResult = Get-McpResultJson -ResponseBody $call.Body
$isError = [bool]$callResult.result.isError
Assert (-not $isError) "whoami succeeded (isError=$isError)"
if (-not $isError) {
    $employeeId = $callResult.result.structuredContent.data[0].employeeId
    Assert ($null -ne $employeeId) "got employeeId from Tripletex: $employeeId"
}

# ---------- summary ----------
Remove-Item "$env:TEMP\smoke-response.body","$env:TEMP\smoke-response.headers" -ErrorAction SilentlyContinue

Write-Host ""
if ($failures.Count -eq 0) {
    Write-Host "All checks passed against $Url" -ForegroundColor Green
    exit 0
} else {
    Write-Host "$($failures.Count) check(s) failed against $Url" -ForegroundColor Red
    exit 1
}
