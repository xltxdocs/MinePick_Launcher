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

"""Main window: sidebar navigation + page stack (rebuilds on UI language switch)."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
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

        from gui.widgets import apply_no_focus_outline, build_sidebar_brand

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        apply_no_focus_outline(self.sidebar)  # remove focus outline from the selected item's text

        # Brand block above the navigation list, so the rail reads as one column
        nav = QWidget()
        nav.setFixedWidth(150)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(2)
        nav_layout.addWidget(build_sidebar_brand())
        nav_layout.addWidget(self.sidebar, 1)

        self.stack = QStackedWidget()

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(nav)
        layout.addWidget(self.stack, 1)

        # Frameless window: the frame is ours, so it follows the theme instead of the OS
        from PySide6.QtWidgets import QSizeGrip

        from gui.title_bar import TitleBar

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.title_bar = TitleBar(self, self.windowTitle())
        outer.addWidget(self.title_bar)
        outer.addWidget(content, 1)
        self.setCentralWidget(central)
        # a frameless window loses the native resize border: keep a grip in the corner
        self.statusBar().addPermanentWidget(QSizeGrip(self))

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
        self._fade_in_current_page()

    def _fade_in_current_page(self) -> None:
        """Short fade when switching pages: cheap, and it hides the layout jump."""
        page = self.stack.currentWidget()
        if page is None:
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(150)
        animation.setStartValue(0.45)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        # drop the effect once done, otherwise every child repaint goes through it
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._fade_animation = animation  # keep a reference so it is not collected

    def _on_settings_changed(self) -> None:
        from launcher import config

        cfg, _ = config.load()
        if i18n.current_language() != cfg.ui_language:
            i18n.set_language(cfg.ui_language)
            self.build_pages()
            self.statusBar().showMessage(i18n.tr("status.ready"))
        self.pages["launch"].refresh_config()
        # The instance registry lives in the game directory: refresh the list immediately
        self.pages["instances"].refresh()

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

    def changeEvent(self, event) -> None:
        """Keep the custom title bar's maximize glyph in step with the window state."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and getattr(self, "title_bar", None):
            self.title_bar.sync_state()

    def closeEvent(self, event) -> None:
        from launcher import config

        cfg, cfg_path = config.load()
        if cfg.window_start_mode == "remember":
            geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
            cfg.window_geometry = bytes(geometry.saveGeometry().toHex()).decode("ascii")
            config.save(cfg, cfg_path)
        super().closeEvent(event)


