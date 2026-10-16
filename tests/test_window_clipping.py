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

"""The window may never be narrower than the layout it has to paint.

The defect this pins: the window carried `setMinimumSize(1000, 610)` from 2026-10-11 (82ca4c7), while
the same layout needs 1164px in fr_fr (1048px even in en_us). A minimum *below* the layout's own
requirement does not make the window fit: Qt paints the page into a strip narrower than its minimum,
which is what a user saw as clipped text on the instances page - an elided "This PC > ... > Resource:"
line, an ellipsis in the search box, truncated buttons.

Two measurement facts decide how this has to be written, both verified on this build:

* a widget's ``minimumSizeHint()`` is refreshed by a layout pass, and a window that was never shown
  never gets one - while it is hidden the hint stays at the launch page's width even after every page
  exists. The window is therefore shown with ``WA_DontShowOnScreen``, the same attribute the render
  tools and ``tests/conftest.py`` use to lay out and paint a real window without touching the desktop;
* the constant only clips in languages whose layout is wider than it. Chinese asks for 990px in total,
  so a gate restricted to the suite's default language would stay green on the broken build - which is
  exactly what happened when the old constant was put back to check it. The widest language (fr_fr,
  1164px per tools/measure_min_width.py) is therefore the case the gate is calibrated on.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui import i18n
from gui.main_window import NAV_KEYS, MainWindow

#: fr_fr drives the width floor (1164px measured by tools/measure_min_width.py); zh_cn is the suite
#: default and proves the gate also holds in the language the rest of the suite runs in.
LANGUAGES = ("fr_fr", "zh_cn")


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Same three stubs tests/test_gui.py installs: no network, no Java probing subprocess."""
    def _fail(**kw):
        raise RuntimeError("offline test")

    monkeypatch.setattr("gui.pages.versions_page.fetch_manifest", _fail)
    monkeypatch.setattr("launcher.mods.modrinth._client", _fail)
    monkeypatch.setattr("gui.pages.java_page.list_java", lambda *a, **kw: [])


def _settle(app, window) -> None:
    """Let the layout pass run: the window's floor is refreshed on it (see MainWindow.event)."""
    for _ in range(8):
        app.processEvents()


def _window(app, ws_tmp, language: str) -> MainWindow:
    """A real, laid-out window in ``language`` that is never on screen (WA_DontShowOnScreen)."""
    i18n.set_language(language)
    built = MainWindow()
    built.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    built.resize(1000, 600)  # what tools/shot_pages.py asks for; the floor has to win over it
    built.show()
    _settle(app, built)
    return built


@pytest.fixture
def window(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "clip"))
    built = _window(app, ws_tmp, "fr_fr")
    yield built
    built.close()
    built.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_window_minimum_is_never_below_the_layout_requirement(app, monkeypatch, ws_tmp, language):
    """minimumWidth() >= minimumSizeHint().width() after every page has been visited."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / f"clip_{language}"))
    built = _window(app, ws_tmp, language)
    try:
        for index, key in enumerate(NAV_KEYS):
            built.sidebar.setCurrentRow(index)
            _settle(app, built)
            needed = built.minimumSizeHint().width()
            assert built.minimumWidth() >= needed, (
                f"[{language}] after visiting '{key}' the layout needs {needed}px but the window would "
                f"accept {built.minimumWidth()}px - the page would be painted into a narrower strip"
            )
    finally:
        built.close()
        built.deleteLater()
        app.processEvents()
        i18n.set_language("zh_cn")


def test_the_widest_language_really_does_exceed_the_old_constant(window, app):
    """Guard against a vacuous pass: fr_fr must demand more than the removed 1000px pin."""
    for index in range(len(NAV_KEYS)):
        window.sidebar.setCurrentRow(index)
        _settle(app, window)
    needed = window.minimumSizeHint().width()
    assert needed > 1000, (
        f"the layout only asks for {needed}px, so this file could not tell the fixed build from the "
        f"clipped one - check that the window was shown before the hint was read"
    )


def test_no_page_is_given_less_width_than_its_own_minimum(window, app):
    """The user-visible half: the page's viewport is as wide as the page says it must be."""
    crowded = []
    for index, key in enumerate(NAV_KEYS):
        window.sidebar.setCurrentRow(index)
        _settle(app, window)
        page = window.pages[key]
        if page.width() < page.minimumSizeHint().width():
            crowded.append(f"{key}: {page.width()}px < {page.minimumSizeHint().width()}px")
    assert not crowded, "pages were painted below their own minimum width: " + "; ".join(crowded)


def test_a_shown_window_takes_the_floor_before_the_first_grab(window, app):
    """A page built after the window is up still widens it, so a screenshot cannot catch the old width."""
    window.sidebar.setCurrentRow(NAV_KEYS.index("instances"))
    _settle(app, window)
    needed = window.minimumSizeHint().width()
    assert window.width() >= needed, (
        f"the shown window is {window.width()}px wide while its layout needs {needed}px"
    )
    assert window.width() >= window.minimumWidth()
