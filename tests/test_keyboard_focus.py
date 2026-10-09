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

Two levels, because the weaker one passed while users still could not see the focus:

1. every page can be walked with Tab alone, and every stop has a focus state defined in the
   stylesheets;
2. focusing a stop actually **changes pixels** around it. A rule can exist and still lose to an
   id-scoped rule - which is what the real-machine walkthrough (T-0001/T-0002) found on the icon
   button and the sidebar while this file reported a clean sheet.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROW = re.compile(r"^\|\s*([a-z_]+)\s*\|\s*`([^`]+)`\s*\|\s*`([^`]*)`\s*\|\s*([^|]*)\|\s*([^|]*)\|")

# Focus stops whose focus state is deliberately invisible. Every entry needs a reason: an entry here
# claims a user can still tell where focus is (usually because a child shows it instead).
FOCUS_VISUAL_WHITELIST: dict[tuple[str, str], str] = {}


@pytest.fixture(scope="module")
def walkthrough_report() -> str:
    """Run the walkthrough once and hand its Markdown to every test in this module.

    The workspace temp folder is used rather than pytest's tmp_path: that one is unusable here (see
    the project's testing note), and the report has to land somewhere writable.
    """
    out_dir = ROOT.parent / "tmp" / "kb_guard"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "keyboard_walkthrough.md"
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
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    return report.read_text(encoding="utf-8")


def _invisible_stops(report: str) -> list[tuple[str, str, str, str, str]]:
    """Rows of the 'no visible focus effect' section: page, class, object name, label, rect."""
    marker = "## 无可辨焦点效果的控件"
    if marker not in report:
        return []
    section = report.split(marker, 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        match = ROW.match(line.strip())
        if match and match.group(2) not in ("控件", "---"):
            page, kind, name, label, rect = match.groups()
            rows.append((page, kind, name, label.strip(), rect.strip()))
    return rows


def test_keyboard_walkthrough_finds_no_gaps(walkthrough_report):
    assert "硬失败:`0`" in walkthrough_report, walkthrough_report
    assert "⚠️" not in walkthrough_report, (
        "some focus stop has no :focus rule in the stylesheets:\n" + walkthrough_report
    )
    # a page with no focus stop at all would mean the page cannot be used with a keyboard
    assert "Tab 完全不动" not in walkthrough_report, walkthrough_report


def test_every_focus_stop_changes_pixels(walkthrough_report):
    """Keyboard focus must be *visible*, not merely styled.

    This is a hard assertion as of the 0.4.0 focus convergence: the check compares the pixels around a
    stop focused versus unfocused, so a rule that exists but never wins (or never repaints) fails here.
    The whitelist stays empty - an entry would claim the user can still tell where focus is.
    """
    offenders = [
        f"{page}: {kind} {name or '-'} {label or '-'} @ {rect}"
        for page, kind, name, label, rect in _invisible_stops(walkthrough_report)
        if (kind, name) not in FOCUS_VISUAL_WHITELIST
    ]
    assert not offenders, (
        "these focus stops produce no visible change (or their exemption is stale):\n  "
        + "\n  ".join(offenders)
    )


def _weak_name_stops(report: str) -> list[str]:
    """Stops whose accessible name is missing, or comes only from a placeholder/tooltip."""
    weak: list[str] = []
    for line in report.splitlines():
        if "可读名称缺失或过弱" not in line:
            continue
        _, _, rest = line.partition(":")
        weak.extend(part.strip() for part in rest.split(",") if part.strip())
    return weak


@pytest.mark.xfail(
    strict=False,
    reason=(
        "0.4.0 has given explicit accessible names to the account button and the three search fields; "
        "the remaining stops are lists, tables, scroll areas and the mods search field, which need new "
        "i18n keys. Tracked by the WCAG conformance table, section four."
    ),
)
def test_every_control_has_a_usable_accessible_name(walkthrough_report):
    """WCAG 4.1.2: a focusable control must expose a name a screen reader can announce.

    A placeholder disappears as soon as the field has content, and a tooltip phrased as an instruction
    ("switch account") is read out as an order - which is why C4 asks for a noun instead. Both are
    counted as weak here.
    """
    offenders = _weak_name_stops(walkthrough_report)
    assert not offenders, "controls without a usable accessible name:\n  " + "\n  ".join(offenders)
