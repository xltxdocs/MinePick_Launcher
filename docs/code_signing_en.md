[简体中文](code_signing.md) | English

# Windows code signing process (#32)
> This document is also available in [Simplified Chinese](code_signing.md).

## Self-signing already performed on this machine (2026-08-15)

- Signer (certificate subject): **CN=WDNDXLTX, E=wdndxltx@gmail.com** (self-signed, a symbolic attribution)
- Validity: **10 years** (until 2036/8/15); the signatures carry a DigiCert timestamp (so older builds stay valid forever)
- Certificate thumbprint: 609714616FD61C6B7BF179C03903F07A13EABDBA
- Private key backup: build/codesign.pfx (the export password is kept on this machine only — never write it into any file that would be committed)
- The root certificate has been imported into `Cert:\CurrentUser\Root` on this machine (trusted here; other people's computers will still warn about an unknown publisher)
- Both EXEs are signed: `Get-AuthenticodeSignature` → `Status: Valid`, and the signer WDNDXLTX is visible in the file properties

### Re-signing after every rebuild (on this machine, no Windows SDK installation needed)

```powershell
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like "CN=WDNDXLTX*" } | Select-Object -First 1
Set-AuthenticodeSignature -FilePath dist\MinePick_Launcher.exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer "http://timestamp.digicert.com"
Set-AuthenticodeSignature -FilePath dist\MinePick_Launcher_cli.exe -Certificate $cert -HashAlgorithm SHA256 -TimestampServer "http://timestamp.digicert.com"
```

> Note: Set-AuthenticodeSignature requires the certificate chain to be trusted on this machine, so the root
> certificate has to be imported into the trusted root store first
> (certutil -user -addstore Root build\codesign-root.cer). See scripts/sign_exe.ps1 for a one-click script.

## Background

SmartScreen warns about unsigned EXEs by default. There are two kinds of signing:

1. **Self-signed certificate (trusted locally, limited for distribution)**: it only removes the warning on
   your own or a controlled machine; other users still see the SmartScreen prompt (they have to choose
   "Run anyway" manually).
2. **A real code signing certificate (recommended for distribution)**: buy an OV/EV certificate from a
   certificate authority (an EV certificate builds SmartScreen reputation quickly).

## 1. Self-signing (local verification flow)

Open PowerShell as administrator and run the following in the project directory:

```powershell
# 1. 创建代码签名证书（个人证书存储）
$cert = New-SelfSignedCertificate -Type CodeSigningCert \
  -Subject "CN=MinePick Launcher" -CertStoreLocation Cert:\CurrentUser\My

# 2. 导出为 pfx（签名时使用）
$password = ConvertTo-SecureString -String "你的导出密码" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath .\build\codesign.pfx -Password $password
```

## 2. Signing with signtool

This needs signtool.exe from the Windows SDK (or the Visual Studio build tools).

```powershell
# 签名（自签名/正式证书均可，/f 指定 pfx）
& signtool.exe sign /fd SHA256 /f .\build\codesign.pfx /p 你的导出密码 \
  /tr http://timestamp.digicert.com /td SHA256 dist\MinePick_Launcher.exe

# 验证签名
& signtool.exe verify /pa /v dist\MinePick_Launcher.exe
```

Notes:
- Both EXEs (MinePick_Launcher.exe and MinePick_Launcher_cli.exe) have to be signed;
- With a real certificate, prefer a hardware token or the certificate store (use `/sha1 <thumbprint>`
  instead of `/f`);
- Every PyInstaller onefile build invalidates the signature, so the EXE has to be signed again (the build
  script can append the signing step automatically);
- See scripts/sign_exe.ps1 for a one-click script (step 1 has to be completed and the pfx exported first).
