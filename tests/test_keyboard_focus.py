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

"""Keyboard-only reachability guard (UI guideline 5.1).

Requires that every page can be walked with Tab alone and that every stop along the way has a focus
state defined in the stylesheets. The walkthrough tool does the walking; this test keeps it honest,
so a new control without a focus style fails the suite instead of quietly shipping.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_keyboard_walkthrough_finds_no_gaps(ws_tmp):
    report = ws_tmp / "keyboard_walkthrough.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "keyboard_walkthrough.py"),
            "--root",
            str(ROOT),
            "--out",
            str(report),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    text = report.read_text(encoding="utf-8")
    assert "硬失败:`0`" in text, text
    assert "⚠️" not in text, "some focus stop has no :focus rule in the stylesheets:\n" + text
    # a page with no focus stop at all would mean the page cannot be used with a keyboard
    assert "Tab 完全不动" not in text, text
