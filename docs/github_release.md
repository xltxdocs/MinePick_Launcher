# 发布到 GitHub（MinePick Launcher）

本机（当前开发环境）未安装 git/gh CLI，以下流程可在任意装有 git 的机器执行。

## 一、首次发布（仓库）

1. GitHub 网页 → New repository（公开/私有自选），**不要**勾选自动生成 README/LICENSE；
2. 本地推送：

```powershell
git init
git add .
git commit -m "MinePick Launcher 首个版本"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

> 注意：build/、dist/、.devdata/、tests/.work/ 等已在 .gitignore 排除；
> 签名私钥 build/codesign.pfx 也在忽略列表内，**切勿**上传。

## 二、发 Release（附带成品）

打包好的成品：
- `dist/MinePick_Launcher.exe`（GUI，已签名）
- `dist/MinePick_Launcher_cli.exe`（CLI，已签名）
- `Source_code.zip`（源代码包，供 GPL-3.0 合规分发）

1. GitHub 仓库页 → Releases → Draft a new release，Tag 填 `v0.1.0`；
2. 把上面三个文件拖进附件区；
3. Release 说明建议写：
   - 功能简介（参考 README 功能列表）；
   - 便携模式说明（EXE 旁生成 config/ 文件夹）；
   - 提示：签名为自签名证书（WDNDXLTX），他人电脑的 SmartScreen 可能提示“未知发布者”，属预期；
   - 许可证：GPL-3.0。

## 三、GPL-3.0 合规提示

- 仓库根目录已含 LICENSE（GNU GPL v3 官方全文）；
- 分发二进制（Release 的 EXE）应同时提供源代码，Source_code.zip 即为此用途；
- 若他人索取源码，指向仓库或 Source_code.zip 均可。
