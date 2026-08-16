# sign_exe.ps1 — 重新签名打包产物（本机，无需 Windows SDK）。
# 使用当前用户证书库中 CN=WDNDXLTX 的代码签名证书（见 docs/code_signing.md）。
param(
    [string]$Subject = "CN=WDNDXLTX, E=wdndxltx@gmail.com",
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$dist = Join-Path $PSScriptRoot "..\dist"
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq $Subject -or $_.Subject -like $Subject + "*" } | Select-Object -First 1
if (-not $cert) { throw "未找到证书 $Subject，请先按 docs/code_signing.md 生成" }
foreach ($name in @("MinePick_Launcher.exe", "MinePick_Launcher_cli.exe")) {
    $exe = Join-Path $dist $name
    if (-not (Test-Path $exe)) { Write-Warning "跳过（不存在）: $exe"; continue }
    $sig = Set-AuthenticodeSignature -FilePath $exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $TimestampServer
    if ($sig.Status -ne "Valid") { throw "签名失败: $exe ($($sig.StatusMessage))" }
    Write-Host "已签名: $exe"
}
