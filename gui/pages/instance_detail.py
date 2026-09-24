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

"""Instance detail panel: header plus the 概览 / 模组 / 资源 / 存档 / 设置 tabs.

The panel owns everything that acts on one instance (launching, mods, resource
packs, saves, per-instance settings). It never touches widgets from a worker
thread: every background job reports through @gui.workers.run_in_background with
bound-method callbacks, so a result that arrives after the page was torn down is
dropped by the owner guard instead of dereferencing a freed C++ object.
"""

from __future__ import annotations

import logging
import time
from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.errors import show_fatal
from gui.view_state import remember_column_widths
from gui.widgets import (
    EmptyState,
    NoWheelDoubleSpinBox,
    NumericTableItem,
    add_search_icon,
    apply_no_focus_outline,
    disable_keeping_focus,
    set_app_status,
    style_form,
)
from gui.workers import ProgressBridge, run_in_background
from launcher import config, paths
from launcher.auth import AccountStore
from launcher.instances import (
    ISOLATION_FOLLOW,
    ISOLATION_OFF,
    ISOLATION_ON,
    InstancesError,
    delete_instance,
    display_version_name,
    export_instance,
    get_instance,
    instance_dir,
    legacy_instances_dir,
    rename_instance,
    reset_instance_settings,
    resolve_instance,
    set_instance_settings,
    update_instance,
    update_instance_note,
)
from launcher.launch import (
    find_new_crash_reports,
    prepare_launch,
    resolve_launch_account,
    run_process,
)
from launcher.mods.local import install_mod_file, scan_mods, set_mod_enabled
from launcher.mods.modrinth import (
    delete_installed_content,
    list_installed_content,
    resolve_content_dir,
)

tr = i18n.tr

# Stacked-page order of the horizontal tab row
TAB_OVERVIEW, TAB_MODS, TAB_RESOURCES, TAB_SAVES, TAB_SETTINGS = range(5)
_TAB_KEYS = ("overview", "mods", "resources", "saves", "settings")
_CONTENT_SUBDIRS = ("resourcepacks", "shaderpacks")


def human_size(size: int) -> str:
    """Format a byte count with the launcher's unit strings."""
    if size >= 1 << 30:
        return f"{size / (1 << 30):.1f} " + tr("unit.gb")
    if size >= 1 << 20:
        return f"{size / (1 << 20):.1f} " + tr("unit.mb")
    if size >= 1 << 10:
        return f"{size / (1 << 10):.0f} " + tr("unit.kb")
    return f"{size} " + tr("unit.bytes")


def directory_size(path: Path) -> int:
    """Total size of the regular files below a directory (0 when it is unreadable)."""
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except OSError:
        return total
    return total


def _delete_content_file(resolved, subdir: str, name: str) -> int:
    """Delete one resource file; a locked file must not stop the rest of the batch."""
    try:
        delete_installed_content(
            resolved.game_dir, subdir, name, version_id=resolved.id, isolated=resolved.isolated
        )
    except Exception:  # a locked file must not stop the batch; reported as a smaller count
        logging.getLogger(__name__).warning("Cannot delete %s/%s", subdir, name, exc_info=True)
        return 0
    return 1


class _ModsTable(QTableWidget):
    """Mods table: supports drag-and-drop of .jar files to install."""

    def __init__(self, detail: InstanceDetail) -> None:
        super().__init__(0, 6)
        self._detail = detail
        self.setAcceptDrops(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)

    def _jar_urls(self, event) -> bool:
        data = event.mimeData()
        if not data.hasUrls():
            return False
        return any(
            u.isLocalFile() and u.toLocalFile().lower().endswith(".jar")
            for u in data.urls()
        )

    def dragEnterEvent(self, event) -> None:
        if self._jar_urls(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._jar_urls(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        jars = [
            Path(u.toLocalFile())
            for u in event.mimeData().urls()
            if u.isLocalFile() and u.toLocalFile().lower().endswith(".jar")
        ]
        if jars:
            self._detail.install_dropped(jars)
            event.acceptProposedAction()
        else:
            event.ignore()


class InstanceDetail(QWidget):
    """Right-hand column of the instances page: everything about one instance."""

    changed = Signal()  # metadata shown in the list changed (name / note / isolation)
    deleted = Signal(str)  # the instance folder is gone

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.instance_id: str | None = None
        self.instance = None  # launcher.instances.Instance
        self.resolved = None  # launcher.instances.ResolvedInstance
        self.game_dir: Path = paths.default_game_dir()

        # Working state
        self._mods: list = []
        self._filling = False  # a widget fill is running: ignore the change signals it fires
        self._filling_mods = False
        self._isolation_warned = False
        self._loaded_tabs: set[int] = set()
        self._content_items: dict[str, list] = {sub: [] for sub in _CONTENT_SUBDIRS}
        self._saves: list[tuple[str, float, int]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_header())
        layout.addLayout(self._build_tab_row())
        layout.addWidget(self.stack, 1)

        self.tab_group.idClicked.connect(self._on_tab_clicked)
        self.launch_button.clicked.connect(self.launch)
        self.crash_button.clicked.connect(self.open_crash_viewer)

    # ---------- construction ----------

    def _build_header(self) -> QWidget:
        box = QWidget()
        self.name_label = QLabel(tr("instances.detail.value.none"))
        self.name_label.setObjectName("title")
        self.id_label = QLabel("")
        self.id_label.setObjectName("hint")
        self.dir_label = QLabel("")
        self.dir_label.setObjectName("hint")
        self.dir_label.setWordWrap(True)
        self.launch_button = QPushButton(tr("instances.launch"))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.name_label)
        row.addWidget(self.id_label)
        row.addStretch(1)
        row.addWidget(self.launch_button)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
        layout.addWidget(self.dir_label)
        return box

    def _build_tab_row(self) -> QHBoxLayout:
        """Horizontal tab row: checkable buttons driving a QStackedWidget.

        The theme styles `QPushButton#categoryTab` (the versions page uses the same
        chip row) but has no QTabWidget appearance, so the tabs are plain buttons.
        """
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tabs: list[QPushButton] = []
        self.stack = QStackedWidget()
        builders = (
            self._build_overview,
            self._build_mods,
            self._build_resources,
            self._build_saves,
            self._build_settings,
        )
        for index, (key, builder) in enumerate(zip(_TAB_KEYS, builders, strict=True)):
            button = QPushButton(tr("instances.detail.tab." + key))
            button.setCheckable(True)
            button.setObjectName("categoryTab")
            self.tab_group.addButton(button, index)
            self.tabs.append(button)
            self.stack.addWidget(builder())
        self.tabs[TAB_OVERVIEW].setChecked(True)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for button in self.tabs:
            row.addWidget(button)
        row.addStretch(1)
        return row

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        form = QFormLayout()
        style_form(form)
        self.overview_values: dict[str, QLabel] = {}
        for key, label_key in (
            ("version", "instances.detail.row.version"),
            ("profile", "instances.detail.row.profile"),
            ("game_dir", "instances.detail.row.game_dir"),
            ("isolation", "instances.detail.row.isolation"),
            ("java", "instances.detail.row.java"),
            ("memory", "instances.detail.row.memory"),
            ("last_played", "instances.detail.row.last_played"),
            ("note", "instances.detail.row.note"),
        ):
            title = QLabel(tr(label_key))
            title.setObjectName("hint")
            value = QLabel(tr("instances.detail.value.none"))
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.overview_values[key] = value
            form.addRow(title, value)
        layout.addLayout(form)

        self.legacy_label = QLabel("")
        self.legacy_label.setObjectName("hint")
        self.legacy_label.setWordWrap(True)
        self.legacy_label.setVisible(False)
        layout.addWidget(self.legacy_label)

        self.open_folder_button = QPushButton(tr("instances.open_folder"))
        self.open_folder_button.setObjectName("secondaryButton")
        self.open_logs_button = QPushButton(tr("instances.detail.open_logs"))
        self.open_logs_button.setObjectName("secondaryButton")
        self.crash_button = QPushButton(tr("crash.viewer"))
        self.crash_button.setObjectName("secondaryButton")
        self.rename_button = QPushButton(tr("instances.rename"))
        self.rename_button.setObjectName("secondaryButton")
        self.export_button = QPushButton(tr("instances.export"))
        self.export_button.setObjectName("secondaryButton")
        self.delete_button = QPushButton(tr("instances.delete"))
        self.delete_button.setObjectName("dangerButton")
        files_row = QHBoxLayout()
        files_row.setContentsMargins(0, 0, 0, 0)
        files_row.setSpacing(6)
        for button in (self.open_folder_button, self.open_logs_button, self.crash_button):
            files_row.addWidget(button)
        files_row.addStretch(1)
        manage_row = QHBoxLayout()
        manage_row.setContentsMargins(0, 0, 0, 0)
        manage_row.setSpacing(6)
        for button in (self.rename_button, self.export_button, self.delete_button):
            manage_row.addWidget(button)
        manage_row.addStretch(1)
        layout.addLayout(files_row)
        layout.addLayout(manage_row)
        layout.addStretch(1)

        self.open_folder_button.clicked.connect(self.open_instance_folder)
        self.open_logs_button.clicked.connect(self.open_logs_folder)
        self.rename_button.clicked.connect(self.rename)
        self.export_button.clicked.connect(self.export)
        self.delete_button.clicked.connect(self.delete)
        return page

    def _build_mods(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        banner, self.mods_banner_label = self._build_share_banner()
        self.mods_banner = banner
        layout.addWidget(banner)

        self.mods_table = _ModsTable(self)
        apply_no_focus_outline(self.mods_table)
        self.mods_table.setHorizontalHeaderLabels(
            [
                tr("instances.mods.col.enabled"),
                tr("instances.mods.col.name"),
                tr("instances.mods.col.id"),
                tr("instances.mods.col.version"),
                tr("instances.mods.col.loader"),
                tr("instances.mods.col.file"),
            ]
        )
        self.mods_table.setColumnWidth(0, 56)
        self.mods_table.setColumnWidth(1, 150)
        self.mods_table.setColumnWidth(2, 110)
        self.mods_table.setColumnWidth(3, 72)
        self.mods_table.setColumnWidth(4, 80)
        self.mods_search = QLineEdit()
        add_search_icon(self.mods_search)
        self.mods_search.setPlaceholderText(tr("instances.mods.search.placeholder"))
        self.mods_search.setClearButtonEnabled(True)
        self.mods_filter = QComboBox()
        self.mods_filter.addItem(tr("instances.mods.filter.all"), "all")
        self.mods_filter.addItem(tr("instances.mods.filter.enabled"), "enabled")
        self.mods_filter.addItem(tr("instances.mods.filter.disabled"), "disabled")
        self.mods_refresh_button = QPushButton(tr("instances.mods.refresh"))
        self.mods_refresh_button.setObjectName("secondaryButton")
        self.mods_folder_button = QPushButton(tr("instances.mods.open_folder"))
        self.mods_folder_button.setObjectName("secondaryButton")
        self.mods_delete_button = QPushButton(tr("instances.mods.delete"))
        self.mods_delete_button.setObjectName("dangerButton")
        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(6)
        tools.addWidget(self.mods_search, 1)
        tools.addWidget(self.mods_filter)
        tools.addWidget(self.mods_refresh_button)
        tools.addWidget(self.mods_folder_button)
        tools.addWidget(self.mods_delete_button)
        layout.addLayout(tools)
        layout.addWidget(self.mods_table, 1)
        remember_column_widths(self.mods_table, "instance_mods")

        self.mods_table.itemChanged.connect(self._on_mod_toggled)
        # Debounce: refill only after 200ms of typing inactivity
        self._mods_search_timer = QTimer(self)
        self._mods_search_timer.setSingleShot(True)
        self._mods_search_timer.timeout.connect(self._refill_mods)
        self.mods_search.textChanged.connect(lambda _t: self._mods_search_timer.start(200))
        self.mods_filter.currentIndexChanged.connect(lambda _i: self._refill_mods())
        self.mods_refresh_button.clicked.connect(self._reload_mods)
        self.mods_folder_button.clicked.connect(self.open_mods_folder)
        self.mods_delete_button.clicked.connect(self.delete_selected_mods)
        return page

    def _build_resources(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        banner, self.res_banner_label = self._build_share_banner()
        self.res_banner = banner
        layout.addWidget(banner)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(12)
        self.content_tables: dict[str, QTableWidget] = {}
        self.content_empty: dict[str, EmptyState] = {}
        for subdir, title_key in (
            ("resourcepacks", "mods.tab.resourcepacks"),
            ("shaderpacks", "mods.tab.shaderpacks"),
        ):
            box, table, empty = self._build_content_section(subdir, tr(title_key))
            self.content_tables[subdir] = table
            self.content_empty[subdir] = empty
            inner_layout.addWidget(box, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        return page

    def _build_content_section(self, subdir: str, title: str):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("title")
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(
            [tr("instances.detail.col.name"), tr("instances.detail.col.size")]
        )
        apply_no_focus_outline(table)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 280)
        remember_column_widths(table, "instance_" + subdir)
        empty = EmptyState(tr("mods.installed.empty"))
        open_button = QPushButton(tr("instances.detail.open_folder"))
        open_button.setObjectName("secondaryButton")
        delete_button = QPushButton(tr("instances.mods.delete"))
        delete_button.setObjectName("dangerButton")
        open_button.clicked.connect(partial(self.open_content_folder, subdir))
        delete_button.clicked.connect(partial(self.delete_selected_content, subdir))
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        buttons.addWidget(open_button)
        buttons.addWidget(delete_button)
        buttons.addStretch(1)
        layout.addWidget(title_label)
        layout.addWidget(table, 1)
        layout.addWidget(empty)
        layout.addLayout(buttons)
        return box, table, empty

    def _build_saves(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.saves_table = QTableWidget(0, 3)
        self.saves_table.setHorizontalHeaderLabels(
            [
                tr("instances.detail.col.name"),
                tr("instances.detail.col.modified"),
                tr("instances.detail.col.size"),
            ]
        )
        apply_no_focus_outline(self.saves_table)
        self.saves_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.saves_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.saves_table.horizontalHeader().setStretchLastSection(True)
        self.saves_table.setColumnWidth(0, 260)
        remember_column_widths(self.saves_table, "instance_saves")
        self.saves_empty = EmptyState(tr("instances.detail.saves.empty"))
        self.saves_refresh_button = QPushButton(tr("instances.mods.refresh"))
        self.saves_refresh_button.setObjectName("secondaryButton")
        self.saves_folder_button = QPushButton(tr("instances.detail.saves.open_folder"))
        self.saves_folder_button.setObjectName("secondaryButton")
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        buttons.addWidget(self.saves_refresh_button)
        buttons.addWidget(self.saves_folder_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(self.saves_table, 1)
        layout.addWidget(self.saves_empty)
        self.saves_refresh_button.clicked.connect(self.reload_saves)
        self.saves_folder_button.clicked.connect(self.open_saves_folder)
        return page

    def _build_settings(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        form = QFormLayout()
        style_form(form)

        self.isolation_combo = QComboBox()
        self.isolation_combo.addItem(tr("instances.detail.settings.follow_global"), ISOLATION_FOLLOW)
        self.isolation_combo.addItem(tr("instances.detail.settings.isolation.on"), ISOLATION_ON)
        self.isolation_combo.addItem(tr("instances.detail.settings.isolation.off"), ISOLATION_OFF)

        self.java_follow_check = QCheckBox(tr("instances.detail.settings.java.follow"))
        self.java_edit = QLineEdit()
        self.java_edit.setPlaceholderText(tr("instances.detail.java.follow_auto"))
        self.java_browse_button = QPushButton(tr("settings.browse"))
        self.java_browse_button.setObjectName("secondaryButton")
        java_box = QWidget()
        java_layout = QVBoxLayout(java_box)
        java_layout.setContentsMargins(0, 0, 0, 0)
        java_layout.setSpacing(4)
        java_row = QHBoxLayout()
        java_row.setContentsMargins(0, 0, 0, 0)
        java_row.setSpacing(6)
        java_row.addWidget(self.java_edit, 1)
        java_row.addWidget(self.java_browse_button)
        java_layout.addWidget(self.java_follow_check)
        java_layout.addLayout(java_row)

        self.memory_follow_check = QCheckBox(tr("instances.detail.settings.follow_global"))
        self.memory_spin = NoWheelDoubleSpinBox()
        self.memory_spin.setRange(1.0, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setSuffix(" " + tr("unit.gb"))
        memory_box = QWidget()
        memory_layout = QVBoxLayout(memory_box)
        memory_layout.setContentsMargins(0, 0, 0, 0)
        memory_layout.setSpacing(4)
        memory_layout.addWidget(self.memory_follow_check)
        memory_layout.addWidget(self.memory_spin)

        self.jvm_args_edit = QLineEdit()
        self.jvm_args_edit.setPlaceholderText(tr("instances.detail.settings.jvm_args"))
        self.game_args_edit = QLineEdit()
        self.game_args_edit.setPlaceholderText(tr("instances.detail.settings.game_args"))

        form.addRow(tr("instances.detail.row.isolation"), self.isolation_combo)
        form.addRow(tr("instances.detail.row.java"), java_box)
        form.addRow(tr("instances.detail.row.memory"), memory_box)
        form.addRow(tr("instances.detail.settings.jvm_args"), self.jvm_args_edit)
        form.addRow(tr("instances.detail.settings.game_args"), self.game_args_edit)
        layout.addLayout(form)

        self.settings_save_button = QPushButton(tr("instances.detail.settings.save"))
        self.settings_reset_button = QPushButton(tr("instances.detail.settings.reset"))
        self.settings_reset_button.setObjectName("dangerButton")
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        buttons.addWidget(self.settings_save_button)
        buttons.addWidget(self.settings_reset_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

        self.java_follow_check.toggled.connect(self._on_java_follow_toggled)
        self.memory_follow_check.toggled.connect(self._on_memory_follow_toggled)
        self.isolation_combo.currentIndexChanged.connect(self._on_isolation_changed)
        self.java_browse_button.clicked.connect(self._browse_java)
        self.settings_save_button.clicked.connect(self._save_settings)
        self.settings_reset_button.clicked.connect(self._reset_settings)
        self._on_java_follow_toggled(True)
        self._on_memory_follow_toggled(True)
        return page

    def _build_share_banner(self) -> tuple[QWidget, QLabel]:
        """Warning strip shown on the mods/resources tabs of a non-isolated instance."""
        box = QWidget()
        label = QLabel("")
        label.setObjectName("hint")
        label.setWordWrap(True)
        button = QPushButton(tr("instances.detail.share.enable"))
        button.setObjectName("secondaryButton")
        button.clicked.connect(self.enable_isolation)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(label, 1)
        layout.addWidget(button)
        box.setVisible(False)
        return box, label

    # ---------- selection ----------

    def set_instance(self, instance_id: str | None) -> None:
        """Show the given instance (None clears the panel)."""
        if instance_id != self.instance_id:
            self._isolation_warned = False
        self.instance_id = instance_id
        if instance_id is None:
            self.instance = None
            self.resolved = None
            self._mods = []
            self._filling_mods = True
            try:
                self.mods_table.setRowCount(0)
            finally:
                self._filling_mods = False
            for subdir in _CONTENT_SUBDIRS:
                self._content_items[subdir] = []
            self._saves = []
            self._clear_rows()
            return
        self.reload()

    def reload(self) -> None:
        """Re-read the instance, resolve it and refresh every part of the panel."""
        if self.instance_id is None:
            return
        cfg, _ = config.load()
        self.game_dir = cfg.game_dir or paths.default_game_dir()
        self.instance = get_instance(self.instance_id, self.game_dir)
        if self.instance is None:
            self.resolved = None
            self._clear_rows()
            return
        try:
            self.resolved = resolve_instance(self.instance_id, cfg, self.game_dir)
        except InstancesError:
            self.resolved = None
            self._clear_rows()
            return
        self._fill_header()
        self._fill_overview()
        self._fill_settings()
        self._fill_banners()
        self._loaded_tabs = set()
        self._reload_mods()
        if self.stack.currentIndex() in (TAB_RESOURCES, TAB_SAVES):
            self._ensure_tab_data(self.stack.currentIndex(), force=True)

    def _clear_rows(self) -> None:
        self.name_label.setText(tr("instances.detail.value.none"))
        self.id_label.setText("")
        self.dir_label.setText("")
        for value in self.overview_values.values():
            value.setText(tr("instances.detail.value.none"))
        self.legacy_label.setVisible(False)
        self.mods_banner.setVisible(False)
        self.res_banner.setVisible(False)

    def _fill_header(self) -> None:
        inst = self.instance
        self.name_label.setText(inst.name)
        self.id_label.setText(tr("instances.detail.header.id", inst.id))
        self.dir_label.setText(tr("instances.detail.header.dir", str(self.resolved.launch_dir)))

    def _fill_overview(self) -> None:
        inst = self.instance
        cfg, _ = config.load()
        values = self.overview_values
        values["version"].setText(inst.id)
        values["profile"].setText(display_version_name(inst.id))
        values["game_dir"].setText(str(self.resolved.launch_dir))
        state = tr("common.on") if self.resolved.isolated else tr("common.off")
        values["isolation"].setText(state + " — " + self._isolation_reason())
        values["java"].setText(self._java_text(cfg))
        values["memory"].setText(
            tr("instances.detail.memory.value", f"{self.resolved.memory_gb:g}")
            + " — "
            + (
                tr("instances.detail.memory.source.instance")
                if self.resolved.memory_from_instance
                else tr("instances.detail.settings.follow_global")
            )
        )
        if inst.last_played:
            values["last_played"].setText(
                time.strftime("%Y-%m-%d %H:%M", time.localtime(inst.last_played))
            )
        else:
            values["last_played"].setText(tr("instances.detail.value.never"))
        values["note"].setText(inst.note or tr("instances.detail.value.no_note"))
        legacy = legacy_instances_dir(self.game_dir)
        if legacy is not None:
            self.legacy_label.setText(tr("instances.detail.legacy.notice", str(legacy)))
            self.legacy_label.setVisible(True)
        else:
            self.legacy_label.setVisible(False)

    def _isolation_reason(self) -> str:
        """Why the instance ended up isolated or not (the documented three-step rule)."""
        inst = self.instance
        if inst.isolated in (ISOLATION_ON, ISOLATION_OFF):
            return tr("instances.detail.isolation.reason.forced")
        folder = instance_dir(self.game_dir, inst.id)
        for sub in ("mods", "saves"):
            directory = folder / sub
            try:
                if directory.is_dir() and any(directory.iterdir()):
                    return tr("instances.detail.isolation.reason.auto")
            except OSError:
                continue
        return tr("instances.detail.isolation.reason.follow")

    def _java_text(self, cfg) -> str:
        pinned = self.instance.settings.java
        if pinned:
            return pinned
        global_java = getattr(cfg, "java_path", None)
        if global_java:
            return tr("instances.detail.java.follow_global", str(global_java))
        return tr("instances.detail.java.follow_auto")

    def _fill_banners(self) -> None:
        isolated = bool(self.resolved and self.resolved.isolated)
        shared = str(self.resolved.game_dir) if self.resolved else ""
        for banner, label in (
            (self.mods_banner, self.mods_banner_label),
            (self.res_banner, self.res_banner_label),
        ):
            if isolated:
                banner.setVisible(False)
                continue
            label.setText(tr("instances.detail.share.banner", shared))
            banner.setVisible(True)

    def _fill_settings(self) -> None:
        inst = self.instance
        settings = inst.settings
        self._filling = True
        try:
            index = self.isolation_combo.findData(inst.isolated)
            self.isolation_combo.setCurrentIndex(max(index, 0))
            self.java_follow_check.setChecked(not settings.java)
            self.java_edit.setText(settings.java or "")
            self.memory_follow_check.setChecked(settings.memory_gb is None)
            memory = settings.memory_gb
            if memory is None and self.resolved is not None:
                memory = self.resolved.memory_gb
            self.memory_spin.setValue(min(max(float(memory or 1.0), 1.0), 64.0))
            self.jvm_args_edit.setText(settings.jvm_args)
            self.game_args_edit.setText(settings.game_args)
        finally:
            self._filling = False
        self._on_java_follow_toggled(self.java_follow_check.isChecked())
        self._on_memory_follow_toggled(self.memory_follow_check.isChecked())

    def _on_java_follow_toggled(self, follow: bool) -> None:
        self.java_edit.setEnabled(not follow)
        self.java_browse_button.setEnabled(not follow)

    def _on_memory_follow_toggled(self, follow: bool) -> None:
        self.memory_spin.setEnabled(not follow)

    def _on_tab_clicked(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self._ensure_tab_data(index)

    def set_tab(self, index: int) -> None:
        """Activate a tab programmatically (used by tests and cross-page jumps)."""
        self.tabs[index].setChecked(True)
        self._on_tab_clicked(index)

    def _ensure_tab_data(self, index: int, force: bool = False) -> None:
        if index not in (TAB_RESOURCES, TAB_SAVES):
            return
        if not force and index in self._loaded_tabs:
            return
        self._loaded_tabs.add(index)
        if index == TAB_RESOURCES:
            self.reload_resources()
        else:
            self.reload_saves()

    # ---------- overview actions ----------

    def _require_instance(self) -> str | None:
        if self.instance_id is None or self.resolved is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return None
        return self.instance_id

    @staticmethod
    def _open_path(target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def open_instance_folder(self) -> None:
        """Open the instance folder (third-party mods can be dropped in directly)."""
        if self._require_instance() is None:
            return
        target = instance_dir(self.game_dir, self.instance_id)
        self._open_path(target)
        set_app_status(self, tr("instances.msg.folder_opened", str(target)))

    def open_logs_folder(self) -> None:
        if self._require_instance() is None:
            return
        target = self.resolved.launch_dir / "logs"
        self._open_path(target)
        set_app_status(self, tr("instances.detail.msg.logs_opened", str(target)))

    def open_mods_folder(self) -> None:
        if self._require_instance() is None:
            return
        self._open_path(self.resolved.mods_dir)
        set_app_status(self, tr("mods.msg.folder_opened", str(self.resolved.mods_dir)))

    def open_content_folder(self, subdir: str) -> None:
        if self._require_instance() is None:
            return
        target = resolve_content_dir(
            self.resolved.game_dir,
            subdir,
            version_id=self.resolved.id,
            isolated=self.resolved.isolated,
        )
        self._open_path(target)
        set_app_status(self, tr("instances.msg.folder_opened", str(target)))

    def open_saves_folder(self) -> None:
        if self._require_instance() is None:
            return
        target = self.resolved.launch_dir / "saves"
        self._open_path(target)
        set_app_status(self, tr("instances.msg.folder_opened", str(target)))

    def open_crash_viewer(self) -> None:
        """Open the crash report viewer for this instance (or the global game dir)."""
        from gui.crash_viewer import CrashViewerDialog

        base = self.resolved.launch_dir if self.resolved is not None else self.game_dir
        CrashViewerDialog(base, self).exec()

    def rename(self) -> None:
        if self._require_instance() is None:
            return
        old_id = self.instance_id
        new_id, ok = QInputDialog.getText(
            self,
            tr("instances.rename.dialog"),
            tr("instances.rename.prompt"),
            text=old_id,
        )
        new_id = new_id.strip()
        if not ok or not new_id or new_id == old_id:
            return
        try:
            rename_instance(old_id, new_id, self.game_dir)
        except InstancesError as exc:
            set_app_status(self, tr("instances.msg.rename_fail", str(exc)), "error")
            return
        self.instance_id = new_id
        self.reload()
        self.changed.emit()
        set_app_status(self, tr("instances.msg.renamed", old_id, new_id))

    def edit_note(self) -> None:
        if self._require_instance() is None:
            return
        text, ok = QInputDialog.getMultiLineText(
            self,
            tr("instances.note"),
            tr("instances.note.prompt"),
            self.instance.note if self.instance else "",
        )
        if not ok:
            return
        try:
            update_instance_note(self.instance_id, text, self.game_dir)
        except InstancesError as exc:
            set_app_status(self, tr("instances.msg.note_fail", str(exc)), "error")
            return
        self.reload()
        self.changed.emit()
        set_app_status(self, tr("instances.msg.note_saved", self.instance_id))

    def export(self) -> None:
        if self._require_instance() is None:
            return
        instance_id = self.instance_id
        dest, _filter = QFileDialog.getSaveFileName(
            self, tr("instances.export"), instance_id + ".zip", "Zip (*.zip)"
        )
        if not dest:
            return
        game_dir = self.game_dir
        run_in_background(
            partial(export_instance, instance_id, Path(dest), game_dir),
            on_result=self._on_exported,
            on_error=self._on_export_failed,
        )

    def _on_exported(self, path) -> None:
        set_app_status(self, tr("instances.msg.exported", str(path)))

    def _on_export_failed(self, message: str) -> None:
        set_app_status(self, tr("instances.msg.export_fail", message), "error")

    def delete(self) -> None:
        if self._require_instance() is None:
            return
        instance_id = self.instance_id
        answer = QMessageBox.question(
            self,
            tr("instances.delete.dialog"),
            tr("instances.delete.msg", instance_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_instance(instance_id, self.game_dir)
        except InstancesError as exc:
            set_app_status(self, tr("instances.msg.delete_fail", str(exc)), "error")
            return
        self.instance_id = None
        self.instance = None
        self.resolved = None
        self.deleted.emit(instance_id)

    # ---------- isolation ----------

    def _on_isolation_changed(self, _index: int) -> None:
        if self._filling or self.instance is None or self._isolation_warned:
            return
        if self.isolation_combo.currentData() == self.instance.isolated:
            return
        answer = QMessageBox.question(
            self,
            tr("instances.detail.settings.isolation.title"),
            tr("instances.detail.settings.isolation.msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._isolation_warned = True
            return
        self._filling = True
        try:
            index = self.isolation_combo.findData(self.instance.isolated)
            self.isolation_combo.setCurrentIndex(max(index, 0))
        finally:
            self._filling = False

    def enable_isolation(self) -> None:
        """One-click isolation for a shared instance: never moves any file."""
        if self._require_instance() is None:
            return
        instance_id = self.instance_id
        try:
            update_instance(instance_id, game_dir=self.game_dir, isolated=ISOLATION_ON)
        except InstancesError as exc:
            set_app_status(self, tr("instances.detail.share.fail", str(exc)), "error")
            return
        self.reload()
        self.changed.emit()
        set_app_status(
            self,
            tr("instances.detail.share.enabled", str(instance_dir(self.game_dir, instance_id))),
        )

    # ---------- settings ----------

    def _browse_java(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, tr("instances.detail.settings.browse_java"), self.java_edit.text()
        )
        if chosen:
            self.java_edit.setText(chosen)

    def _save_settings(self) -> None:
        if self._require_instance() is None:
            return
        instance_id = self.instance_id
        isolated = self.isolation_combo.currentData()
        try:
            set_instance_settings(
                instance_id,
                game_dir=self.game_dir,
                java="" if self.java_follow_check.isChecked() else self.java_edit.text().strip(),
                memory_gb=(
                    None if self.memory_follow_check.isChecked() else float(self.memory_spin.value())
                ),
                jvm_args=self.jvm_args_edit.text().strip(),
                game_args=self.game_args_edit.text().strip(),
            )
            if self.instance is not None and isolated != self.instance.isolated:
                update_instance(instance_id, game_dir=self.game_dir, isolated=isolated)
        except InstancesError as exc:
            set_app_status(self, tr("instances.detail.settings.fail", str(exc)), "error")
            return
        self.reload()
        self.changed.emit()
        set_app_status(self, tr("instances.detail.settings.saved", instance_id))

    def _reset_settings(self) -> None:
        if self._require_instance() is None:
            return
        instance_id = self.instance_id
        answer = QMessageBox.question(
            self,
            tr("instances.detail.settings.reset.title"),
            tr("instances.detail.settings.reset.msg", instance_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            reset_instance_settings(instance_id, self.game_dir)
        except InstancesError as exc:
            set_app_status(self, tr("instances.detail.settings.fail", str(exc)), "error")
            return
        self._isolation_warned = False
        self.reload()
        self.changed.emit()
        set_app_status(self, tr("instances.detail.settings.reset.done", instance_id))

    def _selected_values(self, table: QTableWidget) -> list[str]:
        """Names of the selected rows of a content table (column 0 holds the name)."""
        rows = sorted({index.row() for index in table.selectedItems()})
        out = []
        for row in rows:
            item = table.item(row, 0)
            if item is not None and item.text():
                out.append(item.text())
        return out

    # ---------- mods ----------

    def _reload_mods(self) -> None:
        if self.resolved is None:
            return
        set_app_status(self, tr("instances.mods.loading"))
        run_in_background(
            partial(scan_mods, self.resolved.mods_dir),
            on_result=self._fill_mods_table,
            on_error=self._on_mods_failed,
        )

    def _on_mods_failed(self, message: str) -> None:
        set_app_status(self, tr("instances.mods.msg.load_fail", message), "error")

    def _fill_mods_table(self, mods: list) -> None:
        self._mods = mods
        self._refill_mods()

    def _refill_mods(self) -> None:
        want = self.mods_filter.currentData()
        needle = self.mods_search.text().strip().lower()
        shown = []
        for m in self._mods:
            if want == "enabled" and not m.enabled:
                continue
            if want == "disabled" and m.enabled:
                continue
            if needle and needle not in (m.name + " " + m.mod_id + " " + m.file).lower():
                continue
            shown.append(m)
        self._filling_mods = True
        try:
            self.mods_table.setSortingEnabled(False)
            self.mods_table.setRowCount(0)
            self.mods_table.setRowCount(len(shown))
            for row, m in enumerate(shown):
                check = QTableWidgetItem()
                check.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                check.setCheckState(
                    Qt.CheckState.Checked if m.enabled else Qt.CheckState.Unchecked
                )
                check.setData(Qt.UserRole, m.file)
                self.mods_table.setItem(row, 0, check)
                for col, text in enumerate(
                    (m.name, m.mod_id, m.version, m.loader, m.file), start=1
                ):
                    self.mods_table.setItem(row, col, QTableWidgetItem(text))
            self.mods_table.setSortingEnabled(True)
        finally:
            self._filling_mods = False
        if not shown and self._mods:
            set_app_status(self, tr("instances.mods.search.none"))
        else:
            set_app_status(self, tr("instances.mods.count", len(self._mods)))

    def _on_mod_toggled(self, item: QTableWidgetItem) -> None:
        if self._filling_mods or item.column() != 0:
            return
        mod = next((m for m in self._mods if m.file == item.data(Qt.UserRole)), None)
        if mod is None:
            return
        want = item.checkState() == Qt.CheckState.Checked
        if mod.enabled == want:
            return
        try:
            set_mod_enabled(mod, want)
        except OSError as exc:
            set_app_status(self, tr("instances.mods.msg.toggle_fail", exc), "error")
            self._filling_mods = True
            try:
                item.setCheckState(
                    Qt.CheckState.Checked if mod.enabled else Qt.CheckState.Unchecked
                )
            finally:
                self._filling_mods = False

    def delete_selected_mods(self) -> None:
        rows = sorted({i.row() for i in self.mods_table.selectedItems()}, reverse=True)
        if not rows:
            set_app_status(self, tr("instances.mods.msg.need_select"), "warning")
            return
        files = []
        for row in rows:
            item = self.mods_table.item(row, 5)
            if item:
                files.append(item.text())
        answer = QMessageBox.question(
            self,
            tr("instances.mods.delete"),
            tr("instances.mods.delete.confirm", len(files)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleted = 0
        for name in files:
            mod = next((m for m in self._mods if m.file == name), None)
            if mod is None:
                continue
            try:
                mod.path.unlink()
                deleted += 1
            except OSError:
                continue
        set_app_status(self, tr("instances.mods.msg.deleted", deleted))
        self._reload_mods()

    def install_dropped(self, jars: list[Path]) -> None:
        if self.resolved is None:
            set_app_status(self, tr("instances.mods.hint"))
            return
        errors = []
        for src in jars:
            try:
                install_mod_file(src, self.resolved.mods_dir)
            except OSError as exc:
                errors.append(str(exc))
        if errors:
            set_app_status(self, tr("instances.mods.msg.import_fail", "; ".join(errors)), "error")
        else:
            set_app_status(
                self, tr("instances.mods.msg.imported", ", ".join(j.name for j in jars))
            )
        self._reload_mods()

    # ---------- resources ----------

    def reload_resources(self) -> None:
        if self.resolved is None:
            return
        resolved = self.resolved
        set_app_status(self, tr("instances.detail.res.loading"))

        def work() -> dict:
            return {
                sub: list_installed_content(
                    resolved.game_dir,
                    sub,
                    version_id=resolved.id,
                    isolated=resolved.isolated,
                )
                for sub in _CONTENT_SUBDIRS
            }

        run_in_background(work, on_result=self._fill_resources, on_error=self._on_content_failed)

    def _on_content_failed(self, message: str) -> None:
        set_app_status(self, tr("instances.detail.res.msg.load_fail", message), "error")

    def _fill_resources(self, payload: dict) -> None:
        total = 0
        for subdir, items in payload.items():
            self._content_items[subdir] = items
            total += len(items)
            table = self.content_tables[subdir]
            table.setRowCount(0)
            table.setRowCount(len(items))
            for row, item in enumerate(items):
                table.setItem(row, 0, QTableWidgetItem(item.name))
                table.setItem(
                    row, 1, NumericTableItem(human_size(item.size), float(item.size))
                )
            self.content_empty[subdir].update_for(len(items))
        set_app_status(self, tr("instances.detail.res.count", total))

    def delete_selected_content(self, subdir: str) -> None:
        if self._require_instance() is None:
            return
        names = self._selected_values(self.content_tables[subdir])
        if not names:
            set_app_status(self, tr("instances.detail.res.msg.need_select"), "warning")
            return
        answer = QMessageBox.question(
            self,
            tr("instances.mods.delete"),
            tr("instances.detail.res.delete.confirm", len(names)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        resolved = self.resolved

        def work() -> int:
            return sum(_delete_content_file(resolved, subdir, name) for name in names)

        run_in_background(
            work,
            on_result=self._on_content_deleted,
            on_error=self._on_content_delete_failed,
        )

    def _on_content_deleted(self, deleted: int) -> None:
        set_app_status(self, tr("instances.detail.res.msg.deleted", deleted))
        self.reload_resources()

    def _on_content_delete_failed(self, message: str) -> None:
        set_app_status(self, tr("instances.detail.res.msg.delete_fail", message), "error")

    # ---------- saves ----------

    def reload_saves(self) -> None:
        if self.resolved is None:
            return
        target = self.resolved.launch_dir / "saves"
        set_app_status(self, tr("instances.detail.saves.loading"))

        def work() -> list:
            found = []
            if target.is_dir():
                for entry in sorted(target.iterdir()):
                    try:
                        if not entry.is_dir():
                            continue
                        found.append(
                            (entry.name, entry.stat().st_mtime, directory_size(entry))
                        )
                    except OSError:
                        continue
            return found

        run_in_background(work, on_result=self._fill_saves, on_error=self._on_saves_failed)

    def _on_saves_failed(self, message: str) -> None:
        set_app_status(self, tr("instances.detail.saves.msg.load_fail", message), "error")

    def _fill_saves(self, saves: list) -> None:
        self._saves = saves
        table = self.saves_table
        table.setRowCount(0)
        table.setRowCount(len(saves))
        for row, (name, modified, size) in enumerate(saves):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(
                row, 1, QTableWidgetItem(time.strftime("%Y-%m-%d %H:%M", time.localtime(modified)))
            )
            table.setItem(row, 2, NumericTableItem(human_size(size), float(size)))
        self.saves_empty.update_for(len(saves))
        set_app_status(self, tr("instances.detail.saves.count", len(saves)))

    # ---------- launch ----------

    def launch(self) -> None:
        if self._require_instance() is None:
            return
        instance_id = self.instance_id
        cfg, _ = config.load()
        if not cfg.selected_account:
            from launcher.config import offline_mode_allowed

            if not offline_mode_allowed():
                set_app_status(self, tr("launch.msg.offline_locked"), "warning")
                return
        resolved = self.resolved
        if resolved is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return
        disable_keeping_focus(self.launch_button)
        set_app_status(self, tr("instances.msg.preparing", instance_id))

        def do_prepare() -> object:
            try:
                account = resolve_launch_account(AccountStore(), cfg.selected_account, None)
                prepared = prepare_launch(
                    instance_id,
                    game_dir=resolved.game_dir,
                    cache_dir=paths.launcher_dir() / "cache",
                    account=account,
                    memory_gb=resolved.memory_gb,
                    language=cfg.game_language or None,
                    launch_dir=resolved.launch_dir,
                    java_path=resolved.java_path,
                    jvm_args=resolved.jvm_args or None,
                    game_args=resolved.game_args,
                )
                return ("ok", prepared)
            except Exception as exc:  # noqa: BLE001 - reported as a launch failure
                return ("error", str(exc))

        run_in_background(
            do_prepare,
            on_result=self._on_prepared,
            on_finished=self._on_launch_finished,
        )

    def _on_launch_finished(self) -> None:
        self.launch_button.setEnabled(True)

    def _on_prepared(self, result) -> None:
        kind, payload = result
        if kind == "error":
            text = tr("instances.msg.launch_fail", str(payload))
            set_app_status(self, text, "error")
            show_fatal(self, text)  # fatal error dialog
            return
        prepared = payload
        command = prepared.command
        set_app_status(self, tr("instances.msg.running", prepared.version.id, str(command.cwd)))

        # After-launch behavior (keep / hide / exit) via a signal bridge.
        cfg2, _ = config.load()
        start_bridge = ProgressBridge()
        if cfg2.after_launch_behavior != "keep":
            start_bridge.progress.connect(self._on_game_started)

        def do_run() -> object:
            started = time.time()
            code = run_process(
                command.argv,
                command.cwd,
                on_started=start_bridge if cfg2.after_launch_behavior != "keep" else None,
            )
            crashes = find_new_crash_reports(command.cwd, started)
            return code, crashes

        run_in_background(
            do_run,
            on_result=self._on_exit,
            on_error=self._on_run_failed,
        )

    def _on_run_failed(self, message: str) -> None:
        text = tr("instances.msg.run_error", message)
        set_app_status(self, text, "error")
        show_fatal(self, text)

    def _on_exit(self, result) -> None:
        code, crashes = result
        message = tr("launch.msg.exit", code)
        if crashes:
            message += tr("launch.msg.crash", len(crashes))
        set_app_status(self, message)

    def _on_game_started(self, _value=None) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        cfg, _ = config.load()
        if cfg.trim_memory_on_launch:
            from launcher.launch.memory import trim_working_set

            trim_working_set()
        set_app_status(self, tr("launch.msg.auto_closing"))
        if cfg.after_launch_behavior == "keep":
            return
        if cfg.after_launch_behavior == "hide":
            # Hide the window but keep the launcher running in the background.
            self.window().hide()
            return
        # Exit: hide first so no stale window remains while the app quits.
        self.window().hide()
        QTimer.singleShot(600, QApplication.instance().quit)
