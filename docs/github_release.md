# 发布到 GitHub（MinePick Launcher）

本仓库为 **MinePick Launcher**：远端 `https://github.com/xltxdocs/MinePick_Launcher.git`，分支 `main`，当前版本 `0.3.0`。
本产品线**只发布 GUI 版**，没有 CLI 可执行文件（既不构建 `MinePick_Launcher_cli.exe`，也不打包 `run_cli.py`）。
以下命令均在 Windows 的 **CMD** 中执行；本机未安装 gh CLI，Release 在 GitHub 网页上创建。

## 一、首次发布（仓库）

1. GitHub 网页 → New repository（公开/私有自选），**不要**勾选自动生成 README/LICENSE；
2. 本地推送：

```cmd
git init
git add .
git commit -m "MinePick Launcher 首个版本"
git branch -M main
git remote add origin https://github.com/xltxdocs/MinePick_Launcher.git
git push -u origin main
```

> 注意：build/、dist/、Releases/、.devdata/、tests/.work/ 等已在 .gitignore 排除；
> 签名私钥 build/codesign.pfx 也在忽略列表内，**切勿**上传。

## 二、发 Release（附带成品）

打包好的成品先暂存在仓库的 `Releases\` 文件夹（该文件夹已进 .gitignore，不随 git 提交），同时也会产出到 `dist\`：

- `MinePick_Launcher.exe`（GUI 单文件 EXE，已签名，约 65 MB）
- `Source_code.zip`（源代码包，供 GPL-3.0 合规分发，约 1 MB）

1. GitHub 仓库页 → Releases → Draft a new release，Tag 填 `v0.3.0`（当前版本；仓库已有 `v0.1.0`、`v0.1.1`、`v0.1.2`、`v0.1.4`、`v0.1.5`、`v0.2.0`，远端另有一个 `v0.1.3`）；
2. 把上面两个文件拖进附件区；
3. Release 说明按第四节的规范撰写，并写清：
   - 功能简介（参考 README 功能列表）；
   - 便携模式说明（EXE 旁生成 config/ 文件夹）；
   - 提示：签名为自签名证书（WDNDXLTX），他人电脑的 SmartScreen 可能提示“未知发布者”，属预期；
   - 许可证：GPL-3.0。

## 三、推送提交与标签（CMD）

版本号写在 `launcher/__init__.py` 与 `pyproject.toml`；提交后在 CMD 中推送：

```cmd
cd /d D:\dsh-workspace\Source_code_UI
git push
git push origin v0.3.0
```

> 注意：普通 `git push` **不会**推送标签，必须再执行一次 `git push origin vX.Y.Z`，否则 Release 页面选不到该 Tag。

## 四、发版说明（Release Notes）规范

先写英文，再用一行 `---` 分隔、用中文写同样内容；两部分都按下面的顺序写三个小节：

```markdown
## ✨ New
## 🔧 Improvements
## 🐛 Fixes

**某节没有内容就整节省略**(例如只有改进与修复时不写 ✨ New),不要为凑节数硬编条目。

---

## ✨ 新增
## 🔧 改进
## 🐛 修复
```

内容只写**上一个已发布版本**的用户能观察到的变化；本版本开发过程中引入又修掉的 bug **不要**写进发版说明。

## 五、GPL-3.0 合规提示

- 仓库根目录已含 LICENSE（GNU GPL v3 官方全文）；
- 分发二进制（Release 的 EXE）应同时提供源代码，Source_code.zip 即为此用途；
- 若他人索取源码，指向仓库或 Source_code.zip 均可。

## 六、发版前自检（硬门槛）

```powershell
python tools\ui_regression.py --quick      # 必须全部 OK；检查项清单以脚本为准，不在此枚举
python tools\ui_regression.py --list-checks  # 列出当前检查项
```

- **没跑过自检的改动不算完成**；失败先修到绿。
- 若单元测试撞上已知环境 flake（GUI worker 线程偶发原生崩溃，纯净提交也能复现）：
  整条**重跑一次**；仍非绿则**分半跑**（`-k "not java and not locate and not detected"` 与
  `-k "java or locate or detected"`）。**终止条件：两侧都绿 → 视为 flake，放行；
  任一侧崩且单独重跑仍崩 → 按真失败处理，不得提交。**
  因 flake 重跑才通过的提交，信息末尾加标记 `(flake rerun passed)`。
- 打包/文档/截图有改动时，还要**开箱核验** `Releases\` 里的 EXE 与 `Source_code.zip`
  （包内版本号、9 份 README、截图数、无 `tests/.work` 残留、逐文件 sha256、本次改动确实进包）。

### 版本号提升逻辑（精简）

| 变更 | 升位 |
|---|---|
| 修 bug / 打磨 / 文案与 i18n 修正 / 文档 | PATCH `+1` |
| 普通新增：小功能、单个可调项、局部移除 | PATCH `+1` |
| **重大功能**：成体系的新能力，或明显改变使用方式 | MINOR `+1`，PATCH 归 0 |
| 破坏兼容（配置结构不兼容） | `0.x` 阶段可放 MINOR；`1.0.0` 之后必须 MAJOR |
| UI 定稿转为正式形态 | `1.0.0` |

- **只在要发 Release 时升**，不要提前推版本号（避免仓库里躺着从未发布的版本）；
- 一批改动合并成一次升位；**纯技术 / 文档改动不升版本、不打标签**；
- **拿不准时默认 PATCH**：升慢了可以随时补，升快了无法回收；
- 已发布版本的产物不改写，修好发下一个 PATCH；
- 升位时同步：`launcher/__init__.py`、`pyproject.toml`、9 份 README，提交信息用纯版本号，新建标签，重建 EXE 与源码包。

## 七、构建前置（打包用）

`python -m PyInstaller build_exe.spec --noconfirm` 需要两项本地资源（都不进仓库，由 `.gitignore` 覆盖）：

- `build/cf_key.txt` —— 随包内置的 CurseForge API Key（缺失时打包报 `Unable to find 'build/cf_key.txt'`）；
- 代码签名证书 `CN=WDNDXLTX` —— 见 `docs/code_signing.md`。

打包与签名：`python -m PyInstaller build_exe.spec --noconfirm` → `scripts\sign_exe.ps1`。

源码包重打：README 或 docs 改动后必须重新生成 `Source_code.zip`（包内含 `docs/screenshots/` 与所有 README 翻译）：

```cmd
python tools/build_source_zip.py
```
