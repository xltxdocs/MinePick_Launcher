# Third-party notices / 第三方许可声明

MinePick Launcher 0.2.0 — <https://github.com/xltxdocs/MinePick_Launcher>

MinePick Launcher itself is released under **GPL-3.0-only** (see [LICENSE](LICENSE)). It uses the third-party components and services listed below; their own licences and terms apply to those parts.

Qt for Python (PySide6) is licensed under **LGPL-3.0** and is shipped as a dynamically loaded library that the launcher does not modify. The About page inside the application shows the same list, translated into the interface language.

MinePick Launcher 本体以 **GPL-3.0-only** 发布(见 [LICENSE](LICENSE))。下列第三方组件与服务各自适用其自身许可与条款;Qt for Python(PySide6)以 **LGPL-3.0** 授权,以动态库形式提供且未作修改。应用内的「关于」页展示同一份清单(按界面语言翻译)。

## Dependencies / 依赖项

- **Qt for Python (PySide6)** — `LGPL-3.0-only`
  - the interface framework
  - 界面框架
  - <https://doc.qt.io/qtforpython-6/>
- **httpx** — `BSD-3-Clause`
  - the HTTP client
  - HTTP 客户端
  - <https://www.python-httpx.org/>
- **msal** — `MIT`
  - Microsoft account sign-in
  - 微软账号登录
  - <https://github.com/AzureAD/microsoft-authentication-library-for-python>
- **pydantic** — `MIT`
  - configuration and data models
  - 配置与数据模型
  - <https://docs.pydantic.dev/>
- **platformdirs** — `MIT`
  - cross-platform directories
  - 跨平台目录
  - <https://github.com/platformdirs/platformdirs>
- **tenacity** — `Apache-2.0`
  - retrying failed calls
  - 失败重试
  - <https://github.com/jd/tenacity>
- **rich** — `MIT`
  - coloured command-line output
  - 命令行彩色输出
  - <https://github.com/Textualize/rich>
- **packaging** — `Apache-2.0 or BSD-2-Clause`
  - version parsing and comparison
  - 版本号解析与比较
  - <https://github.com/pypa/packaging>
- **pytest, respx, ruff, PyInstaller** — `MIT / BSD-3-Clause / GPL-2.0 with exception`
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
- **Fabric, Forge & NeoForge**
  - loader metadata and Maven repositories
  - 加载器元数据与 Maven 仓库
  - <https://fabricmc.net/>
- **Adoptium (Eclipse Temurin)**
  - Java runtime downloads
  - Java 运行时下载
  - <https://adoptium.net/>
- **GitHub**
  - code hosting, releases and the update check
  - 代码托管、发布与更新检查
  - <https://github.com/>

## Inspiration and community / 灵感与社区

- **Plain Craft Launcher 2 (PCL2) & PCL CE**
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
  - <https://github.com/TheDarkLord234/MinePick_Launcher_Revision>
- **Prism Launcher**
  - provides the default Microsoft sign-in client id.
  - 提供了默认的微软登录 Client ID。
  - <https://prismlauncher.org/>
