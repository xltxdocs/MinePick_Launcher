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
from gui.view_state import remember_column_widths
from gui.widgets import (
    EmptyState,
    NumericTableItem,
    apply_no_focus_outline,
    build_page_header,
    disable_keeping_focus,
    set_app_status,
    style_page_layout,
    widget_alive,
)
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
        return f"{size / (1 << 30):.2f} {tr('unit.gb')}"
    if size >= 1 << 20:
        return f"{size / (1 << 20):.1f} {tr('unit.mb')}"
    if size >= 1 << 10:
        return f"{size / (1 << 10):.1f} {tr('unit.kb')}"
    return f"{size} {tr('unit.bytes')}"


class JavaPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.managed_table = QTableWidget(0, 3)
        apply_no_focus_outline(self.managed_table)
        self.managed_table.setHorizontalHeaderLabels(
            [tr("java.col.major"), tr("java.col.path"), tr("java.col.size")]
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
        self.delete_button.setObjectName("dangerButton")
        self.refresh_button = QPushButton(tr("java.refresh"))
        self.refresh_button.setObjectName("secondaryButton")
        self.major_combo = QComboBox()
        for major in (8, 11, 17, 21, 25):
            self.major_combo.addItem(str(major), major)
        self.install_button = QPushButton(tr("java.install.button"))

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
        style_page_layout(layout)
        layout.addWidget(build_page_header(tr("nav.java"), tr("page.java.desc")))
        layout.addWidget(QLabel(tr("java.managed.label")))
        layout.addWidget(self.managed_table, 1)
        remember_column_widths(self.managed_table, "java_managed")
        self.empty_managed = EmptyState(tr("empty.java"))
        layout.addWidget(self.empty_managed)
        layout.addLayout(managed_row)
        layout.addWidget(QLabel(tr("java.detected.label")))
        layout.addWidget(self.detected_table, 1)
        remember_column_widths(self.detected_table, "java_detected")
        self.empty_detected = EmptyState(tr("empty.java"))
        layout.addWidget(self.empty_detected)
        layout.addLayout(detected_row)
        layout.addWidget(QLabel(tr("java.install.label")))
        layout.addLayout(install_row)

        self.delete_button.clicked.connect(self._delete_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.install_button.clicked.connect(self._install)
        self.refresh()

    def refresh(self) -> None:
        self._refresh_managed()
        # Probing java -version is slow, so only the *probe* runs on a worker thread. Filling
        # the table happens in the result callback, which Qt delivers on the GUI thread —
        # touching widgets from the worker corrupted Qt's state and crashed the process.
        run_in_background(
            list_java,
            probe_dir=paths.launcher_dir() / "cache",
            on_result=self._apply_detected,
            on_error=lambda _m: None,
        )

    def _refresh_managed(self) -> None:
        items = list_managed_runtimes()
        self._managed = {major: d for major, d in items}
        self.managed_table.setSortingEnabled(False)
        self.managed_table.setRowCount(0)
        self.managed_table.setRowCount(len(items))
        for row, (major, d) in enumerate(items):
            size = _dir_size(d)
            self.managed_table.setItem(row, 0, NumericTableItem(str(major), float(major)))
            self.managed_table.setItem(row, 1, QTableWidgetItem(str(d)))
            self.managed_table.setItem(row, 2, NumericTableItem(_format_size(size), float(size)))
        self.managed_table.setSortingEnabled(True)
        self.empty_managed.update_for(len(items))

    def _refresh_detected(self) -> list:
        """The background half: a pure probe with no widget access at all."""
        return list_java(probe_dir=paths.launcher_dir() / "cache")

    def _apply_detected(self, runtimes: list) -> None:
        """The GUI half: fills the table once the probe comes back.

        Runs on the main thread, and only while this page still exists: closing the window
        while the probe is in flight used to end in an access violation.
        """
        if not widget_alive(self) or not widget_alive(self.detected_table):
            return
        self.detected_table.setSortingEnabled(False)
        self.detected_table.setRowCount(0)
        self.detected_table.setRowCount(len(runtimes))
        for row, r in enumerate(runtimes):
            self.detected_table.setItem(row, 0, NumericTableItem(str(r.major), float(r.major)))
            self.detected_table.setItem(row, 1, QTableWidgetItem(r.provider))
            self.detected_table.setItem(row, 2, QTableWidgetItem(str(r.path)))
        self.detected_table.setSortingEnabled(True)
        self.empty_detected.update_for(len(runtimes))

    def _selected_major(self) -> int | None:
        row = self.managed_table.currentRow()
        if row < 0:
            return None
        item = self.managed_table.item(row, 0)
        return int(item.text()) if item else None

    def _delete_selected(self) -> None:
        major = self._selected_major()
        if major is None:
            set_app_status(self, tr("account.msg.need_select"), "warning")
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

        disable_keeping_focus(self.delete_button)
        run_in_background(
            do_delete,
            on_result=lambda _d: (
                self.refresh(),
                set_app_status(self, tr("java.msg.deleted", "Java " + str(major))),
            ),
            on_error=lambda m: set_app_status(self, tr("java.msg.delete_fail", m), "error"),
            on_finished=lambda: self.delete_button.setEnabled(True),
        )

    def _install(self) -> None:
        major = self.major_combo.currentData()
        disable_keeping_focus(self.install_button)
        set_app_status(self, tr("java.msg.installing", major))
        bridge = ProgressBridge()
        bridge.progress.connect(
            lambda p: set_app_status(
                self,
                "Java " + str(major) + ": " + str(p.done_files) + "/" + str(p.total_files)
                + " " + p.current,
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
            on_result=lambda _r: (
                self.refresh(),
                set_app_status(self, tr("java.msg.installed", major)),
            ),
            on_error=lambda m: set_app_status(self, tr("java.msg.fail", m), "error"),
            on_finished=lambda: self.install_button.setEnabled(True),
        )
