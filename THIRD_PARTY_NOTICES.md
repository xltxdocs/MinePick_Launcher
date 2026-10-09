# Third-party notices / 第三方许可声明

MinePick Launcher 0.4.0 — <https://github.com/xltxdocs/MinePick_Launcher>

MinePick Launcher itself is released under **GPL-3.0-only** (see [LICENSE](LICENSE)). It uses the third-party components and services listed below; their own licences and terms apply to those parts. Versions are read from the installed distribution metadata.

Qt for Python (PySide6) is licensed under **LGPL-3.0** and is shipped as a dynamically loaded library that the launcher does not modify. The single-file build unpacks those Qt libraries from the archive into a temporary directory when it starts; Qt's source code is available from <https://code.qt.io/> and from the Qt release archives at <https://download.qt.io/official_releases/qt/>. The About page inside the application shows the same list, translated into the interface language.

MinePick Launcher 本体以 **GPL-3.0-only** 发布（见 [LICENSE](LICENSE)）。下列第三方组件与服务各自适用其自身许可与条款；版本号取自实际安装的发行版元数据。Qt for Python（PySide6）以 **LGPL-3.0** 授权，以动态库形式提供且未作修改；单文件构建在启动时会把这些 Qt 库从压缩包解压到临时目录。Qt 源码可从 <https://code.qt.io/> 与 <https://download.qt.io/official_releases/qt/> 获取。应用内的「关于」页展示同一份清单（按界面语言翻译）。

## Dependencies / 依赖项

### Runtime dependencies / 运行时随程序分发

- **Qt for Python (PySide6)** — `LGPL-3.0-only` — installed: PySide6 6.11.1, shiboken6 6.11.1
  - the interface framework
  - 界面框架
  - <https://doc.qt.io/qtforpython-6/>
- **httpx** — `BSD-3-Clause` — installed: httpx 0.28.1
  - the HTTP client
  - HTTP 客户端
  - <https://www.python-httpx.org/>
- **msal** — `MIT` — installed: msal 1.37.0
  - Microsoft account sign-in
  - 微软账号登录
  - <https://github.com/AzureAD/microsoft-authentication-library-for-python>
- **pydantic** — `MIT` — installed: pydantic 2.13.4
  - configuration and data models
  - 配置与数据模型
  - <https://docs.pydantic.dev/>
- **platformdirs** — `MIT` — installed: platformdirs 4.11.2
  - cross-platform directories
  - 跨平台目录
  - <https://github.com/platformdirs/platformdirs>
- **tenacity** — `Apache-2.0` — installed: tenacity 9.1.4
  - retrying failed calls
  - 失败重试
  - <https://github.com/jd/tenacity>
- **rich** — `MIT` — installed: rich 15.0.0
  - coloured command-line output
  - 命令行彩色输出
  - <https://github.com/Textualize/rich>
- **packaging** — `Apache-2.0 or BSD-2-Clause` — installed: packaging 26.3
  - version parsing and comparison
  - 版本号解析与比较
  - <https://github.com/pypa/packaging>
- **cryptography (with OpenSSL)** — `Apache-2.0 or BSD-3-Clause` — installed: cryptography 50.0.0
  - token encryption and certificate handling (including OpenSSL)
  - 令牌加密与证书校验（含 OpenSSL）
  - <https://cryptography.io/>
- **truststore** — `MIT` — installed: truststore 0.10.4
  - using the operating system's certificate store
  - 使用系统证书存储
  - <https://github.com/sethmlarson/truststore>
- **anyio 4.14.2, certifi 2026.7.22, httpcore 1.0.9, h11 0.16.0, idna 3.18**
  - pulled in by httpx; no separate notice applies, their licences are listed per package in the distribution metadata
  - 由 httpx 引入；各自的许可条款见对应发行版的元数据

### Build & test tools / 仅构建与测试时使用

- **pytest, respx, ruff, PyInstaller** — `MIT / BSD-3-Clause / GPL-2.0 with exception` — installed: pytest 9.1.1, respx 0.23.1, ruff 0.16.3, pyinstaller 6.22.0
  - build-time tools, not shipped with the launcher
  - 开发期工具，不随程序分发

## Services and data / 服务与数据来源

- **Mojang & Microsoft**
  - the official version manifest, asset library and sign-in services
  - 官方版本清单、资源库与登录服务
  - <https://www.minecraft.net/>
- **Modrinth**
  - mod, resource-pack, shader and modpack search
  - 模组、资源包、光影与整合包检索
  - <https://modrinth.com/>
- **CurseForge**
  - mod search
  - 模组检索
  - <https://www.curseforge.com/minecraft>
- **Fabric**
  - the Fabric loader and its metadata
  - Fabric 加载器与其元数据
  - <https://fabricmc.net/>
- **Forge**
  - the Forge loader and its Maven repository
  - Forge 加载器与其 Maven 仓库
  - <https://files.minecraftforge.net/>
- **NeoForge**
  - the NeoForge loader and its Maven repository
  - NeoForge 加载器与其 Maven 仓库
  - <https://neoforged.net/>
- **Adoptium (Eclipse Temurin)**
  - Java runtime downloads
  - Java 运行时下载
  - <https://adoptium.net/>
- **GitHub**
  - code hosting, releases and the update check
  - 代码托管、发布与更新检查
  - <https://github.com/>

## Inspiration and community / 灵感与社区

- **Plain Craft Launcher 2 (PCL2) & PCL Community Edition (PCL CE)**
  - the inspiration for how this launcher organises its interface and its about/update pages. The technology stacks differ (C#/WPF versus Python/PySide6); this project is independently implemented and contains none of the upstream source code.
  - 本项目在界面组织与「关于 / 更新」信息架构上的灵感来源。技术栈不同（C#/WPF 与 Python/PySide6），本项目完全独立实现，未包含上游源代码。
  - <https://github.com/PCL-Community/PCL-CE>
- **MinePick Launcher Classic**
  - the predecessor of this launcher, archived.
  - 本启动器的前身，已归档。
  - <https://github.com/xltxdocs/MinePick_Launcher_Classic>
- **TheDarkLord234**
  - community member and author of MinePick Launcher Revision — thanks for exploring this space together.
  - 社区伙伴，《MinePick Launcher Revision》的作者，感谢在生态探索上的并肩前行。
  - <https://github.com/TheDarkLord234>
- **Prism Launcher**
  - provides the default Microsoft sign-in client id.
  - 提供了默认的微软登录 Client ID。
  - <https://prismlauncher.org/>
