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

"""First-run wizard: language / game directory / default memory."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from gui import i18n
from gui.widgets import NoWheelDoubleSpinBox

tr = i18n.tr


class FirstRunWizard(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("wizard.title"))
        self.setMinimumWidth(460)
        self.language_combo = QComboBox()
        for code, label in i18n.UI_LANGUAGES:
            self.language_combo.addItem(label, code)
        # Preselect the current language (already detected from the system language on first launch)
        preset = self.language_combo.findData(i18n.current_language())
        self.language_combo.setCurrentIndex(max(preset, 0))
        self.game_dir_edit = QLineEdit()
        self.game_dir_edit.setPlaceholderText(tr("wizard.default_dir.hint"))
        # Prefill with the current config so a re-run never clobbers existing settings
        from launcher import config

        cfg, _ = config.load()
        if cfg.game_dir:
            self.game_dir_edit.setText(str(cfg.game_dir))
        self.browse_button = QPushButton(tr("settings.browse"))
        self.memory_spin = NoWheelDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setValue(cfg.memory_gb)
        self.memory_spin.setSuffix(" GB")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("wizard.finish"))
        self.buttons.accepted.connect(self.accept)
        self.browse_button.clicked.connect(self._browse)

        hint = QLabel(tr("wizard.hint"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.game_dir_edit, 1)
        dir_row.addWidget(self.browse_button)
        form = QFormLayout()
        form.addRow(tr("wizard.language"), self.language_combo)
        form.addRow(tr("wizard.game_dir"), dir_row)
        form.addRow(tr("wizard.memory"), self.memory_spin)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, tr("wizard.game_dir"))
        if chosen:
            self.game_dir_edit.setText(chosen)

    def apply(self, cfg, cfg_path) -> None:
        """Write the wizard result to config (language_initialized follows the existing first-run language rule)."""
        from launcher import config

        cfg.ui_language = self.language_combo.currentData()
        cfg.game_dir = self.game_dir_edit.text().strip() or None
        cfg.memory_gb = self.memory_spin.value()
        cfg.wizard_done = True
        config.save(cfg, cfg_path)
