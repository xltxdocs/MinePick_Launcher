# SPDX-FileCopyrightText: 2026 WDNDXLTX
# SPDX-License-Identifier: GPL-3.0-only
#
# This file is part of MinePick Launcher.
#
# MinePick Launcher is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# MinePick Launcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MinePick Launcher. If not, see <https://www.gnu.org/licenses/>.

"""Launcher config: pydantic model + JSON persistence (atomic writes)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from launcher import paths

CONFIG_FILENAME = "config.json"

# Common game languages (code, display name); en_us is built into the game, the rest are the game's bundled language packs
GAME_LANGUAGES: list[tuple[str, str]] = [
    ("", "跟随游戏内设置"),
    ("zh_cn", "简体中文"),
    ("zh_tw", "繁體中文"),
    ("en_us", "English (US)"),
    ("ja_jp", "日本語"),
    ("ko_kr", "한국어"),
    ("ru_ru", "Русский"),
    ("de_de", "Deutsch"),
    ("fr_fr", "Français"),
    ("es_es", "Español"),
    ("pt_br", "Português (Brasil)"),
    ("it_it", "Italiano"),
    ("pl_pl", "Polski"),
    ("tr_tr", "Türkçe"),
    ("uk_ua", "Українська"),
]


class LauncherConfig(BaseModel):
    """User-editable launcher config. Unknown fields are dropped with a warning on load."""

    model_config = ConfigDict(validate_assignment=True)

    game_dir: Path | None = Field(default=None, description="Minecraft game directory; None means use the default rule")
    java_path: Path | None = Field(default=None, description="Java executable; None means auto-detect")
    memory_gb: float = Field(default=4.0, gt=0, le=64, description="Allocated memory (GB)")
    memory_auto: bool = Field(
        default=False,
        description="Auto-allocate heap size from mod count and available RAM at launch time",
    )
    max_concurrent_downloads: int = Field(default=4, ge=1, le=32, description="Download concurrency")
    selected_account: str | None = Field(default=None, description="Account id selected by default")
    auto_install_java: bool = Field(default=False, description="Auto-download Java from Adoptium when missing")
    msa_client_id: str | None = Field(
        default=None,
        description="Microsoft OAuth client id; None means use the built-in public client id (override by registering your own Azure app)",
    )
    version_isolation: bool = Field(
        default=True, description="Version isolation: each version's saves/mods/config live separately under versions/<id>/"
    )
    game_language: str = Field(
        default="",
        description="Game language code (zh_cn/en_us/ja_jp...); empty = follow in-game setting (not forced)",
    )
    ui_language: str = Field(
        default="zh_cn",
        description="Launcher UI language (zh_cn/zh_tw/en_us/ja_jp/ko_kr/ru_ru/fr_fr/es_es/de_de)",
    )
    language_initialized: bool = Field(
        default=False,
        description="Whether the game language was initialized (auto-set only on first launch, never changed automatically afterward)",
    )
    jvm_args: str = Field(
        default="",
        description="Custom JVM args (appended after the version's default args; -Xmx/-Xms are ignored, memory is controlled by the allocated-memory setting)",
    )
    token_encryption: bool = Field(
        default=False,
        description="Encrypted token storage (encrypt sensitive tokens in accounts.json with a password)",
    )
    download_speed_limit_kb: int = Field(
        default=0,
        ge=0,
        le=1_048_576,
        description="Download speed limit (KB/s); 0 = unlimited",
    )
    window_start_mode: str = Field(
        default="default",
        description="Window start state: default / maximized / minimized / remember",
    )
    window_geometry: str = Field(
        default="",
        description="Geometry info saved when remembering the last window size (QByteArray hex)",
    )
    auto_close_on_launch: bool = Field(
        default=False,
        description="Legacy flag (kept for migration): hide-and-exit after the game starts",
    )
    after_launch_behavior: str = Field(
        default="keep",
        description="Behavior after the game starts: keep / hide / exit",
    )
    trim_memory_on_launch: bool = Field(
        default=True,
        description="Trim the launcher working set after the game starts",
    )
    demo_mode: bool = Field(
        default=False,
        description="Demo Mode",
    )
    theme: str = Field(
        default="dark", description="UI theme (dark / light)"
    )
    curseforge_api_key: str = Field(
        default="",
        description="User-provided CurseForge API Key; empty = use the built-in default key",
    )
    wizard_done: bool = Field(
        default=False,
        description="Whether the first-use wizard is complete (language / game directory / memory)",
    )
    offline_unlocked: bool = Field(
        default=False,
        description="Whether a Microsoft premium login has been verified once (gate for offline mode)",
    )
    http_proxy: str = Field(
        default="",
        description="HTTP proxy address (e.g. http://127.0.0.1:7890); empty = auto-read proxy from environment variables",
    )


def default_config_path() -> Path:
    return paths.launcher_dir() / CONFIG_FILENAME


# (mtime, size) -> config cache: re-parses only when the file actually changed
_config_cache: dict[Path, tuple[float, int, LauncherConfig]] = {}


def load(path: Path | None = None) -> tuple[LauncherConfig, Path]:
    """Load the config; return the default config when the file doesn't exist.

    The parsed result is cached by (mtime, size) so repeated reads are cheap;
    save() refreshes the cache entry directly.
    """
    config_path = path or default_config_path()
    if not config_path.exists():
        return LauncherConfig(), config_path
    try:
        stat = config_path.stat()
        stamp = (stat.st_mtime, stat.st_size)
    except OSError:
        stamp = (-1.0, -1)
    cached = _config_cache.get(config_path)
    if cached is not None and cached[0] == stamp[0] and cached[1] == stamp[1]:
        return cached[2], config_path
    # utf-8-sig tolerates a UTF-8 BOM (some editors and PowerShell add one)
    raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if "after_launch_behavior" not in raw and "auto_close_on_launch" in raw:
        # Migrate the legacy hide-and-exit flag to the three-state behavior
        raw["after_launch_behavior"] = "exit" if raw["auto_close_on_launch"] else "keep"
    unknown = set(raw) - set(LauncherConfig.model_fields)
    if unknown:
        logging.getLogger(__name__).warning("忽略配置中的未知字段: %s", sorted(unknown))
    cfg = LauncherConfig(**raw)
    _config_cache[config_path] = (stamp[0], stamp[1], cfg)
    return cfg, config_path


def save(config: LauncherConfig, path: Path | None = None) -> Path:
    """Write the config back (temp file + atomic replace)."""
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    tmp = config_path.with_name(config_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(config_path)
    try:
        stat = config_path.stat()
        _config_cache[config_path] = (stat.st_mtime, stat.st_size, config)
    except OSError:
        _config_cache.pop(config_path, None)
    return config_path


def system_game_language() -> str:
    """Map the system language to a game language code; return empty (follow game) when unsupported."""
    try:
        import locale

        system = (locale.getdefaultlocale()[0] or "").lower().replace("-", "_")
    except Exception:  # noqa: BLE001 - follow the game when system-language detection fails
        return ""
    for code, _name in GAME_LANGUAGES:
        if code and (code.lower() == system or system.startswith(code.split("_")[0] + "_")):
            return code
    if system.startswith("zh"):
        return "zh_cn"
    if system.startswith("en"):
        return "en_us"
    return ""


def system_language_chinese() -> bool:
    """Whether the system's primary language is Chinese (offline-mode gate branch)."""
    try:
        import locale

        lang = (locale.getdefaultlocale()[0] or "").lower().replace("-", "_")
    except Exception:  # noqa: BLE001 - treat detection failure as non-Chinese
        return False
    return lang == "zh" or lang.startswith("zh_")


def offline_mode_allowed() -> bool:
    """Whether offline mode is unlocked.

    Conditions (logical OR): a Microsoft premium login was verified once; or the
    launcher language and system language are **both Chinese** (non-premium
    offline mode is only available in Chinese environments).
    """
    cfg, _ = load()
    if cfg.offline_unlocked:
        return True
    return cfg.ui_language in ("zh_cn", "zh_tw") and system_language_chinese()


def unlock_offline_mode() -> bool:
    """Call after a successful Microsoft premium login; return whether a write occurred."""
    cfg, path = load()
    if cfg.offline_unlocked:
        return False
    cfg.offline_unlocked = True
    save(cfg, path)
    return True


def initialize_language(config: LauncherConfig, path: Path | None = None) -> bool:
    """Auto-set the game language on first launch (never changed automatically
afterward). Return whether a write occurred.

    Rules: prefer syncing the launcher UI language (ui_language); when unset or
    unsupported, sync the system language; when the system language is not in
    the supported list, keep "follow in-game setting".
    """
    if config.language_initialized:
        return False
    if config.ui_language and any(
        code == config.ui_language for code, _name in GAME_LANGUAGES
    ):
        game_lang = config.ui_language
    else:
        game_lang = system_game_language()
    config.game_language = game_lang
    config.language_initialized = True
    save(config, path)
    return True
