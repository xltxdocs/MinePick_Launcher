"""Path resolution: launcher data directory and Minecraft game directory.

Game directory decision order:
1. Explicitly passed in (CLI args / config game_dir);
2. MINECRAFT_GAME_DIR environment variable;
3. Platform default (Windows: %APPDATA%\\.minecraft, others: ~/.minecraft).

Launcher data directory decision order:
1. MCLAUNCHER_DATA_DIR environment variable (explicit override);
2. Portable mode (packaged run, or MCLAUNCHER_PORTABLE=1): <EXE directory>/config/
   — both build variants (GUI / CLI) in the same folder share the config;
3. platformdirs platform default location (development environment).
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
    """The launcher's own data directory (config / accounts / cache / Java runtimes / logs)."""
    env = os.environ.get(ENV_LAUNCHER_DIR)
    if env:
        return Path(env).expanduser()
    if getattr(sys, "frozen", False) or os.environ.get(ENV_PORTABLE) == "1":
        # Portable mode: config folder next to the EXE, shared by both build variants
        return Path(sys.executable).resolve().parent / PORTABLE_DIRNAME
    return Path(user_data_dir(APP_NAME, APP_NAME))


def resource_path(relative: str | Path) -> Path:
    """Packaging-compatible resource path.

    Under PyInstaller --onefile, bundled resources are extracted to sys._MEIPASS;
    in development it falls back to the project root (launcher/ and gui/ are both
    top-level packages). All bundled data (icons/SVG/QSS, etc.) should be read via
    this function.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative


def default_game_dir() -> Path:
    """Resolve the Minecraft game directory per environment variable / platform defaults."""
    env = os.environ.get(ENV_GAME_DIR)
    if env:
        return Path(env).expanduser()
    appdata = os.environ.get("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / ".minecraft"
    return Path.home() / ".minecraft"


@dataclass(frozen=True)
class GamePaths:
    """Official layout of the subdirectories inside the game directory."""

    game_dir: Path

    def version_dir(self, version_id: str) -> Path:
        return self.versions_dir / version_id

    def mods_dir_for(self, version_id: str | None = None, isolated: bool = False) -> Path:
        """Mods directory: under versions/<id>/mods when version isolation is on, otherwise global mods."""
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
        """Ensure each subdirectory exists (idempotent)."""
        for sub in (self.versions_dir, self.libraries_dir, self.assets_dir, self.mods_dir):
            sub.mkdir(parents=True, exist_ok=True)
        return self
