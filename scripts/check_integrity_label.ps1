# check_integrity_label.ps1 - Guard against shipping a Low-integrity artifact.
#
# Why this exists: this workspace carries a "Low Mandatory Level" label with (OI)(CI) inheritance
# (the agent sandbox uses it to confine writes), so every EXE built inside inherits that label.
# Windows starts a process from a Low-labelled file at low integrity, and a low-integrity process
# may not write to %TEMP% (medium) - so a single-file (onefile) build cannot unpack its runtime and
# pops "Could not create temporary directory" before any of our code runs. The launcher itself looks
# broken, while the very same file works as soon as it is copied to a medium-integrity folder.
#
# Reading labels is harmless (no label is modified), so this script is safe to run anywhere, before
# or after signing. Run it over the artifacts that are actually going to be published.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts\check_integrity_label.ps1 [-Path <dir>]
# Exit code 0 = every artifact is medium integrity; 1 = at least one is low integrity.

param(
    [string]$Path = (Join-Path $PSScriptRoot "..\Releases")
)

$ErrorActionPreference = "Stop"
$targets = Get-ChildItem -LiteralPath $Path -File -ErrorAction SilentlyContinue
if (-not $targets) { throw "No files to check in: $Path" }

$bad = @()
foreach ($file in $targets) {
    $label = (icacls $file.FullName | Where-Object { $_ -match "Mandatory Label" }) -join " "
    $level = if ($label -match "Low Mandatory Level") { "Low" } elseif ($label -match "Medium Mandatory Level") { "Medium" } else { "(default/Medium)" }
    "{0,-28} {1}" -f $file.Name, $level
    if ($level -eq "Low") { $bad += $file.FullName }
}

if ($bad.Count -gt 0) {
    Write-Host ""
    Write-Host "FAIL: these artifacts are low integrity and will not start when double-clicked:" -ForegroundColor Red
    $bad | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host "Fix (needs an elevated shell): icacls `<folder`> /setintegritylevel (OI)(CI)Medium"
    exit 1
}
Write-Host ""
Write-Host "OK: every artifact is medium integrity"
exit 0
