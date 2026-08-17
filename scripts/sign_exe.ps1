# sign_exe.ps1 - Re-sign build outputs (self-signed CN=WDNDXLTX).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\sign_exe.ps1
param(
    [string]$Subject = "CN=WDNDXLTX, E=wdndxltx@gmail.com",
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$dist = Join-Path $PSScriptRoot "..\dist"
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq $Subject } | Select-Object -First 1
if (-not $cert) { throw "Certificate not found: $Subject" }
foreach ($name in @("MinePick_Launcher.exe", "MinePick_Launcher_cli.exe")) {
    $exe = Join-Path $dist $name
    if (-not (Test-Path $exe)) { Write-Warning "Skip (missing): $exe"; continue }
    $sig = Set-AuthenticodeSignature -FilePath $exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $TimestampServer
    if ($sig.Status -ne "Valid") { throw "Sign failed: $exe ($($sig.StatusMessage))" }
    Write-Host "Signed: $exe"
}