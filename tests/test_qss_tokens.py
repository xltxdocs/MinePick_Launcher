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

"""The stylesheets must hold no colour literals, and every token they use must resolve.

Two failure modes this catches, both of which are invisible until someone looks at the UI:
  * a colour written straight into a sheet - it then ignores the theme and the accent setting;
  * a token that exists in only one theme's palette - the placeholder is substituted with nothing
    and Qt renders the raw text `__TOKEN__` in its place, or the colour silently falls back.

Comment text and selectors are ignored: `QLabel#accentSwatch` and a prose `#0f141b` in a comment are
not colours, and a naive regex over the whole file reports both as if they were.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gui import theme

RESOURCES = Path(__file__).resolve().parent.parent / "gui/resources"
SHEETS = ("style.qss", "style_light.qss")
THEMES = ("dark", "light")

COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
HEX = re.compile(r"#[0-9a-fA-F]{3,8}")
PLACEHOLDER = re.compile(r"__([A-Za-z0-9_]+)__")
# resolved by apply_theme() from other sources (fonts, image paths, radius presets)
NON_COLOUR_PLACEHOLDERS = {
    "FONT",
    "CHECK",
    "DOWN_ARROW",
    "SPIN_UP",
    "SPIN_DOWN",
    "RADIUS_XS",
    "RADIUS_SM",
    "RADIUS_LG",
}


def _declaration_values(text: str) -> list[tuple[int, str]]:
    """(line number, declaration text) with comments and selector parts removed."""
    stripped = COMMENT.sub(lambda match: "\n" * match.group(0).count("\n"), text)
    out: list[tuple[int, str]] = []
    for number, raw in enumerate(stripped.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if "{" in line:
            line = line.split("{", 1)[1]
        line = line.split("}", 1)[0].strip()
        if line:
            out.append((number, line))
    return out


@pytest.mark.parametrize("sheet", SHEETS)
def test_stylesheet_has_no_colour_literal(sheet: str):
    offenders = [
        f"{sheet}:{number}: {line}"
        for number, line in _declaration_values((RESOURCES / sheet).read_text(encoding="utf-8"))
        if HEX.search(line)
    ]
    assert not offenders, (
        "These declarations use a colour literal; add a token to theme.NEUTRAL_TOKENS instead:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("sheet", SHEETS)
@pytest.mark.parametrize("mode", THEMES)
def test_every_placeholder_resolves_in_both_themes(sheet: str, mode: str):
    text = (RESOURCES / sheet).read_text(encoding="utf-8")
    body = COMMENT.sub("", text)
    used = set()
    for _number, line in _declaration_values(body):
        used |= set(PLACEHOLDER.findall(line))
    used -= NON_COLOUR_PLACEHOLDERS

    palette = theme.theme_palette(mode, None)
    missing = sorted(name for name in used if name not in palette)
    assert not missing, (
        f"{sheet} uses tokens that the '{mode}' palette does not define: {missing}\n"
        f"Add them to theme.NEUTRAL_TOKENS (or accent_palette) with a value for '{mode}'."
    )
