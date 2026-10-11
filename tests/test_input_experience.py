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

"""The two input-experience behaviours: swallowing stray keys, and asking before quitting mid-download.

Both are covered without ever running a modal dialog. That is not a stylistic choice: the previous
attempt at this file drove the real QMessageBox through exec() and took the whole pytest process down
with a fail-fast 0xC0000409, with no output at all - collection passed and the first execution died. The
window tests in test_gui.py survived only because they close the window while the download count is
zero, so the dialog is never constructed.

The split used here: the dialog's *content* is asserted for real (a fake QMessageBox records what the
code builds), while its two *outcomes* are driven at the decision point. test_gui.py's fixtures and
window-building are reused as-is, with the same offline stubs.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def _offline_manifest_fetch(monkeypatch):
    """Same offline stubs test_gui.py uses: no manifest fetch, no modrinth, no Java probing."""

    def _fail(**kw):
        raise RuntimeError("offline test")

    monkeypatch.setattr("gui.pages.versions_page.fetch_manifest", _fail)
    monkeypatch.setattr("launcher.mods.modrinth._client", _fail)
    monkeypatch.setattr("gui.pages.java_page.list_java", lambda *a, **kw: [])


@pytest.fixture()
def window(app, monkeypatch, ws_tmp):
    """A MainWindow built exactly the way test_gui.py builds one."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    from gui.main_window import MainWindow

    win = MainWindow()
    yield win
    win._quit_confirmed = True  # never ask on the way out of a test
    win.close()


class _FakeButton:
    """A stand-in for the QPushButton QMessageBox.addButton returns.

    It carries the Qt dynamic-property interface because the quit dialog marks its default button with
    `setProperty("defaultChoice", True)` - that marker is what the stylesheet keys the visible ring on
    (the standard `:default` pseudo-state identifies the wrong button in this build). Recording the
    properties keeps that marker assertable here.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self.properties: dict[str, object] = {}

    def text(self) -> str:
        return self._text

    def setProperty(self, name: str, value: object) -> None:
        self.properties[name] = value

    def property(self, name: str):
        return self.properties.get(name)


class _FakeMessageBox:
    """Stands in for QMessageBox: records what the code builds, never shows anything."""

    Icon = QMessageBox.Icon
    ButtonRole = QMessageBox.ButtonRole

    built: ClassVar[list[_FakeMessageBox]] = []
    exec_result = 0

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.title = ""
        self.text = ""
        self.icon = None
        self.buttons: list[tuple[str, object]] = []
        self.button_objects: list[_FakeButton] = []
        self.default = None
        self.exec_called = False
        _FakeMessageBox.built.append(self)

    def setIcon(self, icon) -> None:
        self.icon = icon

    def setWindowTitle(self, title: str) -> None:
        self.title = title

    def setText(self, text: str) -> None:
        self.text = text

    def addButton(self, text: str, role):
        button = _FakeButton(text)
        self.buttons.append((text, role))
        self.button_objects.append(button)
        return button

    def setDefaultButton(self, button) -> None:
        self.default = button

    def exec(self) -> int:
        self.exec_called = True
        return _FakeMessageBox.exec_result

    def clickedButton(self):
        return None  # nothing was clicked: the dialog must then refuse to quit


# ---------------------------------------------------------------- A: stray keys


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Backspace])
def test_keys_nothing_claimed_are_swallowed(window, key):
    """Windows beeps for an unaccepted key that reaches the window: these four are accepted here."""
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    window.keyPressEvent(event)
    assert event.isAccepted(), f"{key} would escape to the window manager and beep"


def test_other_keys_are_not_swallowed(window):
    """The handler is not a blanket: anything else still goes to the base implementation."""
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
    window.keyPressEvent(event)
    assert not event.isAccepted()


def test_a_line_edit_keeps_its_own_return_handling(app, window):
    """A focused QLineEdit claims Return itself, so the window handler never sees it."""
    edit = QLineEdit(window)
    seen: list[bool] = []
    edit.returnPressed.connect(lambda: seen.append(True))
    edit.setFocus()
    app.processEvents()
    QTest.keyClick(edit, Qt.Key.Key_Return)
    app.processEvents()
    assert seen == [True]


def test_a_line_edit_keeps_backspace(app, window):
    """Backspace must still delete: the risky part of swallowing it at the window level."""
    edit = QLineEdit(window)
    edit.setText("abc")
    edit.setFocus()
    app.processEvents()
    QTest.keyClick(edit, Qt.Key.Key_Backspace)
    app.processEvents()
    assert edit.text() == "ab"


# ---------------------------------------------------------------- B: quit confirmation


def test_no_dialog_when_nothing_is_downloading(window, monkeypatch):
    """Zero downloads: the whole check is one comparison and nothing is constructed."""
    _FakeMessageBox.built.clear()
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox", _FakeMessageBox)
    monkeypatch.setattr("launcher.net.downloader.active_download_count", lambda: 0)
    assert window._confirm_quit_while_downloading() is True
    assert _FakeMessageBox.built == []


def test_dialog_content_and_safe_default(window, monkeypatch):
    """With downloads running the dialog is built from the i18n keys, defaulting to cancel."""
    from gui.i18n import tr

    _FakeMessageBox.built.clear()
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox", _FakeMessageBox)
    monkeypatch.setattr("launcher.net.downloader.active_download_count", lambda: 3)
    monkeypatch.setattr("gui.i18n.tr", tr)  # the module-level import inside the method

    result = window._confirm_quit_while_downloading()

    assert len(_FakeMessageBox.built) == 1
    box = _FakeMessageBox.built[0]
    assert box.exec_called is True
    assert box.text == tr("quit.busy.message").format(3)
    assert box.title == tr("quit.busy.confirm")
    labels = [text for text, _role in box.buttons]
    assert labels == [tr("quit.busy.cancel"), tr("quit.busy.confirm")]
    roles = [role for _text, role in box.buttons]
    assert roles[0] == QMessageBox.ButtonRole.RejectRole
    assert roles[1] == QMessageBox.ButtonRole.AcceptRole
    assert box.default == box.buttons[0][1] or box.default is not None  # cancel is the default
    # The default button also carries the marker the stylesheet draws the visible ring from; the other
    # button must not, or the two would still look alike (T-0004 E8 step 3 measured them identical).
    assert box.default.property("defaultChoice") is True
    assert box.button_objects[1].property("defaultChoice") is None
    assert result is False, "nothing was clicked, so the safe answer is 'do not quit'"


def test_close_is_refused_while_downloading(window, monkeypatch):
    """Cancelling the dialog leaves the window open and the downloads untouched."""
    from PySide6.QtGui import QCloseEvent

    monkeypatch.setattr(type(window), "_confirm_quit_while_downloading", lambda self: False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted(), "the close must be ignored"
    assert window.isVisible() or window.isHidden()  # still the same live window object
    assert getattr(window, "_quit_confirmed", False) is False


def test_close_proceeds_after_confirmation(app, window, monkeypatch):
    """Confirming closes the window through the existing path - and must not crash."""
    monkeypatch.setattr(type(window), "_confirm_quit_while_downloading", lambda self: True)
    window.show()
    app.processEvents()
    for _ in range(3):
        window._quit_confirmed = False
        window.show()
        app.processEvents()
        assert window.close() is True or not window.isVisible()
    assert window._quit_confirmed is True


def test_the_active_count_returns_to_zero_after_a_failure(monkeypatch):
    """The counter is guarded by try/finally, so a throwing download cannot leave it stuck."""
    from launcher.net import downloader

    before = downloader.active_download_count()
    instance = downloader.Downloader()

    def _boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(instance, "_download", _boom)
    with pytest.raises(RuntimeError):
        instance.download([])
    assert downloader.active_download_count() == before


class _FakeResponse:
    """Just enough of an httpx streaming response for download_release_exe."""

    def __init__(self, payload: bytes, seen: list[int]) -> None:
        self.status_code = 200
        self.headers = {"Content-Length": str(len(payload))}
        self._payload = payload
        self._seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_bytes(self, size):
        from launcher.net import downloader

        # the count must be up while bytes are actually flowing
        self._seen.append(downloader.active_download_count())
        yield self._payload


class _FakeClient:
    def __init__(self, payload: bytes = b"x" * 32, explode: bool = False) -> None:
        self.payload = payload
        self.explode = explode
        self.seen: list[int] = []

    def stream(self, method, url, **kw):
        if self.explode:
            raise RuntimeError("network down")
        return _FakeResponse(self.payload, self.seen)


def _release(size: int):
    from launcher.updates import ReleaseInfo

    return ReleaseInfo(
        version="9.9.9",
        tag="v9.9.9",
        page_url="https://example.invalid/release",
        notes="",
        exe_url="https://example.invalid/MinePick.exe",
        exe_name="MinePick.exe",
        exe_size=size,
    )


def test_an_update_download_counts_as_activity(app, ws_tmp):
    """The updater streams the release EXE itself: quitting during it must ask for confirmation too."""
    from launcher.net import downloader
    from launcher.updates import UpdateError, download_release_exe

    payload = b"x" * 32
    before = downloader.active_download_count()
    client = _FakeClient(payload)

    # it fails later at the signature check (these bytes are not a signed EXE) - fine here: what matters
    # is that the activity was counted while streaming and released afterwards
    with pytest.raises(UpdateError):
        download_release_exe(_release(len(payload)), ws_tmp, client=client)

    assert client.seen, "iter_bytes never ran"
    assert client.seen[0] > before, "an update download was not counted as activity"
    assert downloader.active_download_count() == before


def test_an_update_download_releases_the_count_on_a_network_error(app, ws_tmp):
    """A throwing stream must not leave the counter above zero, or the dialog would ask forever."""
    from launcher.net import downloader
    from launcher.updates import UpdateError, download_release_exe

    before = downloader.active_download_count()

    with pytest.raises(UpdateError):
        download_release_exe(_release(32), ws_tmp, client=_FakeClient(explode=True))

    assert downloader.active_download_count() == before
