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

"""Round 3 interaction helpers: keyboard-focus marking, hover scrollbars, sorting, column memory."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QListWidget, QTableWidget

from gui.models.version_list_model import VersionListModel
from gui.view_state import remember_column_widths
from gui.widgets import KeyboardFocusTracker, NumericTableItem, attach_hover_scrollbar


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_version_model_sorts_both_orders(app) -> None:
    model = VersionListModel(["id", "type", "time", "status"])
    model.set_rows([("1.20.1", "正式版", "2023-06-12", "已安装"), ("1.21.11", "正式版", "2025-12-09", "—")])
    model.sort(0, Qt.SortOrder.AscendingOrder)
    assert model.row_id(0) == "1.20.1"
    model.sort(0, Qt.SortOrder.DescendingOrder)
    assert model.row_id(0) == "1.21.11"


def test_numeric_table_item_sorts_numerically(app) -> None:
    table = QTableWidget(2, 1)
    table.setItem(0, 0, NumericTableItem("21", 21.0))
    table.setItem(1, 0, NumericTableItem("8", 8.0))
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    assert table.item(0, 0).text() == "8"  # text sorting would put "21" first


def test_hover_scrollbar_sets_active_property(app) -> None:
    view = QListWidget()
    attach_hover_scrollbar(view)
    bar = view.verticalScrollBar()
    view.viewport().installEventFilter(view._hover_scrollbar_filter)
    QApplication.sendEvent(view.viewport(), QEvent(QEvent.Type.Enter))
    assert bar.property("active") is True
    QApplication.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
    assert bar.property("active") is False


def test_keyboard_focus_survives_mouse_navigation(app) -> None:
    """Tab marks the control; a mouse click clears the mark again."""
    tracker = KeyboardFocusTracker()
    widget = QListWidget()
    widget.installEventFilter(tracker)

    tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, tab)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.FocusIn))
    assert widget.property("keyboardFocus") is True

    click = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(2, 2),
        QPointF(2, 2),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, click)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.FocusIn))
    assert widget.property("keyboardFocus") is False

    wheel = QWheelEvent(
        QPointF(2, 2),
        QPointF(2, 2),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, wheel)
    QApplication.sendEvent(widget, QEvent(QEvent.Type.FocusIn))
    assert widget.property("keyboardFocus") is False


def test_column_widths_are_remembered(app, monkeypatch, ws_tmp) -> None:
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_widths"))
    table = QTableWidget(1, 3)
    remember_column_widths(table, "demo")
    table.setColumnWidth(1, 222)
    table.horizontalHeader().sectionResized.emit(1, 100, 222)  # user drag

    restored = QTableWidget(1, 3)
    remember_column_widths(restored, "demo")
    assert restored.columnWidth(1) == 222
