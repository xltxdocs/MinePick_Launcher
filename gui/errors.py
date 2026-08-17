"""错误分级显示（#31）：致命错误弹窗，普通警告仅状态栏。"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from gui import i18n


def show_fatal(parent: QWidget | None, message: str) -> None:
    """致命错误：弹窗 + 状态栏文本。返回 None（调用方自行设置状态栏）。"""
    QMessageBox.critical(parent, i18n.tr("error.title"), message)


def show_warning(parent: QWidget | None, message: str) -> None:
    """普通警告：弹提示框（非阻断式）。"""
    QMessageBox.warning(parent, i18n.tr("error.warning.title"), message)
