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

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui import i18n

tr = i18n.tr
from gui.pages.about_page import AboutPage
from gui.pages.instances_page import InstancesPage
from gui.pages.java_page import JavaPage
from gui.pages.launch_page import LaunchPage
from gui.pages.login_page import LoginPage
from gui.pages.mods_page import ResourcesPage
from gui.pages.settings_page import SettingsPage
from gui.pages.versions_page import VersionsPage
from gui.wizard_overlay import BulletList, OptionGrid, WizardOverlay, WizardStep

NAV_KEYS = ["launch", "instances", "versions", "java", "account", "mods", "settings", "about"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MinePick Launcher")
        self.resize(1000, 600)

        from gui.widgets import StatusLabel, apply_no_focus_outline

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        apply_no_focus_outline(self.sidebar)  # remove focus outline from the selected item's text

        nav = QWidget()
        nav.setFixedWidth(150)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.addWidget(self.sidebar, 1)

        self.stack = QStackedWidget()

        content = QWidget()
        content.setObjectName("appContent")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(nav)
        layout.addWidget(self.stack, 1)

        # Frameless window: the frame is ours, so it follows the theme instead of the OS
        from PySide6.QtWidgets import QSizeGrip

        from gui.title_bar import TitleBar

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        central = QWidget()
        central.setObjectName("appRoot")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.title_bar = TitleBar(self, self.windowTitle())
        outer.addWidget(self.title_bar)
        outer.addWidget(content, 1)
        self.setCentralWidget(central)
        # The whole app reports on this one line: pages forward their progress and
        # errors here through gui.widgets.set_app_status (colours follow the severity).
        self.status_label = StatusLabel("")
        self.status_label.setObjectName("hint")
        self.statusBar().addWidget(self.status_label)
        # a frameless window loses the native resize border: keep a grip in the corner
        self.statusBar().addPermanentWidget(QSizeGrip(self))

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        self.build_pages()
        self.sidebar.setCurrentRow(0)
        self.set_status(tr("status.ready"))
        # Startup update check: delayed so the window is up first, once per session
        self._update_checked = False
        QTimer.singleShot(2500, self._auto_check_updates)

    def _auto_check_updates(self) -> None:
        """Let the About page run its startup check (it honours the configured update mode)."""
        if self._update_checked:
            return
        self._update_checked = True
        page = self.pages.get("about")
        if page is not None:
            page.auto_check_on_start()

    def set_status(self, text: str, level: str | None = None) -> None:
        """Single status line of the app: ``level`` is "info" (default), "warning" or "error".

        An empty message falls back to the neutral ready line, so the bar never ends up
        blank when a page clears what used to be its own page-local status label.
        """
        if not text:
            self.status_label.setText(tr("status.ready"))
            return
        if level == "error":
            self.status_label.set_error(text)
        elif level == "warning":
            self.status_label.set_warning(text)
        else:
            self.status_label.setText(text)

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
            "about": AboutPage(),
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
            self.set_status(tr("status.ready"))
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


    # ---------- first-run wizard (in-window overlay) ----------

    def show_wizard(self) -> None:
        """First run: cover the content area with the wizard instead of opening a dialog."""

        overlay = self._build_wizard_overlay()
        overlay.setParent(self)
        overlay.setGeometry(self.rect())
        overlay.finished.connect(self._on_wizard_finished)
        # the status bar and its size grip are managed by QMainWindow's layout and would be
        # painted above an unmanaged child, so they step aside while the overlay is up
        self.statusBar().hide()
        overlay.show_overlay()
        self.wizard_overlay = overlay

    def _build_wizard_overlay(self):
        from PySide6.QtWidgets import QAbstractSpinBox, QFileDialog, QLineEdit, QPushButton, QSlider

        from gui import i18n
        from gui.widgets import NoWheelDoubleSpinBox
        from launcher import config, paths

        cfg, _ = config.load()

        # 1 / start: what is about to happen, as a short list instead of one lonely line
        welcome = BulletList(tr("wizard.points").split("\n"))

        # 2 + 3 / languages: every option is visible, nothing hidden inside a dropdown
        self._wz_ui_language = OptionGrid(list(i18n.UI_LANGUAGES), columns=3)
        self._wz_ui_language.set_value(cfg.ui_language)
        # settings apply immediately everywhere — including the interface language chosen here
        self._wz_ui_language.selected.connect(self._on_wizard_language_selected)
        game_languages = [
            (code, label if code else tr("settings.game_language.follow"))
            for code, label in config.GAME_LANGUAGES
        ]
        self._wz_game_language = OptionGrid(game_languages, columns=3)
        self._wz_game_language.set_value(cfg.game_language)

        # 4 / game directory: field + browse + a live status line
        self._wz_game_dir = QLineEdit(str(cfg.game_dir) if cfg.game_dir else "")
        self._wz_game_dir.setPlaceholderText(str(paths.default_game_dir()))
        browse = QPushButton(tr("settings.browse"))
        browse.setObjectName("wizardBrowse")

        def pick_directory() -> None:
            chosen = QFileDialog.getExistingDirectory(
                self, tr("wizard.game_dir"), str(paths.default_game_dir())
            )
            if chosen:
                self._wz_game_dir.setText(chosen)

        browse.clicked.connect(pick_directory)
        self._wz_dir_status = QLabel("")
        self._wz_dir_status.setObjectName("wizardStatus")

        def refresh_status() -> None:
            raw = self._wz_game_dir.text().strip()
            target = Path(raw) if raw else paths.default_game_dir()
            if target.is_dir():
                self._wz_dir_status.setText("\u2713  " + str(target))
            else:
                self._wz_dir_status.setText("\u2022  " + str(target))

        self._wz_game_dir.textChanged.connect(refresh_status)
        dir_line = QWidget()
        dir_line_layout = QHBoxLayout(dir_line)
        dir_line_layout.setContentsMargins(0, 0, 0, 0)
        dir_line_layout.setSpacing(8)
        dir_line_layout.addWidget(self._wz_game_dir, 1)
        dir_line_layout.addWidget(browse)
        dir_box = QWidget()
        dir_box_layout = QVBoxLayout(dir_box)
        dir_box_layout.setContentsMargins(0, 0, 0, 0)
        dir_box_layout.setSpacing(8)
        dir_box_layout.addWidget(dir_line)
        dir_box_layout.addWidget(self._wz_dir_status)
        dir_box_layout.addStretch(1)
        refresh_status()

        # 5 / memory: one-line box with its own steppers plus a slider
        self._wz_memory = NoWheelDoubleSpinBox()
        self._wz_memory.setObjectName("wizardMemory")
        # the slider is the control here: the spin box is a read-out, not a stepper
        self._wz_memory.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._wz_memory.setRange(0.5, 64.0)
        self._wz_memory.setSingleStep(0.5)
        self._wz_memory.setValue(cfg.memory_gb or 4.0)
        self._wz_memory.setSuffix(" " + tr("unit.gb"))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(5, 640)
        slider.setValue(int((cfg.memory_gb or 4.0) * 10))
        slider.valueChanged.connect(lambda value: self._wz_memory.setValue(value / 10))
        self._wz_memory.valueChanged.connect(lambda value: slider.setValue(int(value * 10)))
        memory_box = QWidget()
        memory_layout = QVBoxLayout(memory_box)
        memory_layout.setContentsMargins(0, 0, 0, 0)
        memory_layout.setSpacing(12)
        memory_layout.addWidget(self._wz_memory)
        memory_layout.addWidget(slider)
        memory_layout.addStretch(1)

        steps = [
            WizardStep(tr("wizard.start"), tr("wizard.welcome.desc"), welcome, tr("wizard.start")),
            WizardStep(
                tr("settings.ui_language"), tr("wizard.hint"), self._wz_ui_language,
                tr("settings.ui_language"),
            ),
            WizardStep(
                tr("settings.game_language"), tr("wizard.hint"), self._wz_game_language,
                tr("settings.game_language"),
            ),
            WizardStep(tr("wizard.game_dir"), tr("wizard.default_dir.hint"), dir_box, tr("wizard.game_dir")),
            WizardStep(tr("wizard.memory"), tr("wizard.hint"), memory_box, tr("wizard.memory")),
        ]
        labels = {
            "back": tr("wizard.back"),
            "next": tr("wizard.next"),
            "done": tr("wizard.done"),
            "skip": tr("wizard.skip"),
        }
        return WizardOverlay(self, steps, labels)

    def _on_wizard_language_selected(self, code: str) -> None:
        """Apply the chosen interface language at once: re-translate and rebuild the wizard."""
        from gui import i18n
        from gui.theme import apply_theme
        from launcher import config

        cfg, cfg_path = config.load()
        cfg.ui_language = code
        config.save(cfg, cfg_path)
        i18n.set_language(code)
        apply_theme(cfg.theme, cfg.accent_color, cfg.ui_font, cfg.ui_radius)
        self._rebuild_wizard()

    def _rebuild_wizard(self) -> None:
        """Rebuild the overlay in the new language, staying on the same step."""
        overlay = getattr(self, "wizard_overlay", None)
        step = getattr(overlay, "_index", 0)
        if overlay is not None:
            overlay.hide()
            overlay.deleteLater()
        fresh = self._build_wizard_overlay()
        fresh.setParent(self)
        fresh.setGeometry(self.rect())
        fresh.finished.connect(self._on_wizard_finished)
        fresh._index = step
        fresh._sync()
        fresh.show_overlay()
        self.wizard_overlay = fresh

    def _on_wizard_finished(self) -> None:
        """Persist the wizard choices (never clobbering what the user already had) and switch theme."""
        from gui import i18n
        from gui.theme import apply_theme
        from launcher import config

        cfg, cfg_path = config.load()
        cfg.ui_language = self._wz_ui_language.value() or cfg.ui_language
        cfg.game_language = self._wz_game_language.value() or cfg.game_language
        chosen_dir = self._wz_game_dir.text().strip()
        if chosen_dir:
            cfg.game_dir = chosen_dir
        cfg.memory_gb = self._wz_memory.value()
        cfg.wizard_done = True
        config.save(cfg, cfg_path)
        config.initialize_language(cfg, cfg_path)
        i18n.set_language(cfg.ui_language)
        apply_theme(cfg.theme, cfg.accent_color, cfg.ui_font, cfg.ui_radius)
        self.build_pages()
        self.statusBar().show()
        self.set_status(tr("status.ready"))

    def closeEvent(self, event) -> None:
        from launcher import config

        page = self.pages.get("about")
        if page is not None:
            page.install_pending_on_exit()  # "download and install" mode swaps the EXE on exit
        cfg, cfg_path = config.load()
        if cfg.window_start_mode == "remember":
            geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
            cfg.window_geometry = bytes(geometry.saveGeometry().toHex()).decode("ascii")
            config.save(cfg, cfg_path)
        super().closeEvent(event)


