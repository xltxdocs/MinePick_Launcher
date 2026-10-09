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

"""WCAG 4.1.3: status messages must reach assistive technology.

Qt has no live region, so a changed status line is invisible to a screen reader unless the
application announces it. These tests count the announcements: exactly one per distinct message,
none for a repeat, and severity-carrying messages included.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QApplication

from gui.widgets import StatusLabel


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


def test_status_change_is_announced(app, announcements):
    label = StatusLabel("")
    label.setText("正在下载")
    assert len(announcements) == 1
    assert announcements[0][0] is label
    assert announcements[0][1] == QAccessible.Event.Alert


def test_repeating_the_same_message_is_silent(app, announcements):
    """Progress messages repeat; repeating the announcement would only talk over the reader."""
    label = StatusLabel("")
    label.setText("正在下载 3/10")
    label.setText("正在下载 3/10")
    label.setText("正在下载 3/10")
    assert len(announcements) == 1


def test_each_distinct_message_is_announced(app, announcements):
    label = StatusLabel("")
    label.setText("正在下载 3/10")
    label.setText("正在下载 4/10")
    assert len(announcements) == 2


def test_errors_and_warnings_are_announced(app, announcements):
    label = StatusLabel("")
    label.set_error("导入失败：文件损坏")
    label.set_warning("内存接近上限")
    assert len(announcements) == 2
    assert all(kind == QAccessible.Event.Alert for _obj, kind in announcements)


def test_clearing_the_status_is_silent(app, announcements):
    """An empty status line is not a message; announcing it would be noise."""
    label = StatusLabel("准备就绪")
    announcements.clear()
    label.setText("")
    assert announcements == []


def test_same_text_after_an_error_is_announced_again(app, announcements):
    """Returning to a message the user has already seen is still a state change."""
    label = StatusLabel("")
    label.set_error("失败")
    label.setText("准备就绪")
    label.set_error("失败")
    assert len(announcements) == 3
