"""run.py / run_cli.py 入口分发测试（CLI 构建与 GUI 构建分离）。"""

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
