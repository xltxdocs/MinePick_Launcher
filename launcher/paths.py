"""路径解析：启动器数据目录与 Minecraft 游戏目录。

游戏目录决策顺序：
1. 显式传入（CLI 参数 / 配置文件 game_dir）；
2. 环境变量 MINECRAFT_GAME_DIR；
3. 平台默认值（Windows: %APPDATA%\\.minecraft，其余: ~/.minecraft）。

启动器自身数据目录决策顺序：
1. 环境变量 MCLAUNCHER_DATA_DIR（显式覆盖）；
2. 便携模式（打包运行，或 MCLAUNCHER_PORTABLE=1）：<EXE 所在目录>/config/
   —— 两个构建版本（GUI / CLI）放在同一文件夹即可共用配置；
3. platformdirs 平台默认位置（开发环境）。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "mclauncher"
ENV_GAME_DIR = "MINECRAFT_GAME_DIR"
ENV_LAUNCHER_DIR = "MCLAUNCHER_DATA_DIR"
ENV_PORTABLE = "MCLAUNCHER_PORTABLE"
PORTABLE_DIRNAME = "config"


def launcher_dir() -> Path:
    """启动器自身数据目录（配置/账号/缓存/Java 运行时/日志）。"""
    env = os.environ.get(ENV_LAUNCHER_DIR)
    if env:
        return Path(env).expanduser()
    if getattr(sys, "frozen", False) or os.environ.get(ENV_PORTABLE) == "1":
        # 便携模式：配置文件夹与 EXE 同目录，两个构建版本共用
        return Path(sys.executable).resolve().parent / PORTABLE_DIRNAME
    return Path(user_data_dir(APP_NAME, APP_NAME))


def resource_path(relative: str | Path) -> Path:
    """打包兼容的资源路径。

    PyInstaller --onefile 下随包资源被解压到 sys._MEIPASS；
    开发环境则回退到项目根目录（launcher/ 与 gui/ 均为顶层包）。
    所有随包数据（图标/SVG/QSS 等）都应经此函数读取。
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative


def default_game_dir() -> Path:
    """按环境变量/平台默认规则解析 Minecraft 游戏目录。"""
    env = os.environ.get(ENV_GAME_DIR)
    if env:
        return Path(env).expanduser()
    appdata = os.environ.get("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / ".minecraft"
    return Path.home() / ".minecraft"


@dataclass(frozen=True)
class GamePaths:
    """游戏目录内各子目录的官方布局。"""

    game_dir: Path

    def version_dir(self, version_id: str) -> Path:
        return self.versions_dir / version_id

    def mods_dir_for(self, version_id: str | None = None, isolated: bool = False) -> Path:
        """模组目录：版本隔离时位于 versions/<id>/mods，否则全局 mods。"""
        if isolated and version_id is not None:
            return self.version_dir(version_id) / "mods"
        return self.mods_dir

    @property
    def versions_dir(self) -> Path:
        return self.game_dir / "versions"

    @property
    def libraries_dir(self) -> Path:
        return self.game_dir / "libraries"

    @property
    def assets_dir(self) -> Path:
        return self.game_dir / "assets"

    @property
    def mods_dir(self) -> Path:
        return self.game_dir / "mods"

    def ensure_all(self) -> GamePaths:
        """确保各子目录存在（幂等）。"""
        for sub in (self.versions_dir, self.libraries_dir, self.assets_dir, self.mods_dir):
            sub.mkdir(parents=True, exist_ok=True)
        return self
