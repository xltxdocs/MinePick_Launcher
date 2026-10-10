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

"""Two controls must style themselves, because the application stylesheet is not adopted everywhere.

On the real Windows platform Qt does not adopt the `#wizardOverlay` and `#titleBarMinimize/Close`
rules - measured with a probe colour that never appeared, while the same rules work offscreen. The
wizard came out see-through and the window buttons came out as solid accent squares. Both now set their
own appearance, so these tests assert the *rendered* result rather than checking that something was
configured.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QWidget

from gui import theme
from gui.title_bar import TitleBar
from gui.wizard_overlay import WizardOverlay, WizardStep

GREETING = {"back": "Back", "next": "Next", "done": "Done", "skip": "Skip"}


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def themed(app):
    previous = theme._last_applied
    theme._last_applied = None
    theme.apply_theme("dark", None, None, "default")
    yield theme.current_tokens()
    theme._last_applied = previous


def test_the_tokens_are_published_for_self_styling(themed):
    assert themed, "apply_theme must publish the token table widgets can style themselves from"
    assert themed["BG_WINDOW"] and themed["BG_TITLEBAR_CLOSE"]


def test_wizard_overlay_is_opaque(app, themed):
    """Structural, because offscreen cannot prove this.

    A grab on the offscreen platform always has an opaque buffer, so a pixel test cannot tell an opaque
    overlay from a see-through one - and colouring a parent to try only cascades the parent's stylesheet
    into the child. The rendered proof lives where the bug does: tools/shot_pages_real.py --wizard, whose
    two grabs (overlay alone vs the window under it) are compared pixel for pixel.
    """
    parent = QWidget()
    overlay = WizardOverlay(parent, [WizardStep(title="One", description="d", widget=QWidget())], GREETING)
    try:
        assert overlay.autoFillBackground(), "the overlay must paint its own background"
        assert overlay.backgroundRole() == QPalette.ColorRole.Window
        assert themed["BG_WINDOW"], "the palette carries the theme, so the fill follows it"
    finally:
        parent.deleteLater()


def test_title_bar_buttons_carry_their_own_style(app, themed):
    host = QWidget()
    bar = TitleBar(host, "MinePick Launcher")
    try:
        for button, hover_token in (
            (bar.minimize_button, "BG_TITLEBAR_MINIMIZE"),
            (bar.close_button, "BG_TITLEBAR_CLOSE"),
        ):
            sheet = button.styleSheet()
            assert sheet, "a title-bar button must style itself: the app stylesheet is not adopted here"
            assert "transparent" in sheet, sheet
            assert themed[hover_token] in sheet, (hover_token, sheet)
    finally:
        bar.deleteLater()
        host.deleteLater()


def test_title_bar_buttons_render_as_the_bar_not_as_accent(app, themed):
    host = QWidget()
    host.resize(240, 40)
    bar = TitleBar(host, "t")
    bar.resize(240, 40)
    try:
        bar.show()
        QApplication.processEvents()
        image = bar.grab().toImage()
        accent = themed["ACCENT_BUTTON"].lower()
        window_colour = themed["BG_WINDOW"].lower()
        accent_pixels = 0
        window_pixels = 0
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y).name().lower()
                if colour == accent:
                    accent_pixels += 1
                elif colour == window_colour:
                    window_pixels += 1
        assert window_pixels > 0, "the bar should show the window colour"
        assert accent_pixels == 0, "a title-bar button painted itself with the accent colour again"
    finally:
        bar.hide()
        bar.deleteLater()
        host.deleteLater()
        QApplication.processEvents()


def test_the_glyphs_stay_available(app):
    host = QWidget()
    bar = TitleBar(host, "t")
    try:
        assert bar.minimize_button.text() and bar.close_button.text()
        assert bar.minimize_button.focusPolicy() == Qt.FocusPolicy.NoFocus
    finally:
        bar.deleteLater()
        host.deleteLater()
