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

"""Account page: multi-account list and switching, Microsoft device-code login (live countdown), offline login, logout."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.widgets import apply_no_focus_outline
from gui.workers import ProgressBridge, run_in_background
from launcher import config
from launcher.auth import AccountStore, MicrosoftSession, create_offline_account

tr = i18n.tr


class LoginPage(QWidget):
    account_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(48, 48)
        self.account_label = QLabel()
        self.accounts_list = QListWidget()
        apply_no_focus_outline(self.accounts_list)
        self.accounts_list.setMaximumHeight(120)
        self.switch_button = QPushButton(tr("account.switch"))
        self.device_code = QTextEdit()
        self.device_code.setReadOnly(True)
        self.device_code.setFixedHeight(110)
        self.ms_button = QPushButton(tr("login.ms.button"))
        self.offline_edit = QLineEdit()
        self.offline_edit.setPlaceholderText(tr("login.offline.placeholder"))
        self.offline_button = QPushButton(tr("login.offline.button"))
        self.logout_button = QPushButton(tr("login.logout.button"))
        self.status = QLabel("")
        self.status.setObjectName("hint")

        account_row = QHBoxLayout()
        account_row.addWidget(self.avatar_label)
        account_row.addWidget(self.account_label, 1)
        account_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(account_row)
        layout.addWidget(QLabel(tr("account.list.label")))
        layout.addWidget(self.accounts_list)
        switch_row = QHBoxLayout()
        switch_row.addWidget(self.switch_button)
        switch_row.addStretch(1)
        layout.addLayout(switch_row)
        layout.addWidget(QLabel(tr("login.ms.hint")))
        layout.addWidget(self.device_code)
        layout.addWidget(self.ms_button)
        layout.addSpacing(12)
        layout.addWidget(QLabel(tr("login.offline.hint")))
        offline_row = QHBoxLayout()
        offline_row.addWidget(self.offline_edit, 1)
        offline_row.addWidget(self.offline_button)
        layout.addLayout(offline_row)
        layout.addWidget(self.logout_button)
        layout.addWidget(self.status)
        layout.addStretch(1)

        self.ms_button.clicked.connect(self.start_ms_login)
        self.offline_button.clicked.connect(self.offline_login)
        self.logout_button.clicked.connect(self.logout)
        self.switch_button.clicked.connect(self.switch_account)
        self.accounts_list.itemDoubleClicked.connect(lambda _item: self.switch_account())
        # Device-code countdown
        self._countdown = QTimer(self)
        self._countdown.setInterval(1000)
        self._countdown.timeout.connect(self._on_countdown_tick)
        self._countdown_seconds = 0
        self.refresh()

    def refresh(self) -> None:
        cfg, _ = config.load()
        accounts = AccountStore().load()
        account = accounts.get(cfg.selected_account) if cfg.selected_account else None
        if account is None:
            self.account_label.setText(tr("account.none"))
            self._set_letter_avatar("?")
        else:
            kind = tr("kind.ms") if account.type == "microsoft" else tr("kind.offline")
            self.account_label.setText(tr("account.current", account.username, kind))
            self._update_avatar(account)
        self._refresh_accounts_list()

    # ---------- Avatar ----------

    def _set_letter_avatar(self, username: str) -> None:
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        hue = (sum(ord(c) for c in username) * 37) % 360
        painter.setBrush(QColor.fromHsv(hue, 160, 150))
        painter.setPen(_Qt.NoPen)
        painter.drawEllipse(0, 0, 64, 64)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setPixelSize(30)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), _Qt.AlignCenter, (username[:1] or "?").upper())
        painter.end()
        self.avatar_label.setPixmap(pixmap.scaled(48, 48, _Qt.KeepAspectRatio, _Qt.SmoothTransformation))

    def _update_avatar(self, account) -> None:
        self._set_letter_avatar(account.username)
        if not account.skin_url:
            return

        def do_fetch() -> object:
            from launcher.meta.manifest import _new_client

            client = _new_client()
            try:
                resp = client.get(account.skin_url)
                resp.raise_for_status()
                return resp.content
            finally:
                client.close()

        def on_ok(data) -> None:
            from PySide6.QtCore import Qt as _Qt
            from PySide6.QtGui import QPixmap

            try:
                pixmap = QPixmap()
                if data and pixmap.loadFromData(data):
                    self.avatar_label.setPixmap(
                        pixmap.scaled(48, 48, _Qt.KeepAspectRatio, _Qt.SmoothTransformation)
                    )
            except RuntimeError:
                pass  # page already destroyed (language switch rebuild)

        run_in_background(
            do_fetch,
            on_result=on_ok,
            on_error=lambda _m: None,  # keep the letter avatar on failure
        )

    def _refresh_accounts_list(self) -> None:
        cfg, _ = config.load()
        accounts = AccountStore().load()
        self.accounts_list.clear()
        for account_id, account in sorted(accounts.items(), key=lambda kv: kv[1].username):
            kind = tr("kind.ms") if account.type == "microsoft" else tr("kind.offline")
            item = QListWidgetItem(account.username + "（" + kind + "）")
            item.setData(Qt.UserRole, account_id)
            if account_id == cfg.selected_account:
                item.setText(item.text() + "  [" + tr("versions.status.installed") + "]")
            self.accounts_list.addItem(item)

    def _selected_account_id(self) -> str | None:
        item = self.accounts_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def switch_account(self) -> None:
        account_id = self._selected_account_id()
        if account_id is None:
            self.status.setText(tr("account.msg.need_select"))
            return
        cfg, cfg_path = config.load()
        cfg.selected_account = account_id
        config.save(cfg, cfg_path)
        self.refresh()
        account = AccountStore().load().get(account_id)
        self.status.setText(tr("account.msg.switched", account.username if account else account_id))
        self.account_changed.emit()

    def _save_account(self, account) -> None:
        store = AccountStore()
        accounts = store.load()
        accounts[account.id] = account
        store.save(accounts)
        cfg, cfg_path = config.load()
        cfg.selected_account = account.id
        config.save(cfg, cfg_path)
        if account.type == "microsoft":
            from launcher.config import unlock_offline_mode

            unlock_offline_mode()  # unlock offline mode after a licensed login
        self.refresh()
        self.account_changed.emit()

    def start_ms_login(self) -> None:
        self.ms_button.setEnabled(False)
        self.device_code.clear()
        self.status.setText(tr("login.msg.waiting"))
        bridge = ProgressBridge()
        bridge.progress.connect(self._on_progress)
        flow_bridge = ProgressBridge()
        flow_bridge.progress.connect(self._on_flow)  # worker thread -> main thread
        cfg, _ = config.load()

        def do_login(progress) -> object:
            session = MicrosoftSession(client_id=cfg.msa_client_id)
            return session.login_interactive(progress=progress, on_flow=flow_bridge)

        run_in_background(
            do_login,
            bridge,
            on_result=self._on_ms_ok,
            on_error=self._on_error,
            on_finished=self._on_login_finished,
        )

    def _on_flow(self, flow: dict) -> None:
        """Device code generated: auto-open the auth page + copy the code + start the countdown."""
        uri = str(flow.get("verification_uri") or "")
        if uri:
            QDesktopServices.openUrl(QUrl(uri))
            self.device_code.append(tr("login.msg.page_opened"))
        code = str(flow.get("user_code") or "")
        if code:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.clipboard().setText(code)
                self.device_code.append(tr("login.msg.code_copied", code))
        try:
            self._countdown_seconds = int(flow.get("expires_in") or 0)
        except (TypeError, ValueError):
            self._countdown_seconds = 0
        self._on_countdown_tick()
        if self._countdown_seconds > 0:
            self._countdown.start()

    def _on_countdown_tick(self) -> None:
        if self._countdown_seconds > 0:
            minutes, seconds = divmod(self._countdown_seconds, 60)
            self.status.setText(
                tr("login.msg.countdown", f"{minutes:02d}:{seconds:02d}")
            )
            self._countdown_seconds -= 1

    def _stop_countdown(self) -> None:
        self._countdown.stop()
        self._countdown_seconds = 0

    def _on_login_finished(self) -> None:
        self._stop_countdown()
        self.ms_button.setEnabled(True)

    def _on_progress(self, message: str) -> None:
        self.device_code.append(message)

    def _on_ms_ok(self, account) -> None:
        self._stop_countdown()
        self.status.setText(tr("login.msg.ok"))
        self._save_account(account)

    def _on_error(self, message: str) -> None:
        self._stop_countdown()
        self.status.setText(tr("login.msg.fail", message))

    def offline_login(self) -> None:
        from launcher.config import offline_mode_allowed

        if not offline_mode_allowed():
            self.status.setText(tr("launch.msg.offline_locked"))
            return
        try:
            account = create_offline_account(self.offline_edit.text())
        except ValueError as exc:
            self.status.setText(tr("login.msg.fail", exc))
            return
        self._save_account(account)
        self.status.setText(tr("login.msg.offline_ok"))

    def logout(self) -> None:
        cfg, cfg_path = config.load()
        store = AccountStore()
        accounts = store.load()
        # Prefer logging out the account selected in the list, otherwise the current account
        target = self._selected_account_id() or cfg.selected_account
        if not target:
            self.status.setText(tr("login.msg.no_account"))
            return
        accounts.pop(target, None)
        if cfg.selected_account == target:
            cfg.selected_account = None
        store.save(accounts)
        config.save(cfg, cfg_path)
        self.refresh()
        self.account_changed.emit()
        self.status.setText(tr("login.msg.logged_out"))
