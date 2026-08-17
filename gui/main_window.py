"""Main window: sidebar navigation + page stack (rebuilds on UI language switch)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from gui import i18n
from gui.pages.instances_page import InstancesPage
from gui.pages.java_page import JavaPage
from gui.pages.launch_page import LaunchPage
from gui.pages.login_page import LoginPage
from gui.pages.mods_page import ResourcesPage
from gui.pages.settings_page import SettingsPage
from gui.pages.versions_page import VersionsPage

NAV_KEYS = ["launch", "instances", "versions", "java", "account", "mods", "settings"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MinePick Launcher")
        self.resize(1000, 600)

        from gui.widgets import apply_no_focus_outline

        self.sidebar = QListWidget()
        apply_no_focus_outline(self.sidebar)  # remove focus outline from the selected item's text
        self.sidebar.setFixedWidth(120)
        self.stack = QStackedWidget()

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        self.build_pages()
        self.sidebar.setCurrentRow(0)
        self.statusBar().showMessage(i18n.tr("status.ready"))

    def build_pages(self) -> None:
        """(Re)build all pages in the current language."""
        self.pages: dict[str, QWidget] = {
            "launch": LaunchPage(),
            "instances": InstancesPage(),
            "versions": VersionsPage(),
            "java": JavaPage(),
            "account": LoginPage(),
            "mods": ResourcesPage(),
            "settings": SettingsPage(),
        }
        # Clear and rebuild the navigation + page stack
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for key in NAV_KEYS:
            self.sidebar.addItem(i18n.tr("nav." + key))
        self.sidebar.blockSignals(False)
        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()
        for key in NAV_KEYS:
            self.stack.addWidget(self.pages[key])
        self.sidebar.setCurrentRow(0)

        # Cross-page wiring
        self.pages["account"].account_changed.connect(self.pages["launch"].refresh_account)
        self.pages["launch"].account_changed.connect(self.pages["account"].refresh)
        self.pages["settings"].settings_changed.connect(self._on_settings_changed)
        self.pages["versions"].launch_requested.connect(self._goto_launch)
        self.pages["versions"].versions_changed.connect(self.pages["launch"].refresh_versions)

    def _on_nav_changed(self, row: int) -> None:
        """Refresh the version dropdown when switching to the launch page (auto-syncs after loader/modpack install)."""
        if row == 0:
            self.pages["launch"].refresh_versions()

    def _on_settings_changed(self) -> None:
        from launcher import config

        cfg, _ = config.load()
        if i18n.current_language() != cfg.ui_language:
            i18n.set_language(cfg.ui_language)
            self.build_pages()
            self.statusBar().showMessage(i18n.tr("status.ready"))
        self.pages["launch"].refresh_config()

    def _goto_launch(self, version_id: str) -> None:
        self.pages["launch"].set_version_id(version_id)
        self.sidebar.setCurrentRow(0)

    def apply_window_mode(self) -> None:
        """Apply the window startup state from config: default/maximized/minimized/remember last size."""
        from launcher import config

        cfg, _ = config.load()
        mode = cfg.window_start_mode
        if mode == "maximized":
            self.showMaximized()
        elif mode == "minimized":
            self.showMinimized()
        elif mode == "remember" and cfg.window_geometry:
            try:
                from PySide6.QtCore import QByteArray

                self.restoreGeometry(
                    QByteArray.fromHex(bytes(cfg.window_geometry, "ascii"))
                )
            except (TypeError, ValueError):
                pass

    def closeEvent(self, event) -> None:
        from launcher import config

        cfg, cfg_path = config.load()
        if cfg.window_start_mode == "remember":
            geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
            cfg.window_geometry = bytes(geometry.saveGeometry().toHex()).decode("ascii")
            config.save(cfg, cfg_path)
        super().closeEvent(event)


