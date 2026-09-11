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

"""Guard: no hard-coded English in user-facing strings (proper nouns and units excepted)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

GUI_ROOT = Path(__file__).resolve().parent.parent / "gui"

# Calls whose literal arguments end up on screen
DISPLAY_CALLS = {
    "addItem",
    "setHorizontalHeaderLabels",
    "setPlaceholderText",
    "setSpecialValueText",
    "setSuffix",
    "setText",
    "setToolTip",
    "setWindowTitle",
}

# Product names, platform names and unit symbols are intentionally not translated
ALLOWED_WORDS = {
    "MinePick",
    "Launcher",
    "Java",
    "Modrinth",
    "CurseForge",
    "Fabric",
    "Forge",
    "NeoForge",
    "Quilt",
    "B",
    "KB",
    "MB",
    "GB",
    "KB/s",
    "MB/s",
    "JVM",
    "UI",
    "PNG",
    "SSD",
}
ALLOWED_PATTERNS = (
    re.compile(r"^#[0-9a-fA-F]{3,8}$"),  # colour literals
    re.compile(r"^[A-Za-z ]+$"),  # font family names (checked against the allow-list below)
)


def _iter_literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        if name not in DISPLAY_CALLS:
            continue
        for argument in list(node.args) + [keyword.value for keyword in node.keywords]:
            values = []
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                values = [argument.value]
            elif isinstance(argument, (ast.List, ast.Tuple)):
                values = [
                    item.value for item in argument.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)
                ]
            for text in values:
                if text.strip():
                    yield node.lineno, text


def test_no_hardcoded_english_in_ui_strings() -> None:
    problems = []
    for path in sorted(GUI_ROOT.rglob("*.py")):
        for lineno, text in _iter_literals(path):
            if not any(ch.isalpha() for ch in text):
                continue
            if not all(ord(ch) < 128 for ch in text):
                continue  # already localized
            if "{}" in text or "%s" in text:
                continue  # formatted from a translation elsewhere
            if any(pattern.match(text) for pattern in ALLOWED_PATTERNS):
                continue
            words = {word for word in re.split(r"[^A-Za-z]+", text) if word}
            if words and words <= ALLOWED_WORDS:
                continue
            problems.append(f"{path.relative_to(GUI_ROOT.parent)}:{lineno}: {text!r}")
    assert not problems, "hard-coded UI strings (use i18n keys instead):\n" + "\n".join(problems)
