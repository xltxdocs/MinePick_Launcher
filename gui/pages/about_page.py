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

"""About page: version and source link, legal notices, credits, and the update check with its settings.

All feedback goes to the single status bar (like every other page). The check and the download run on
worker threads and only report back through queued callbacks; the swap itself is delegated to a helper
script that runs after this process exits, because a running single-file EXE cannot replace itself.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.widgets import build_page_header, disable_keeping_focus, set_app_status, style_page_layout
from gui.workers import ProgressBridge, run_in_background
from launcher import __version__, config, notices, updates

tr = i18n.tr

SOURCE_URL = f"https://github.com/{updates.REPO}"
LICENSE_URL = f"https://github.com/{updates.REPO}/blob/main/LICENSE"
NOTICES_URL = f"https://github.com/{updates.REPO}/blob/main/THIRD_PARTY_NOTICES.md"

MODE_KEYS: tuple[tuple[str, str], ...] = (
    ("download_install", "about.update.mode.download_install"),
    ("download_notify", "about.update.mode.download_notify"),
    ("notify", "about.update.mode.notify"),
    ("off", "about.update.mode.off"),
)
MODES = {value for value, _key in MODE_KEYS}
DEFAULT_MODE = "download_notify"
FAILURE_CODES = ("network", "http", "parse", "no_asset", "size", "signature")
PROGRESS_STEP = 1 << 20  # report download progress about once per MB


class AboutPage(QWidget):
    """About / update page (see the module docstring)."""

    def __init__(self) -> None:
        super().__init__()
        self._release: updates.ReleaseInfo | None = None
        self._pending: Path | None = None
        self._pending_version = ""
        self._checking = False
        self._downloading = False

        inner = QWidget()
        layout = QVBoxLayout(inner)
        style_page_layout(layout)
        layout.addWidget(self._build_information())
        layout.addWidget(self._build_updates())
        layout.addWidget(self._build_credits())
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        style_page_layout(outer)
        outer.addWidget(build_page_header(tr("nav.about"), tr("page.about.desc")))
        outer.addWidget(scroll)

        self.load()
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

    # ---------- construction ----------

    def _build_information(self) -> QGroupBox:
        box = QGroupBox(tr("about.info.title"))
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        layout.addWidget(QLabel(tr("about.info.version", __version__)))

        self.source_button = QPushButton(tr("about.info.source"))
        self.source_button.clicked.connect(lambda: self._open(SOURCE_URL))
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_button)
        source_row.addStretch(1)
        layout.addLayout(source_row)

        layout.addWidget(
            self._legal_block("about.legal.title", "about.legal.body", LICENSE_URL, "about.legal.view_license")
        )
        layout.addWidget(self._legal_block("about.upstream.title", "about.upstream.body", None, None))
        layout.addWidget(
            self._legal_block(
                "about.licenses.title", "about.licenses.body", NOTICES_URL, "about.licenses.notices"
            )
        )
        return box

    def _legal_block(self, title_key: str, body_key: str, url: str | None, link_key: str | None) -> QWidget:
        """A titled paragraph of legal text with an optional link button."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(3)
        title = QLabel(tr(title_key))
        title.setObjectName("title")
        layout.addWidget(title)
        body = QLabel(tr(body_key))
        body.setObjectName("hint")
        body.setWordWrap(True)
        layout.addWidget(body)
        if url and link_key:
            button = QPushButton(tr(link_key))
            button.setObjectName("secondaryButton")
            button.clicked.connect(lambda _checked=False, target=url: self._open(target))
            row = QHBoxLayout()
            row.addWidget(button)
            row.addStretch(1)
            layout.addLayout(row)
        return holder

    def _build_updates(self) -> QGroupBox:
        box = QGroupBox(tr("about.update.title"))
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        versions = QHBoxLayout()
        self.current_label = QLabel(tr("about.update.current", __version__))
        self.latest_label = QLabel(tr("about.update.latest_unknown"))
        self.latest_label.setObjectName("hint")
        versions.addWidget(self.current_label)
        versions.addSpacing(18)
        versions.addWidget(self.latest_label)
        versions.addStretch(1)
        layout.addLayout(versions)

        self.check_button = QPushButton(tr("about.update.check"))
        self.check_button.clicked.connect(self.check_updates)
        self.open_page_button = QPushButton(tr("about.update.open_page"))
        self.open_page_button.setObjectName("secondaryButton")
        self.open_page_button.clicked.connect(self.open_release_page)
        self.open_page_button.setVisible(False)
        button_row = QHBoxLayout()
        button_row.addWidget(self.check_button)
        button_row.addWidget(self.open_page_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel(tr("about.update.mode.title")))
        self.mode_combo = QComboBox()
        for value, key in MODE_KEYS:
            self.mode_combo.addItem(tr(key), value)
        layout.addWidget(self.mode_combo)
        self.mode_hint = QLabel()
        self.mode_hint.setObjectName("hint")
        self.mode_hint.setWordWrap(True)
        layout.addWidget(self.mode_hint)
        return box

    def _build_credits(self) -> QGroupBox:
        box = QGroupBox(tr("about.credits.title"))
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        for group_key, entries in notices.groups():
            heading = QLabel(tr(group_key))
            heading.setObjectName("title")
            layout.addWidget(heading)
            for entry in entries:
                layout.addWidget(self._credit_row(entry))
        return box

    def _credit_row(self, entry: notices.Credit) -> QWidget:
        """One acknowledgment: name (never translated), translated description, optional link."""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        text = QLabel(f"<b>{entry.name}</b> — {tr(entry.detail_key)}")
        text.setWordWrap(True)
        row.addWidget(text, 1)
        if entry.url:
            button = QPushButton(tr("about.credits.link"))
            button.setObjectName("secondaryButton")
            button.clicked.connect(lambda _checked=False, target=entry.url: self._open(target))
            row.addWidget(button)
        return holder

    # ---------- config ----------

    def load(self) -> None:
        """Fill the widgets from the config (signals blocked: this is not a user change)."""
        cfg, _ = config.load()
        self.mode_combo.blockSignals(True)
        index = self.mode_combo.findData(self._valid_mode(cfg.auto_update_mode))
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self.mode_combo.blockSignals(False)
        self._update_mode_hint()

    @staticmethod
    def _valid_mode(value: str) -> str:
        return value if value in MODES else DEFAULT_MODE

    def current_mode(self) -> str:
        return self._valid_mode(str(self.mode_combo.currentData() or DEFAULT_MODE))

    def _on_mode_changed(self) -> None:
        cfg, cfg_path = config.load()
        cfg.auto_update_mode = self.current_mode()
        config.save(cfg, cfg_path)
        self._update_mode_hint()

    def _update_mode_hint(self) -> None:
        self.mode_hint.setText(tr(f"{dict(MODE_KEYS)[self.current_mode()]}.desc"))

    # ---------- links ----------

    @staticmethod
    def _open(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def open_release_page(self) -> None:
        page = self._release.page_url if self._release is not None else updates.RELEASES_PAGE
        self._open(page)

    # ---------- update check ----------

    def check_updates(self) -> None:
        """Manual check; the automatic one goes through :meth:`auto_check_on_start`."""
        if self._checking or self._downloading:
            return
        self._checking = True
        disable_keeping_focus(self.check_button)
        set_app_status(self, tr("about.update.checking"))
        run_in_background(
            updates.check_for_update,
            __version__,
            on_result=self._on_check_result,
            on_finished=self._on_check_finished,
        )

    def _on_check_finished(self) -> None:
        self._checking = False
        self.check_button.setEnabled(True)

    def _on_check_result(self, result: updates.UpdateCheck) -> None:
        if result.status == "failed":
            set_app_status(self, tr(self._failure_key(result.error)), "error")
            return
        self.latest_label.setText(tr("about.update.latest", result.latest))
        if result.status == "up_to_date":
            self._release = None
            self.open_page_button.setVisible(False)
            set_app_status(self, tr("about.update.up_to_date"))
            return
        self._release = result.release
        self.open_page_button.setVisible(True)
        set_app_status(self, tr("about.update.available", result.latest))
        self._handle_available(result.release)

    @staticmethod
    def _failure_key(code: str) -> str:
        return f"about.update.failed.{code if code in FAILURE_CODES else 'network'}"

    def _handle_available(self, release: updates.ReleaseInfo | None) -> None:
        """Act on a new release according to the configured mode."""
        if release is None:
            return
        if self.current_mode() in ("download_install", "download_notify"):
            self._start_download(release)
        else:
            self._prompt_available(release)

    # ---------- download ----------

    def _start_download(self, release: updates.ReleaseInfo) -> None:
        if self._downloading:
            return
        self._downloading = True
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        set_app_status(self, tr("about.update.downloading", "0"))
        bridge = ProgressBridge()
        bridge.progress.connect(self._on_download_progress)

        def do_download(progress) -> tuple[str, object]:
            last = 0

            def on_progress(done: int, total: int) -> None:
                nonlocal last
                if done - last >= PROGRESS_STEP or (total and done == total):
                    last = done
                    progress((done, total))

            try:
                path = updates.download_release_exe(release, updates.updates_dir(), on_progress=on_progress)
            except updates.UpdateError as exc:
                return "failed", exc.code
            return "ok", path

        self._pending_version = release.version
        run_in_background(
            do_download,
            bridge,
            # bound methods on purpose: the dispatcher's owner guard only sees callbacks that
            # expose __self__ (a lambda would still run against a page rebuilt by a language switch)
            on_result=self._on_download_result,
            on_error=self._on_download_failed,
            on_finished=self._on_download_finished,
        )

    def _on_download_finished(self) -> None:
        self._downloading = False
        self.check_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    def _on_download_progress(self, payload) -> None:
        done, total = payload
        if total:
            self.progress_bar.setValue(int(done * 1000 / total))
            set_app_status(self, tr("about.update.downloading", str(done * 100 // total)))
        else:
            set_app_status(self, tr("about.update.downloading", "?"))

    def _on_download_result(self, payload) -> None:
        status, value = payload
        version = self._pending_version
        if status == "failed":
            self._on_download_failed(str(value))
            return
        self._pending = Path(value)
        updates.save_pending(self._pending, version)
        if self.current_mode() == "download_install":
            if not updates.can_self_update():
                # never promise an install-on-exit that cannot happen (source checkout / read-only)
                set_app_status(self, tr("about.update.install_dev"), "warning")
                self.open_page_button.setVisible(True)
                return
            set_app_status(self, tr("about.update.install_on_exit"))
            return
        set_app_status(self, tr("about.update.downloaded", version))
        self._prompt_install(version)

    def _on_download_failed(self, code: str) -> None:
        set_app_status(self, tr(self._failure_key(str(code))), "error")
        if self._release is not None:
            self.open_page_button.setVisible(True)

    # ---------- prompts ----------

    def _prompt_available(self, release: updates.ReleaseInfo) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("about.update.prompt.title"))
        box.setText(tr("about.update.prompt.message", release.version))
        open_button = box.addButton(tr("about.update.open_page"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("about.update.prompt.later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self._open(release.page_url)

    def _prompt_install(self, version: str) -> None:
        if not updates.can_self_update():
            set_app_status(self, tr("about.update.install_dev"), "warning")
            self.open_page_button.setVisible(True)
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("about.update.prompt.title"))
        box.setText(tr("about.update.downloaded", version))
        install_button = box.addButton(tr("about.update.install_now"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("about.update.install_later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is install_button:
            self.install_now()

    # ---------- install ----------

    def _staged_update(self) -> Path | None:
        if self._pending is not None and self._pending.is_file():
            return self._pending
        staged = updates.load_pending()
        return staged[0] if staged is not None else None

    def install_now(self) -> None:
        """Swap the running EXE through a detached helper, then quit; failure keeps everything as is."""
        pending = self._staged_update()
        if pending is None:
            return
        if not updates.can_self_update():
            set_app_status(self, tr("about.update.install_manual"), "warning")
            self.open_page_button.setVisible(True)
            return
        try:
            script = updates.write_install_script(pending, Path(sys.executable), restart=True)
        except OSError:
            set_app_status(self, tr("about.update.install_manual"), "error")
            self.open_page_button.setVisible(True)
            return
        if not updates.launch_install_script(script):
            set_app_status(self, tr("about.update.install_manual"), "error")
            self.open_page_button.setVisible(True)
            return
        updates.clear_pending()
        set_app_status(self, tr("about.update.install_on_exit"))
        application = QApplication.instance()
        if application is not None:
            QTimer.singleShot(200, application.quit)

    def has_pending_install(self) -> bool:
        """Whether an update is staged (the window uses this when deciding about installing on exit)."""
        return bool(self._staged_update())

    def install_pending_on_exit(self) -> None:
        """Install a staged update when the app closes (the "download and install" mode)."""
        if self.current_mode() != "download_install" or not updates.can_self_update():
            return
        pending = self._staged_update()
        if pending is None:
            return
        try:
            script = updates.write_install_script(pending, Path(sys.executable), restart=False)
        except OSError:
            return  # closing must never raise; the staged update stays for the next start
        if not updates.launch_install_script(script):
            # The staged update stays pending, and the log records why: an update that silently
            # does nothing is worse than one that fails loudly.
            logging.getLogger(__name__).warning(
                "could not start the update helper %s; the staged update stays pending", script
            )

    def auto_check_on_start(self) -> None:
        """Startup check; the "off" mode really means no automatic check.

        An update that was downloaded in an earlier session is offered again instead of being
        downloaded twice (the user may have answered "later" to the prompt).
        """
        updates.cleanup_backups(Path(sys.executable))
        staged = updates.load_pending()
        if staged is not None and self.current_mode() != "off":
            self._pending, self._pending_version = staged
            if self.current_mode() != "download_install":  # that mode installs it on exit
                self._prompt_install(self._pending_version)
            return
        if self.current_mode() == "off":
            return
        self.check_updates()

    def refresh(self) -> None:
        """Reload the update settings (the window calls this whenever the page is shown)."""
        self.load()
