"""GUI entry point."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from launcher import paths
from launcher.logging_setup import configure_logging


def build_app_icon() -> QIcon:
    """Multi-size app icon: small sizes (title bar 16/24) use a simplified version for clarity,
    32px and up (taskbar) use the full design. All PNG (no QtSvg plugin dependency in the EXE)."""
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QPixmap

    icon = QIcon()
    for name in ("window_icon_16.png", "window_icon_24.png"):
        path = paths.resource_path("gui/resources/" + name)
        if path.exists():
            icon.addPixmap(QPixmap(str(path)))
    full = paths.resource_path("gui/resources/icon.png")
    if full.exists():
        base = QPixmap(str(full))
        for size in (32, 48, 64, 128, 256):
            icon.addPixmap(
                base.scaled(
                    QSize(size, size),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
    return icon


def _unlock_token_vault() -> None:
    """When token encryption is on, prompt for the password to unlock (in-memory cache); on failure stay locked and related operations will error."""
    from gui import i18n
    from launcher import config
    from launcher.auth import secure

    cfg, _ = config.load()
    if not cfg.token_encryption or not secure.vault_exists():
        return
    try:
        if secure.unlock_vault(interactive=False):
            return
    except secure.VaultError:
        pass
    from PySide6.QtWidgets import QInputDialog, QLineEdit

    for _attempt in range(3):
        text, ok = QInputDialog.getText(
            None,
            "MinePick Launcher",
            i18n.tr("settings.encrypt.current.prompt"),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        if secure.verify_password(text):
            secure.set_password(text)
            return


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("MinePick Launcher")
    app.setOrganizationName("mclauncher")
    # Use Fusion as the base style: the native Windows style (windows11) draws its own
    # white rounded boxes for tabs/menus/dropdowns that override QSS; Fusion follows QSS fully.
    app.setStyle("Fusion")
    from gui import i18n
    from launcher import config

    cfg, cfg_path = config.load()
    # First launch (wizard not done): preselect the UI language from the system language, changeable in the wizard; no longer auto-changed after the wizard completes
    if not cfg.wizard_done:
        cfg.ui_language = i18n.detect_system_language()
    # First launch: auto-initialize the game language (sync launcher/system language, once only)
    config.initialize_language(cfg, cfg_path)
    i18n.set_language(cfg.ui_language)
    _unlock_token_vault()
    app.setWindowIcon(build_app_icon())
    # Theme: dark / light QSS
    from gui.theme import apply_theme

    apply_theme(cfg.theme)
    # The wheel only scrolls page content; combo/spin/tab-bar wheel input is blocked
    from gui.widgets import WheelBlocker

    app._wheel_blocker = WheelBlocker(app)  # keep a reference so the filter stays alive
    app.installEventFilter(app._wheel_blocker)
    return app


def main() -> int:
    configure_logging(log_file=paths.launcher_dir() / "logs" / "launcher.log")
    app = create_app()

    # First-run wizard: language / game directory / default memory
    # (skip during the headless smoke test MCLAUNCHER_GUI_AUTOQUIT_MS to avoid blocking on the modal dialog)
    from launcher import config as config_mod

    cfg, cfg_path = config_mod.load()
    auto_quit = __import__("os").environ.get("MCLAUNCHER_GUI_AUTOQUIT_MS")
    if not cfg.wizard_done and not auto_quit:
        from PySide6.QtWidgets import QDialog

        from gui.pages.wizard import FirstRunWizard

        wizard = FirstRunWizard()
        if wizard.exec() == QDialog.DialogCode.Accepted:
            wizard.apply(cfg, cfg_path)
            from gui import i18n

            i18n.set_language(cfg.ui_language)

    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    window.apply_window_mode()

    # Headless/CI verification: auto-quit when MCLAUNCHER_GUI_AUTOQUIT_MS=3000
    auto_quit = __import__("os").environ.get("MCLAUNCHER_GUI_AUTOQUIT_MS")
    if auto_quit:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(int(auto_quit), app.quit)

    return app.exec()
