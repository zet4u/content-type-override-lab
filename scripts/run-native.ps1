# Native (no-Docker) Windows runner: starts MinIO from its standalone
# windows-amd64 binary, prepares the public bucket with a small Python
# (boto3) script - no mc.exe involved - installs the site's Python
# dependencies in a local venv and runs TargetSocial same-origin at
# http://target.com:8080
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

$PINNED_MINIO_URL = "https://github.com/minio/minio/releases/download/RELEASE.2024-10-13T13-34-11Z/minio.windows-amd64.RELEASE.2024-10-13T13-34-11Z.exe"
if (-not ((Test-Path "bin\minio.exe") -and ((Get-Item "bin\minio.exe").Length -gt 10MB))) {
    Write-Host "[*] Downloading the MinIO server binary (first run only)..."
    New-Item -ItemType Directory -Force -Path bin | Out-Null
    Get-RemoteFile $PINNED_MINIO_URL "bin\minio.exe"
} else {
    $versionLine = (& "bin\minio.exe" --version 2>$null | Select-Object -First 1)
    if ("$versionLine" -notmatch "RELEASE\.2024-10-13T13-34-11Z") {
        Write-Host "[!] bin\minio.exe is not the verified release: $versionLine"
        Write-Host "    Newer MinIO builds (2025+/AIStor) removed anonymous bucket policies,"
        Write-Host "    which this lab depends on. Swapping in the pinned version..."
        Get-RemoteFile $PINNED_MINIO_URL "bin\minio.exe"
    }
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

if (-not $up) { Write-Error "MinIO did not become healthy. Check the log output and that ports 9000/9001 are free, then re-run this script." }

Write-Host "[*] Preparing the TargetSocial site (venv + deps)..."
python -m venv .venv
& .venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check flask boto3

Write-Host "[*] Preparing public bucket and demo objects (via boto3, no mc.exe)..."
$env:MINIO_ENDPOINT = "http://127.0.0.1:9000"
$env:BUCKET = "public"
& .venv\Scripts\python.exe scripts\setup_minio.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Bucket setup failed. Is MinIO still running? Re-run this script."
}

Write-Host "[*] Starting TargetSocial (same-origin /uploads proxy) on port 8080..."
$env:PORT = "8080"
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
