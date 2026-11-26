# Native (no-Docker) Windows runner: starts MinIO from its standalone
# windows-amd64 binary, prepares the public bucket with mc, installs the
# site's Python dependencies in a local venv and runs TargetSocial
# same-origin at http://target.com:8080
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\run-native.ps1
#
# Requirements (no Docker needed):
#   - Python 3.10+ on PATH (https://www.python.org/downloads/ — tick "Add to PATH")
#   - internet access the first time (downloads minio.exe, mc.exe, pip packages)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Windows PowerShell 5.1 defaults to old TLS; dl.min.io needs TLS 1.2+.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "[*] Running in: $(Get-Location)"

function Get-RemoteFile([string]$Url, [string]$OutFile) {
    $tmpFile = "$OutFile.part"
    $ok = $false
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -fsSL --retry 2 -o $tmpFile $Url
        $ok = ($LASTEXITCODE -eq 0) -and (Test-Path $tmpFile) -and ((Get-Item $tmpFile).Length -gt 10MB)
    }
    if (-not $ok) {
        Write-Host "    curl.exe unavailable or failed; trying Invoke-WebRequest..."
        try {
            Invoke-WebRequest -Uri $Url -OutFile $tmpFile -UseBasicParsing
            $ok = (Test-Path $tmpFile) -and ((Get-Item $tmpFile).Length -gt 10MB)
        } catch {
            Write-Host "    Invoke-WebRequest also failed: $($_.Exception.Message)"
        }
    }
    if ($ok) {
        Move-Item -Force $tmpFile $OutFile
        Write-Host "    saved $OutFile ($([math]::Round((Get-Item $OutFile).Length / 1MB)) MB)"
    } else {
        Write-Error "Could not download $Url. Check your internet connection / antivirus / proxy and run the script again."
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python was not found on PATH. Install Python 3.10+ from https://www.python.org/downloads/ (tick 'Add to PATH') and re-run."
}

$targets = "bin\minio.exe", "bin\mc.exe"
$missing = @($targets | Where-Object { -not ((Test-Path $_) -and ((Get-Item $_).Length -gt 10MB)) })
if ($missing.Count -gt 0) {
    Write-Host "[*] Downloading MinIO binaries (first run only)..."
    New-Item -ItemType Directory -Force -Path bin | Out-Null
    Get-RemoteFile "https://dl.min.io/server/minio/release/windows-amd64/minio.exe" "bin\minio.exe"
    Get-RemoteFile "https://dl.min.io/client/mc/release/windows-amd64/mc.exe" "bin\mc.exe"
}

$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$hostsText = if (Test-Path $hostsPath) { Get-Content $hostsPath -Raw } else { "" }
if ($hostsText -notmatch "(?m)^\s*127\.0\.0\.1\s+target\.com") {
    Write-Host "[!] 'target.com' is not in your hosts file yet. Run ONCE in an"
    Write-Host "    Administrator PowerShell:"
    Write-Host '    Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 target.com"'
}

Write-Host "[*] Starting MinIO server (standalone binary, data in .\minio-data)..."
$env:MINIO_ROOT_USER = "labadmin"
$env:MINIO_ROOT_PASSWORD = "labdev-only-change-me"
New-Item -ItemType Directory -Force -Path minio-data | Out-Null
$minio = Start-Process -FilePath "bin\minio.exe" `
    -ArgumentList "server .\minio-data", "--console-address", ":9001" `
    -PassThru -WindowStyle Hidden
"minio=$($minio.Id)" | Set-Content .lab-pids.txt

Write-Host "[*] Waiting for MinIO..."
$up = $false
foreach ($i in 1..60) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:9000/minio/health/live" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $up = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}

if (-not $up) { Write-Error "MinIO did not become healthy. Check 'bin\mc.exe admin info local' after 'bin\mc.exe alias set local http://127.0.0.1:9000 labadmin labdev-only-change-me'." }

Write-Host "[*] Preparing public bucket and demo objects..."
& bin\mc.exe alias set local http://127.0.0.1:9000 labadmin labdev-only-change-me | Out-Null
& bin\mc.exe mb --ignore-existing local/public | Out-Null
& bin\mc.exe anonymous set download local/public
& bin\mc.exe cp --attr "Content-Type=image/png" payloads\avatar-payload.png "local/public/avatar-payload.png"
& bin\mc.exe cp --attr "Content-Type=text/plain" payloads\secret-notes.txt "local/public/secret-notes.txt"

Write-Host "[*] Preparing the TargetSocial site (venv + deps)..."
python -m venv .venv
& .venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check flask boto3

Write-Host "[*] Starting TargetSocial (same-origin /uploads proxy) on port 8080..."
$env:PORT = "8080"
$env:MINIO_ENDPOINT = "http://127.0.0.1:9000"
$env:BUCKET = "public"
$env:FLASK_SECRET = "lab-secret-change-me"
$env:SESSION_COOKIE_HTTPONLY = "0"
$site = Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList "web\app.py" -PassThru -WindowStyle Hidden
"site=$($site.Id)" | Add-Content .lab-pids.txt

Write-Host "[*] Waiting for the site..."
$up = $false
foreach ($i in 1..30) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $up = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $up) { Write-Error "TargetSocial did not start. Run '.venv\Scripts\python.exe web\app.py' in a visible window to see the error." }

Write-Host ""
Write-Host "=============================================================="
Write-Host " Lab is UP (no Docker involved)"
Write-Host "=============================================================="
Write-Host " Part A - direct MinIO, anonymous:"
Write-Host "   http://127.0.0.1:9000/public/avatar-payload.png"
Write-Host "   http://127.0.0.1:9000/public/avatar-payload.png?response-content-type=text/html"
Write-Host " Part B - the 'real target' site, same origin:"
Write-Host "   http://target.com:8080/                (login: alice / alice-pass-123)"
Write-Host "   login bob / bob-pass-123, Upload avatar -> payloads\avatar-payload.png"
Write-Host "   crafted link:"
Write-Host "   http://target.com:8080/uploads/avatar-bob.png?response-content-type=text/html"
Write-Host ""
Write-Host "Stop everything: powershell -ExecutionPolicy Bypass -File .\scripts\stop-native.ps1"
