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
application announces it. These tests count the announcements: one set per distinct message, none for
a repeat, and severity-carrying messages included.

One message travels on several carriers (``gui.widgets.A11Y_CHANNELS``) because a screen reader that
ignores one of them still hears another; the tests therefore count per carrier - "the label's name
changed" and "the announcement carries the sentence" - instead of pinning a total that only one
carrier can satisfy.

They also pin when *not* to announce: nothing at all is sent while no screen reader is running
(QAccessible.isActive()), and the tests cover both sides of that switch. The last two tests here are
the guard for the event that is never sent at all - the alert, which Qt's Windows bridge answers with
a system sound rather than with speech - because that noise is what this whole path was fixed for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtGui
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QApplication, QStatusBar

import gui
from gui.widgets import A11Y_ALERT_ENV, A11Y_CHANNELS, StatusLabel

# Qt 6.8 added the announcement event (QAccessibleAnnouncementEvent). The launcher allows
# PySide6 >= 6.6, so an older Qt skips that carrier - the tests follow the same switch as the code
# instead of assuming the Qt they happen to run on.
HAS_ANNOUNCEMENT = hasattr(QtGui, "QAccessibleAnnouncementEvent")

# The only event types a status message may ever leave on. Alert is deliberately absent: see the guard
# tests at the end of this file.
ALLOWED_EVENTS = {QAccessible.Event.NameChanged, QAccessible.Event.Announcement}

DOWNLOADING = "正在下载"


def carriers(announcements, kind):
    """Every event of one carrier: each carrier is counted on its own, none of them replaces another."""
    return [(obj, event_type) for obj, event_type in announcements if event_type == kind]


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


@pytest.fixture()
def hosted(app):
    """A status label hosted the way the main window hosts it: a child of a QStatusBar.

    This is what makes the status-bar carrier possible at all, so the tests that care about it build
    the same parent/child relation the window does instead of a bare label.
    """
    bar = QStatusBar()
    label = StatusLabel("")
    bar.addWidget(label)
    yield bar, label
    bar.close()
    bar.deleteLater()


# ---------------------------------------------------------------- with a screen reader attached


def test_status_change_is_announced(app, announcements, reader_running):
    """The label's own name change is the first thing sent - an alert is not sent at all."""
    label = StatusLabel("")
    label.setText(DOWNLOADING)
    assert announcements[0] == (label, QAccessible.Event.NameChanged)
    assert len(carriers(announcements, QAccessible.Event.NameChanged)) == 1
    # The message also leaves as the spoken announcement, and as nothing else.
    if HAS_ANNOUNCEMENT:
        assert len(carriers(announcements, QAccessible.Event.Announcement)) == 1


def test_every_carrier_of_a_hosted_status_line_is_used(app, announcements, reader_running, hosted):
    """One message, every carrier, in the order they are sent - none of them an alert."""
    bar, label = hosted
    label.setText(DOWNLOADING)

    expected = [
        (label, QAccessible.Event.NameChanged),
        (bar, QAccessible.Event.NameChanged),
    ]
    if HAS_ANNOUNCEMENT:
        expected.append((label, QAccessible.Event.Announcement))
    assert announcements == expected


def test_the_announcement_carries_the_message_itself(app, reader_running, hosted, monkeypatch):
    """The carrier a reader is asked to *speak* carries the sentence, not a pointer to it."""
    if not HAS_ANNOUNCEMENT:
        pytest.skip("this Qt has no QAccessibleAnnouncementEvent (Qt < 6.8)")
    seen: list[str] = []
    monkeypatch.setattr(
        QAccessible,
        "updateAccessibility",
        staticmethod(
            lambda event: seen.append(event.message())
            if event.type() == QAccessible.Event.Announcement
            else None
        ),
    )
    _bar, label = hosted
    label.set_error("导入失败：文件损坏")
    assert seen == ["导入失败：文件损坏"]


def test_the_status_bar_accessible_name_follows_the_message(app, reader_running, hosted):
    """The container is named after the message, which is what a reader announces on landing on it."""
    bar, label = hosted
    label.setText(DOWNLOADING)
    assert bar.accessibleName() == DOWNLOADING

    label.set_error("导入失败")
    assert bar.accessibleName() == "导入失败"

    label.setText("准备就绪")
    assert bar.accessibleName() == "准备就绪"


def test_a_label_without_a_status_bar_skips_only_that_carrier(app, announcements, reader_running):
    """A bare label (a page test, a render tool) still announces; only the container carrier is gone."""
    label = StatusLabel("")
    label.setText(DOWNLOADING)
    expected = [(label, QAccessible.Event.NameChanged)]
    if HAS_ANNOUNCEMENT:
        expected.append((label, QAccessible.Event.Announcement))
    assert announcements == expected


def test_repeating_the_same_message_is_silent(app, announcements, reader_running):
    """Progress messages repeat; repeating the announcement would only talk over the reader."""
    label = StatusLabel("")
    label.setText("正在下载 3/10")
    after_first = list(announcements)
    assert after_first  # the message did go out once
    label.setText("正在下载 3/10")
    label.setText("正在下载 3/10")
    assert announcements == after_first


def test_each_distinct_message_is_announced(app, announcements, reader_running):
    label = StatusLabel("")
    label.setText("正在下载 3/10")
    label.setText("正在下载 4/10")
    assert len(carriers(announcements, QAccessible.Event.NameChanged)) == 2
    if HAS_ANNOUNCEMENT:
        assert len(carriers(announcements, QAccessible.Event.Announcement)) == 2


def test_errors_and_warnings_are_announced(app, announcements, reader_running):
    label = StatusLabel("")
    label.set_error("导入失败：文件损坏")
    label.set_warning("内存接近上限")
    assert len(carriers(announcements, QAccessible.Event.NameChanged)) == 2
    if HAS_ANNOUNCEMENT:
        assert len(carriers(announcements, QAccessible.Event.Announcement)) == 2


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
    assert len(carriers(announcements, QAccessible.Event.NameChanged)) == 3


# ---------------------------------------------------------------- staying silent with no reader


def test_nothing_is_announced_without_a_reader(app, announcements, no_reader):
    """No screen reader: stay silent, because nothing is there to consume the announcement.

    The message itself must be unaffected - on screen, colourised by severity - and the
    once-per-message bookkeeping still runs.
    """
    label = StatusLabel("")
    label.setText(DOWNLOADING)
    assert announcements == []
    assert label.text() == DOWNLOADING
    assert label.current_level() == "info"

    label.set_error("导入失败")
    assert announcements == []
    assert label.text() == "导入失败"
    assert label.current_level() == "error"


def test_no_carrier_is_used_without_a_reader_and_the_bar_keeps_its_name(
    app, announcements, no_reader, hosted
):
    """The gate closes before the first carrier, so not even the container gets renamed."""
    bar, label = hosted
    bar.setAccessibleName("状态栏")
    label.setText(DOWNLOADING)
    label.set_error("导入失败")
    assert announcements == []
    assert bar.accessibleName() == "状态栏"


def test_a_reader_that_starts_later_hears_the_next_message(app, announcements, no_reader, monkeypatch):
    """isActive() is consulted per message, so a reader started later still gets announcements."""
    label = StatusLabel("")
    label.setText("准备就绪")
    assert announcements == []

    monkeypatch.setattr(QAccessible, "isActive", staticmethod(lambda: True))
    label.setText("正在下载 1/10")
    assert len(carriers(announcements, QAccessible.Event.NameChanged)) == 1
    if HAS_ANNOUNCEMENT:
        assert len(carriers(announcements, QAccessible.Event.Announcement)) == 1


def test_the_escape_hatch_forces_silence_even_with_a_reader(app, announcements, reader_running, monkeypatch):
    """MCLAUNCHER_NO_A11Y_ALERT=1 is the emergency off switch: it wins over an active reader."""
    monkeypatch.setenv(A11Y_ALERT_ENV, "1")
    label = StatusLabel("")
    label.setText(DOWNLOADING)
    assert announcements == []
    assert label.text() == DOWNLOADING

    monkeypatch.delenv(A11Y_ALERT_ENV)
    label.setText("准备就绪")
    assert len(carriers(announcements, QAccessible.Event.NameChanged)) == 1
    if HAS_ANNOUNCEMENT:
        assert len(carriers(announcements, QAccessible.Event.Announcement)) == 1


def test_the_escape_hatch_is_off_by_default(app, announcements, reader_running, monkeypatch):
    monkeypatch.delenv(A11Y_ALERT_ENV, raising=False)
    label = StatusLabel("")
    label.setText(DOWNLOADING)
    assert len(carriers(announcements, QAccessible.Event.NameChanged)) == 1


# ------------------------------------------- the guard: an alert event may never come back


def test_no_alert_event_can_come_back_through_any_status_path(app, announcements, reader_running):
    """No status path may send an alert - the one accessibility event Qt's Windows backend sounds.

    Qt calls PlaySound for exactly three events - PopupMenuStart, MenuCommand and QAccessible::Alert -
    and an alert on a widget that is not a QMessageBox plays the "SystemAsterisk" sound, reader
    attached or not (QWindowsUiaAccessibility::notifyAccessibilityUpdate). That sound is what made the
    launcher chime on startup, on exit and during the first-run wizard; and the alert reached no reader
    on Windows either, since that same backend does not forward it for static text. The announcement
    carries the message instead, and Qt never turns it into a sound.

    So this is not a style guard: re-adding an alert carrier brings the noise back. Every path that can
    announce anything is driven here; if this fails, remove the carrier - do not relax the test.
    """
    bar = QStatusBar()
    label = StatusLabel("")
    bar.addWidget(label)
    try:
        label.setText(DOWNLOADING)  # an ordinary message
        label.set_error("导入失败")  # a severity-carrying one
        label.set_warning("内存接近上限")
        label.setText("准备就绪")  # returning to an earlier message is still a change
        label.setText("准备就绪")  # a repeat is not
        label.setText("")  # clearing is not a message
        label.setText(DOWNLOADING)
    finally:
        bar.close()
        bar.deleteLater()

    kinds = [kind for _obj, kind in announcements]
    assert announcements, "nothing was announced: this guard would pass vacuously"
    assert QAccessible.Event.Alert not in kinds, [str(kind) for kind in kinds]
    assert set(kinds) <= ALLOWED_EVENTS, [str(kind) for kind in kinds]


def test_no_alert_event_can_creep_back_into_the_source():
    """The same guard for the paths nobody exercises: the string must be gone from the whole package.

    The runtime guard above can only catch what a test drives; this one fails the moment an alert
    event is written anywhere under ``gui/``, which is the hand-slip it exists for. A genuinely
    wanted alert (a real QMessageBox does have an icon and a matching sound) has to be a deliberate
    decision, and then this test is the place to say so.
    """
    assert "label_alert" not in A11Y_CHANNELS
    root = Path(gui.__file__).parent
    offenders = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if "Event.Alert" in path.read_text(encoding="utf-8")
    )
    assert offenders == [], f"an alert event is sent from: {offenders}"
