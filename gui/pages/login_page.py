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

from PySide6.QtCore import QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPixmap
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
from gui.widgets import (
    apply_no_focus_outline,
    build_page_header,
    set_app_status,
    style_page_layout,
)
from gui.workers import ProgressBridge, run_in_background
from launcher import config
from launcher.auth import AccountStore, MicrosoftSession, create_offline_account

tr = i18n.tr

AVATAR_SIZE = 42  # px; the account avatar is square, so one size covers both uses
MIN_VISIBLE_ACCOUNTS = 2  # rows kept readable even in a short window (a half-cut row is worse)
MAX_VISIBLE_ACCOUNTS = 4  # rows shown once the page has room for them


def skin_face_pixmap(skin: QPixmap, size: int = AVATAR_SIZE) -> QPixmap | None:
    """Crop just the head out of a Minecraft skin texture (hat overlay included).

    A modern skin is 64x64 (HD skins are 128x128, 256x256...): the head's front face sits at
    (8, 8) and its hat overlay at (40, 8), both 8x8 units. Legacy 64x32 skins have no overlay.
    Nearest-neighbour scaling keeps the pixel-art look. Returns None for textures too small to
    be a skin (the caller then keeps the letter avatar).
    """
    if skin.isNull() or skin.width() < 64 or skin.height() < 32:
        return None
    unit = max(1, skin.width() // 64)  # HD skins store the same layout at a larger scale
    face = skin.copy(QRect(8 * unit, 8 * unit, 8 * unit, 8 * unit))
    if face.isNull():
        return None
    canvas = QPixmap(size, size)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    target = QRect(0, 0, size, size)
    painter.drawPixmap(target, face)
    if skin.height() >= 64 * unit:  # legacy 64x32 textures carry no hat layer
        painter.drawPixmap(target, skin.copy(QRect(40 * unit, 8 * unit, 8 * unit, 8 * unit)))
    painter.end()
    return canvas


def avatar_pixmap(data: bytes | None, size: int = AVATAR_SIZE) -> QPixmap | None:
    """Decode downloaded skin bytes into a face-only avatar; None keeps the letter avatar."""
    skin = QPixmap()
    if not data or not skin.loadFromData(data):
        return None
    return skin_face_pixmap(skin, size)


class LoginPage(QWidget):
    account_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self.account_label = QLabel()
        self.accounts_list = QListWidget()
        apply_no_focus_outline(self.accounts_list)
        self.switch_button = QPushButton(tr("account.switch"))
        self.switch_button.setObjectName("secondaryButton")
        self.device_code = QTextEdit()
        self.device_code.setMinimumHeight(40)
        self.device_code.setReadOnly(True)
        self.device_code.setFixedHeight(110)
        self.ms_button = QPushButton(tr("login.ms.button"))
        self.offline_edit = QLineEdit()
        self.offline_edit.setPlaceholderText(tr("login.offline.placeholder"))
        self.offline_button = QPushButton(tr("login.offline.button"))
        self.offline_button.setObjectName("secondaryButton")
        self.logout_button = QPushButton(tr("login.logout.button"))
        self.logout_button.setObjectName("dangerButton")

        account_row = QHBoxLayout()
        account_row.addWidget(self.avatar_label)
        account_row.addWidget(self.account_label, 1)
        account_row.addStretch(1)

        layout = QVBoxLayout(self)
        style_page_layout(layout)
        layout.addWidget(build_page_header(tr("nav.account"), tr("page.account.desc")))
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
        self.avatar_label.setPixmap(
            pixmap.scaled(AVATAR_SIZE, AVATAR_SIZE, _Qt.KeepAspectRatio, _Qt.SmoothTransformation)
        )

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
            try:
                avatar = avatar_pixmap(data)
                if avatar is not None:  # unusable texture: keep the letter avatar
                    self.avatar_label.setPixmap(avatar)
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
                item.setText(item.text() + "  [" + tr("account.status.current") + "]")
            self.accounts_list.addItem(item)
        self._fit_accounts_list()

    def _fit_accounts_list(self) -> None:
        """Size the account list by whole rows, so no account is ever cut in half.

        Row height is measured from the live list (it follows the QSS padding, the UI font and
        the active language) and the frame from the widget, so nothing here is hardcoded.
        """
        measure = None
        if self.accounts_list.count() == 0:
            measure = QListWidgetItem(" ")  # throw-away row: an empty list has nothing to measure
            self.accounts_list.addItem(measure)
        row_height = self.accounts_list.sizeHintForRow(0)
        if measure is not None:
            self.accounts_list.takeItem(0)
        if row_height <= 0:  # not polished yet: showEvent() measures again
            return
        frame = 2 * self.accounts_list.frameWidth()
        rows = max(1, self.accounts_list.count())
        low = min(rows, MIN_VISIBLE_ACCOUNTS)
        high = max(low, min(rows, MAX_VISIBLE_ACCOUNTS))
        self.accounts_list.setMinimumHeight(low * row_height + frame)
        self.accounts_list.setMaximumHeight(high * row_height + frame)

    def showEvent(self, event) -> None:  # Qt override
        super().showEvent(event)
        self._fit_accounts_list()  # first chance to measure the styled row height

    def _selected_account_id(self) -> str | None:
        item = self.accounts_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def switch_account(self) -> None:
        account_id = self._selected_account_id()
        if account_id is None:
            set_app_status(self, tr("account.msg.need_select"), "warning")
            return
        cfg, cfg_path = config.load()
        cfg.selected_account = account_id
        config.save(cfg, cfg_path)
        self.refresh()
        account = AccountStore().load().get(account_id)
        set_app_status(self, tr("account.msg.switched", account.username if account else account_id))
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
        # Disabling a button that holds focus hands focus to the next widget in the chain - here the
        # offline username box, which the user never clicked. Park it on the read-only code view
        # instead: that is where the device code shows up, and it has no focus outline in QSS.
        self.device_code.setFocus()
        self.ms_button.setEnabled(False)
        self.device_code.clear()
        set_app_status(self, tr("login.msg.waiting"))
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
            set_app_status(self, tr("login.msg.countdown", f"{minutes:02d}:{seconds:02d}"))
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
        set_app_status(self, tr("login.msg.ok"))
        self._save_account(account)

    def _on_error(self, message: str) -> None:
        self._stop_countdown()
        set_app_status(self, tr("login.msg.fail", message), "error")

    def offline_login(self) -> None:
        from launcher.config import offline_mode_allowed

        if not offline_mode_allowed():
            set_app_status(self, tr("launch.msg.offline_locked"), "warning")
            return
        try:
            account = create_offline_account(self.offline_edit.text())
        except ValueError as exc:
            set_app_status(self, tr("login.msg.fail", exc), "error")
            return
        self._save_account(account)
        set_app_status(self, tr("login.msg.offline_ok"))

    def logout(self) -> None:
        cfg, cfg_path = config.load()
        store = AccountStore()
        accounts = store.load()
        # Prefer logging out the account selected in the list, otherwise the current account
        target = self._selected_account_id() or cfg.selected_account
        if not target:
            set_app_status(self, tr("login.msg.no_account"))
            return
        accounts.pop(target, None)
        if cfg.selected_account == target:
            cfg.selected_account = None
        store.save(accounts)
        config.save(cfg, cfg_path)
        self.refresh()
        self.account_changed.emit()
        set_app_status(self, tr("login.msg.logged_out"))
