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

"""Game-process running (stdio inherit mode).

Sandbox/packaging compatible: output is not captured via pipes (restricted environments forbid piped stdio);
output inherits the console directly, and log redirection is up to the caller. The GUI runs the same argv with QProcess.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


def run_process(
    argv: list[str], cwd: Path, on_started: Callable[[], None] | None = None
) -> int:
    """Run with inherited stdio and wait for exit; Ctrl+C forwards a termination signal.

    on_started is called once after the process starts successfully (used by the GUI to auto-hide).
    """
    # Under a GUI (no console parent process), don't pop a console window (console-flash fix); the CLI keeps inheritance.
    # creationflags is Windows-only; passing it on other platforms raises ValueError.
    extra: dict = {}
    if os.name == "nt" and sys.stdout is None and sys.stdin is None:
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(argv, cwd=str(cwd), **extra)
    if on_started is not None:
        on_started()
    try:
        return proc.wait()
    except KeyboardInterrupt:
        print()
        print("正在关闭游戏进程...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return 130


def find_new_crash_reports(game_dir: Path, since: float) -> list[Path]:
    """Return crash reports generated after `since`."""
    reports_dir = game_dir / "crash-reports"
    if not reports_dir.exists():
        return []
    out: list[Path] = []
    for report in reports_dir.glob("crash-*.txt"):
        try:
            if report.stat().st_mtime >= since:
                out.append(report)
        except OSError:
            continue
    return out
