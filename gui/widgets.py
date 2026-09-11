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

from PySide6.QtCore import QEvent, QModelIndex, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabBar,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
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
    attach_hover_scrollbar(view)


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
    tab bars) so the mouse wheel only scrolls page content such as lists, tables
    and scroll areas.

    Open dropdown lists are the one exception: they must stay wheel-scrollable,
    otherwise long lists (every installed font family, for instance) cannot be
    reached at all. The closed combo itself still ignores the wheel, so scrolling
    a page past a combo never changes its value.
    """

    _WHEEL_REACTIVE = (QComboBox, QSpinBox, QDoubleSpinBox, QTabBar)

    @staticmethod
    def _is_dropdown_view(view) -> bool:
        """True for an item view that belongs to a combo box (its dropdown list)."""
        if view.windowFlags() & Qt.WindowType.Popup:
            return True
        node = view.parent()
        while node is not None:
            if isinstance(node, QComboBox):
                return True
            node = node.parent()
        return False

    @classmethod
    def _is_open_dropdown_list(cls, obj) -> bool:
        """True when the wheel targets a dropdown list: the view, its viewport or its popup."""
        node = obj
        while node is not None:
            if isinstance(node, QAbstractItemView) and cls._is_dropdown_view(node):
                return True
            node = node.parent()
        return False

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.Wheel:
            return False
        if self._is_open_dropdown_list(obj):
            return False  # let the dropdown list scroll
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


class StatusLabel(QLabel):
    """Status text whose colour follows the severity of the last message.

    ``setText`` always returns to the neutral look, so a red error message never
    sticks: the next ordinary message (progress, "done") is muted again. This keeps
    every existing ``setText`` call site unchanged and only marks the failures.
    """

    def setText(self, text: str) -> None:  # Qt's slot name, kept camelCase on purpose
        self._apply_level("info")
        super().setText(text)

    def set_error(self, text: str) -> None:
        self._apply_level("error")
        super().setText(text)

    def set_warning(self, text: str) -> None:
        self._apply_level("warning")
        super().setText(text)

    def _apply_level(self, level: str) -> None:
        name = {"error": "statusError", "warning": "statusWarning"}.get(level, "hint")
        if self.objectName() == name:
            return
        self.setObjectName(name)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


def build_page_header(title: str, subtitle: str) -> QWidget:
    """Page header: a big title plus one line describing what the page is for."""
    box = QWidget()
    box.setObjectName("pageHeader")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 2)
    layout.setSpacing(1)
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("pageSubtitle")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return box


def build_sidebar_brand() -> QWidget:
    """Sidebar brand block: the product name only (the icon lives in the title bar)."""
    box = QWidget()
    box.setObjectName("sidebarBrand")
    layout = QHBoxLayout(box)
    layout.setContentsMargins(14, 6, 8, 10)
    layout.setSpacing(8)
    name_label = QLabel("MinePick")
    name_label.setObjectName("brandName")
    layout.addWidget(name_label)
    layout.addStretch(1)
    return box


def style_page_layout(layout) -> None:
    """One spacing scale for every page: 14px outer margin, 8px between blocks."""
    layout.setContentsMargins(14, 12, 14, 6)
    layout.setSpacing(8)


def style_form(form) -> None:
    """One spacing scale for every form: label/value gap and row gap."""
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(8)


def add_search_icon(line_edit) -> None:
    """Leading magnifier icon inside a search field."""
    from PySide6.QtGui import QIcon

    from launcher import paths

    icon_path = paths.resource_path("gui/resources/search.png")
    if icon_path.exists():
        line_edit.addAction(QIcon(str(icon_path)), QLineEdit.LeadingPosition)


class EmptyState(QLabel):
    """Muted hint shown instead of an empty list/table, hidden as soon as data arrives."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("emptyState")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setVisible(False)

    def update_for(self, count: int) -> None:
        self.setVisible(count == 0)


class _ScrollBarHoverFilter(QObject):
    """Reveals the owning scroll area's slim scrollbar while the pointer is inside it."""

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Enter:
            _set_scrollbars_active(obj, True)
        elif event.type() == QEvent.Type.Leave:
            _set_scrollbars_active(obj, False)
        return False


def _set_scrollbars_active(source, active: bool) -> None:
    node = source
    while node is not None and not isinstance(node, QAbstractScrollArea):
        node = node.parent()
    if node is None:
        return
    for bar in (node.verticalScrollBar(), node.horizontalScrollBar()):
        if bar is None or bool(bar.property("active")) == active:
            continue
        bar.setProperty("active", active)
        style = bar.style()
        style.unpolish(bar)
        style.polish(bar)


def attach_hover_scrollbar(area) -> None:
    """Install the hover filter on a scroll area (and its viewport)."""
    hover_filter = _ScrollBarHoverFilter(area)
    targets = [area]
    viewport_getter = getattr(area, "viewport", None)
    if callable(viewport_getter):
        targets.append(area.viewport())
    for target in targets:
        target.installEventFilter(hover_filter)
    area._hover_scrollbar_filter = hover_filter  # keep the filter alive


class KeyboardFocusTracker(QObject):
    """Marks a focused control when focus came from the keyboard.

    Qt also paints focus for mouse clicks, which this launcher suppresses so the
    interface stays flat; this restores an indicator for keyboard users only.
    """

    _INTERACTIVE = (
        QAbstractItemView,
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QTextEdit,
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._keyboard = False

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress:
            self._keyboard = True
        elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            self._keyboard = False
        elif kind == QEvent.Type.FocusIn and isinstance(obj, self._INTERACTIVE):
            self._mark(obj, self._keyboard)
        elif kind == QEvent.Type.FocusOut and isinstance(obj, self._INTERACTIVE):
            self._mark(obj, False)
        return False

    @staticmethod
    def _mark(widget, active: bool) -> None:
        if bool(widget.property("keyboardFocus")) == active:
            return
        widget.setProperty("keyboardFocus", active)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)


class NumericTableItem(QTableWidgetItem):
    """Table item that sorts by a number instead of the displayed text (8 before 21)."""

    def __init__(self, text: str, value: float) -> None:
        super().__init__(text)
        self._value = value

    def __lt__(self, other) -> bool:
        if isinstance(other, NumericTableItem):
            return self._value < other._value
        return super().__lt__(other)
