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

"""Shared widget helpers: no-focus-outline views, no-wheel controls and a global wheel blocker."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabBar,
)


class NoFocusDelegate(QStyledItemDelegate):
    """List/table delegate: remove the HasFocus state when painting so the style engine stops drawing the focus rectangle."""

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        option.state &= ~QStyle.StateFlag.State_HasFocus


def apply_no_focus_outline(view) -> None:
    """Apply a no-focus-outline delegate and smooth pixel scrolling to list/table views.

    Pixel scrolling keeps the wheel from moving the current item: with the
    default per-item scroll mode, scrolling "selects" whichever item ends up
    under the cursor.
    """
    view.setItemDelegate(NoFocusDelegate(view))
    for method in ("setVerticalScrollMode", "setHorizontalScrollMode"):
        setter = getattr(view, method, None)
        if setter is not None:
            setter(QAbstractItemView.ScrollMode.ScrollPerPixel)


class NoWheelSpinBox(QSpinBox):
    """Spin box that ignores the mouse wheel so scrolling the page never changes its value."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Double spin box that ignores the mouse wheel so scrolling the page never changes its value."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class WheelBlocker(QObject):
    """Application-wide event filter.

    Blocks wheel input on controls that react to it (combo boxes, spin boxes,
    tab bars) including their inner children (popup views, line edits), so the
    mouse wheel only scrolls page content such as lists, tables and scroll
    areas.
    """

    _WHEEL_REACTIVE = (QComboBox, QSpinBox, QDoubleSpinBox, QTabBar)

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.Wheel:
            return False
        node = obj
        while node is not None:
            if isinstance(node, self._WHEEL_REACTIVE):
                event.ignore()
                # The wheel would otherwise hand the control focus (Qt WheelFocus),
                # which paints the green focus border: drop that focus again.
                if node.hasFocus():
                    node.clearFocus()
                return True
            node = node.parent()
        return False
