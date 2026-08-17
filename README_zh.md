[English](README.md) | 简体中文

# MinePick Launcher

基于 Python + PySide6 的开源 Minecraft 启动器：正版/离线登录、版本安装、Modrinth 模组与整合包、Fabric/Forge/NeoForge 加载器、实例管理，打包为免安装单文件 EXE。

> 许可证：**GPL-3.0**（见 LICENSE）。发布流程见 docs/github_release.md。

## 主要功能

### 账号
- 微软正版登录（设备码流程：自动打开授权页面并复制授权码）
- 多账号管理与一键切换、皮肤头像显示、令牌自动续期
- 令牌加密存储（可选，密码保护）

### 版本与 Java
- 版本清单 / 详情查看 / 一键安装卸载
- Java 自动匹配与下载（Adoptium JRE，SHA256 校验），内置 Java 管理页
- 版本隔离：每个版本的存档 / 模组 / 配置独立

### 启动游戏
- 内存 / 游戏语言 / 自定义 JVM 参数 / 服务器直连 / 演示模式
- 实时游戏日志、崩溃报告查看器
- 启动后自动隐藏启动器（游戏独立运行）

### 资源（Modrinth）
- 模组搜索与安装（关键词 / 下载量排序 / 版本选择）
- 整合包一键安装（自动装加载器 → 建实例 → 下载全部文件并合并 overrides）
- 资源包 / 光影下载、已安装内容管理（列表 / 大小 / 删除）

### 加载器与实例
- Fabric / Forge / NeoForge 官方安装器静默安装
- 实例：新建 / 启动 / 删除 / 重命名 / 备注 / 排序 / 导入导出

### 界面与体验
- 中英双语界面（即时切换）、深色 / 浅色主题
- 首次使用向导（语言 / 游戏目录 / 内存）
- 下载限速、断点续传、实时速率与剩余时间

## 下载与使用

从 Releases 页下载：
- `MinePick_Launcher.exe` —— 图形界面（双击即用，无控制台窗口）
- `MinePick_Launcher_cli.exe` —— 命令行（终端运行全部命令）

便携模式：EXE 同目录自动生成 `config/` 配置文件夹，两个版本可共用。

命令行示例：
```powershell
MinePick_Launcher_cli.exe login            # 微软正版登录
MinePick_Launcher_cli.exe install 1.20.1   # 安装一个版本
MinePick_Launcher_cli.exe launch 1.20.1    # 启动游戏
MinePick_Launcher_cli.exe --help           # 查看全部命令
```

> 说明：EXE 使用自签名证书签名（WDNDXLTX），其它电脑的 SmartScreen 可能提示“未知发布者”，点击“仍要运行”即可。

## 开发

```powershell
pip install -r requirements-dev.txt
python -m gui                # 运行 GUI
python -m launcher --help    # 运行 CLI
pytest -q                    # 测试（160+）
ruff check launcher gui tests
```

打包与签名：`pyinstaller build_exe.spec` → `scripts/sign_exe.ps1`（详见 docs/code_signing.md）。

## 开源许可

GPL-3.0，见 LICENSE。
