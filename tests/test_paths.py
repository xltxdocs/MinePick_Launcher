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

from launcher import paths


def test_default_game_dir_env_override(monkeypatch, ws_tmp):
    monkeypatch.setenv(paths.ENV_GAME_DIR, str(ws_tmp / "game"))
    assert paths.default_game_dir() == ws_tmp / "game"


def test_default_game_dir_no_env(monkeypatch):
    monkeypatch.delenv(paths.ENV_GAME_DIR, raising=False)
    assert paths.default_game_dir().name == ".minecraft"


def test_launcher_dir_env_override(monkeypatch, ws_tmp):
    monkeypatch.setenv(paths.ENV_LAUNCHER_DIR, str(ws_tmp / "data"))
    assert paths.launcher_dir() == ws_tmp / "data"


def test_launcher_dir_platformdirs(monkeypatch):
    monkeypatch.delenv(paths.ENV_LAUNCHER_DIR, raising=False)
    monkeypatch.delenv(paths.ENV_PORTABLE, raising=False)
    monkeypatch.delattr(__import__("sys"), "frozen", raising=False)
    assert "mclauncher" in str(paths.launcher_dir())


def test_launcher_dir_portable(monkeypatch, ws_tmp):
    import sys

    exe = ws_tmp / "MinePick_Launcher.exe"
    monkeypatch.setenv(paths.ENV_PORTABLE, "1")
    monkeypatch.setattr(sys, "executable", str(exe))
    assert paths.launcher_dir() == ws_tmp / "config"  # the config folder next to the EXE


def test_launcher_dir_frozen(monkeypatch, ws_tmp):
    import sys

    exe = ws_tmp / "dist" / "MinePick_Launcher_cli.exe"
    monkeypatch.delenv(paths.ENV_PORTABLE, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert paths.launcher_dir() == ws_tmp / "dist" / "config"


def test_launcher_dir_env_wins_over_portable(monkeypatch, ws_tmp):
    import sys

    monkeypatch.setenv(paths.ENV_PORTABLE, "1")
    monkeypatch.setenv(paths.ENV_LAUNCHER_DIR, str(ws_tmp / "explicit"))
    monkeypatch.setattr(sys, "executable", str(ws_tmp / "x.exe"))
    assert paths.launcher_dir() == ws_tmp / "explicit"


def test_game_paths_layout_and_ensure(ws_tmp):
    gp = paths.GamePaths(ws_tmp / ".minecraft")
    assert gp.versions_dir == ws_tmp / ".minecraft" / "versions"
    assert gp.libraries_dir == ws_tmp / ".minecraft" / "libraries"
    assert gp.assets_dir == ws_tmp / ".minecraft" / "assets"
    assert gp.mods_dir == ws_tmp / ".minecraft" / "mods"
    gp.ensure_all()
    for sub in (gp.versions_dir, gp.libraries_dir, gp.assets_dir, gp.mods_dir):
        assert sub.is_dir()
