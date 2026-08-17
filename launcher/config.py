"""启动器配置：pydantic 模型 + JSON 持久化（原子写入）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from launcher import paths

CONFIG_FILENAME = "config.json"

# 常用游戏语言（代码, 显示名）；en_us 内置于游戏，其余为游戏自带语言包
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
    """用户可编辑的启动器配置。未知字段在加载时丢弃并告警。"""

    model_config = ConfigDict(validate_assignment=True)

    game_dir: Path | None = Field(default=None, description="Minecraft 游戏目录；None 表示用默认规则")
    java_path: Path | None = Field(default=None, description="Java 可执行文件；None 表示自动探测")
    memory_gb: float = Field(default=4.0, gt=0, le=64, description="分配内存（GB）")
    max_concurrent_downloads: int = Field(default=4, ge=1, le=32, description="下载并发数")
    selected_account: str | None = Field(default=None, description="默认选中的账号标识")
    auto_install_java: bool = Field(default=False, description="缺少 Java 时自动从 Adoptium 下载")
    msa_client_id: str | None = Field(
        default=None,
        description="微软 OAuth client id；None 表示使用内置公开 client id（可注册自有 Azure 应用后覆盖）",
    )
    version_isolation: bool = Field(
        default=True, description="版本隔离：每个版本的存档/模组/配置独立存放于 versions/<id>/ 下"
    )
    game_language: str = Field(
        default="",
        description="游戏语言代码（zh_cn/en_us/ja_jp...）；空 = 跟随游戏内设置（不强制）",
    )
    ui_language: str = Field(
        default="zh_cn", description="启动器界面语言（zh_cn / en_us）"
    )
    language_initialized: bool = Field(
        default=False,
        description="游戏语言是否已初始化（仅首次启动自动设置，之后不再自动更改）",
    )
    jvm_args: str = Field(
        default="",
        description="自定义 JVM 参数（追加到版本默认参数之后；-Xmx/-Xms 会被忽略，内存由分配内存设置控制）",
    )
    token_encryption: bool = Field(
        default=False,
        description="令牌加密存储（用密码加密 accounts.json 中的敏感令牌）",
    )
    download_speed_limit_kb: int = Field(
        default=0,
        ge=0,
        le=1_048_576,
        description="下载速度限制（KB/s）；0 = 不限速",
    )
    window_start_mode: str = Field(
        default="default",
        description="窗口启动状态：default / maximized / minimized / remember",
    )
    window_geometry: str = Field(
        default="",
        description="记住上次窗口尺寸时保存的几何信息（QByteArray hex）",
    )
    auto_close_on_launch: bool = Field(
        default=False,
        description="启动游戏成功后自动隐藏启动器（游戏进程独立运行）",
    )
    demo_mode: bool = Field(
        default=False,
        description="演示模式（Demo Mode）",
    )
    theme: str = Field(
        default="dark", description="界面主题（dark / light）"
    )
    wizard_done: bool = Field(
        default=False,
        description="首次使用向导是否已完成（语言/游戏目录/内存）",
    )
    offline_unlocked: bool = Field(
        default=False,
        description="是否已通过一次微软正版登录验证（离线模式门槛）",
    )
    http_proxy: str = Field(
        default="",
        description="HTTP 代理地址（如 http://127.0.0.1:7890）；空 = 自动读环境变量代理",
    )


def default_config_path() -> Path:
    return paths.launcher_dir() / CONFIG_FILENAME


def load(path: Path | None = None) -> tuple[LauncherConfig, Path]:
    """读取配置；文件不存在时返回默认配置。"""
    config_path = path or default_config_path()
    if not config_path.exists():
        return LauncherConfig(), config_path
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    unknown = set(raw) - set(LauncherConfig.model_fields)
    if unknown:
        logging.getLogger(__name__).warning("忽略配置中的未知字段: %s", sorted(unknown))
    return LauncherConfig(**raw), config_path


def save(config: LauncherConfig, path: Path | None = None) -> Path:
    """写回配置（临时文件 + 原子替换）。"""
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json")
    tmp = config_path.with_name(config_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(config_path)
    return config_path


def system_game_language() -> str:
    """按系统语言映射到游戏语言代码；不在支持列表时返回空（跟随游戏）。"""
    try:
        import locale

        system = (locale.getdefaultlocale()[0] or "").lower().replace("-", "_")
    except Exception:  # noqa: BLE001 - 系统语言探测失败时跟随游戏
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
    """系统主语言是否为中文（离线模式门槛分支）。"""
    try:
        import locale

        lang = (locale.getdefaultlocale()[0] or "").lower().replace("-", "_")
    except Exception:  # noqa: BLE001 - 探测失败按非中文处理
        return False
    return lang == "zh" or lang.startswith("zh_")


def offline_mode_allowed() -> bool:
    """离线模式是否解锁。

    条件（逻辑或）：曾通过微软正版登录验证；或启动器语言与系统语言
    **均为中文**（无正版离线模式仅对中文环境开放）。
    """
    cfg, _ = load()
    if cfg.offline_unlocked:
        return True
    return cfg.ui_language == "zh_cn" and system_language_chinese()


def unlock_offline_mode() -> bool:
    """在成功登录微软正版账号后调用；返回是否发生了写入。"""
    cfg, path = load()
    if cfg.offline_unlocked:
        return False
    cfg.offline_unlocked = True
    save(cfg, path)
    return True


def initialize_language(config: LauncherConfig, path: Path | None = None) -> bool:
    """首次启动时自动设置游戏语言（之后不再自动更改）。返回是否发生了写入。

    规则：优先同步启动器界面语言（ui_language）；未设置/不支持时同步系统语言；
    系统语言不在支持列表则保持"跟随游戏内设置"。
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
