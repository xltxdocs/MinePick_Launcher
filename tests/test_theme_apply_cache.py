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

"""Re-applying the theme that is already in force must not touch the stylesheet.

``QApplication.setStyleSheet`` makes Qt re-polish every widget, and the cost accumulates over a
session: measured in a clean process with one window, eight consecutive calls took 0.06s, 0.25s, 0.42s,
0.42s, 0.44s, 1.72s, 2.16s. The settings page saves on every control change and re-applies the theme
each time, so tests that drive a handful of settings spent tens of seconds inside Qt - and the same
redundant work happens whenever a save does not actually change the theme.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from gui import theme


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _counting_setstylesheet(monkeypatch) -> dict[str, int]:
    counter = {"calls": 0}
    original = QApplication.setStyleSheet

    def counting(self, sheet):  # type: ignore[no-untyped-def]
        counter["calls"] += 1
        return original(self, sheet)

    monkeypatch.setattr(QApplication, "setStyleSheet", counting)
    return counter


def test_repeated_identical_apply_touches_the_stylesheet_once(app, monkeypatch):
    counter = _counting_setstylesheet(monkeypatch)
    monkeypatch.setattr(theme, "_last_applied", None)

    theme.apply_theme("dark", "", None, "default")
    assert counter["calls"] == 1

    for _ in range(4):
        theme.apply_theme("dark", "", None, "default")
    assert counter["calls"] == 1, "an unchanged theme re-polished the whole application"


def test_a_real_change_still_applies(app, monkeypatch):
    counter = _counting_setstylesheet(monkeypatch)
    monkeypatch.setattr(theme, "_last_applied", None)

    theme.apply_theme("dark", "", None, "default")
    theme.apply_theme("light", "", None, "default")
    theme.apply_theme("dark", "", None, "default")
    assert counter["calls"] == 3

    # and an accent change is a change too
    theme.apply_theme("dark", "#35a06a", None, "default")
    assert counter["calls"] == 4


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
