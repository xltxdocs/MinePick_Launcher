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

"""Custom window frame: the window title and buttons drawn in the app's own style.

The native Windows title bar stays light-grey/white no matter what the app looks like, which
breaks the flat dark design. This bar replaces it: the window is frameless and the frame is
painted by the style sheet, so both themes match.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from gui import theme

BAR_HEIGHT = 38


class _WindowButton(QPushButton):
    """A window control that styles itself.

    The application stylesheet addresses these by object name and, on the real Windows platform,
    Qt does not adopt those rules: measured with a probe colour that never appeared, while the
    same rules work offscreen. The buttons therefore came out as solid accent squares with no
    hover feedback. A widget-level stylesheet is always honoured, and rebuilding it on
    StyleChange keeps it in step with the theme.
    """

    def __init__(self, glyph: str, name: str, hover_token: str, hover_text_token: str) -> None:
        super().__init__(glyph)
        self.setObjectName(name)
        self._hover_token = hover_token
        self._hover_text_token = hover_text_token
        self._restyling = False
        self._restyle()
        # Restyled from apply_theme() once the application stylesheet swap is complete; see _restyle.
        theme.register_self_styling(self)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange and not self._restyling:
            self._restyle()

    def on_theme_applied(self) -> None:
        """Called by apply_theme() after the application stylesheet swap has finished."""
        self._restyle()

    def _restyle(self) -> None:
        if theme.is_applying():
            # apply_theme() is mid-swap: Qt is walking the widget tree sending StyleChange, and
            # installing a sheet here mutates style data during that walk. It corrupted the heap
            # (0xc0000374) when the theme change came from a widget's own signal handler - the
            # settings page saving, for instance. on_theme_applied() does this once the swap is done.
            return
        tokens = theme.current_tokens()
        hint = tokens.get("FG_HINT", "palette(mid)")
        sheet = f"QPushButton {{ background: transparent; border: none; color: {hint}; }}"
        fill = tokens.get(self._hover_token)
        if fill:
            text = tokens.get(self._hover_text_token, hint)
            sheet += f" QPushButton:hover {{ background: {fill}; color: {text}; }}"
        if sheet == self.styleSheet():
            return  # nothing to do: and installing an identical sheet would bounce a StyleChange back
        # setStyleSheet delivers StyleChange to this widget, which would call us again: the flag breaks
        # that loop (without it the suite died with a stack overflow), and the equality check above keeps
        # the common no-op case from re-entering at all.
        self._restyling = True
        try:
            self.setStyleSheet(sheet)
        finally:
            self._restyling = False


class TitleBar(QWidget):
    """Drag to move, double-click to maximize/restore, minimize and close buttons."""

    def __init__(self, window, title: str) -> None:
        super().__init__(window)
        self._window = window
        self._drag_offset: QPoint | None = None

        self.setObjectName("titleBar")
        self.setFixedHeight(BAR_HEIGHT)

        title_label = QLabel(title)
        title_label.setObjectName("titleBarTitle")

        self.minimize_button = self._make_button("titleBarMinimize", "–", window.showMinimized)
        self.close_button = self._make_button("titleBarClose", "×", window.close)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        layout.setSpacing(8)
        layout.addWidget(title_label)
        layout.addStretch(1)
        for button in (self.minimize_button, self.close_button):
            layout.addWidget(button)

    @staticmethod
    def _make_button(name: str, glyph: str, slot) -> QPushButton:
        is_minimize = name.endswith("Minimize")
        button = _WindowButton(
            glyph,
            name,
            "BG_TITLEBAR_MINIMIZE" if is_minimize else "BG_TITLEBAR_CLOSE",
            "FG_TEXT" if is_minimize else "FG_SELECTED",
        )
        button.setFixedSize(36, 26)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the bar is mouse-only
        # Flat, and never a default button. On the real Windows platform these two were the only controls
        # that came out as solid accent-green squares: the platform style drew them as push buttons even
        # though the stylesheet asks for a transparent background (offscreen never reproduced it, because
        # a different style is in charge there). Flat removes the frame the native style paints, which is
        # what we wanted all along, and the stylesheet still supplies the hover fills.
        button.setFlat(True)
        button.setAutoDefault(False)
        button.setDefault(False)
        button.clicked.connect(slot)
        return button

    # ---------- window behaviour ----------

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._window.isMaximized():
            # dragging a maximized window restores it first, like the native frame
            ratio = event.position().x() / max(self.width(), 1)
            self._window.showNormal()
            self._drag_offset = QPoint(int(self._window.width() * ratio), event.position().toPoint().y())
        self._window.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
