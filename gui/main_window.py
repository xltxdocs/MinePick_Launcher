"""主窗口：侧边栏导航 + 页面栈（支持界面语言切换重建）。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QPushButton,
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
        self.resize(1000, 660)

        from gui.widgets import apply_no_focus_outline

        self.sidebar = QListWidget()
        apply_no_focus_outline(self.sidebar)  # 去掉选中项文字焦点框
        self.sidebar.setFixedWidth(120)
        self.stack = QStackedWidget()

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        # 状态栏：崩溃报告查看入口（#13）
        self.crash_button = QPushButton(i18n.tr("crash.viewer"))
        self.crash_button.clicked.connect(self._open_crash_viewer)
        self.statusBar().addPermanentWidget(self.crash_button)
        self.build_pages()
        self.sidebar.setCurrentRow(0)
        self.statusBar().showMessage(i18n.tr("status.ready"))

    def build_pages(self) -> None:
        """按当前语言（重）建全部页面。"""
        self.pages: dict[str, QWidget] = {
            "launch": LaunchPage(),
            "instances": InstancesPage(),
            "versions": VersionsPage(),
            "java": JavaPage(),
            "account": LoginPage(),
            "mods": ResourcesPage(),
            "settings": SettingsPage(),
        }
        self.crash_button.setText(i18n.tr("crash.viewer"))
        # 清空并重建导航 + 页面栈
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

        # 跨页联动
        self.pages["account"].account_changed.connect(self.pages["launch"].refresh_account)
        self.pages["settings"].settings_changed.connect(self._on_settings_changed)
        self.pages["versions"].launch_requested.connect(self._goto_launch)

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
        """按配置应用窗口启动状态（#12）：默认/最大化/最小化/记住上次尺寸。"""
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

    def _open_crash_viewer(self) -> None:
        from gui.crash_viewer import CrashViewerDialog
        from launcher import config, paths

        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        dialog = CrashViewerDialog(game_dir, self)
        dialog.exec()
