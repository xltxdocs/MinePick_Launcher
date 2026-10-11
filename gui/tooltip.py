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

r"""A tooltip the pointer can travel into, and that stays put while it is read (WCAG 1.4.13).

Qt's own ``QToolTip`` fails two clauses of 1.4.13 on the desktop: the bubble disappears the moment the
pointer moves towards it, and it retires on its own timer. For a keyboard or magnification user that
means the text can be read only while the mouse is frozen in place.

So the launcher draws its own, and the difference is deliberate:

* **Hoverable** - the bubble is a real window that accepts the pointer. Leaving the widget starts a
  short grace period instead of closing: arrive inside the bubble in time and it stays.
* **Persistent** - nothing closes it on a timer. It goes away when the pointer leaves both the widget
  and the bubble, on Escape, on a click or wheel, and when the window is deactivated.
* **Dismissible** - Escape closes it without side effects, which is the clause Qt already satisfied.

The application event filter swallows ``QEvent.ToolTip``, so Qt never draws its own bubble on top of
ours. Only the plain-text ``toolTip()`` of the widget is used, which is all the launcher sets.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from gui import motion
from gui.widgets import widget_alive

__all__ = ["TooltipController", "TooltipLayer"]

TOOLTIP_DELAY_MS = 700  # Qt's own rhythm; users already expect a short pause before the bubble
TOOLTIP_GRACE_MS = 140  # time to travel from the widget into the bubble
TOOLTIP_FADE_MS = 90  # opacity only: nothing moves, so only the fade has to respect reduced motion
TOOLTIP_MARGIN_X = 12
TOOLTIP_MARGIN_Y = 16
TOOLTIP_MAX_WIDTH = 360


class TooltipLayer(QWidget):
    """The bubble itself: frameless, never focused, and able to hold the pointer."""

    def __init__(self, controller: TooltipController | None = None) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self._controller = controller
        self.setObjectName("tooltipLayer")
        # A tooltip must never take focus or appear in the taskbar, and it must not steal activation
        # from the window the user is working in.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setMaximumWidth(TOOLTIP_MAX_WIDTH)
        self._label.setObjectName("tooltipLayerText")
        layout = QVBoxLayout(self)
        # Spacing lives here rather than in the stylesheet so the bubble sizes to its text exactly.
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self._label)

    # -- content ---------------------------------------------------------------

    def text(self) -> str:
        return self._label.text()

    def set_text(self, text: str) -> None:
        self._label.setText(text)
        self.adjustSize()

    # -- pointer tracking (the "hoverable" half of 1.4.13) ----------------------

    def enterEvent(self, event) -> None:
        if self._controller is not None:
            self._controller.pointer_entered_layer()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._controller is not None:
            self._controller.pointer_left_layer()
        super().leaveEvent(event)

    # -- placement -------------------------------------------------------------

    def show_at(self, global_pos: QPoint, text: str) -> None:
        """Show the bubble near ``global_pos``, kept inside the screen it appears on."""
        self.set_text(text)
        pos = QPoint(global_pos.x() + TOOLTIP_MARGIN_X, global_pos.y() + TOOLTIP_MARGIN_Y)
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            size = self.sizeHint()
            pos.setX(min(pos.x(), area.right() - size.width()))
            pos.setY(min(pos.y(), area.bottom() - size.height()))
            pos.setX(max(pos.x(), area.left()))
            pos.setY(max(pos.y(), area.top()))
        self.move(pos)
        if motion.animations_enabled():
            self.setWindowOpacity(0.0)
            self.show()
            self._fade_in()
        else:
            # Reduced motion keeps the feedback (the bubble appears) and drops the animation.
            self.setWindowOpacity(1.0)
            self.show()

    def _fade_in(self) -> None:
        from PySide6.QtCore import QPropertyAnimation

        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(TOOLTIP_FADE_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation


class TooltipController(QObject):
    """Application event filter: turns Qt tooltip requests into our own hoverable bubble."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.layer = TooltipLayer(self)
        self._source: QWidget | None = None
        self._text = ""
        self._pos = QPoint()
        self._pointer_in_layer = False
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.setInterval(TOOLTIP_DELAY_MS)
        self._delay.timeout.connect(self._show_now)
        self._grace = QTimer(self)
        self._grace.setSingleShot(True)
        self._grace.setInterval(TOOLTIP_GRACE_MS)
        self._grace.timeout.connect(self._close_if_outside)

    # -- public API (also what the tests drive) --------------------------------

    def show_for(self, source: QWidget | None, text: str, global_pos: QPoint) -> None:
        """Show ``text`` for ``source`` right away, without waiting out the delay."""
        if not text.strip():
            self.hide_now()
            return
        self._source = source
        self._text = text
        self._pos = QPoint(global_pos)
        self._show_now()

    def hide_now(self) -> None:
        """Close the bubble and forget what it was showing."""
        self._delay.stop()
        self._grace.stop()
        self._pointer_in_layer = False
        self._source = None
        self._text = ""
        self.layer.hide()

    def visible(self) -> bool:
        try:
            return self.layer.isVisible()
        except RuntimeError:  # the C++ layer is already gone (application teardown)
            return False

    # -- pointer bookkeeping ---------------------------------------------------

    def pointer_entered_layer(self) -> None:
        self._pointer_in_layer = True
        self._grace.stop()

    def pointer_left_layer(self) -> None:
        # Leaving the bubble starts the same short grace as leaving the widget, so crossing its edge
        # does not flicker it away, and a Leave that arrives without a preceding Enter (the offscreen
        # platform synthesises one when a tool window is first shown) closes nothing by itself.
        if not self._pointer_in_layer:
            return
        self._pointer_in_layer = False
        self._grace.start()

    # -- event filter ----------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            self._on_tooltip_request(obj, event)
            # Swallow it: Qt must not draw its own bubble, which cannot be hovered.
            return True
        if kind == QEvent.Type.Leave and obj is self._source:
            self._grace.start()
        elif self._is_dismiss_event(obj, kind, event) and self._layer_visible():
            self.hide_now()
        return False

    def _layer_visible(self) -> bool:
        """Whether the bubble is on screen, tolerating a layer whose C++ object is already gone.

        The controller is installed as the application-wide event filter and outlives the bubble when
        something else destroys that top-level widget first: the shared test teardown closes and deletes
        every window, and a later click or wheel then reached this filter with a deleted ``TooltipLayer``
        and raised "Internal C++ object already deleted" out of the filter. Same defence as ``visible()``
        and as the other application-wide filter in ``gui.widgets`` - read the layer by attribute and
        treat a dead one as "nothing to dismiss".
        """
        layer = getattr(self, "layer", None)
        if layer is None or not widget_alive(layer):
            return False
        try:
            return layer.isVisible()
        except RuntimeError:  # the C++ object died between the validity check and the call
            return False

    def _is_dismiss_event(self, obj, kind, event) -> bool:
        """Escape, a click, a wheel, or the window the user is working in losing activation."""
        if kind in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
            QEvent.Type.ApplicationDeactivate,
        ):
            return True
        if kind == QEvent.Type.KeyPress:
            return event.key() == Qt.Key.Key_Escape
        # WindowDeactivate is deliberately not a dismissal. Qt reports one for the source's own window
        # the moment our tool window appears, and for the bubble itself (measured); neither means the
        # user went away. The whole application losing activation still closes the bubble, which is
        # what actually matters.
        return False

    def _on_tooltip_request(self, obj, event) -> None:
        if not isinstance(obj, QWidget) or not widget_alive(obj):
            return
        if obj is self.layer or self.layer.isAncestorOf(obj):
            # The pointer is on our own bubble, which has no tooltip of its own. Rotating the state
            # here would close what the user is trying to read: staying open is the whole point.
            return
        text = obj.toolTip()
        if not text.strip():
            self.hide_now()
            return
        self._source = obj
        self._text = text
        if isinstance(event, QHelpEvent):
            self._pos = event.globalPos()
        self._delay.start()

    def _show_now(self) -> None:
        if not self._text:
            return
        if self._source is not None and not widget_alive(self._source):
            self.hide_now()
            return
        self._pointer_in_layer = False
        self.layer.show_at(self._pos, self._text)

    def _close_if_outside(self) -> None:
        """The grace period expired: close unless the pointer is genuinely on the widget or bubble.

        Asking the cursor is not redundant. Qt sends a Leave to the widget when our tool window
        appears, and window managers are inconsistent about enter/leave for tool windows, so the
        events alone would close the bubble while the pointer is still sitting on the widget.
        """
        if self._pointer_in_layer or self._pointer_over_widgets():
            return
        self.hide_now()

    def _pointer_over_widgets(self) -> bool:
        """True when the cursor is inside the source widget or the bubble."""
        from PySide6.QtGui import QCursor

        position = QCursor.pos()
        for widget in (self.layer, self._source):
            if widget is None or not widget_alive(widget) or not widget.isVisible():
                continue
            try:
                if widget.rect().contains(widget.mapFromGlobal(position)):
                    return True
            except RuntimeError:  # the C++ object died between the check and the call
                continue
        return False
