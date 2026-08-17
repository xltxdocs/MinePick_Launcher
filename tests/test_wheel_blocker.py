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

"""gui/widgets.py WheelBlocker tests: wheel blocked on combos/spins and their inner children, allowed on lists."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QListWidget

from gui.widgets import WheelBlocker


def _wheel_event():
    return QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_wheel_blocker_blocks_combo() -> None:
    QApplication.instance() or QApplication([])
    blocker = WheelBlocker()
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    combo.setCurrentIndex(0)
    assert blocker.eventFilter(combo, _wheel_event()) is True
    assert combo.currentIndex() == 0


def test_wheel_blocker_blocks_combo_popup_view() -> None:
    """The open popup list must not react to the wheel either."""
    app = QApplication.instance() or QApplication([])
    blocker = WheelBlocker()
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    combo.show()
    app.processEvents()
    view = combo.view()
    assert view is not None
    assert blocker.eventFilter(view, _wheel_event()) is True  # ancestor chain reaches the combo


def test_wheel_blocker_blocks_spin_lineedit() -> None:
    """The spin box inner line edit must not react to the wheel either."""
    app = QApplication.instance() or QApplication([])
    blocker = WheelBlocker()
    spin = QDoubleSpinBox()
    spin.show()
    app.processEvents()
    line = spin.lineEdit()
    assert line is not None
    assert blocker.eventFilter(line, _wheel_event()) is True


def test_wheel_blocker_allows_lists() -> None:
    QApplication.instance() or QApplication([])
    blocker = WheelBlocker()
    view = QListWidget()
    assert blocker.eventFilter(view, _wheel_event()) is False  # wheel passes through to the view


def test_views_use_pixel_scrolling() -> None:
    """Pixel scrolling keeps the wheel from moving the current item."""
    from PySide6.QtWidgets import QAbstractItemView, QTableWidget

    from gui.widgets import apply_no_focus_outline

    QApplication.instance() or QApplication([])
    view = QListWidget()
    apply_no_focus_outline(view)
    assert view.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
    table = QTableWidget()
    apply_no_focus_outline(table)
    assert table.horizontalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel

