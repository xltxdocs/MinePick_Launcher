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

"""Settings page: game directory, Java, memory, concurrency, version isolation, game language, launcher language."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
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
from gui.theme import DEFAULT_ACCENTS, normalize_hex, resolve_theme
from gui.widgets import (
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
    StatusLabel,
    build_page_header,
    style_form,
    style_page_layout,
)
from launcher import config, paths

tr = i18n.tr

# One-click accent colours offered next to the hex field
ACCENT_PRESETS = ("#35a06a", "#3b82f6", "#a855f7", "#e0703a", "#e05a5a", "#14b8a6", "#ec4899", "#f59e0b")

# Pinned to the top of the font list when installed
COMMON_FONTS = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimSun",
    "SimHei",
    "DengXian",
    "Segoe UI",
    "Consolas",
    "Cascadia Mono",
)


class SettingsPage(QWidget):
    settings_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.game_dir_edit = QLineEdit()
        self.browse_game = QPushButton(tr("settings.browse"))
        self.browse_game.setObjectName("secondaryButton")
        self.java_path_edit = QLineEdit()
        self.browse_java = QPushButton(tr("settings.browse"))
        self.browse_java.setObjectName("secondaryButton")
        self.memory_spin = NoWheelDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setSuffix(" " + tr("unit.gb"))
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
        self.encrypt_button.setObjectName("secondaryButton")
        self.language_combo = QComboBox()
        for code, label in config.GAME_LANGUAGES:
            label = label if code else tr("settings.game_language.follow")
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
        self.speed_limit_spin.setSuffix(" " + tr("unit.kb_s"))
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
            ("system", tr("settings.theme.system")),
            ("dark", tr("settings.theme.dark")),
            ("light", tr("settings.theme.light")),
        ):
            self.theme_combo.addItem(label, code)
        self.radius_combo = QComboBox()
        for code, label in (
            ("compact", tr("settings.radius.compact")),
            ("default", tr("settings.radius.default")),
            ("round", tr("settings.radius.round")),
        ):
            self.radius_combo.addItem(label, code)
        self.open_data_dir_button = QPushButton(tr("settings.open_data_dir"))
        self.open_data_dir_button.setObjectName("secondaryButton")
        self.status = StatusLabel("")
        self.status.setObjectName("hint")

        # Accent color: free hex input with a live swatch and a reset-to-default button
        self.accent_edit = QLineEdit()
        self.accent_edit.setPlaceholderText(DEFAULT_ACCENTS["dark"])
        self.accent_edit.setMaxLength(7)
        self.accent_edit.setToolTip(tr("settings.accent.hint"))
        self.accent_swatch = QLabel()
        self.accent_swatch.setFixedSize(22, 22)
        self.accent_swatch.setObjectName("accentSwatch")
        self.accent_swatch.setToolTip(tr("settings.accent.hint"))
        self.accent_default_button = QPushButton(tr("settings.accent.default"))
        self.accent_default_button.setObjectName("secondaryButton")
        self.accent_default_button.clicked.connect(lambda: self.accent_edit.setText(""))
        self.accent_pick_button = QPushButton(tr("settings.accent.pick"))
        self.accent_pick_button.setObjectName("secondaryButton")
        self.accent_pick_button.clicked.connect(self._pick_accent_color)
        self.accent_preset_buttons = [
            self._make_preset_button(color) for color in ACCENT_PRESETS
        ]
        self.accent_edit.textChanged.connect(self._update_accent_swatch)

        # UI font: common families first, then every installed family; typing filters the list
        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.addItem(tr("settings.font.default"), "")
        families = QFontDatabase.families()
        common = [name for name in COMMON_FONTS if name in families]
        for family in common:
            self.font_combo.addItem(family, family)
        header_row = self.font_combo.count()  # remember where the section header lands
        self.font_combo.addItem(tr("settings.font.common"), "")
        for family in families:
            if family not in common:
                self.font_combo.addItem(family, family)
        header_item = self.font_combo.model().item(header_row)
        if header_item is not None:
            header_item.setEnabled(False)  # a header row, not a choice
        completer = QCompleter(families, self.font_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.font_combo.setCompleter(completer)
        self.font_combo.setToolTip(tr("settings.font"))

        form = QFormLayout()
        style_form(form)
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
        accent_row = QHBoxLayout()
        accent_row.addWidget(self.accent_edit, 1)
        accent_row.addWidget(self.accent_swatch)
        accent_row.addWidget(self.accent_pick_button)
        accent_row.addWidget(self.accent_default_button)
        form.addRow(tr("settings.accent"), accent_row)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for button in self.accent_preset_buttons:
            preset_row.addWidget(button)
        preset_row.addStretch(1)
        form.addRow("", preset_row)
        form.addRow(tr("settings.radius"), self.radius_combo)
        form.addRow(tr("settings.font"), self.font_combo)
        form.addRow(tr("settings.game_language"), self.language_combo)
        form.addRow(tr("settings.ui_language"), self.ui_language_combo)
        form.addRow(tr("settings.after_launch"), self.after_launch_combo)

        encrypt_row = QHBoxLayout()
        encrypt_row.addWidget(self.encrypt_check, 1)
        encrypt_row.addWidget(self.encrypt_button)

        buttons_row = QHBoxLayout()
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
        style_page_layout(outer)
        outer.addWidget(build_page_header(tr("nav.settings"), tr("page.settings.desc")))
        outer.addWidget(scroll)

        self.browse_game.clicked.connect(self._browse_game)
        self.browse_java.clicked.connect(self._browse_java)
        self.encrypt_button.clicked.connect(self._change_password)
        self.open_data_dir_button.clicked.connect(self._open_data_dir)
        self.theme_combo.currentIndexChanged.connect(self._update_accent_swatch)
        self.load()
        self._connect_autosave()

    def _connect_autosave(self) -> None:
        """There is no Save button: every control writes its value as soon as it changes.

        Connected after ``load()`` so filling the widgets from the config does not
        immediately write everything back.
        """

        def on_change(signal) -> None:
            signal.connect(lambda *_: self.save())

        for combo in (
            self.theme_combo,
            self.radius_combo,
            self.ui_language_combo,
            self.language_combo,
            self.after_launch_combo,
            self.window_mode_combo,
            self.font_combo,
        ):
            on_change(combo.currentIndexChanged)
        for check in (
            self.memory_auto_check,
            self.isolation_check,
            self.demo_check,
            self.trim_memory_check,
            self.encrypt_check,
        ):
            on_change(check.toggled)
        for spin in (self.memory_spin, self.concurrency_spin, self.speed_limit_spin):
            on_change(spin.valueChanged)
        for edit in (
            self.game_dir_edit,
            self.java_path_edit,
            self.proxy_edit,
            self.cf_key_edit,
            self.accent_edit,
        ):
            on_change(edit.editingFinished)
        font_line = self.font_combo.lineEdit()
        if font_line is not None:
            on_change(font_line.editingFinished)
        self.accent_default_button.clicked.connect(lambda *_: self.save())

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
        index5 = self.radius_combo.findData(cfg.ui_radius)
        self.radius_combo.setCurrentIndex(max(index5, 0))
        self.accent_edit.setText(cfg.accent_color or "")
        self._update_accent_swatch()
        font_index = self.font_combo.findData(cfg.ui_font or "")
        if font_index >= 0:
            self.font_combo.setCurrentIndex(font_index)
        elif cfg.ui_font:
            self.font_combo.setEditText(cfg.ui_font)
        self.proxy_edit.setText(cfg.http_proxy or "")
        self.cf_key_edit.setText(cfg.curseforge_api_key or "")

    def _make_preset_button(self, color: str) -> QPushButton:
        """One-click accent swatch."""
        button = QPushButton()
        button.setFixedSize(22, 22)
        button.setToolTip(color)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"background: {color}; border: 1px solid #3a4757; border-radius: 5px;"
        )
        button.clicked.connect(lambda *_, value=color: self._set_accent(value))
        return button

    def _set_accent(self, color: str) -> None:
        self.accent_edit.setText(color)
        self.save()

    def _pick_accent_color(self) -> None:
        """System colour picker for the accent."""
        from PySide6.QtGui import QColor

        current = QColor(normalize_hex(self.accent_edit.text()) or DEFAULT_ACCENTS["dark"])
        chosen = QColorDialog.getColor(current, self, tr("settings.accent"))
        if chosen.isValid():
            self._set_accent(chosen.name())

    def _update_accent_swatch(self) -> None:
        """Paint the swatch with the typed color, falling back to the theme default."""
        theme = resolve_theme(self.theme_combo.currentData() or "dark")
        fallback = DEFAULT_ACCENTS.get(theme, DEFAULT_ACCENTS["dark"])
        color = normalize_hex(self.accent_edit.text()) or fallback
        # only the fill is set here: the outline comes from the theme's QSS
        self.accent_swatch.setStyleSheet(f"background: {color};")

    def _selected_font(self) -> str:
        """Chosen font family: the picked list entry, or whatever the user typed."""
        index = self.font_combo.currentIndex()
        if index >= 0 and self.font_combo.currentText() == self.font_combo.itemText(index):
            return str(self.font_combo.itemData(index) or "")
        return self.font_combo.currentText().strip()

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
        cfg.ui_radius = self.radius_combo.currentData()
        accent_input = self.accent_edit.text().strip()
        accent = normalize_hex(accent_input)
        if accent_input and accent is None:
            self.accent_edit.setText("")  # invalid input: fall back to the theme default
        cfg.accent_color = accent or ""
        cfg.ui_font = self._selected_font()
        config.save(cfg, cfg_path)
        self._update_accent_swatch()
        # Theme, accent color and UI font take effect immediately
        from gui.theme import apply_theme

        apply_theme(cfg.theme, cfg.accent_color, cfg.ui_font, cfg.ui_radius)
        # Proxy / CurseForge key changes need a fresh HTTP connection pool
        from launcher.meta.manifest import reset_http_client

        reset_http_client()
        self._update_encrypt_button()
        self.status.setText(
            tr("settings.accent.invalid")
            if (accent_input and accent is None)
            else tr("settings.autosave")
        )
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
            self.status.set_error(tr("settings.encrypt.msg.failed", str(exc)))
            return False
        self.status.setText(tr("settings.encrypt.msg.enabled"))
        return True

    def _disable_encryption(self, cfg, cfg_path) -> bool:
        from launcher.auth import AccountStore, secure

        password = self._prompt_current_password()
        if password is None:
            return False
        if not secure.verify_password(password):
            self.status.set_error(tr("settings.encrypt.wrong"))
            return False
        secure.set_password(password)
        store = AccountStore()
        try:
            accounts = store.load()
        except Exception as exc:  # noqa: BLE001
            secure.forget_password()
            self.status.set_error(tr("settings.encrypt.msg.failed", str(exc)))
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
            self.status.set_error(tr("settings.encrypt.wrong"))
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
            self.status.set_error(tr("settings.encrypt.msg.failed", str(exc)))
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
            self.save()  # picking a folder is a change: no Save button to press

    def _browse_java(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Java")
        if chosen:
            self.java_path_edit.setText(chosen)
            self.save()
