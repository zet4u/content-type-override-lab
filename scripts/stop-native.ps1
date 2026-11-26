# Stops everything started by run-native.ps1 (MinIO + TargetSocial).
$ErrorActionPreference = "SilentlyContinue"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Test-Path .lab-pids.txt) {
    Get-Content .lab-pids.txt | ForEach-Object {
        $id = ($_ -split "=", 2)[1]
        if ($id) {
            Stop-Process -Id $id -Force
            Write-Host "[*] stopped process $id"
        }
    }
    Remove-Item .lab-pids.txt
} else {
    Write-Host "[*] no record of native lab processes; also trying by name"
    Get-Process minio -ErrorAction SilentlyContinue | Stop-Process -Force
}

Write-Host "Done. To wipe bucket data too: Remove-Item -Recurse -Force minio-data"
