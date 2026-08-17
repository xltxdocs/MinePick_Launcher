"""首次使用向导（#29）：语言 / 游戏目录 / 默认内存。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from gui import i18n

tr = i18n.tr


class FirstRunWizard(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("wizard.title"))
        self.setMinimumWidth(460)
        self.language_combo = QComboBox()
        for code, label in i18n.UI_LANGUAGES:
            self.language_combo.addItem(label, code)
        # 预选当前语言（首次启动已按系统语言探测）
        preset = self.language_combo.findData(i18n.current_language())
        self.language_combo.setCurrentIndex(max(preset, 0))
        self.game_dir_edit = QLineEdit()
        self.game_dir_edit.setPlaceholderText(tr("wizard.default_dir.hint"))
        self.browse_button = QPushButton(tr("settings.browse"))
        self.memory_spin = QDoubleSpinBox()
        self.memory_spin.setRange(0.5, 64.0)
        self.memory_spin.setSingleStep(0.5)
        self.memory_spin.setValue(4.0)
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
        """把向导结果写入配置（language_initialized 走既有首启语言规则）。"""
        from launcher import config

        cfg.ui_language = self.language_combo.currentData()
        cfg.game_dir = self.game_dir_edit.text().strip() or None
        cfg.memory_gb = self.memory_spin.value()
        cfg.wizard_done = True
        config.save(cfg, cfg_path)
