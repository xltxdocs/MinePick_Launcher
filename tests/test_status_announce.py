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

"""WCAG 4.1.3: status messages must reach assistive technology - and only then.

Qt has no live region, so a changed status line is invisible to a screen reader unless the
application announces it. These tests count the announcements: exactly one per distinct message,
none for a repeat, and severity-carrying messages included.

They also pin when *not* to announce. Sending the event with no reader attached buys nothing and
costs something real: Qt's Windows accessibility bridge turns Event.Alert into a system alert, and
Windows plays the alert sound for it either way - which is what made the launcher chime on startup,
on exit and during the first-run wizard. So the announcement goes out only while a screen reader is
actually running (QAccessible.isActive()), and the tests cover both sides of that switch.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QApplication

from gui.widgets import A11Y_ALERT_ENV, StatusLabel


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def announcements(monkeypatch):
    """Collect every accessibility update the label sends."""
    seen: list[tuple[object, object]] = []
    monkeypatch.setattr(
        QAccessible,
        "updateAccessibility",
        staticmethod(lambda event: seen.append((event.object(), event.type()))),
    )
    return seen


@pytest.fixture()
def reader_running(monkeypatch):
    """Pretend a screen reader is attached, which is what enables the announcements."""
    monkeypatch.setattr(QAccessible, "isActive", staticmethod(lambda: True))


@pytest.fixture()
def no_reader(monkeypatch):
    """The default on a machine with no assistive technology running."""
    monkeypatch.setattr(QAccessible, "isActive", staticmethod(lambda: False))


# ---------------------------------------------------------------- with a screen reader attached


def test_status_change_is_announced(app, announcements, reader_running):
    label = StatusLabel("")
    label.setText("正在下载")
    assert len(announcements) == 1
    assert announcements[0][0] is label
    assert announcements[0][1] == QAccessible.Event.Alert


def test_repeating_the_same_message_is_silent(app, announcements, reader_running):
    """Progress messages repeat; repeating the announcement would only talk over the reader."""
    label = StatusLabel("")
    label.setText("正在下载 3/10")
    label.setText("正在下载 3/10")
    label.setText("正在下载 3/10")
    assert len(announcements) == 1


def test_each_distinct_message_is_announced(app, announcements, reader_running):
    label = StatusLabel("")
    label.setText("正在下载 3/10")
    label.setText("正在下载 4/10")
    assert len(announcements) == 2


def test_errors_and_warnings_are_announced(app, announcements, reader_running):
    label = StatusLabel("")
    label.set_error("导入失败：文件损坏")
    label.set_warning("内存接近上限")
    assert len(announcements) == 2
    assert all(kind == QAccessible.Event.Alert for _obj, kind in announcements)


def test_clearing_the_status_is_silent(app, announcements, reader_running):
    """An empty status line is not a message; announcing it would be noise."""
    label = StatusLabel("准备就绪")
    announcements.clear()
    label.setText("")
    assert announcements == []


def test_same_text_after_an_error_is_announced_again(app, announcements, reader_running):
    """Returning to a message the user has already seen is still a state change."""
    label = StatusLabel("")
    label.set_error("失败")
    label.setText("准备就绪")
    label.set_error("失败")
    assert len(announcements) == 3


# ---------------------------------------------------------------- staying silent with no reader


def test_nothing_is_announced_without_a_reader(app, announcements, no_reader):
    """No screen reader: stay silent, because the event would still make Windows play a sound.

    The message itself must be unaffected - on screen, colourised by severity - and the
    once-per-message bookkeeping still runs.
    """
    label = StatusLabel("")
    label.setText("正在下载")
    assert announcements == []
    assert label.text() == "正在下载"
    assert label.current_level() == "info"

    label.set_error("导入失败")
    assert announcements == []
    assert label.text() == "导入失败"
    assert label.current_level() == "error"


def test_a_reader_that_starts_later_hears_the_next_message(app, announcements, no_reader, monkeypatch):
    """isActive() is consulted per message, so a reader started later still gets announcements."""
    label = StatusLabel("")
    label.setText("准备就绪")
    assert announcements == []

    monkeypatch.setattr(QAccessible, "isActive", staticmethod(lambda: True))
    label.setText("正在下载 1/10")
    assert len(announcements) == 1
    assert announcements[0][1] == QAccessible.Event.Alert


def test_the_escape_hatch_forces_silence_even_with_a_reader(app, announcements, reader_running, monkeypatch):
    """MCLAUNCHER_NO_A11Y_ALERT=1 is the emergency off switch: it wins over an active reader."""
    monkeypatch.setenv(A11Y_ALERT_ENV, "1")
    label = StatusLabel("")
    label.setText("正在下载")
    assert announcements == []
    assert label.text() == "正在下载"

    monkeypatch.delenv(A11Y_ALERT_ENV)
    label.setText("准备就绪")
    assert len(announcements) == 1


def test_the_escape_hatch_is_off_by_default(app, announcements, reader_running, monkeypatch):
    monkeypatch.delenv(A11Y_ALERT_ENV, raising=False)
    label = StatusLabel("")
    label.setText("正在下载")
    assert len(announcements) == 1
