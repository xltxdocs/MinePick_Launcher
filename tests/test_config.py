import json
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from launcher import config as config_mod


def test_defaults():
    c = config_mod.LauncherConfig()
    assert c.memory_gb == 4.0
    assert c.max_concurrent_downloads == 4
    assert c.game_dir is None
    assert c.java_path is None
    assert c.auto_install_java is False
    assert c.version_isolation is True  # 默认开启版本隔离
    assert c.game_language == ""  # 默认跟随游戏内设置（不强制）
    assert c.language_initialized is False  # 首次启动才自动设置


def test_initialize_language_first_run(ws_tmp):
    p = ws_tmp / "config.json"
    c = config_mod.LauncherConfig(ui_language="en_us")
    assert config_mod.initialize_language(c, p) is True
    assert c.game_language == "en_us"  # 同步启动器语言
    assert c.language_initialized is True
    # 第二次调用：不再更改
    c.ui_language = "zh_cn"
    assert config_mod.initialize_language(c, p) is False
    assert c.game_language == "en_us"


def test_initialize_language_system_fallback(ws_tmp, monkeypatch):
    p = ws_tmp / "config.json"
    import locale

    monkeypatch.setattr(
        locale, "getdefaultlocale", lambda: ("ja_JP", "cp932")
    )
    c = config_mod.LauncherConfig(ui_language="")  # 未设置启动器语言
    config_mod.initialize_language(c, p)
    assert c.game_language == "ja_jp"  # 同步系统语言

    monkeypatch.setattr(
        locale, "getdefaultlocale", lambda: ("cs_CZ", "cp1250")
    )
    c2 = config_mod.LauncherConfig(ui_language="")
    config_mod.initialize_language(c2, p)
    assert c2.game_language == ""  # 捷克语不在支持列表 -> 跟随游戏


def test_roundtrip(ws_tmp):
    p = ws_tmp / "config.json"
    c = config_mod.LauncherConfig(
        game_dir=ws_tmp / "mc",
        java_path=ws_tmp / "java" / "bin" / "java.exe",
        memory_gb=8,
        max_concurrent_downloads=8,
        selected_account="alice",
    )
    saved = config_mod.save(c, p)
    assert saved == p
    loaded, _ = config_mod.load(p)
    assert loaded == c
    data = json.loads(p.read_text(encoding="utf-8"))
    assert Path(data["game_dir"]) == ws_tmp / "mc"
    assert data["memory_gb"] == 8


def test_load_missing_file_returns_defaults(ws_tmp):
    c, p = config_mod.load(ws_tmp / "nope.json")
    assert c == config_mod.LauncherConfig()
    assert p == ws_tmp / "nope.json"


def test_unknown_fields_dropped_with_warning(ws_tmp, caplog):
    p = ws_tmp / "config.json"
    p.write_text(json.dumps({"memory_gb": 6, "future_field": 1}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        c, _ = config_mod.load(p)
    assert c.memory_gb == 6.0
    assert "future_field" in caplog.text


def test_invalid_values_rejected():
    with pytest.raises(ValidationError):
        config_mod.LauncherConfig(memory_gb=-1)
    with pytest.raises(ValidationError):
        config_mod.LauncherConfig(max_concurrent_downloads=0)


def test_validate_assignment_coerces_and_rejects():
    c = config_mod.LauncherConfig()
    c.memory_gb = "6"  # 弱模式强转
    assert c.memory_gb == 6.0
    with pytest.raises(ValidationError):
        c.max_concurrent_downloads = 99

def test_offline_mode_allowed_branches(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.setattr(config_mod, "system_language_chinese", lambda: False)
    # 未解锁 + 中文界面 + 非中文系统 → 锁定
    cfg, p = config_mod.load()
    cfg.ui_language = "zh_cn"
    config_mod.save(cfg, p)
    assert config_mod.offline_mode_allowed() is False
    # 未解锁 + 英文界面 + 中文系统 → 锁定（必须两者都中文）
    monkeypatch.setattr(config_mod, "system_language_chinese", lambda: True)
    cfg.ui_language = "en_us"
    config_mod.save(cfg, p)
    assert config_mod.offline_mode_allowed() is False
    # 未解锁 + 中文界面 + 中文系统 → True（逻辑或）
    cfg.ui_language = "zh_cn"
    config_mod.save(cfg, p)
    assert config_mod.offline_mode_allowed() is True
    # 已解锁 → True（无论语言）
    cfg.offline_unlocked = True
    cfg.ui_language = "en_us"
    config_mod.save(cfg, p)
    monkeypatch.setattr(config_mod, "system_language_chinese", lambda: False)
    assert config_mod.offline_mode_allowed() is True


def test_unlock_offline_mode_roundtrip(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data2"))
    assert config_mod.unlock_offline_mode() is True
    cfg, _ = config_mod.load()
    assert cfg.offline_unlocked is True
    assert config_mod.unlock_offline_mode() is False  # 已解锁不再写

