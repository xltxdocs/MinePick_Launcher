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

import sys

from launcher.launch.runner import find_new_crash_reports, run_process


def test_run_process_exit_code(ws_tmp):
    code = run_process(
        [sys.executable, "-c", "import sys; sys.exit(3)"], cwd=ws_tmp
    )
    assert code == 3


def test_find_new_crash_reports(ws_tmp):
    reports = ws_tmp / "crash-reports"
    reports.mkdir(parents=True)
    (reports / "crash-2024-01-01.txt").write_text("x", encoding="utf-8")
    import time

    recent = find_new_crash_reports(ws_tmp, time.time() - 1)
    assert len(recent) == 1
    old = find_new_crash_reports(ws_tmp, time.time() + 100000)
    assert old == []

def test_run_process_no_creationflags_on_posix(ws_tmp, monkeypatch):
    """Non-Windows platforms must not pass creationflags (otherwise subprocess raises ValueError)."""
    import subprocess

    captured = {}

    class FakeProc:
        def __init__(self, *a, **kw):
            captured.update(kw)

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(subprocess, "Popen", FakeProc)
    monkeypatch.setattr("launcher.launch.runner.os.name", "posix")
    assert run_process(["java", "-x"], ws_tmp) == 0
    assert "creationflags" not in captured

