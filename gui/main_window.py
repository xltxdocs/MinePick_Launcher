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

"""Main window: sidebar navigation + page stack (pages built on first visit, rebuilt on language switch)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QSizePolicy,
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
PAGE_FADE_MS = 150  # interactive, so it stays under the 200ms ceiling (guideline §2.3)


class _LazyPages:
    """The window's page registry, building each page the first time it is asked for.

    Startup used to construct all eight pages - 802 widgets offscreen, 1457 in the real window - before
    the window was even up, and every one of them is polished by the application stylesheet at that
    cost. Only the first page is visible at that moment, so the other seven are now built on first use.

    Two access patterns are deliberately different:

    * ``pages[key]`` / ``pages.get(key)`` build that one page - this is what navigation and the
      cross-page slots use, so opening one page never builds another.
    * iterating (``for key in pages``, ``pages.items()``, ``len(pages)``) means "I want all of them" and
      materialises the lot. The quality audits and the GUI tests walk every page on purpose, and this
      keeps them working without change - and without silently auditing a single page.
    """

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        self._built: dict[str, QWidget] = {}

    # -- building ---------------------------------------------------------
    def _build(self, key: str) -> QWidget:
        page = self._window._make_page(key)
        self._built[key] = page
        self._window._adopt_page(key, page)
        return page

    def _materialise_all(self) -> None:
        for key in NAV_KEYS:
            if key not in self._built:
                self._build(key)

    def built_keys(self) -> tuple[str, ...]:
        """Keys built so far, without building anything - for tests and diagnostics."""
        return tuple(key for key in NAV_KEYS if key in self._built)

    def peek(self, key: str) -> QWidget | None:
        """The page if it happens to be built, else ``None`` - never builds."""
        return self._built.get(key)

    def clear(self) -> None:
        """Drop every page (language switch): the next access builds a fresh one."""
        for page in self._built.values():
            page.setParent(None)
            page.deleteLater()
        self._built.clear()

    # -- mapping behaviour ------------------------------------------------
    def __getitem__(self, key: str) -> QWidget:
        page = self._built.get(key)
        return page if page is not None else self._build(key)

    def get(self, key: str, default: QWidget | None = None) -> QWidget | None:
        if key not in NAV_KEYS:
            return default
        return self[key]

    def __contains__(self, key: object) -> bool:
        return key in NAV_KEYS

    def __iter__(self):
        self._materialise_all()
        return iter(NAV_KEYS)

    def __len__(self) -> int:
        return len(NAV_KEYS)

    def keys(self) -> list[str]:
        return list(NAV_KEYS)

    def values(self) -> list[QWidget]:
        self._materialise_all()
        return [self._built[key] for key in NAV_KEYS]

    def items(self) -> list[tuple[str, QWidget]]:
        self._materialise_all()
        return [(key, self._built[key]) for key in NAV_KEYS]
ENTRY_START_OPACITY = 0.45  # rolled back to the pre-0.4.0 value at the user's request: the page
# switch fades in from a clearly translucent state again, which is what it used to look like


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MinePick Launcher")
        self.resize(1000, 600)
        # Declared explicitly because the layout would otherwise derive the minimum from whichever pages
        # happen to be built: with lazy construction that grows the moment someone visits a tall page and
        # the window refuses to shrink afterwards. 1000x610 is the size the width audit holds every
        # language to (tools/measure_min_width.py raises the window from its own minimum).
        self.setMinimumSize(1000, 610)

        from gui.widgets import StatusLabel, apply_no_focus_outline

        self.sidebar = QListWidget()
        self.sidebar.setAccessibleName(tr("a11y.nav"))  # WCAG 4.1.2
        self.sidebar.setObjectName("sidebar")
        apply_no_focus_outline(self.sidebar)  # remove focus outline from the selected item's text

        nav = QWidget()
        nav.setFixedWidth(150)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.addWidget(self.sidebar, 1)

        self.stack = QStackedWidget()
        # The window's minimum must not depend on which pages happen to be built. A stacked widget
        # reports the largest minimum of its children, so with lazy construction the floor would rise
        # the moment a tall page was first visited - and the window would refuse to shrink again.
        # Ignoring the height stops that; the explicit minimum above is the floor every page fits at.
        self.stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)

        content = QWidget()
        content.setObjectName("appContent")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(nav)
        layout.addWidget(self.stack, 1)

        # Frameless window: the frame is ours, so it follows the theme instead of the OS
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

        # One handler for both jobs: it builds the page if this is its first visit, shows it, refreshes
        # it. Connecting the stack directly as well would fight it over which widget is current.
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

    def _make_page(self, key: str) -> QWidget:
        """Construct one page. Called by the registry the first time that page is needed."""
        factories = {
            "launch": LaunchPage,
            "instances": InstancesPage,
            "versions": VersionsPage,
            "java": JavaPage,
            "account": LoginPage,
            "mods": ResourcesPage,
            "settings": SettingsPage,
            "about": AboutPage,
        }
        return factories[key]()

    def _wiring_for(self, key: str) -> list[tuple[str, object]]:
        """Outgoing signal → window-level slot for one page.

        Connected when the page is built. The slots resolve the peer page through the registry at
        signal time, because connecting straight to another page's bound method would build that peer
        immediately and undo the laziness this exists for.
        """
        return {
            "account": [("account_changed", self._on_account_changed)],
            "launch": [
                ("account_changed", self._on_launch_account_changed),
                ("instance_requested", self._goto_instance),
                ("instance_settings_requested", self._goto_instance_settings),
                ("account_requested", self._goto_account),
            ],
            "settings": [("settings_changed", self._on_settings_changed)],
            "versions": [
                ("versions_changed", self._on_versions_changed),
                ("launch_requested", self._goto_launch),
                ("instance_requested", self._goto_instance),
            ],
        }.get(key, [])

    def _adopt_page(self, key: str, page: QWidget) -> None:
        """Put a freshly built page into the stack and connect its outgoing signals."""
        self.stack.addWidget(page)
        for signal_name, slot in self._wiring_for(key):
            getattr(page, signal_name).connect(slot)

    def build_pages(self) -> None:
        """(Re)create the navigation. Pages themselves are constructed on first use."""
        # A fresh registry: after a language switch every page must be built again in the new language
        self.pages = _LazyPages(self)
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for key in NAV_KEYS:
            self.sidebar.addItem(i18n.tr("nav." + key))
        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()
        self.sidebar.setCurrentRow(0)
        self.sidebar.blockSignals(False)
        self._on_nav_changed(0)  # blocks were held, so the first page is shown explicitly

    def _on_nav_changed(self, row: int) -> None:
        """Show the page for ``row`` - building it on first visit - then refresh and fade it in."""
        if not 0 <= row < len(NAV_KEYS):
            return
        key = NAV_KEYS[row]
        page = self.pages[key]  # first visit to a page is what constructs it
        self.stack.setCurrentWidget(page)
        if key == "launch":
            # auto-syncs the version dropdown after a loader/modpack install
            page.refresh_versions()
        elif key == "instances":
            page.refresh()
        elif key == "versions":
            # a version can be deleted on the instances page: re-mark the installed column
            page.refresh_installed()
        elif key == "about":
            page.refresh()  # the update settings may have changed elsewhere
        self._fade_in_current_page()

    # -- cross-page slots (resolve the peer lazily, so peers are not built by wiring alone) --
    def _on_account_changed(self) -> None:
        self.pages["launch"].refresh_account()

    def _on_launch_account_changed(self) -> None:
        self.pages["account"].refresh()

    def _on_versions_changed(self) -> None:
        self.pages["launch"].refresh_versions()

    def _fade_in_current_page(self) -> None:
        """Short fade when switching pages: cheap, and it hides the layout jump.

        Reduced motion keeps this fade on purpose (guideline §5.2: transparency helps read a state
        change; it is movement and scaling that cause discomfort), so only the timing and the entry
        opacity differ from the overlay's fancier entrance.
        """
        page = self.stack.currentWidget()
        if page is None:
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(PAGE_FADE_MS)
        # R-QT-6: a page fades in from near-opaque, not from nothing.
        animation.setStartValue(ENTRY_START_OPACITY)
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

    def _goto_instance(self, version_id: str) -> None:
        """The versions page hands an installed profile over to the instances page."""
        self.sidebar.setCurrentRow(NAV_KEYS.index("instances"))
        self.pages["instances"].select_instance(version_id)

    def _goto_instance_settings(self, version_id: str) -> None:
        """Open the per-instance settings of the profile selected on the launch page."""
        from gui.pages.instance_detail import TAB_SETTINGS

        self._goto_instance(version_id)
        self.pages["instances"].detail.set_tab(TAB_SETTINGS)

    def _goto_account(self) -> None:
        """The launch page's account button: switching happens on the account page."""
        self.sidebar.setCurrentRow(NAV_KEYS.index("account"))

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

    def keyPressEvent(self, event) -> None:
        """Accept keys that nothing in the window claimed.

        Windows plays its default alert sound when a key event reaches the window unused and unaccepted
        - pressing Enter or Space with the focus on a list item, a label or a disabled button was the
        audible "ding". This handler only runs after every child widget declined the key, so buttons,
        dialogs and line edits keep their own behaviour; it just stops the event escaping to the desktop.
        """
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
            Qt.Key.Key_Backspace,
        ):
            event.accept()
            return
        super().keyPressEvent(event)

    def _confirm_quit_while_downloading(self) -> bool:
        """Ask before quitting when downloads are still running. Returns True when it is fine to close.

        The downloads themselves have no cancellation (an interrupted one keeps its .part and resumes
        next time), so the only real choices are "wait" and "quit now" - the dialog exists so the second
        one is deliberate. Nothing runs it when no download is active: the count is zero and the whole
        thing is one integer comparison.
        """
        from launcher.net import downloader

        active = downloader.active_download_count()
        if active <= 0:
            return True
        from PySide6.QtWidgets import QMessageBox

        from gui.i18n import tr

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("quit.busy.confirm"))
        box.setText(tr("quit.busy.message").format(active))
        cancel = box.addButton(tr("quit.busy.cancel"), QMessageBox.ButtonRole.RejectRole)
        confirm = box.addButton(tr("quit.busy.confirm"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(cancel)  # the safe choice is the default one
        box.exec()
        return box.clickedButton() is confirm

    def closeEvent(self, event) -> None:
        if not getattr(self, "_quit_confirmed", False):
            if not self._confirm_quit_while_downloading():
                event.ignore()
                return
            self._quit_confirmed = True
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


