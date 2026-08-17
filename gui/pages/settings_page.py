"""Settings page: game directory, Java, memory, concurrency, version isolation, game language, launcher language."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.widgets import NoWheelDoubleSpinBox, NoWheelSpinBox
from launcher import config, paths

tr = i18n.tr


class SettingsPage(QWidget):
    settings_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.game_dir_edit = QLineEdit()
        self.browse_game = QPushButton(tr("settings.browse"))
        self.java_path_edit = QLineEdit()
        self.browse_java = QPushButton(tr("settings.browse"))
        self.memory_spin = NoWheelDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setSuffix(" GB")
        self.memory_auto_check = QCheckBox(tr("settings.memory_auto"))
        self.memory_auto_check.toggled.connect(self._on_memory_auto_toggled)
        self.memory_suggest_label = QLabel("")
        self.memory_suggest_label.setObjectName("hint")
        self.concurrency_spin = NoWheelSpinBox()
        self.concurrency_spin.setRange(1, 32)
        self.isolation_check = QCheckBox(tr("settings.isolation"))
        self.demo_check = QCheckBox(tr("launch.demo"))
        self.after_launch_combo = QComboBox()
        for code, label in (
            ("keep", tr("settings.after_launch.keep")),
            ("hide", tr("settings.after_launch.hide")),
            ("exit", tr("settings.after_launch.exit")),
        ):
            self.after_launch_combo.addItem(label, code)
        self.trim_memory_check = QCheckBox(tr("settings.trim_memory"))
        self.encrypt_check = QCheckBox(tr("settings.encrypt_tokens"))
        self.encrypt_button = QPushButton(tr("settings.encrypt_set"))
        self.language_combo = QComboBox()
        for code, label in config.GAME_LANGUAGES:
            self.language_combo.addItem(label, code)
        self.ui_language_combo = QComboBox()
        for code, label in i18n.UI_LANGUAGES:
            self.ui_language_combo.addItem(label, code)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText(tr("settings.proxy.placeholder"))
        self.cf_key_edit = QLineEdit()
        self.cf_key_edit.setPlaceholderText(tr("settings.cf_key.hint"))
        self.cf_key_edit.setClearButtonEnabled(True)
        self.speed_limit_spin = NoWheelSpinBox()
        self.speed_limit_spin.setRange(0, 1_048_576)
        self.speed_limit_spin.setSingleStep(100)
        self.speed_limit_spin.setSuffix(" KB/s")
        self.speed_limit_spin.setSpecialValueText(tr("common.off"))
        self.window_mode_combo = QComboBox()
        for code, label in (
            ("default", tr("settings.window_mode.default")),
            ("maximized", tr("settings.window_mode.maximized")),
            ("minimized", tr("settings.window_mode.minimized")),
            ("remember", tr("settings.window_mode.remember")),
        ):
            self.window_mode_combo.addItem(label, code)
        self.theme_combo = QComboBox()
        for code, label in (
            ("dark", tr("settings.theme.dark")),
            ("light", tr("settings.theme.light")),
        ):
            self.theme_combo.addItem(label, code)
        self.save_button = QPushButton(tr("settings.save"))
        self.open_data_dir_button = QPushButton(tr("settings.open_data_dir"))
        self.status = QLabel("")
        self.status.setObjectName("hint")

        form = QFormLayout()
        game_row = QHBoxLayout()
        game_row.addWidget(self.game_dir_edit, 1)
        game_row.addWidget(self.browse_game)
        java_row = QHBoxLayout()
        java_row.addWidget(self.java_path_edit, 1)
        java_row.addWidget(self.browse_java)
        form.addRow(tr("settings.game_dir"), game_row)
        form.addRow(tr("settings.java"), java_row)
        form.addRow(tr("settings.memory"), self.memory_spin)
        form.addRow("", self.memory_auto_check)
        form.addRow("", self.memory_suggest_label)
        form.addRow(tr("settings.concurrency"), self.concurrency_spin)
        form.addRow(tr("settings.speed_limit"), self.speed_limit_spin)
        form.addRow(tr("settings.proxy"), self.proxy_edit)
        form.addRow(tr("settings.cf_key"), self.cf_key_edit)
        form.addRow(tr("settings.window_mode"), self.window_mode_combo)
        form.addRow(tr("settings.theme"), self.theme_combo)
        form.addRow(tr("settings.game_language"), self.language_combo)
        form.addRow(tr("settings.ui_language"), self.ui_language_combo)
        form.addRow(tr("settings.after_launch"), self.after_launch_combo)

        encrypt_row = QHBoxLayout()
        encrypt_row.addWidget(self.encrypt_check, 1)
        encrypt_row.addWidget(self.encrypt_button)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.save_button)
        buttons_row.addWidget(self.open_data_dir_button)
        buttons_row.addStretch(1)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.addLayout(form)
        layout.addWidget(self.isolation_check)
        layout.addWidget(self.demo_check)
        layout.addWidget(self.trim_memory_check)
        layout.addLayout(encrypt_row)
        layout.addLayout(buttons_row)
        layout.addWidget(self.status)
        layout.addStretch(1)

        # Wrap the form in a scroll area so the main window can stay compact
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)

        self.browse_game.clicked.connect(self._browse_game)
        self.browse_java.clicked.connect(self._browse_java)
        self.save_button.clicked.connect(self.save)
        self.encrypt_button.clicked.connect(self._change_password)
        self.open_data_dir_button.clicked.connect(self._open_data_dir)
        self.load()

    def load(self) -> None:
        cfg, _ = config.load()
        self.game_dir_edit.setText(str(cfg.game_dir) if cfg.game_dir else "")
        self.java_path_edit.setText(str(cfg.java_path) if cfg.java_path else "")
        self.memory_spin.setValue(cfg.memory_gb)
        self.memory_auto_check.setChecked(cfg.memory_auto)
        self._refresh_memory_suggestion()
        self.concurrency_spin.setValue(cfg.max_concurrent_downloads)
        self.isolation_check.setChecked(cfg.version_isolation)
        self.demo_check.setChecked(cfg.demo_mode)
        idx = self.after_launch_combo.findData(cfg.after_launch_behavior)
        self.after_launch_combo.setCurrentIndex(max(idx, 0))
        self.trim_memory_check.setChecked(cfg.trim_memory_on_launch)
        self.encrypt_check.setChecked(cfg.token_encryption)
        self._update_encrypt_button()
        index = self.language_combo.findData(cfg.game_language)
        self.language_combo.setCurrentIndex(max(index, 0))
        index2 = self.ui_language_combo.findData(cfg.ui_language)
        self.ui_language_combo.setCurrentIndex(max(index2, 0))
        self.speed_limit_spin.setValue(cfg.download_speed_limit_kb)
        index3 = self.window_mode_combo.findData(cfg.window_start_mode)
        self.window_mode_combo.setCurrentIndex(max(index3, 0))
        index4 = self.theme_combo.findData(cfg.theme)
        self.theme_combo.setCurrentIndex(max(index4, 0))
        self.proxy_edit.setText(cfg.http_proxy or "")
        self.cf_key_edit.setText(cfg.curseforge_api_key or "")

    def save(self) -> None:
        cfg, cfg_path = config.load()
        want_encryption = self.encrypt_check.isChecked()
        if want_encryption and not cfg.token_encryption:
            if not self._enable_encryption(cfg, cfg_path):
                self.encrypt_check.setChecked(False)  # revert the checked state
                return
            cfg, cfg_path = config.load()
        elif not want_encryption and cfg.token_encryption:
            if not self._disable_encryption(cfg, cfg_path):
                self.encrypt_check.setChecked(True)  # keep it enabled
                return
            cfg, cfg_path = config.load()
        cfg.game_dir = self.game_dir_edit.text().strip() or None
        cfg.java_path = self.java_path_edit.text().strip() or None
        cfg.memory_gb = self.memory_spin.value()
        cfg.memory_auto = self.memory_auto_check.isChecked()
        cfg.max_concurrent_downloads = self.concurrency_spin.value()
        cfg.version_isolation = self.isolation_check.isChecked()
        cfg.demo_mode = self.demo_check.isChecked()
        cfg.after_launch_behavior = self.after_launch_combo.currentData() or "keep"
        cfg.trim_memory_on_launch = self.trim_memory_check.isChecked()
        cfg.game_language = self.language_combo.currentData()
        cfg.ui_language = self.ui_language_combo.currentData()
        cfg.download_speed_limit_kb = self.speed_limit_spin.value()
        cfg.http_proxy = self.proxy_edit.text().strip()
        cfg.curseforge_api_key = self.cf_key_edit.text().strip()
        cfg.window_start_mode = self.window_mode_combo.currentData()
        cfg.theme = self.theme_combo.currentData()
        config.save(cfg, cfg_path)
        # Theme takes effect immediately
        from gui.theme import apply_theme

        apply_theme(cfg.theme)
        # Proxy / CurseForge key changes need a fresh HTTP connection pool
        from launcher.meta.manifest import reset_http_client

        reset_http_client()
        self._update_encrypt_button()
        self.status.setText(tr("settings.saved", str(cfg_path)))
        self.settings_changed.emit()

    def _on_memory_auto_toggled(self, checked: bool) -> None:
        self.memory_spin.setEnabled(not checked)
        if checked:
            self._refresh_memory_suggestion()

    def _refresh_memory_suggestion(self) -> None:
        """Show the suggested heap size for the current game directory."""
        try:
            from launcher.memory import count_mods, suggest_memory_gb

            cfg, _ = config.load()
            game_dir = cfg.game_dir or paths.default_game_dir()
            mod_count = count_mods(game_dir / "mods")
            suggestion = suggest_memory_gb(mod_count)
            self.memory_suggest_label.setText(tr("settings.memory_suggest", f"{suggestion:.1f}"))
        except OSError:  # probe failures are non-fatal
            self.memory_suggest_label.setText("")

    def _update_encrypt_button(self) -> None:
        cfg, _ = config.load()
        if cfg.token_encryption:
            self.encrypt_button.setText(tr("settings.encrypt_change"))
        else:
            self.encrypt_button.setText(tr("settings.encrypt_set"))

    def _prompt_new_password(self) -> str | None:
        from PySide6.QtWidgets import QInputDialog, QLineEdit

        first, ok = QInputDialog.getText(
            self,
            tr("settings.encrypt_set"),
            tr("settings.encrypt.password.prompt"),
            QLineEdit.EchoMode.Password,
        )
        if not ok or not first:
            return None
        second, ok2 = QInputDialog.getText(
            self,
            tr("settings.encrypt_set"),
            tr("settings.encrypt.password.confirm"),
            QLineEdit.EchoMode.Password,
        )
        if not ok2 or first != second:
            self.status.setText(tr("settings.encrypt.password.mismatch"))
            return None
        return first

    def _prompt_current_password(self) -> str | None:
        from PySide6.QtWidgets import QInputDialog, QLineEdit

        text, ok = QInputDialog.getText(
            self,
            tr("settings.encrypt_change"),
            tr("settings.encrypt.current.prompt"),
            QLineEdit.EchoMode.Password,
        )
        if not ok or not text:
            return None
        return text

    def _enable_encryption(self, cfg, cfg_path) -> bool:
        from launcher.auth import AccountStore, secure

        password = self._prompt_new_password()
        if password is None:
            return False
        try:
            secure.create_vault(password)
            cfg.token_encryption = True
            config.save(cfg, cfg_path)
            store = AccountStore()
            store.save(store.load())  # re-save as ciphertext with the new password
        except Exception as exc:  # noqa: BLE001 - funnel uniformly to UI status
            self.status.setText(tr("settings.encrypt.msg.failed", str(exc)))
            return False
        self.status.setText(tr("settings.encrypt.msg.enabled"))
        return True

    def _disable_encryption(self, cfg, cfg_path) -> bool:
        from launcher.auth import AccountStore, secure

        password = self._prompt_current_password()
        if password is None:
            return False
        if not secure.verify_password(password):
            self.status.setText(tr("settings.encrypt.wrong"))
            return False
        secure.set_password(password)
        store = AccountStore()
        try:
            accounts = store.load()
        except Exception as exc:  # noqa: BLE001
            secure.forget_password()
            self.status.setText(tr("settings.encrypt.msg.failed", str(exc)))
            return False
        cfg.token_encryption = False
        config.save(cfg, cfg_path)
        store.save(accounts)  # plaintext
        (paths.launcher_dir() / secure.VAULT_FILENAME).unlink(missing_ok=True)
        secure.forget_password()
        self.status.setText(tr("settings.encrypt.msg.disabled"))
        return True

    def _change_password(self) -> None:
        cfg, cfg_path = config.load()
        if not cfg.token_encryption:
            self._enable_encryption(cfg, cfg_path)
            if cfg.token_encryption:
                self.encrypt_check.setChecked(True)
                self._update_encrypt_button()
            return
        from launcher.auth import AccountStore, secure

        current = self._prompt_current_password()
        if current is None:
            return
        if not secure.verify_password(current):
            self.status.setText(tr("settings.encrypt.wrong"))
            return
        new_password = self._prompt_new_password()
        if new_password is None:
            return
        secure.set_password(current)
        store = AccountStore()
        try:
            accounts = store.load()
            secure.create_vault(new_password)
            store.save(accounts)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(tr("settings.encrypt.msg.failed", str(exc)))
            return
        self.status.setText(tr("settings.encrypt.msg.changed"))

    def _open_data_dir(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        target = paths.launcher_dir()
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        self.status.setText(tr("settings.msg.data_dir_opened", str(target)))

    def _browse_game(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, tr("settings.game_dir"), str(paths.default_game_dir()))
        if chosen:
            self.game_dir_edit.setText(chosen)

    def _browse_java(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Java")
        if chosen:
            self.java_path_edit.setText(chosen)
