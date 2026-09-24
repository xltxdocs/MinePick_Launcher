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

"""Every translation key referenced in code must exist in the language tables.

The key-set test only compares the nine tables with each other; it cannot notice a key that is
used in code but missing everywhere, which is exactly how a button once shipped showing
`diagnosis.dialog.copy` instead of a label. This test reads the source and checks the literals.
"""

from __future__ import annotations

import re
from pathlib import Path

from gui import i18n
from launcher import i18n as ci18n

ROOT = Path(__file__).resolve().parent.parent
# `tr(...)` is the GUI translator; the core only owns `tr_core(...)`. The knowledge base's report
# module uses a local alias named `tr` for the caller-supplied translate callable, so its literals
# belong to the GUI tables - hence the separate patterns per layer.
UI_CALL = re.compile(r"""\btr\(\s*["']([a-z][a-z0-9_.]*)["']""")
CORE_CALL = re.compile(r"""\btr_core\(\s*["']([a-z][a-z0-9_.]*)["']""")
UI_DIRS = (ROOT / "gui", ROOT / "tools")
CORE_DIRS = (ROOT / "launcher",)


def _keys_in(directories: tuple[Path, ...], pattern: re.Pattern[str]) -> set[str]:
    keys: set[str] = set()
    for directory in directories:
        for path in directory.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            # A literal ending in "." is a prefix that gets concatenated with a dynamic suffix
            keys.update(key for key in pattern.findall(text) if not key.endswith("."))
    return keys


def test_ui_keys_used_in_code_exist() -> None:
    table = i18n.TRANSLATIONS["en_us"]
    missing = sorted(key for key in _keys_in(UI_DIRS, UI_CALL) if key not in table)
    assert not missing, f"keys used in code but missing from the UI tables: {missing}"


def test_core_keys_used_in_code_exist() -> None:
    table = ci18n.CORE_TRANSLATIONS["en_us"]
    missing = sorted(key for key in _keys_in(CORE_DIRS, CORE_CALL) if key not in table)
    assert not missing, f"keys used in code but missing from the core tables: {missing}"
