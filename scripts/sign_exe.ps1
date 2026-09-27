# sign_exe.ps1 - Re-sign build outputs (self-signed CN=WDNDXLTX).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\sign_exe.ps1
#
# Note: the integrity label is deliberately NOT touched here. Build outputs inside this workspace
# inherit a Low mandatory label (the agent sandbox confines writes that way), and Windows would start
# such an EXE at low integrity - which cannot write to %TEMP% (Medium), so a single-file build fails
# to unpack with "Could not create temporary directory" before any of our code runs.
# Stripping the label here would be self-defeating: the next build could no longer overwrite its own
# output (a low-integrity process may not write a medium-integrity object). The label is therefore
# handled where the artifacts are published - see scripts\check_integrity_label.ps1 and the
# packaging checklist in the process document. Re-signing a file does not change its label either way.
param(
    [string]$Subject = "CN=WDNDXLTX, E=wdndxltx@gmail.com",
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$dist = Join-Path $PSScriptRoot "..\dist"
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq $Subject } | Select-Object -First 1
if (-not $cert) { throw "Certificate not found: $Subject" }
foreach ($name in @("MinePick_Launcher.exe")) {
    $exe = Join-Path $dist $name
    if (-not (Test-Path $exe)) { Write-Warning "Skip (missing): $exe"; continue }
    $sig = Set-AuthenticodeSignature -FilePath $exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $TimestampServer
    if ($sig.Status -ne "Valid") { throw "Sign failed: $exe ($($sig.StatusMessage))" }
    Write-Host "Signed: $exe"
}
