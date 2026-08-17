"""设置页：游戏目录、Java、内存、并发、版本隔离、游戏语言、启动器语言。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
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
        self.memory_spin = QDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setSuffix(" GB")
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 32)
        self.isolation_check = QCheckBox(tr("settings.isolation"))
        self.demo_check = QCheckBox(tr("launch.demo"))
        self.auto_close_check = QCheckBox(tr("launch.auto_close"))
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
        self.speed_limit_spin = QSpinBox()
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
        form.addRow(tr("settings.concurrency"), self.concurrency_spin)
        form.addRow(tr("settings.speed_limit"), self.speed_limit_spin)
        form.addRow(tr("settings.proxy"), self.proxy_edit)
        form.addRow(tr("settings.cf_key"), self.cf_key_edit)
        form.addRow(tr("settings.window_mode"), self.window_mode_combo)
        form.addRow(tr("settings.theme"), self.theme_combo)
        form.addRow(tr("settings.game_language"), self.language_combo)
        form.addRow(tr("settings.ui_language"), self.ui_language_combo)

        encrypt_row = QHBoxLayout()
        encrypt_row.addWidget(self.encrypt_check, 1)
        encrypt_row.addWidget(self.encrypt_button)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.save_button)
        buttons_row.addWidget(self.open_data_dir_button)
        buttons_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.isolation_check)
        layout.addWidget(self.demo_check)
        layout.addWidget(self.auto_close_check)
        layout.addLayout(encrypt_row)
        layout.addLayout(buttons_row)
        layout.addWidget(self.status)
        layout.addStretch(1)

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
        self.concurrency_spin.setValue(cfg.max_concurrent_downloads)
        self.isolation_check.setChecked(cfg.version_isolation)
        self.demo_check.setChecked(cfg.demo_mode)
        self.auto_close_check.setChecked(cfg.auto_close_on_launch)
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
                self.encrypt_check.setChecked(False)  # 回退勾选状态
                return
            cfg, cfg_path = config.load()
        elif not want_encryption and cfg.token_encryption:
            if not self._disable_encryption(cfg, cfg_path):
                self.encrypt_check.setChecked(True)  # 保持开启
                return
            cfg, cfg_path = config.load()
        cfg.game_dir = self.game_dir_edit.text().strip() or None
        cfg.java_path = self.java_path_edit.text().strip() or None
        cfg.memory_gb = self.memory_spin.value()
        cfg.max_concurrent_downloads = self.concurrency_spin.value()
        cfg.version_isolation = self.isolation_check.isChecked()
        cfg.demo_mode = self.demo_check.isChecked()
        cfg.auto_close_on_launch = self.auto_close_check.isChecked()
        cfg.game_language = self.language_combo.currentData()
        cfg.ui_language = self.ui_language_combo.currentData()
        cfg.download_speed_limit_kb = self.speed_limit_spin.value()
        cfg.http_proxy = self.proxy_edit.text().strip()
        cfg.curseforge_api_key = self.cf_key_edit.text().strip()
        cfg.window_start_mode = self.window_mode_combo.currentData()
        cfg.theme = self.theme_combo.currentData()
        config.save(cfg, cfg_path)
        # 主题立即生效（#30）
        from gui.theme import apply_theme

        apply_theme(cfg.theme)
        self._update_encrypt_button()
        self.status.setText(tr("settings.saved", str(cfg_path)))
        self.settings_changed.emit()

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
            store.save(store.load())  # 用新密码重存为密文
        except Exception as exc:  # noqa: BLE001 - 统一转 UI 状态
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
        store.save(accounts)  # 明文
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
