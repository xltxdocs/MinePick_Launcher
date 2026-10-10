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

"""The focus tracker must survive being handed a widget that no longer exists.

Qt delivers FocusOut from the event queue, so the event can arrive after the widget's C++ side is gone -
during shutdown, or when a window the tests have finished with is collected. The tracker used to reach
straight into property()/style()/unpolish()/polish() on such a wrapper.

The "gone" state is simulated by stubbing shiboken6.isValid rather than by actually deleting a C++
object. Deleting one on purpose leaves a wrapper whose lifetime no longer matches the object it wraps,
and the garbage collector can then run a finalizer on it at an arbitrary later moment - in a full-suite
run that landed inside a download test and took the whole process down with an access violation. A test
must not manufacture that hazard to prove a guard against it.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtWidgets import QApplication, QLineEdit, QScrollArea

from gui import widgets
from gui.widgets import KeyboardFocusTracker


def _app():
    return QApplication.instance() or QApplication([])


def test_marking_an_invalid_edit_is_a_no_op(monkeypatch):
    _app()
    tracker = KeyboardFocusTracker()
    monkeypatch.setattr(shiboken6, "isValid", lambda _widget: False)
    tracker._mark(QLineEdit(), True)
    tracker._mark(QLineEdit(), False)


def test_marking_an_invalid_scroll_area_is_a_no_op(monkeypatch):
    """Scroll areas are what the tracker started covering when the abort appeared."""
    _app()
    tracker = KeyboardFocusTracker()
    monkeypatch.setattr(shiboken6, "isValid", lambda _widget: False)
    tracker._mark(QScrollArea(), True)
    tracker._mark(QScrollArea(), False)


def test_a_widget_that_dies_between_check_and_call_is_tolerated(monkeypatch):
    """The object can go away after the validity check; that path must stay quiet too."""
    _app()
    tracker = KeyboardFocusTracker()
    monkeypatch.setattr(shiboken6, "isValid", lambda _widget: True)

    widget = QLineEdit()

    def die(*_args, **_kwargs):
        raise RuntimeError("already deleted")

    monkeypatch.setattr(widget, "property", die)
    tracker._mark(widget, True)


def test_a_live_widget_is_still_marked():
    """The guard must not stop the tracker from working: a live widget is marked and restyled."""
    _app()
    tracker = KeyboardFocusTracker()
    widget = QLineEdit()
    tracker._mark(widget, True)
    assert bool(widget.property("keyboardFocus")) is True
    tracker._mark(widget, False)
    assert bool(widget.property("keyboardFocus")) is False
    assert widgets.KeyboardFocusTracker is KeyboardFocusTracker
