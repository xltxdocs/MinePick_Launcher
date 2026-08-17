"""Error severity display: fatal errors use a dialog, ordinary warnings only the status bar."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from gui import i18n


def show_fatal(parent: QWidget | None, message: str) -> None:
    """Fatal error: dialog + status bar text. Returns None (the caller sets the status bar itself)."""
    QMessageBox.critical(parent, i18n.tr("error.title"), message)


def show_warning(parent: QWidget | None, message: str) -> None:
    """Ordinary warning: non-blocking prompt box."""
    QMessageBox.warning(parent, i18n.tr("error.warning.title"), message)
