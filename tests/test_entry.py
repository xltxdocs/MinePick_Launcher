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

"""Entry dispatch tests for run.py / run_cli.py (CLI build vs GUI build separation)."""

from __future__ import annotations

import run as run_entry


def test_frozen_cli_build_no_args_shows_help(monkeypatch, capsys):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", "C:/x/MinePick_Launcher_cli.exe")
    monkeypatch.setattr("sys.argv", ["MinePick_Launcher_cli.exe"])
    code = run_entry.main()
    captured = capsys.readouterr()
    assert code == 0
    assert "usage" in captured.out.lower()


def test_frozen_cli_build_with_args_runs_cli(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", "C:/x/MinePick_Launcher_cli.exe")
    monkeypatch.setattr("sys.argv", ["MinePick_Launcher_cli.exe", "--version"])
    monkeypatch.setattr("launcher.cli.main", lambda argv: 7)
    assert run_entry.main() == 7


def test_frozen_gui_build_always_gui(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", "C:/x/MinePick_Launcher.exe")
    monkeypatch.setattr("sys.argv", ["MinePick_Launcher.exe", "--whatever"])
    monkeypatch.setattr("gui.main.main", lambda: 42)
    assert run_entry.main() == 42


def test_dev_mode_args_go_to_cli(monkeypatch):
    monkeypatch.setattr("sys.frozen", False, raising=False)
    monkeypatch.setattr("sys.argv", ["run.py", "whoami"])
    monkeypatch.setattr("launcher.cli.main", lambda argv: 5)
    assert run_entry.main() == 5


def test_dev_mode_no_args_go_to_gui(monkeypatch):
    monkeypatch.setattr("sys.frozen", False, raising=False)
    monkeypatch.setattr("sys.argv", ["run.py"])
    monkeypatch.setattr("gui.main.main", lambda: 9)
    assert run_entry.main() == 9
