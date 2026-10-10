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

"""How ``apply_theme`` talks to ``QApplication.setStyleSheet``: skip repeats, clear before changing.

``setStyleSheet`` makes Qt re-polish every widget, and the cost of *replacing* the application sheet
accumulates within a process: in a clean run with one window, eight consecutive replacements took 0.06s,
0.25s, 0.42s, 0.42s, 0.44s, 1.72s, 2.16s, and a real 1455-widget window paid 4.5-6.5s per dark/light
switch once it had. Two things follow, and both are pinned here:

* re-applying the theme that is already in force must not touch the stylesheet at all - the settings page
  saves on every control change, so without that guard a session pays seconds per change;
* a genuine change must drop the sheet before installing the new one, which keeps the cost flat (0.79s
  for the first switch, ~1.1s after: ten switches cost 9.7s instead of 54.3s).
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


def _record_setstylesheet(monkeypatch) -> list[str]:
    """Every sheet handed to ``QApplication.setStyleSheet``, in order."""
    calls: list[str] = []
    original = QApplication.setStyleSheet

    def recording(self, sheet):  # type: ignore[no-untyped-def]
        calls.append(sheet)
        return original(self, sheet)

    monkeypatch.setattr(QApplication, "setStyleSheet", recording)
    return calls


def test_repeated_identical_apply_does_not_touch_the_stylesheet(app, monkeypatch):
    calls = _record_setstylesheet(monkeypatch)
    monkeypatch.setattr(theme, "_last_applied", None)

    theme.apply_theme("dark", "", None, "default")
    after_first = len(calls)

    for _ in range(4):
        theme.apply_theme("dark", "", None, "default")
    assert len(calls) == after_first, "an unchanged theme re-polished the whole application"


def test_a_real_change_clears_before_installing(app, monkeypatch):
    """A real change is two calls: empty the application sheet, then install the new one in full.

    The clearing is deliberate and load-bearing for performance (see the module docstring). It is safe
    only because the palette is set first, which is what ``test_the_palette_is_in_force_before_the_sheet``
    checks: while the sheet is momentarily absent, the surfaces Qt draws itself come from the palette
    rather than from the platform default.

    This used to assert the opposite - that the sheet is never cleared - on the evidence of the 0.4.0
    build shipping unstyled widgets. Re-measuring on the real platform after the palette was themed
    (commit 3166c91) showed the fast path is pixel-identical: 8 pages plus the wizard, before and after a
    dark->light switch, match exactly at 3.3M samples each, against a measured noise floor of zero.
    """
    monkeypatch.setattr(theme, "_last_applied", None)
    app.setStyleSheet("")  # nothing installed yet: the first apply has nothing to clear
    calls = _record_setstylesheet(monkeypatch)

    theme.apply_theme("dark", "", None, "default")
    assert len(calls) == 1, calls
    assert "QWidget" in calls[0], "the first apply must install the full sheet"
    assert "__ACCENT__" not in calls[0], "placeholders survived into the stylesheet"

    calls.clear()
    theme.apply_theme("light", "", None, "default")
    assert len(calls) == 2, calls
    assert calls[0] == "", "the old sheet was replaced without being cleared first"
    assert "QWidget" in calls[1], "the sheet installed after the clear must be the full sheet"
    assert "__ACCENT__" not in calls[1]

    calls.clear()
    theme.apply_theme("dark", "#35a06a", None, "default")  # an accent change is a change too
    assert len(calls) == 2 and calls[0] == "", calls
    assert "QWidget" in calls[1] and "__ACCENT__" not in calls[1]


def test_the_palette_is_in_force_before_the_sheet(app, monkeypatch):
    """The palette carries the theme, so the window is never unstyled while the sheet is cleared.

    This is the precondition that makes clearing safe, so it is asserted rather than assumed. The record
    below is (was this call a clear?, the Window role colour at the time): the clear itself must already
    be running with the new theme's palette, because the Window role is what Qt paints the surfaces it
    draws itself with - native popup frames, viewports - while the stylesheet is momentarily absent.
    """
    monkeypatch.setattr(theme, "_last_applied", None)
    app.setStyleSheet("")

    seen: list[tuple[bool, str]] = []
    original = QApplication.setStyleSheet

    def recording(self, sheet):  # type: ignore[no-untyped-def]
        seen.append((sheet == "", self.palette().color(QPalette.ColorRole.Window).name().lower()))
        return original(self, sheet)

    monkeypatch.setattr(QApplication, "setStyleSheet", recording)

    theme.apply_theme("light", "", None, "default")
    theme.apply_theme("dark", "", None, "default")

    light_window = theme.theme_palette("light", "")["BG_WINDOW"].lower()
    dark_window = theme.theme_palette("dark", "")["BG_WINDOW"].lower()
    assert seen == [(False, light_window), (True, dark_window), (False, dark_window)], seen


def test_the_sheet_on_the_application_matches_the_last_apply(app, monkeypatch):
    monkeypatch.setattr(theme, "_last_applied", None)
    theme.apply_theme("light", "", None, "default")
    light_sheet = app.styleSheet()
    assert light_sheet

    theme.apply_theme("dark", "", None, "default")
    dark_sheet = app.styleSheet()
    assert dark_sheet != light_sheet, "switching the theme left the previous stylesheet in place"

    for palette_name in ("light", "dark"):
        for key in theme.theme_palette(palette_name):
            assert f"__{key}__" not in light_sheet, f"{key} survived as a placeholder"
            assert f"__{key}__" not in dark_sheet, f"{key} survived as a placeholder"
