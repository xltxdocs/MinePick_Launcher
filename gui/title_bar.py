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

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

BAR_HEIGHT = 38


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
        button = QPushButton(glyph)
        button.setObjectName(name)
        button.setFixedSize(36, 26)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the bar is mouse-only
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
