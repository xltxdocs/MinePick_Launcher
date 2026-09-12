[English](README.md) | **简体中文** | [繁體中文](README_zh_TW.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Русский](README_ru.md) | [Français](README_fr.md) | [Español](README_es.md) | [Deutsch](README_de.md)

# MinePick Launcher — UI Trial

基于 Python + PySide6 的便携版 Minecraft 启动器：微软正版 / 离线登录、版本安装、Modrinth 与 CurseForge 资源、
Fabric/Forge/NeoForge/Quilt 加载器、实例隔离管理 —— 打包为免安装单文件 EXE。

**本仓库是界面试验线（版本 0.1.2）**：启动器功能与主线一致，区别在于下面这套界面重做；并且**只提供 GUI 版**，
不含命令行版可执行文件。

> 主线启动器：[xltxdocs/MinePick_Launcher](https://github.com/xltxdocs/MinePick_Launcher)

## 界面演示

<table>
  <tr>
    <td><img src="docs/screenshots/launch_zh.png" width="480" alt="启动页"/></td>
    <td><img src="docs/screenshots/versions_zh.png" width="480" alt="版本页"/></td>
  </tr>
  <tr>
    <td align="center"><sub>启动页</sub></td>
    <td align="center"><sub>版本页</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/instances_mods_zh.png" width="480" alt="实例页与本地模组管理"/></td>
    <td><img src="docs/screenshots/settings_zh.png" width="480" alt="设置页"/></td>
  </tr>
  <tr>
    <td align="center"><sub>实例页与本地模组管理</sub></td>
    <td align="center"><sub>设置页（界面个性化）</sub></td>
  </tr>
</table>

## 界面（本线改了什么）

- **窗口内的首次向导** —— 欢迎流程是主窗口里的覆盖层（左侧步骤栏、右侧内容、底部操作栏），不再是独立弹窗；
  完成后淡出让位
- **自定义窗口框架** —— 标题栏由启动器自绘，风格跟随主题；窗口图标在所有场景、所有尺寸下统一为镐子设计
- **外观可自定义** —— 强调色（填任意 16 进制色码、8 个预设色块、系统取色器）、界面字体（系统已安装的全部字体，
  常用置顶，输入即过滤）、界面圆角（紧凑 / 默认 / 圆润）、主题（深色 / 浅色 / 跟随系统）
- **版式更清楚** —— 每页顶部有大标题与一句说明、侧边栏顶部品牌区、全局统一间距标尺、搜索框内嵌放大镜图标
- **交互更安静** —— 滚动条只在鼠标移入列表时出现、焦点描边只对键盘导航显示、切页有淡入过渡、
  表格列宽会被记住、点表头即可排序
- **状态更易读** —— 按钮分三级（主操作 / 次要描边 / 危险红描边）、状态文字按严重程度着色、空列表会告诉你下一步做什么
- **默认即无障碍** —— 所有文字与背景的对比度达 WCAG AA（承载白字的填充色自动加深），界面支持 9 种语言

## 启动器功能

### 账号
- 微软设备码登录（自动打开授权页并把授权码复制到剪贴板），带实时轮询状态
- 离线模式；多账号列表一键切换；皮肤头像；令牌自动续期
- 可选令牌加密（cryptography Fernet + 密码，支持 `MCLAUNCHER_TOKEN_PASSWORD`）

### 版本与 Java
- 官方版本清单，分类页签（正式版 / 快照版 / 愚人节版本 / 远古版）、「最新正式版 / 最新快照版」卡片、
  版本名搜索、一键安装与卸载、版本详情
- 版本隔离：每个版本拥有独立的存档 / 模组 / 配置
- Java 需求映射（1.16.5→8、1.17–1.20.4→17、1.20.5–1.21.11→21、26.1+→25），支持 Adoptium 自动下载与运行时管理器

### 启动与实例
- 按模组数量与可用内存给出内存建议、自定义 JVM 参数、服务器直连、游戏语言、实时日志、
  「启动游戏后」三态行为、启动后释放启动器内存
- 实例隔离，支持备注、重命名、导入导出；实例内嵌本地模组管理（读取 Fabric / Quilt / NeoForge / Forge /
  mcmod.info 的 jar 元数据，一键启用禁用、搜索筛选、拖入安装）

### 资源
- 来自 **Modrinth** 与 **CurseForge** 的模组 / 资源包 / 光影 / 整合包，每个页签的下载量 Top 30、
  关键词搜索（含社区中文译名）、一键安装、`.mrpack` 整合包安装

## 下载与使用

到 Releases 页下载 `MinePick_UI_Trial.exe`，双击即用 —— 免安装、无控制台窗口。首次运行会在 EXE 同目录生成
`config/` 文件夹，配置、账号与实例都留在这一个文件夹里。

所有设置都在界面内调整：**改完即生效，没有保存按钮。**

> 此版本使用自签名证书（WDNDXLTX），他人电脑的 SmartScreen 可能提示「未知发布者」，
> 点「更多信息 → 仍要运行」即可。

## 开发

```powershell
pip install -r requirements-dev.txt
python -m gui                # run the GUI
pytest -q                    # tests (240+)
ruff check launcher gui tests
```

打包与签名：`pyinstaller build_exe.spec` → `scripts/sign_exe.ps1`（见 `docs/code_signing.md`）。
打包产物为**单个 GUI 版 EXE**（构建前置条件见 `docs/github_release.md`）。

一条命令跑完整界面检查（测试 + lint + 对比度/溢出/高 DPI + 圆角审计 + 截图）：

```powershell
python tools/ui_regression.py            # add --quick to skip the screenshots
```

主题机制（占位符、可调项挂钩、如何新增一个可调项）：`docs/theming.md`。

## 许可证

GPL-3.0-only —— 见 [LICENSE](LICENSE)。每次发布附带的源码包（`Source_code.zip`）满足 GPL 的源码分发要求。

## 相关项目

- [MinePick Launcher](https://github.com/xltxdocs/MinePick_Launcher) —— 主线启动器（GUI + CLI）
- [MinePick Launcher Revision](https://github.com/TheDarkLord234/MinePick_Launcher_Revision) —— 社区小伙伴基于主线改制的修订版
