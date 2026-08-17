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

"""Java page: managed runtime management (delete), detected list, install a new JRE."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.widgets import apply_no_focus_outline
from gui.workers import ProgressBridge, run_in_background
from launcher import paths
from launcher.java import install_java, list_java
from launcher.java.install import delete_managed_runtime, list_managed_runtimes

tr = i18n.tr


def _dir_size(path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except OSError:
        pass
    return total


def _format_size(size: int) -> str:
    if size >= 1 << 30:
        return f"{size / (1 << 30):.2f} GB"
    if size >= 1 << 20:
        return f"{size / (1 << 20):.1f} MB"
    if size >= 1 << 10:
        return f"{size / (1 << 10):.1f} KB"
    return str(size) + " B"


class JavaPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.title = QLabel(tr("java.page.title"))
        self.title.setObjectName("title")
        self.managed_table = QTableWidget(0, 3)
        apply_no_focus_outline(self.managed_table)
        self.managed_table.setHorizontalHeaderLabels(
            [tr("java.col.major"), tr("java.col.path"), "Size"]
        )
        # Let the path column stretch so the full path stays visible
        managed_header = self.managed_table.horizontalHeader()
        managed_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        managed_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        managed_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.managed_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.managed_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.detected_table = QTableWidget(0, 3)
        apply_no_focus_outline(self.detected_table)
        self.detected_table.setHorizontalHeaderLabels(
            [tr("java.col.major"), tr("java.col.provider"), tr("java.col.path")]
        )
        # Let the path column stretch so the full path stays visible
        detected_header = self.detected_table.horizontalHeader()
        detected_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        detected_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        detected_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.detected_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.detected_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.delete_button = QPushButton(tr("java.delete"))
        self.refresh_button = QPushButton(tr("java.refresh"))
        self.major_combo = QComboBox()
        for major in (8, 11, 17, 21, 25):
            self.major_combo.addItem(str(major), major)
        self.install_button = QPushButton(tr("java.install.button"))
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        managed_row = QHBoxLayout()
        managed_row.addWidget(self.delete_button)
        managed_row.addStretch(1)
        detected_row = QHBoxLayout()
        detected_row.addWidget(self.refresh_button)
        detected_row.addStretch(1)
        install_row = QHBoxLayout()
        install_row.addWidget(QLabel(tr("java.install.major")))
        install_row.addWidget(self.major_combo)
        install_row.addWidget(self.install_button)
        install_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(QLabel(tr("java.managed.label")))
        layout.addWidget(self.managed_table, 1)
        layout.addLayout(managed_row)
        layout.addWidget(QLabel(tr("java.detected.label")))
        layout.addWidget(self.detected_table, 1)
        layout.addLayout(detected_row)
        layout.addWidget(QLabel(tr("java.install.label")))
        layout.addLayout(install_row)
        layout.addWidget(self.status)

        self.delete_button.clicked.connect(self._delete_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.install_button.clicked.connect(self._install)
        self.refresh()

    def refresh(self) -> None:
        self._refresh_managed()
        # Probing java -version is slow: run in the background to avoid freezing the UI on start/refresh
        run_in_background(
            self._refresh_detected,
            on_error=lambda _m: None,
        )

    def _refresh_managed(self) -> None:
        items = list_managed_runtimes()
        self._managed = {major: d for major, d in items}
        self.managed_table.setRowCount(0)
        self.managed_table.setRowCount(len(items))
        for row, (major, d) in enumerate(items):
            self.managed_table.setItem(row, 0, QTableWidgetItem(str(major)))
            self.managed_table.setItem(row, 1, QTableWidgetItem(str(d)))
            self.managed_table.setItem(row, 2, QTableWidgetItem(_format_size(_dir_size(d))))

    def _refresh_detected(self) -> None:
        runtimes = list_java(probe_dir=paths.launcher_dir() / "cache")
        self.detected_table.setRowCount(0)
        self.detected_table.setRowCount(len(runtimes))
        for row, r in enumerate(runtimes):
            self.detected_table.setItem(row, 0, QTableWidgetItem(str(r.major)))
            self.detected_table.setItem(row, 1, QTableWidgetItem(r.provider))
            self.detected_table.setItem(row, 2, QTableWidgetItem(str(r.path)))

    def _selected_major(self) -> int | None:
        row = self.managed_table.currentRow()
        if row < 0:
            return None
        item = self.managed_table.item(row, 0)
        return int(item.text()) if item else None

    def _delete_selected(self) -> None:
        major = self._selected_major()
        if major is None:
            self.status.setText(tr("account.msg.need_select"))
            return
        answer = QMessageBox.question(
            self,
            tr("java.delete.dialog"),
            tr("java.delete.msg", major, str(self._managed.get(major, ""))),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def do_delete() -> object:
            return delete_managed_runtime(major)

        self.delete_button.setEnabled(False)
        run_in_background(
            do_delete,
            on_result=lambda _d: (self.refresh(), self.status.setText(tr("java.msg.deleted", "Java " + str(major)))),
            on_error=lambda m: self.status.setText(tr("java.msg.delete_fail", m)),
            on_finished=lambda: self.delete_button.setEnabled(True),
        )

    def _install(self) -> None:
        major = self.major_combo.currentData()
        self.install_button.setEnabled(False)
        self.status.setText(tr("java.msg.installing", major))
        bridge = ProgressBridge()
        bridge.progress.connect(
            lambda p: self.status.setText(
                "Java " + str(major) + ": " + str(p.done_files) + "/" + str(p.total_files)
                + " " + p.current
            )
        )

        def do_install(progress) -> object:
            return install_java(
                major,
                runtime_dir=paths.launcher_dir() / "runtime",
                probe_dir=paths.launcher_dir() / "cache",
                progress=progress,
            )

        run_in_background(
            do_install,
            bridge,
            on_result=lambda _r: (self.refresh(), self.status.setText(tr("java.msg.installed", major))),
            on_error=lambda m: self.status.setText(tr("java.msg.fail", m)),
            on_finished=lambda: self.install_button.setEnabled(True),
        )
