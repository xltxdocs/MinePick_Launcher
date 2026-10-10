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

"""A theme swap must not be interrupted by widgets that style themselves.

While apply_theme() has the application stylesheet cleared, Qt walks every widget to tell it the style
changed. A widget that answers by installing its own sheet mutates style data during that walk, which
corrupted the heap (0xc0000374) whenever the theme change came from inside a widget's own signal handler -
saving the settings page, for example. These tests pin the two halves of the fix: self-styling widgets are
not restyled mid-swap, and they are restyled once it has finished.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gui import theme


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_a_self_styling_widget_is_told_after_the_swap_not_during_it(app):
    seen: list[bool] = []

    class Probe:
        def on_theme_applied(self) -> None:
            seen.append(theme.is_applying())

    probe = Probe()
    theme.register_self_styling(probe)
    assert theme.is_applying() is False
    theme.apply_theme("light", "#2f9e6f")
    # The notification is queued on purpose (see apply_theme): it must not run until the event loop has
    # finished dispatching whatever triggered the theme change.
    app.processEvents()
    assert seen == [False], "the widget must be restyled once, and only after the swap finished"
    assert theme.is_applying() is False, "the flag must not be left behind"
    del probe


def test_is_applying_is_only_true_inside_the_swap(app):
    observed: list[bool] = []

    class Probe:
        def on_theme_applied(self) -> None:
            observed.append(theme.is_applying())

    probe = Probe()
    theme.register_self_styling(probe)
    theme.apply_theme("dark", "#35a06a")
    app.processEvents()
    assert observed == [False]
    del probe


def test_window_buttons_carry_the_current_tokens(app):
    """The title-bar buttons are self-styling, so on_theme_applied has to leave them on the new tokens.

    Asserted against the tokens rather than against a remembered sheet: which theme is in force when this
    runs depends on the rest of the session, and apply_theme() skips a repeat of the same pair.
    """
    from gui.main_window import MainWindow

    window = MainWindow()
    try:
        theme.apply_theme("dark", "#35a06a")
        # the restyle is queued, so let it run before looking at the button
        app.processEvents()
        button = window.title_bar.close_button
        dark_sheet = button.styleSheet()
        assert dark_sheet, "the button should carry its own stylesheet"
        assert theme.current_tokens()["FG_HINT"] in dark_sheet, "the dark hint colour should be in force"
        assert theme.is_applying() is False

        theme.apply_theme("light", "#2f9e6f")
        app.processEvents()
        light_sheet = button.styleSheet()
        assert theme.current_tokens()["FG_HINT"] in light_sheet, "the light hint colour should be in force"
        assert light_sheet != dark_sheet, "a theme change must reach the button"
    finally:
        window.close()
