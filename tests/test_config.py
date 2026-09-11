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
    assert c.version_isolation is True  # version isolation enabled by default
    assert c.game_language == ""  # defaults to the in-game setting (not forced)
    assert c.language_initialized is False  # auto-set only on first launch


def test_initialize_language_first_run(ws_tmp):
    p = ws_tmp / "config.json"
    c = config_mod.LauncherConfig(ui_language="en_us")
    assert config_mod.initialize_language(c, p) is True
    assert c.game_language == "en_us"  # syncs the launcher language
    assert c.language_initialized is True
    # second call: no further change
    c.ui_language = "zh_cn"
    assert config_mod.initialize_language(c, p) is False
    assert c.game_language == "en_us"


def test_initialize_language_system_fallback(ws_tmp, monkeypatch):
    p = ws_tmp / "config.json"
    import locale

    monkeypatch.setattr(
        locale, "getdefaultlocale", lambda: ("ja_JP", "cp932")
    )
    c = config_mod.LauncherConfig(ui_language="")  # launcher language not set
    config_mod.initialize_language(c, p)
    assert c.game_language == "ja_jp"  # syncs the system language

    monkeypatch.setattr(
        locale, "getdefaultlocale", lambda: ("cs_CZ", "cp1250")
    )
    c2 = config_mod.LauncherConfig(ui_language="")
    config_mod.initialize_language(c2, p)
    assert c2.game_language == ""  # Czech not in the supported list -> follow the game


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
    c.memory_gb = "6"  # weak mode coerces
    assert c.memory_gb == 6.0
    with pytest.raises(ValidationError):
        c.max_concurrent_downloads = 99

def test_offline_mode_allowed_branches(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.setattr(config_mod, "system_language_chinese", lambda: False)
    # not unlocked + Chinese UI + non-Chinese system -> locked
    cfg, p = config_mod.load()
    cfg.ui_language = "zh_cn"
    config_mod.save(cfg, p)
    assert config_mod.offline_mode_allowed() is False
    # not unlocked + English UI + Chinese system -> locked (both must be Chinese)
    monkeypatch.setattr(config_mod, "system_language_chinese", lambda: True)
    cfg.ui_language = "en_us"
    config_mod.save(cfg, p)
    assert config_mod.offline_mode_allowed() is False
    # not unlocked + Chinese UI + Chinese system -> True (logical OR)
    cfg.ui_language = "zh_cn"
    config_mod.save(cfg, p)
    assert config_mod.offline_mode_allowed() is True
    # already unlocked -> True (regardless of language)
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
    assert config_mod.unlock_offline_mode() is False  # already unlocked, no write


def test_config_migrates_legacy_auto_close(ws_tmp, monkeypatch):
    """Legacy auto_close_on_launch flag migrates to after_launch_behavior."""
    import json

    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data3"))
    cfg, cfg_path = config_mod.load()
    config_mod.save(cfg, cfg_path)
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    raw.pop("after_launch_behavior", None)
    raw["auto_close_on_launch"] = True
    cfg_path.write_text(json.dumps(raw), encoding="utf-8")
    cfg2, _ = config_mod.load()
    assert cfg2.after_launch_behavior == "exit"
    raw["auto_close_on_launch"] = False
    cfg_path.write_text(json.dumps(raw), encoding="utf-8")
    cfg3, _ = config_mod.load()
    assert cfg3.after_launch_behavior == "keep"

