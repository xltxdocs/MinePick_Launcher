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

"""Table model for the versions list: lightweight rows instead of thousands of QTableWidgetItems."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, Qt

COLUMNS = 4


class VersionListModel(QAbstractTableModel):
    """Rows are plain tuples (id, type label, release date, status)."""

    def __init__(self, headers: list[str], parent=None) -> None:
        super().__init__(parent)
        self._headers = headers
        self._rows: list[tuple[str, str, str, str]] = []

    def rowCount(self, parent=None) -> int:
        return 0 if (parent is not None and parent.isValid()) else len(self._rows)

    def columnCount(self, parent=None) -> int:
        return 0 if (parent is not None and parent.isValid()) else COLUMNS

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        row, col = index.row(), index.column()
        if 0 <= row < len(self._rows) and 0 <= col < COLUMNS:
            return self._rows[row][col]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal and 0 <= section < COLUMNS:
            return self._headers[section]
        return None

    def set_rows(self, rows: list[tuple[str, str, str, str]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_id(self, row: int) -> str | None:
        if 0 <= row < len(self._rows):
            return self._rows[row][0]
        return None

