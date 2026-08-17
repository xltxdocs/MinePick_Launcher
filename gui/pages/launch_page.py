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

"""Launch page: choose version/account/memory/language, launch the game and tail the log."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.errors import show_fatal
from gui.widgets import NoWheelDoubleSpinBox, NoWheelSpinBox
from gui.workers import run_in_background
from launcher import config, paths
from launcher.auth import AccountStore
from launcher.launch import (
    JavaMissingError,
    find_new_crash_reports,
    prepare_launch,
    resolve_launch_account,
    run_process,
)

tr = i18n.tr


class LaunchPage(QWidget):
    account_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.version_combo = QComboBox()
        self.version_combo.setEditable(True)
        self.account_combo = QComboBox()
        self.offline_edit = QLineEdit()
        self.offline_edit.setPlaceholderText(tr("launch.offline.placeholder"))
        self.memory_spin = NoWheelDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setSuffix(" GB")
        self.language_combo = QComboBox()
        for code, label in config.GAME_LANGUAGES:
            self.language_combo.addItem(label, code)
        self.jvm_args_edit = QLineEdit()
        self.jvm_args_edit.setPlaceholderText(tr("launch.jvm_args.placeholder"))
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText(tr("launch.server.placeholder"))
        self.server_port_spin = NoWheelSpinBox()
        self.server_port_spin.setRange(0, 65535)
        self.server_port_spin.setSpecialValueText(tr("common.off"))
        self.launch_button = QPushButton(tr("launch.button"))
        self.status = QLabel(tr("status.ready"))
        self.status.setObjectName("hint")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)

        form = QFormLayout()
        form.addRow(tr("launch.version"), self.version_combo)
        form.addRow(tr("launch.account"), self.account_combo)
        form.addRow(tr("launch.offline"), self.offline_edit)
        form.addRow(tr("launch.memory"), self.memory_spin)
        form.addRow(tr("launch.language"), self.language_combo)
        form.addRow(tr("launch.jvm_args"), self.jvm_args_edit)
        server_row = QHBoxLayout()
        server_row.addWidget(self.server_edit, 1)
        server_row.addWidget(QLabel(tr("launch.port")))
        server_row.addWidget(self.server_port_spin)
        form.addRow(tr("launch.server"), server_row)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.launch_button)
        layout.addWidget(self.status)
        layout.addWidget(QLabel(tr("launch.log.label")))
        layout.addWidget(self.log_view, 1)

        self.launch_button.clicked.connect(self.launch)
        self.account_combo.currentIndexChanged.connect(self._on_account_selected)

        self._log_timer = QTimer(self)
        self._log_timer.setInterval(2000)
        self._log_timer.timeout.connect(self._tail_log)
        self._log_path: Path | None = None
        self._log_pos = 0

        self.refresh_config()
        self.refresh_account()
        self._populate_versions()

    def refresh_config(self) -> None:
        cfg, _ = config.load()
        self.memory_spin.setValue(cfg.memory_gb)
        index = self.language_combo.findData(cfg.game_language)
        self.language_combo.setCurrentIndex(max(index, 0))
        self.jvm_args_edit.setText(cfg.jvm_args or "")

    def refresh_account(self) -> None:
        cfg, _ = config.load()
        accounts = AccountStore().load()
        # Block signals so rebuilding the list doesn't accidentally trigger a save
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        self.account_combo.addItem(tr("launch.account.none.item"), None)
        for account_id, account in sorted(accounts.items(), key=lambda kv: kv[1].username):
            kind = tr("kind.ms") if account.type == "microsoft" else tr("kind.offline")
            self.account_combo.addItem(account.username + "（" + kind + "）", account_id)
        index = self.account_combo.findData(cfg.selected_account)
        self.account_combo.setCurrentIndex(max(index, 0))
        self.account_combo.blockSignals(False)

    def _on_account_selected(self) -> None:
        """Dropdown account switch: write the config and sync the account page."""
        account_id = self.account_combo.currentData()
        cfg, cfg_path = config.load()
        if cfg.selected_account == account_id:
            return
        cfg.selected_account = account_id
        config.save(cfg, cfg_path)
        self.account_changed.emit()

    def set_version_id(self, version_id: str) -> None:
        index = self.version_combo.findData(version_id)
        if index >= 0:
            self.version_combo.setCurrentIndex(index)
        else:
            from launcher.instances import display_version_name

            self.version_combo.setEditText(display_version_name(version_id))

    def _game_dir(self) -> Path:
        cfg, _ = config.load()
        env_value = os.environ.get(paths.ENV_GAME_DIR)
        return (
            cfg.game_dir
            or (Path(env_value).expanduser() if env_value else None)
            or paths.default_game_dir()
        )

    def _populate_versions(self) -> None:
        """Version dropdown lists only installed versions/profiles (kept editable so an uninstalled id can be typed manually)."""
        from launcher.install import list_installed_versions
        from launcher.instances import display_version_name

        installed = sorted(list_installed_versions(self._game_dir()))
        current_id = self.version_combo.currentData() or self.version_combo.currentText().strip()
        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        for version_id in installed:
            self.version_combo.addItem(display_version_name(version_id), version_id)
        if current_id and current_id in installed:
            self.version_combo.setCurrentIndex(self.version_combo.findData(current_id))
        elif installed:
            self.version_combo.setCurrentIndex(0)
        self.version_combo.blockSignals(False)

    def refresh_versions(self) -> None:
        """Refresh the dropdown after the versions page installs/uninstalls."""
        self._populate_versions()

    def launch(self) -> None:
        version_id = (self.version_combo.currentData() or self.version_combo.currentText()).strip()
        if not version_id:
            self.status.setText(tr("launch.msg.need_id"))
            return
        cfg, cfg_path = config.load()
        env_value = os.environ.get(paths.ENV_GAME_DIR)
        game_dir = (
            cfg.game_dir
            or (Path(env_value).expanduser() if env_value else None)
            or paths.default_game_dir()
        )
        # Custom JVM args: save to config so they are prefilled next time (demo mode / auto-hide on the settings page)
        jvm_args = self.jvm_args_edit.text().strip() or None
        if (cfg.jvm_args or "") != (jvm_args or ""):
            cfg.jvm_args = jvm_args or ""
            config.save(cfg, cfg_path)
        self.launch_button.setEnabled(False)
        self.status.setText(tr("launch.msg.preparing", version_id))
        offline_name = self.offline_edit.text().strip() or None
        # Offline-mode gate: explicit offline launch or the no-account fallback both require unlock
        if (offline_name or not cfg.selected_account):
            from launcher.config import offline_mode_allowed

            if not offline_mode_allowed():
                self.launch_button.setEnabled(True)
                self.status.setText(tr("launch.msg.offline_locked"))
                return
        language = self.language_combo.currentData()
        server = self.server_edit.text().strip() or None
        server_port = self.server_port_spin.value() or None
        # Auto memory: size the heap from mod count and available RAM at launch time
        memory_gb = self.memory_spin.value()
        if cfg.memory_auto:
            from launcher.memory import count_mods, suggest_memory_gb, system_memory_gb

            mods_dir = game_dir / "mods"
            memory_gb = suggest_memory_gb(count_mods(mods_dir))
            _total, avail = system_memory_gb()
            if avail < memory_gb + 2:
                self.status.setText(tr("launch.msg.low_ram", f"{avail:.1f}", f"{memory_gb:.1f}"))
            else:
                self.status.setText(tr("launch.msg.auto_memory", f"{memory_gb:.1f}"))

        def do_prepare() -> object:
            try:
                account = resolve_launch_account(
                    AccountStore(), cfg.selected_account, offline_name
                )
                prepared = prepare_launch(
                    version_id,
                    game_dir=game_dir,
                    cache_dir=paths.launcher_dir() / "cache",
                    account=account,
                    memory_gb=memory_gb,
                    demo=cfg.demo_mode,
                    isolated=cfg.version_isolation,
                    language=language,
                    jvm_args=jvm_args,
                    server=server,
                    server_port=server_port,
                )
                return ("ok", prepared)
            except JavaMissingError as exc:
                return ("java", exc.required_major)

        run_in_background(
            do_prepare,
            on_result=self._on_prepared,
            on_error=self._on_launch_error,
            on_finished=lambda: self.launch_button.setEnabled(True),
        )

    def _confirm_java_download(self, major: int) -> bool:
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            "Java",
            tr("launch.msg.java_need", major),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _download_java_then_retry(self, major: int) -> None:
        from gui.workers import ProgressBridge
        from launcher.java import install_java

        self.status.setText(tr("launch.msg.java_downloading", major))
        bridge = ProgressBridge()
        bridge.progress.connect(
            lambda p: self.status.setText(
                "Java: " + str(p.done_files) + "/" + str(p.total_files) + " " + p.current
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
            on_result=lambda _r: self.launch(),
            on_error=lambda m: self.status.setText(tr("launch.msg.java_fail", m)),
        )

    def _on_prepared(self, result) -> None:
        kind, payload = result
        if kind == "java":
            major = payload
            if self._confirm_java_download(major):
                self._download_java_then_retry(major)
            else:
                self.status.setText(tr("launch.msg.cancelled", major))
            return
        prepared = payload
        command = prepared.command
        self.status.setText(
            tr(
                "launch.msg.running",
                prepared.version.id,
                prepared.java.major,
                prepared.account.username,
                tr("common.on") if prepared.isolated else tr("common.off"),
            )
        )
        self._log_path = command.cwd / "logs" / "latest.log"
        self._log_pos = 0

        # After-launch behavior (keep / hide / exit) is handled via a signal
        # bridge back to the main thread once the game process starts.
        from gui.workers import ProgressBridge

        cfg2, _ = config.load()
        start_bridge = ProgressBridge()
        if cfg2.after_launch_behavior != "keep":
            start_bridge.progress.connect(self._on_game_started)

        def do_run() -> object:
            started = __import__("time").time()
            code = run_process(
                command.argv,
                command.cwd,
                on_started=start_bridge if cfg2.after_launch_behavior != "keep" else None,
            )
            crashes = find_new_crash_reports(command.cwd, started)
            return code, crashes

        run_in_background(
            do_run,
            on_result=self._on_game_exit,
            on_error=lambda m: (
                self.status.setText(tr("launch.msg.run_error", m)),
                show_fatal(self, tr("launch.msg.run_error", m)),
            ),
        )
        self._log_timer.start()

    def _on_game_started(self, _value=None) -> None:
        from PySide6.QtWidgets import QApplication

        cfg, _ = config.load()
        if cfg.trim_memory_on_launch:
            from launcher.launch.memory import trim_working_set

            trim_working_set()
        self.status.setText(tr("launch.msg.auto_closing"))
        if cfg.after_launch_behavior == "keep":
            return
        if cfg.after_launch_behavior == "hide":
            # Hide the window but keep the launcher running in the background.
            self.window().hide()
            return
        # Exit: hide first so no stale window remains while the app quits.
        self.window().hide()
        QTimer.singleShot(600, QApplication.instance().quit)

    def _on_game_exit(self, result) -> None:
        self._log_timer.stop()
        self._tail_log()
        code, crashes = result
        message = tr("launch.msg.exit", code)
        if crashes:
            message += tr("launch.msg.crash", len(crashes))
        self.status.setText(message)

    def _on_launch_error(self, message: str) -> None:
        text = tr("launch.msg.fail", message)
        self.status.setText(text)
        show_fatal(self, text)  # fatal error dialog

    def _tail_log(self) -> None:
        if self._log_path is None or not self._log_path.exists():
            return
        try:
            text = self._log_path.read_text(encoding="utf-8", errors="replace")
            if len(text) > self._log_pos:
                new_text = text[self._log_pos :]
                self._log_pos = len(text)
                if new_text.strip():
                    self.log_view.appendPlainText(new_text.rstrip())
        except OSError:
            return
