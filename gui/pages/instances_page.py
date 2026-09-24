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

"""Instances page: list of installed instances on the left, details of the selected one on the right.

An instance *is* a version folder (`versions/<id>/`), so this page owns every
management action for the installed versions: launching, mods, resource packs,
saves, per-instance settings, rename, export and delete. Everything that acts on
one instance lives in @gui.pages.instance_detail.InstanceDetail; this module only
keeps the list, the search box and the cross-instance actions.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.pages.instance_detail import InstanceDetail
from gui.widgets import (
    EmptyState,
    add_search_icon,
    apply_no_focus_outline,
    build_page_header,
    disable_keeping_focus,
    set_app_status,
    style_page_layout,
)
from gui.workers import run_in_background
from launcher import config, paths
from launcher.install import list_installed_versions
from launcher.instances import (
    create_instance,
    default_instance_name,
    display_version_name,
    import_instance,
    instance_dir,
    list_instances,
)

tr = i18n.tr

LEFT_WIDTH = 320  # the list column keeps a fixed width so the detail panel gets the rest


class _CreateDialog(QDialog):
    """Create another instance by copying an installed profile (instances are version folders)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("instances.dialog.title"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("instances.name.placeholder"))
        self.version_combo = QComboBox()
        self.version_combo.setEditable(True)
        self.version_combo.addItem(tr("instances.loading"))
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("instances.create.ok"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            tr("instances.create.cancel")
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.version_combo.currentIndexChanged.connect(self._auto_name)

        form = QFormLayout(self)
        form.addRow(tr("instances.name"), self.name_edit)
        form.addRow(tr("instances.version"), self.version_combo)
        form.addRow(self.buttons)

        self._fill_versions()

    def _fill_versions(self) -> None:
        """List installed profiles only - a copy needs the profile files to duplicate."""
        self.version_combo.clear()
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        try:
            installed = sorted(list_installed_versions(game_dir))
        except OSError:
            installed = []
        if not installed:
            self.version_combo.addItem(tr("instances.none_installed"))
            return
        for version_id in installed:
            self.version_combo.addItem(display_version_name(version_id), version_id)

    def _auto_name(self) -> None:
        version_id = (self.version_combo.currentData() or self.version_combo.currentText()).strip()
        if not version_id or version_id.startswith(tr("instances.loading").split("（")[0]):
            return
        if not self.name_edit.text().strip():
            self.name_edit.setText(default_instance_name(version_id))

    def values(self) -> tuple[str, str]:
        version_id = self.version_combo.currentData() or self.version_combo.currentText().strip()
        return self.name_edit.text().strip(), version_id


class InstancesPage(QWidget):
    """Master-detail instances page."""

    def __init__(self) -> None:
        super().__init__()
        self.search_edit = QLineEdit()
        add_search_icon(self.search_edit)
        self.search_edit.setPlaceholderText(tr("instances.search.placeholder"))
        self.search_edit.setClearButtonEnabled(True)

        self.list = QListWidget()
        apply_no_focus_outline(self.list)
        self.empty_instances = EmptyState(tr("empty.instances"))
        self.empty_search = EmptyState(tr("instances.search.none"))
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.list)
        self.list_stack.addWidget(self.empty_instances)
        self.list_stack.addWidget(self.empty_search)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem(tr("instances.sort.name"), "name")
        self.sort_combo.addItem(tr("instances.sort.time"), "time")

        self.create_button = QPushButton(tr("instances.create_copy"))
        self.import_button = QPushButton(tr("instances.import"))
        self.import_button.setObjectName("secondaryButton")

        self.detail = InstanceDetail()
        self.no_selection = QLabel(tr("instances.select.hint"))
        self.no_selection.setObjectName("emptyState")
        self.no_selection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_selection.setWordWrap(True)
        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(self.detail)
        self.detail_stack.addWidget(self.no_selection)

        # Legacy attribute names kept for callers (and tests) that predate the detail panel
        self.open_folder_button = self.detail.open_folder_button
        self.launch_button = self.detail.launch_button
        self.crash_button = self.detail.crash_button
        self.mods_table = self.detail.mods_table

        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self.search_edit)
        sort_row = QHBoxLayout()
        sort_row.setContentsMargins(0, 0, 0, 0)
        sort_row.setSpacing(6)
        sort_row.addWidget(QLabel(tr("instances.sort.label")))
        sort_row.addWidget(self.sort_combo, 1)
        left_layout.addLayout(sort_row)
        left_layout.addWidget(self.list_stack, 1)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        actions.addWidget(self.create_button)
        actions.addWidget(self.import_button)
        actions.addStretch(1)
        left_layout.addLayout(actions)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        body.addWidget(left)
        body.addWidget(self.detail_stack, 1)

        layout = QVBoxLayout(self)
        style_page_layout(layout)
        layout.addWidget(build_page_header(tr("nav.instances"), tr("page.instances.desc")))
        layout.addLayout(body, 1)

        self.create_button.clicked.connect(self._create)
        self.import_button.clicked.connect(self._import)
        self.sort_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        # Debounce: refilter only after 200ms of typing inactivity
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._on_search_changed)
        self.search_edit.textChanged.connect(lambda _t: self._search_timer.start(200))
        self.list.currentRowChanged.connect(self._on_selection_changed)
        self.detail.changed.connect(self._on_detail_changed)
        self.detail.deleted.connect(self._on_detail_deleted)
        self.refresh()

    # ---------- list ----------

    def refresh(self, select: str | None = None) -> None:
        """Rebuild the instance list; `select` forces a selection (None keeps the current one)."""
        wanted = select if select is not None else self._current_name()
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        instances = list_instances(game_dir)
        self._instances = instances
        ordered = sorted(instances.values(), key=self._sort_key)
        needle = self.search_edit.text().strip().lower()
        self.list.blockSignals(True)
        try:
            self.list.clear()
            shown = 0
            for inst in ordered:
                if needle and needle not in self._haystack(inst):
                    continue
                item = QListWidgetItem(self._row_text(inst))
                item.setData(Qt.UserRole, inst.id)  # instance id in a data role, never parsed
                item.setToolTip(str(instance_dir(game_dir, inst.id)))
                self.list.addItem(item)
                shown += 1
        finally:
            self.list.blockSignals(False)
        self._update_list_state(len(instances), self.list.count())
        self._select(wanted)

    def _sort_key(self, inst):
        # Starred instances come first, then the chosen order
        primary = 0 if inst.star else 1
        if self.sort_combo.currentData() == "time":
            return (primary, -float(inst.created_at or 0.0), inst.name.lower())
        return (primary, inst.name.lower())

    def _row_text(self, inst) -> str:
        text = inst.name  # display name (falls back to the folder name)
        label = display_version_name(inst.id)
        if label != inst.name:
            text += "   [" + label + "]"
        if inst.note:
            text += "  — " + inst.note
        return text

    def _haystack(self, inst) -> str:
        """Search matches the display name, the instance id and the profile label."""
        return " ".join(
            (inst.name, inst.id, display_version_name(inst.id), inst.note)
        ).lower()

    def _update_list_state(self, total: int, shown: int) -> None:
        if total == 0:
            self.list_stack.setCurrentWidget(self.empty_instances)
            self.empty_instances.update_for(0)
            return
        if shown == 0:
            self.list_stack.setCurrentWidget(self.empty_search)
            self.empty_search.update_for(0)
            return
        self.list_stack.setCurrentWidget(self.list)

    def _select(self, instance_id: str | None) -> None:
        """Select a row by instance id (no selection when it is gone)."""
        row = -1
        if instance_id:
            for index in range(self.list.count()):
                if self.list.item(index).data(Qt.UserRole) == instance_id:
                    row = index
                    break
        self.list.setCurrentRow(row)  # -1 when the instance disappeared: shows the hint panel
        self._on_selection_changed(row)

    def select_instance(self, instance_id: str) -> bool:
        """Show one instance (used by the versions page's 打开实例 button)."""
        self.refresh(select=instance_id)
        found = self._current_name() == instance_id
        if not found:
            set_app_status(self, tr("instances.msg.not_found", instance_id), "warning")
        return found

    def _current_name(self) -> str | None:
        item = self.list.currentItem()
        if item is None:
            return None
        instance_id = item.data(Qt.UserRole)
        return instance_id if instance_id else None

    def _on_search_changed(self) -> None:
        self.refresh()

    def _on_selection_changed(self, _row: int) -> None:
        instance_id = self._current_name()
        if instance_id is None:
            self.detail.set_instance(None)
            self.detail_stack.setCurrentWidget(self.no_selection)
            return
        self.detail_stack.setCurrentWidget(self.detail)
        self.detail.set_instance(instance_id)

    def _on_detail_changed(self) -> None:
        """Metadata changed in the detail: rebuild the list, keeping the shown instance."""
        self.refresh(select=self.detail.instance_id or self._current_name())

    def _on_detail_deleted(self, _instance_id: str) -> None:
        self.refresh()

    def _selected_instance(self):
        instance_id = self._current_name()
        if not instance_id:
            return None
        return self._instances.get(instance_id) if hasattr(self, "_instances") else None

    # ---------- page-level actions (delegating to the detail) ----------

    def _open_folder(self) -> None:
        """Open the selected instance folder."""
        if self._current_name() is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return
        self.detail.open_instance_folder()

    def _rename(self) -> None:
        if self._current_name() is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return
        self.detail.rename()

    def _edit_note(self) -> None:
        if self._current_name() is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return
        self.detail.edit_note()

    def _export(self) -> None:
        if self._current_name() is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return
        self.detail.export()

    def _delete(self) -> None:
        if self._current_name() is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return
        self.detail.delete()

    def _launch(self) -> None:
        if self._current_name() is None:
            set_app_status(self, tr("instances.msg.need_select"), "warning")
            return
        self.detail.launch()

    def _open_crash_viewer(self) -> None:
        self.detail.open_crash_viewer()

    def _install_dropped(self, jars: list[Path]) -> None:
        self.detail.install_dropped(jars)

    def _create(self) -> None:
        dialog = _CreateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, version = dialog.values()
        if not name or not version:
            set_app_status(self, tr("instances.msg.need_fields"), "warning")
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()

        def do_create() -> object:
            return create_instance(
                name, version, game_dir, cache_dir=paths.launcher_dir() / "cache"
            )

        disable_keeping_focus(self.create_button)
        run_in_background(
            do_create,
            on_result=self._on_created,
            on_error=self._on_create_failed,
            on_finished=self._on_create_finished,
        )

    def _on_created(self, instance) -> None:
        self.refresh(select=instance.id)
        set_app_status(self, tr("instances.msg.created", instance.name))

    def _on_create_failed(self, message: str) -> None:
        set_app_status(self, tr("instances.msg.create_fail", message), "error")

    def _on_create_finished(self) -> None:
        self.create_button.setEnabled(True)

    def _import(self) -> None:
        zip_path, _filter = QFileDialog.getOpenFileName(
            self, tr("instances.import"), "", "Zip (*.zip)"
        )
        if not zip_path:
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()

        disable_keeping_focus(self.import_button)
        run_in_background(
            import_instance,
            Path(zip_path),
            game_dir,
            on_result=self._on_imported,
            on_error=self._on_import_failed,
            on_finished=self._on_import_finished,
        )

    def _on_imported(self, instance) -> None:
        self.refresh(select=instance.id)
        set_app_status(self, tr("instances.msg.imported", instance.name))

    def _on_import_failed(self, message: str) -> None:
        set_app_status(self, tr("instances.msg.import_fail", message), "error")

    def _on_import_finished(self) -> None:
        self.import_button.setEnabled(True)
