"""实例页：实例的创建/删除/启动/重命名/备注/导入导出（独立存档、模组与配置）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.errors import show_fatal
from gui.widgets import apply_no_focus_outline
from gui.workers import run_in_background
from launcher import config, paths
from launcher.auth import AccountStore
from launcher.instances import (
    InstancesError,
    create_instance,
    default_instance_name,
    delete_instance,
    export_instance,
    import_instance,
    instance_dir,
    list_instances,
    rename_instance,
    update_instance_note,
)
from launcher.launch import (
    find_new_crash_reports,
    prepare_launch,
    resolve_launch_account,
    run_process,
)
from launcher.meta import fetch_manifest

tr = i18n.tr


class _CreateDialog(QDialog):
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
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("instances.create.cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.version_combo.currentIndexChanged.connect(self._auto_name)

        form = QFormLayout(self)
        form.addRow(tr("instances.name"), self.name_edit)
        form.addRow(tr("instances.version"), self.version_combo)
        form.addRow(self.buttons)

        cache = paths.launcher_dir() / "cache" / "version_manifest.json"

        def do_fetch() -> object:
            return fetch_manifest(cache_path=cache)

        run_in_background(
            do_fetch,
            on_result=self._fill_versions,
            on_error=lambda m: self.version_combo.setItemText(0, tr("instances.fetch_fail", m)),
        )

    def _fill_versions(self, manifest) -> None:
        self.version_combo.clear()
        for v in manifest.versions:
            if v.type in ("release", "snapshot"):
                self.version_combo.addItem(v.id)

    def _auto_name(self) -> None:
        version_id = self.version_combo.currentText().strip()
        if not version_id or version_id.startswith(tr("instances.loading").split("（")[0]):
            return
        if not self.name_edit.text().strip():
            self.name_edit.setText(default_instance_name(version_id))

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.version_combo.currentText().strip()


class InstancesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.list = QListWidget()
        apply_no_focus_outline(self.list)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem(tr("instances.sort.name"), "name")
        self.sort_combo.addItem(tr("instances.sort.time"), "time")
        self.create_button = QPushButton(tr("instances.create"))
        self.open_folder_button = QPushButton(tr("instances.open_folder"))
        self.import_button = QPushButton(tr("instances.import"))
        self.delete_button = QPushButton(tr("instances.delete"))
        self.launch_button = QPushButton(tr("instances.launch"))
        self.status = QLabel(tr("instances.hint"))
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel(tr("instances.sort.label")))
        sort_row.addWidget(self.sort_combo)
        sort_row.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.open_folder_button)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.launch_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(sort_row)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.status)

        self.create_button.clicked.connect(self._create)
        self.delete_button.clicked.connect(self._delete)
        self.import_button.clicked.connect(self._import)
        self.open_folder_button.clicked.connect(self._open_folder)
        self.launch_button.clicked.connect(self._launch)
        self.sort_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        self.list.itemDoubleClicked.connect(lambda _item: self._rename())
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        instances = list_instances()
        if self.sort_combo.currentData() == "time":
            ordered = sorted(instances.values(), key=lambda i: i.created_at, reverse=True)
        else:
            ordered = sorted(instances.values(), key=lambda i: i.name)
        for inst in ordered:
            text = inst.name + "   [" + inst.version_id + "]"
            if inst.note:
                text += "  — " + inst.note
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, inst.name)  # 名称存数据角色，避免按文本解析
            self.list.addItem(item)

    def _current_name(self) -> str | None:
        row = self.list.currentRow()
        if row < 0:
            return None
        item = self.list.item(row)
        name = item.data(Qt.UserRole)
        return name if name else None

    def _create(self) -> None:
        dialog = _CreateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, version = dialog.values()
        if not name or not version:
            self.status.setText(tr("instances.msg.need_fields"))
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()

        def do_create() -> object:
            return create_instance(
                name, version, game_dir, cache_dir=paths.launcher_dir() / "cache"
            )

        self.create_button.setEnabled(False)
        run_in_background(
            do_create,
            on_result=lambda _inst: (self.refresh(), self.status.setText(tr("instances.msg.created", name))),
            on_error=lambda m: self.status.setText(tr("instances.msg.create_fail", m)),
            on_finished=lambda: self.create_button.setEnabled(True),
        )

    def _delete(self) -> None:
        name = self._current_name()
        if name is None:
            self.status.setText(tr("instances.msg.need_select"))
            return
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            tr("instances.delete.dialog"),
            tr("instances.delete.msg", name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        try:
            delete_instance(name, game_dir)
        except InstancesError as exc:
            self.status.setText(tr("instances.msg.delete_fail", str(exc)))
            return
        self.refresh()
        self.status.setText(tr("instances.msg.deleted", name))

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        rename_action = menu.addAction(tr("instances.rename"))
        note_action = menu.addAction(tr("instances.note"))
        folder_action = menu.addAction(tr("instances.open_folder"))
        export_action = menu.addAction(tr("instances.export"))
        launch_action = menu.addAction(tr("instances.launch"))
        delete_action = menu.addAction(tr("instances.delete"))
        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen == rename_action:
            self._rename()
        elif chosen == note_action:
            self._edit_note()
        elif chosen == folder_action:
            self._open_folder()
        elif chosen == export_action:
            self._export()
        elif chosen == launch_action:
            self._launch()
        elif chosen == delete_action:
            self._delete()

    def _rename(self) -> None:
        name = self._current_name()
        if name is None:
            self.status.setText(tr("instances.msg.need_select"))
            return
        new_name, ok = QInputDialog.getText(
            self,
            tr("instances.rename.dialog"),
            tr("instances.rename.prompt"),
            text=name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == name:
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        try:
            rename_instance(name, new_name, game_dir)
        except InstancesError as exc:
            self.status.setText(tr("instances.msg.rename_fail", str(exc)))
            return
        self.refresh()
        # 保持选中重命名后的实例
        for row in range(self.list.count()):
            if self.list.item(row).text().startswith(new_name + "   ["):
                self.list.setCurrentRow(row)
                break
        self.status.setText(tr("instances.msg.renamed", name, new_name))

    def _edit_note(self) -> None:
        name = self._current_name()
        if name is None:
            self.status.setText(tr("instances.msg.need_select"))
            return
        inst = list_instances().get(name)
        text, ok = QInputDialog.getMultiLineText(
            self,
            tr("instances.note"),
            tr("instances.note.prompt"),
            inst.note if inst else "",
        )
        if not ok:
            return
        try:
            update_instance_note(name, text)
        except InstancesError as exc:
            self.status.setText(tr("instances.msg.note_fail", str(exc)))
            return
        self.refresh()
        self.status.setText(tr("instances.msg.note_saved", name))

    def _export(self) -> None:
        name = self._current_name()
        if name is None:
            self.status.setText(tr("instances.msg.need_select"))
            return
        from PySide6.QtWidgets import QFileDialog

        dest, _filter = QFileDialog.getSaveFileName(
            self, tr("instances.export"), name + ".zip", "Zip (*.zip)"
        )
        if not dest:
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()

        def do_export() -> object:
            return export_instance(name, Path(dest), game_dir)

        run_in_background(
            do_export,
            on_result=lambda p: self.status.setText(tr("instances.msg.exported", str(p))),
            on_error=lambda m: self.status.setText(tr("instances.msg.export_fail", m)),
        )

    def _import(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        zip_path, _filter = QFileDialog.getOpenFileName(
            self, tr("instances.import"), "", "Zip (*.zip)"
        )
        if not zip_path:
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()

        def do_import() -> object:
            return import_instance(Path(zip_path), game_dir)

        run_in_background(
            do_import,
            on_result=self._on_imported,
            on_error=lambda m: self.status.setText(tr("instances.msg.import_fail", m)),
        )

    def _on_imported(self, inst) -> None:
        self.refresh()
        self.status.setText(tr("instances.msg.imported", inst.name))

    def _open_folder(self) -> None:
        """打开实例文件夹（用户可直接放入第三方模组/资源包/光影）。"""
        name = self._current_name()
        if name is None:
            self.status.setText(tr("instances.msg.need_select"))
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        target = instance_dir(game_dir, name)
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        self.status.setText(tr("instances.msg.folder_opened", str(target)))

    def _launch(self) -> None:
        name = self._current_name()
        if name is None:
            self.status.setText(tr("instances.msg.need_select"))
            return
        instances = list_instances()
        inst = instances.get(name)
        if inst is None:
            self.status.setText(tr("instances.msg.not_found", name))
            return
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        # 离线模式门槛：无正版账号时启动实例等同离线启动
        if not cfg.selected_account:
            from launcher.config import offline_mode_allowed

            if not offline_mode_allowed():
                self.status.setText(tr("launch.msg.offline_locked"))
                return
        self.launch_button.setEnabled(False)
        self.status.setText(tr("instances.msg.preparing", name))

        def do_prepare() -> object:
            try:
                account = resolve_launch_account(
                    AccountStore(), cfg.selected_account, None
                )
                prepared = prepare_launch(
                    inst.version_id,
                    game_dir=game_dir,
                    cache_dir=paths.launcher_dir() / "cache",
                    account=account,
                    memory_gb=cfg.memory_gb,
                    language=cfg.game_language or None,
                    instance_name=name,
                    jvm_args=cfg.jvm_args or None,
                )
                return ("ok", prepared)
            except Exception as exc:  # noqa: BLE001
                return ("error", str(exc))

        run_in_background(
            do_prepare,
            on_result=self._on_prepared,
            on_finished=lambda: self.launch_button.setEnabled(True),
        )

    def _on_prepared(self, result) -> None:
        kind, payload = result
        if kind == "error":
            text = tr("instances.msg.launch_fail", str(payload))
            self.status.setText(text)
            show_fatal(self, text)  # #31 致命错误弹窗
            return
        prepared = payload
        command = prepared.command
        self.status.setText(
            tr("instances.msg.running", prepared.version.id, str(command.cwd))
        )

        # #14 启动成功后自动隐藏（跟随配置）
        from gui.workers import ProgressBridge

        cfg2, _ = config.load()
        start_bridge = ProgressBridge()
        if cfg2.auto_close_on_launch:
            start_bridge.progress.connect(self._on_game_started)

        def do_run() -> object:
            started = __import__("time").time()
            code = run_process(
                command.argv,
                command.cwd,
                on_started=start_bridge if cfg2.auto_close_on_launch else None,
            )
            crashes = find_new_crash_reports(command.cwd, started)
            return code, crashes

        run_in_background(
            do_run,
            on_result=self._on_exit,
            on_error=lambda m: (
                self.status.setText(tr("instances.msg.run_error", m)),
                show_fatal(self, tr("instances.msg.run_error", m)),
            ),
        )

    def _on_exit(self, result) -> None:
        code, crashes = result
        message = tr("launch.msg.exit", code)
        if crashes:
            message += tr("launch.msg.crash", len(crashes))
        self.status.setText(message)

    def _on_game_started(self, _value=None) -> None:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        self.status.setText(tr("launch.msg.auto_closing"))
        # 立即隐藏窗口（quit 后进程要等游戏结束才真正退出，窗口会残留）
        self.window().hide()
        QTimer.singleShot(600, QApplication.instance().quit)
