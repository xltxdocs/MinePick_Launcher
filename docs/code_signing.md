# Windows 代码签名流程（#32）

## 本机已执行的自签名（2026-08-15）

- 签名者（证书主体）：**CN=WDNDXLTX, E=wdndxltx@gmail.com**（自签名，象征性署名）
- 有效期：**10 年**（至 2036/8/15）；签名已打 DigiCert 时间戳（旧包永久有效）
- 证书指纹：609714616FD61C6B7BF179C03903F07A13EABDBA
- 私钥备份：build/codesign.pfx（导出密码仅保存在本机，切勿写入任何会被提交的文件）
- 根证书已导入本机 `Cert:\CurrentUser\Root`（本机信任；他人电脑仍会提示未知发布者）
- 两个 EXE 均已签名：`Get-AuthenticodeSignature` → `Status: Valid`，属性里可见签名者 WDNDXLTX

### 每次重新打包后重签（本机，无需安装 Windows SDK）

```powershell
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like "CN=WDNDXLTX*" } | Select-Object -First 1
Set-AuthenticodeSignature -FilePath dist\MinePick_Launcher.exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer "http://timestamp.digicert.com"
Set-AuthenticodeSignature -FilePath dist\MinePick_Launcher_cli.exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer "http://timestamp.digicert.com"
```

> 注：Set-AuthenticodeSignature 要求证书链被本机信任，因此根证书必须先导入受信任根
> （certutil -user -addstore Root build\codesign-root.cer）。一键脚本见 scripts/sign_exe.ps1。

## 背景说明

SmartScreen 默认会警告未签名 EXE。签名分两种：

1. **自签名证书（本地信任，分发受限）**：仅在自己/受控环境的机器上消除警告，
   其它用户仍会看到 SmartScreen 提示（需手动"仍要运行"）。
2. **正式代码签名证书（推荐分发）**：从证书机构购买 OV/EV 证书
   （EV 证书可快速建立 SmartScreen 信誉）。

## 一、自签名（本地验证流程）

以管理员身份打开 PowerShell，在项目目录执行：

```powershell
# 1. 创建代码签名证书（个人证书存储）
$cert = New-SelfSignedCertificate -Type CodeSigningCert \
  -Subject "CN=MinePick Launcher" -CertStoreLocation Cert:\CurrentUser\My

# 2. 导出为 pfx（签名时使用）
$password = ConvertTo-SecureString -String "你的导出密码" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath .\build\codesign.pfx -Password $password
```

## 二、使用 signtool 签名

需要 Windows SDK（或 Visual Studio 构建工具）中的 signtool.exe。

```powershell
# 签名（自签名/正式证书均可，/f 指定 pfx）
& signtool.exe sign /fd SHA256 /f .\build\codesign.pfx /p 你的导出密码 \
  /tr http://timestamp.digicert.com /td SHA256 dist\MinePick_Launcher.exe

# 验证签名
& signtool.exe verify /pa /v dist\MinePick_Launcher.exe
```

注意：
- 双 EXE（MinePick_Launcher.exe 与 MinePick_Launcher_cli.exe）都要签名；
- 正式证书建议使用硬件令牌或证书库（`/sha1 <指纹>` 代替 `/f`）；
- 每次 PyInstaller 重新打包后签名失效，需重新签名（打包脚本可自动追加签名步骤）；
- 一键脚本见 scripts/sign_exe.ps1（需先完成第一步并导出 pfx）。
