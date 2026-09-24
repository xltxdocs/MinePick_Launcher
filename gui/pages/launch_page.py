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

"""Launch page: choose version/account/memory/language and launch the game."""

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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui import i18n, icons
from gui.errors import show_fatal
from gui.widgets import (
    NoWheelDoubleSpinBox,
    build_page_header,
    disable_keeping_focus,
    set_app_status,
    style_form,
    style_page_layout,
)
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
    instance_requested = Signal(str)  # show this profile on the instances page
    instance_settings_requested = Signal(str)  # ... and open its per-instance settings
    account_requested = Signal()  # the account button jumps to the account page

    def __init__(self) -> None:
        super().__init__()
        self.version_combo = QComboBox()
        self.version_combo.setEditable(True)
        # Accounts are picked on the account page: an icon-only button jumps there, and the label
        # next to it says which account is active.
        self.account_label = QLabel("")
        self.account_label.setObjectName("hint")
        self.account_button = QPushButton()
        self.account_button.setObjectName("iconButton")
        self.account_button.setIcon(icons.icon("switch"))
        self.account_button.setToolTip(tr("launch.account.switch"))
        self.account_button.setFixedWidth(46)
        self.memory_spin = NoWheelDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setSuffix(" " + tr("unit.gb"))
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText(tr("launch.server.placeholder"))
        self.launch_button = QPushButton(tr("launch.button"))
        self.select_instance_button = QPushButton(tr("launch.instances.select"))
        self.select_instance_button.setObjectName("secondaryButton")
        self.select_instance_button.setIcon(icons.icon("instances"))
        self.instance_settings_button = QPushButton(tr("launch.instances.settings"))
        self.instance_settings_button.setObjectName("secondaryButton")
        self.instance_settings_button.setIcon(icons.icon("settings"))

        # Only what a normal launch needs: version, account, memory and (optionally) a server to
        # join. The offline user name, the game language, custom JVM arguments and the server port
        # used to sit here too, but almost nobody touched them: the language and the JVM arguments
        # are launcher settings, an offline name falls back to "Player", and the port defaults to
        # 25565. They all still work - just not as clutter on the main page.
        account_row = QHBoxLayout()
        account_row.setContentsMargins(0, 0, 0, 0)
        account_row.setSpacing(6)
        account_row.addWidget(self.account_label, 1)
        account_row.addWidget(self.account_button)

        form = QFormLayout()
        style_form(form)
        form.addRow(tr("launch.version"), self.version_combo)
        form.addRow(tr("launch.account"), account_row)
        form.addRow(tr("launch.memory"), self.memory_spin)
        form.addRow(tr("launch.server"), self.server_edit)

        instance_actions = QHBoxLayout()
        instance_actions.setContentsMargins(0, 0, 0, 0)
        instance_actions.setSpacing(6)
        instance_actions.addWidget(self.select_instance_button)
        instance_actions.addWidget(self.instance_settings_button)
        instance_actions.addStretch(1)

        layout = QVBoxLayout(self)
        style_page_layout(layout)
        layout.addWidget(build_page_header(tr("nav.launch"), tr("page.launch.desc")))
        layout.addLayout(form)
        layout.addWidget(self.launch_button)
        layout.addLayout(instance_actions)
        layout.addStretch(1)

        self.launch_button.clicked.connect(self.launch)
        self.account_button.clicked.connect(self.account_requested.emit)
        self.select_instance_button.clicked.connect(self._request_instance)
        self.instance_settings_button.clicked.connect(self._request_instance_settings)

        self.refresh_config()
        self.refresh_account()
        self._populate_versions()

    def refresh_config(self) -> None:
        cfg, _ = config.load()
        self.memory_spin.setValue(cfg.memory_gb)

    def refresh_account(self) -> None:
        """Show the selected account; switching happens on the account page (one click away)."""
        cfg, _ = config.load()
        accounts = AccountStore().load()
        account = accounts.get(cfg.selected_account) if cfg.selected_account else None
        if account is None:
            self.account_label.setText(tr("launch.account.none.item"))
            return
        kind = tr("kind.ms") if account.type == "microsoft" else tr("kind.offline")
        self.account_label.setText(tr("launch.account.label", account.username, kind))

    def _current_version_id(self) -> str:
        """The profile id behind the version dropdown (it shows display names, stores ids)."""
        return str(self.version_combo.currentData() or self.version_combo.currentText().strip())

    def _request_instance(self) -> None:
        """Jump to the instances page showing the selected profile."""
        version_id = self._current_version_id()
        if not version_id:
            set_app_status(self, tr("launch.msg.need_id"), "warning")
            return
        self.instance_requested.emit(version_id)

    def _request_instance_settings(self) -> None:
        """Jump to the selected profile's per-instance settings."""
        version_id = self._current_version_id()
        if not version_id:
            set_app_status(self, tr("launch.msg.need_id"), "warning")
            return
        self.instance_settings_requested.emit(version_id)

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
            set_app_status(self, tr("launch.msg.need_id"))
            return
        cfg, _ = config.load()
        env_value = os.environ.get(paths.ENV_GAME_DIR)
        game_dir = (
            cfg.game_dir
            or (Path(env_value).expanduser() if env_value else None)
            or paths.default_game_dir()
        )
        disable_keeping_focus(self.launch_button)
        set_app_status(self, tr("launch.msg.preparing", version_id))
        # Offline-mode gate: the no-account fallback still requires the offline unlock
        if not cfg.selected_account:
            from launcher.config import offline_mode_allowed

            if not offline_mode_allowed():
                self.launch_button.setEnabled(True)
                set_app_status(self, tr("launch.msg.offline_locked"), "warning")
                return
        server = self.server_edit.text().strip() or None
        # Auto memory: size the heap from mod count and available RAM at launch time
        memory_gb = self.memory_spin.value()
        if cfg.memory_auto:
            from launcher.memory import count_mods, suggest_memory_gb, system_memory_gb

            mods_dir = game_dir / "mods"
            memory_gb = suggest_memory_gb(count_mods(mods_dir))
            _total, avail = system_memory_gb()
            if avail < memory_gb + 2:
                set_app_status(
                    self, tr("launch.msg.low_ram", f"{avail:.1f}", f"{memory_gb:.1f}"), "warning"
                )
            else:
                set_app_status(self, tr("launch.msg.auto_memory", f"{memory_gb:.1f}"))

        def do_prepare() -> object:
            try:
                account = resolve_launch_account(
                    AccountStore(), cfg.selected_account, None
                )
                from launcher.instances import resolve_instance

                resolved = resolve_instance(version_id, cfg, game_dir)
                prepared = prepare_launch(
                    version_id,
                    game_dir=game_dir,
                    cache_dir=paths.launcher_dir() / "cache",
                    account=account,
                    memory_gb=resolved.memory_gb if resolved.memory_from_instance else memory_gb,
                    demo=cfg.demo_mode,
                    launch_dir=resolved.launch_dir,
                    java_path=resolved.java_path,
                    language=cfg.game_language or None,
                    jvm_args=resolved.jvm_args or (cfg.jvm_args or None),
                    game_args=resolved.game_args,
                    server=server,
                )
                return ("ok", prepared, resolved)
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

        set_app_status(self, tr("launch.msg.java_downloading", major))
        bridge = ProgressBridge()
        bridge.progress.connect(
            lambda p: set_app_status(
                self, "Java: " + str(p.done_files) + "/" + str(p.total_files) + " " + p.current
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
            on_error=lambda m: set_app_status(
                self, tr("launch.msg.java_fail", m), "error"
            ),
        )

    def _on_prepared(self, result) -> None:
        kind = result[0]
        if kind == "java":
            major = result[1]
            if self._confirm_java_download(major):
                self._download_java_then_retry(major)
            else:
                set_app_status(self, tr("launch.msg.cancelled", major))
            return
        _kind, prepared, resolved = result
        command = prepared.command
        self._last_launch = (prepared, resolved)  # the exit callback needs it for the diagnosis
        set_app_status(
            self,
            tr(
                "launch.msg.running",
                prepared.version.id,
                prepared.java.major,
                prepared.account.username,
                tr("common.on") if prepared.isolated else tr("common.off"),
            )
        )

        # After-launch behavior (keep / hide / exit) is handled via a signal
        # bridge back to the main thread once the game process starts.
        from gui.workers import ProgressBridge

        cfg2, _ = config.load()
        start_bridge = ProgressBridge()
        if cfg2.after_launch_behavior != "keep":
            start_bridge.progress.connect(self._on_game_started)

        def do_run() -> object:
            started = __import__("time").time()
            run = run_process(
                command.argv,
                command.cwd,
                on_started=start_bridge if cfg2.after_launch_behavior != "keep" else None,
                capture_tail=True,  # the tail is the only trace when the game dies before logging
            )
            crashes = find_new_crash_reports(command.cwd, started)
            return run, crashes, started

        run_in_background(
            do_run,
            on_result=self._on_game_exit,
            on_error=lambda m: (
                set_app_status(self, tr("launch.msg.run_error", m), "error"),
                show_fatal(self, tr("launch.msg.run_error", m)),
            ),
        )

    def _on_game_started(self, _value=None) -> None:
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

    def _on_game_exit(self, result) -> None:
        run, crashes, started = result
        code = getattr(run, "exit_code", run)
        tail = list(getattr(run, "tail", ()) or ())
        message = tr("launch.msg.exit", code)
        if crashes:
            message += tr("launch.msg.crash", len(crashes))
        set_app_status(self, message)
        self._diagnose(code, tail, started)

    def _diagnose(self, code, tail, started) -> None:
        """Run the knowledge base for a finished launch and show the diagnosis overlay."""
        cfg, _ = config.load()
        if not cfg.auto_crash_analysis:
            return
        pending = getattr(self, "_last_launch", None)
        if pending is None:
            return
        prepared, resolved = pending
        from gui.dialogs.crash_dialog import context_for_launch, diagnose_after_exit

        context = context_for_launch(
            version_id=prepared.version.id,
            game_dir=resolved.game_dir,
            launch_dir=resolved.launch_dir,
            exit_code=code,
            started=started,
            tail=tail,
            instance=resolved,
        )
        diagnose_after_exit(
            self.window(), context, log_path=resolved.launch_dir / "logs" / "latest.log",
            blur=cfg.blur_dialogs,
        )

    def _on_launch_error(self, message: str) -> None:
        text = tr("launch.msg.fail", message)
        set_app_status(self, text, "error")
        show_fatal(self, text)  # fatal error dialog
        cfg, _ = config.load()
        if not cfg.auto_crash_analysis:
            return
        from gui.dialogs.crash_dialog import context_for_launch, diagnose_after_exit

        game_dir = cfg.game_dir or paths.default_game_dir()
        context = context_for_launch(
            version_id="", game_dir=game_dir, error_text=text, memory_gb=cfg.memory_gb
        )
        diagnose_after_exit(self.window(), context, blur=cfg.blur_dialogs)
