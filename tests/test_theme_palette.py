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

"""The application palette must follow the theme, not the platform's colour scheme.

The launcher styles everything through QSS, and QSS colours never reach QPalette. Qt still draws some
surfaces itself - native popup frames, menu shadows, platform-drawn viewports, disabled text - from the
palette, and the platform hands us one that follows the *system* colour scheme. On a dark-mode Windows
the light theme therefore painted dark surfaces wherever the stylesheet stopped, which is what the user
reported as "the light theme is inexplicably ugly". These tests pin the palette to the same tokens the
stylesheet uses, so the two halves cannot drift apart again.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from gui import theme


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


CHECKED_ROLES = (
    "Window",
    "WindowText",
    "Base",
    "AlternateBase",
    "Text",
    "Button",
    "ButtonText",
    "Highlight",
    "HighlightedText",
    "ToolTipBase",
    "ToolTipText",
    "PlaceholderText",
)


@pytest.mark.parametrize("name", ("dark", "light"))
def test_every_palette_role_comes_from_a_token(app, name):
    tokens = theme.theme_palette(name)
    palette = theme.theme_qpalette(name)
    for role_name in CHECKED_ROLES:
        role = getattr(QPalette.ColorRole, role_name, None)
        if role is None:
            continue
        token = theme.PALETTE_ROLES[role_name]
        assert palette.color(role).name() == tokens[token].lower(), (
            f"{name}: {role_name} is {palette.color(role).name()}, "
            f"but token {token} is {tokens[token]}"
        )


def test_the_two_themes_do_not_share_a_palette(app):
    dark = theme.theme_qpalette("dark")
    light = theme.theme_qpalette("light")
    for role_name in ("Window", "Base", "Text", "Button"):
        role = getattr(QPalette.ColorRole, role_name)
        assert dark.color(role).name() != light.color(role).name(), role_name


def test_light_window_is_light_and_dark_window_is_dark(app):
    """The concrete failure the user hit: a light theme over the platform's dark palette."""
    light_window = theme.theme_qpalette("light").color(QPalette.ColorRole.Window)
    dark_window = theme.theme_qpalette("dark").color(QPalette.ColorRole.Window)
    assert light_window.lightness() > 128, light_window.name()
    assert dark_window.lightness() < 128, dark_window.name()


def test_disabled_group_uses_the_disabled_tokens(app):
    tokens = theme.theme_palette("light")
    palette = theme.theme_qpalette("light")
    assert (
        palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()
        == tokens["FG_DISABLED"].lower()
    )
    assert (
        palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base).name()
        == tokens["BG_DISABLED"].lower()
    )


def test_highlight_pairs_with_a_readable_foreground(app):
    """ACCENT_SEL carries ACCENT_SEL_TEXT in the stylesheet; the palette must say the same."""
    for name in ("dark", "light"):
        tokens = theme.theme_palette(name)
        palette = theme.theme_qpalette(name)
        assert palette.color(QPalette.ColorRole.Highlight).name() == tokens["ACCENT_SEL"].lower()
        assert (
            palette.color(QPalette.ColorRole.HighlightedText).name()
            == tokens["ACCENT_SEL_TEXT"].lower()
        )


def test_apply_theme_installs_the_palette(app, monkeypatch):
    monkeypatch.setattr(theme, "_last_applied", None)
    theme.apply_theme("light", None, None, "default")
    assert (
        app.palette().color(QPalette.ColorRole.Window).name()
        == theme.theme_palette("light")["BG_WINDOW"].lower()
    )

    monkeypatch.setattr(theme, "_last_applied", None)
    theme.apply_theme("dark", None, None, "default")
    assert (
        app.palette().color(QPalette.ColorRole.Window).name()
        == theme.theme_palette("dark")["BG_WINDOW"].lower()
    )
