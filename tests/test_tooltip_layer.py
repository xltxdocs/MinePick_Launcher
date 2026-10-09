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

"""WCAG 1.4.13: the tooltip must be hoverable, persistent and dismissible.

Qt's native tooltip fails the first two - it vanishes as soon as the pointer moves towards it and it
retires on its own timer. These tests pin down the replacement: arrival inside the bubble keeps it,
nothing closes it by itself, and Escape still dismisses it.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QCursor, QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from gui import motion
from gui.tooltip import TOOLTIP_GRACE_MS, TooltipController


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def controller(app):
    motion.set_override_for_tests(None)
    control = TooltipController()
    app.installEventFilter(control)
    yield control
    app.removeEventFilter(control)
    control.hide_now()
    motion.set_override_for_tests(None)
    app.processEvents()


def _widget_with_tooltip(app, text: str = "完整名称") -> QWidget:
    widget = QWidget()
    widget.setGeometry(40, 40, 200, 40)
    widget.setToolTip(text)
    widget.show()
    app.processEvents()
    return widget


def _point_at(app, widget) -> None:
    """Put the virtual cursor in the middle of ``widget`` (the offscreen platform honours this)."""
    QCursor.setPos(widget.mapToGlobal(widget.rect().center()))
    app.processEvents()


def _point_away(app) -> None:
    QCursor.setPos(2, 2)
    app.processEvents()


def test_qt_tooltip_request_shows_our_own_bubble(app, controller):
    """Qt asks for a tooltip; our filter answers it instead of letting Qt draw one."""
    widget = _widget_with_tooltip(app)
    _point_at(app, widget)
    event = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), QPoint(120, 220))
    QApplication.sendEvent(widget, event)
    controller._show_now()  # skip the 700ms courtesy delay
    assert controller.visible()
    assert controller.layer.text() == "完整名称"


def test_empty_tooltip_shows_nothing(app, controller):
    widget = _widget_with_tooltip(app, "")
    _point_at(app, widget)
    QApplication.sendEvent(widget, QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), QPoint(120, 220)))
    controller._show_now()
    assert not controller.visible()


def _settle(app, ms: int = 250) -> None:
    """Let the platform's own enter/leave transitions (synthesised when a tool window appears) pass.

    The offscreen platform emits a Leave for a freshly shown tool window even though no pointer moved.
    Waiting it out keeps these tests about the clause under test rather than about that quirk.
    """
    QTest.qWait(ms)
    app.processEvents()


def test_bubble_survives_the_pointer_travelling_into_it(app, controller):
    """Hoverable: the pointer can leave the widget and carry on onto the bubble without losing it."""
    widget = _widget_with_tooltip(app)
    _point_at(app, widget)
    controller.show_for(widget, "完整名称", QPoint(200, 200))
    assert controller.visible()
    _settle(app)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))
    _point_at(app, controller.layer)  # the pointer travelled onto the bubble
    QTest.qWait(TOOLTIP_GRACE_MS + 120)
    assert controller.visible(), "the bubble closed although the pointer was on it"


def test_bubble_closes_when_the_pointer_leaves_both(app, controller):
    widget = _widget_with_tooltip(app)
    _point_at(app, widget)
    controller.show_for(widget, "完整名称", QPoint(200, 200))
    _settle(app)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.Leave))
    _point_away(app)
    QTest.qWait(TOOLTIP_GRACE_MS + 150)
    assert not controller.visible()


def test_bubble_has_no_timeout(app, controller):
    """Persistent: Qt retires its own tooltip after a few seconds; ours must not.

    The pointer rests on the bubble for the whole wait, so anything that closed it here could only be
    a timer of ours - which is exactly what 1.4.13 forbids.
    """
    widget = _widget_with_tooltip(app)
    _point_at(app, widget)
    controller.show_for(widget, "完整名称", QPoint(200, 200))
    _settle(app)
    _point_at(app, controller.layer)
    QTest.qWait(1500)
    assert controller.visible(), "the bubble timed out on its own"


def test_escape_dismisses_the_bubble(app, controller):
    widget = _widget_with_tooltip(app)
    controller.show_for(widget, "完整名称", QPoint(200, 200))
    QTest.keyClick(widget, Qt.Key.Key_Escape)
    app.processEvents()
    assert not controller.visible()


def test_click_dismisses_the_bubble(app, controller):
    widget = _widget_with_tooltip(app)
    controller.show_for(widget, "完整名称", QPoint(200, 200))
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    assert not controller.visible()


def test_reduced_motion_drops_the_fade(app, controller):
    """The bubble still appears; only the animation is dropped, exactly as the guideline asks."""
    widget = _widget_with_tooltip(app)
    motion.set_override_for_tests(False)
    controller.show_for(widget, "完整名称", QPoint(200, 200))
    assert controller.visible()
    assert controller.layer.windowOpacity() == 1.0
    assert getattr(controller.layer, "_animation", None) is None


def test_animation_is_used_when_the_system_allows_it(app, controller):
    widget = _widget_with_tooltip(app)
    motion.set_override_for_tests(True)
    controller.show_for(widget, "完整名称", QPoint(200, 200))
    assert controller.visible()
    assert getattr(controller.layer, "_animation", None) is not None


def test_bubble_never_takes_focus(app, controller):
    """A tooltip that steals focus would interrupt typing; it must stay out of the way.

    The offscreen platform never activates a window, so this checks the properties that guarantee it
    rather than comparing ``focusWidget()`` across a window being shown (which is meaningless here;
    the real desktop check belongs to the T-000x task sheets).
    """
    window = QWidget()
    field = QLineEdit(window)
    window.show()
    field.setFocus()
    app.processEvents()
    controller.show_for(field, "提示", QPoint(200, 200))
    app.processEvents()
    assert QApplication.focusWidget() is not controller.layer
    assert controller.layer.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert controller.layer.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert controller.layer.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
