"""启动页：选择版本/账号/内存/语言，启动游戏并跟踪日志。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.errors import show_fatal
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
from launcher.meta import fetch_manifest

tr = i18n.tr


class LaunchPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.version_combo = QComboBox()
        self.version_combo.setEditable(True)
        self.account_label = QLabel()
        self.account_label.setObjectName("hint")
        self.offline_edit = QLineEdit()
        self.offline_edit.setPlaceholderText(tr("launch.offline.placeholder"))
        self.memory_spin = QDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setSuffix(" GB")
        self.language_combo = QComboBox()
        for code, label in config.GAME_LANGUAGES:
            self.language_combo.addItem(label, code)
        self.demo_check = QCheckBox(tr("launch.demo"))
        self.jvm_args_edit = QLineEdit()
        self.jvm_args_edit.setPlaceholderText(tr("launch.jvm_args.placeholder"))
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText(tr("launch.server.placeholder"))
        self.server_port_spin = QSpinBox()
        self.server_port_spin.setRange(0, 65535)
        self.server_port_spin.setSpecialValueText(tr("common.off"))
        self.auto_close_check = QCheckBox(tr("launch.auto_close"))
        self.launch_button = QPushButton(tr("launch.button"))
        self.status = QLabel(tr("status.ready"))
        self.status.setObjectName("hint")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)

        form = QFormLayout()
        form.addRow(tr("launch.version"), self.version_combo)
        form.addRow(tr("launch.account"), self.account_label)
        form.addRow(tr("launch.offline"), self.offline_edit)
        form.addRow(tr("launch.memory"), self.memory_spin)
        form.addRow(tr("launch.language"), self.language_combo)
        form.addRow(tr("launch.jvm_args"), self.jvm_args_edit)
        server_row = QHBoxLayout()
        server_row.addWidget(self.server_edit, 1)
        server_row.addWidget(QLabel(tr("launch.port")))
        server_row.addWidget(self.server_port_spin)
        form.addRow(tr("launch.server"), server_row)
        form.addRow("", self.demo_check)
        form.addRow("", self.auto_close_check)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.launch_button)
        layout.addWidget(self.status)
        layout.addWidget(QLabel(tr("launch.log.label")))
        layout.addWidget(self.log_view, 1)

        self.launch_button.clicked.connect(self.launch)

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
        self.auto_close_check.setChecked(cfg.auto_close_on_launch)

    def refresh_account(self) -> None:
        cfg, _ = config.load()
        accounts = AccountStore().load()
        account = accounts.get(cfg.selected_account) if cfg.selected_account else None
        if account is None:
            self.account_label.setText(tr("launch.account.none"))
        else:
            self.account_label.setText(tr("launch.account.current", account.username))

    def set_version_id(self, version_id: str) -> None:
        self.version_combo.setEditText(version_id)

    def _populate_versions(self) -> None:
        cache = paths.launcher_dir() / "cache" / "version_manifest.json"

        def do_fetch() -> object:
            return fetch_manifest(cache_path=cache)

        run_in_background(
            do_fetch,
            on_result=self._fill_versions,
            on_error=lambda _m: None,
        )

    def _fill_versions(self, manifest) -> None:
        current = self.version_combo.currentText()
        self.version_combo.clear()
        for v in manifest.versions:
            if v.type in ("release", "snapshot"):
                self.version_combo.addItem(v.id)
        if current:
            self.version_combo.setEditText(current)

    def launch(self) -> None:
        version_id = self.version_combo.currentText().strip()
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
        # 自定义 JVM 参数/自动关闭：写入配置以便下次预填
        jvm_args = self.jvm_args_edit.text().strip() or None
        auto_close = self.auto_close_check.isChecked()
        changed = (cfg.jvm_args or "") != (jvm_args or "") or cfg.auto_close_on_launch != auto_close
        if changed:
            cfg.jvm_args = jvm_args or ""
            cfg.auto_close_on_launch = auto_close
            config.save(cfg, cfg_path)
        self.launch_button.setEnabled(False)
        self.status.setText(tr("launch.msg.preparing", version_id))
        offline_name = self.offline_edit.text().strip() or None
        # 离线模式门槛：显式离线启动或无账号回退都需解锁
        if (offline_name or not cfg.selected_account):
            from launcher.config import offline_mode_allowed

            if not offline_mode_allowed():
                self.launch_button.setEnabled(True)
                self.status.setText(tr("launch.msg.offline_locked"))
                return
        language = self.language_combo.currentData()
        server = self.server_edit.text().strip() or None
        server_port = self.server_port_spin.value() or None

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
                    memory_gb=self.memory_spin.value(),
                    demo=self.demo_check.isChecked(),
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

        # #14 启动成功后自动隐藏：进程启动时经信号桥回到主线程退出
        from gui.workers import ProgressBridge

        start_bridge = ProgressBridge()
        if self.auto_close_check.isChecked():
            start_bridge.progress.connect(self._on_game_started)

        def do_run() -> object:
            started = __import__("time").time()
            code = run_process(
                command.argv,
                command.cwd,
                on_started=start_bridge if self.auto_close_check.isChecked() else None,
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

        self.status.setText(tr("launch.msg.auto_closing"))
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
        show_fatal(self, text)  # #31 致命错误弹窗

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
