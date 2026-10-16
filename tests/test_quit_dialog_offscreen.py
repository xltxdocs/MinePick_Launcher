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

"""The quit confirmation must not be built at all when its window is kept off screen.

Why this file exists. ``gui/main_window.py`` asked "quit while a download is running?" with a
``QMessageBox``. That box is a top-level window of its own, so it does not inherit its parent's
``WA_DontShowOnScreen``: with the parent marked, the box was a real window (the report measured
``box.isVisible() = True``, ``winId = 4262432``, ``testAttribute(WA_DontShowOnScreen) = False``), and it
only appeared while a download was in flight, which is why it was intermittent.

Carrying the attribute onto the box does not fix it. Measured on this Qt/Windows build by asking the OS
about the box's own handle (``IsWindowVisible``):

  * a plain ``QWidget`` with ``WA_DontShowOnScreen`` set is *not* visible     -> the attribute works;
  * a ``QMessageBox`` with the same attribute set *is* visible               -> it does not, because the
    box re-creates its own window and drops the attribute.

Making the box a child (``setWindowFlag(Qt.WidgetType.Widget)``) does not help either - measured visible
as well. So the fix is to not build the box when there is nobody to ask: the window is kept off screen,
which is exactly the case for the render tools and this suite, and refusing the quit is the same
conservative answer the dialog gives when nothing is clicked.

These tests pin both halves: the off-screen window must skip the question (and must not block), and a
normal window must still ask it, so only the one branch changed.
"""

from __future__ import annotations

import logging

import pytest


@pytest.fixture()
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def asking_quit(monkeypatch, ws_tmp):
    """A real MainWindow with a download in flight, plus a non-blocking stand-in for the dialog.

    ``QMessageBox`` is patched on the module object ``gui/main_window.py`` imports from, so the product
    code path is unchanged and only ``exec`` is replaced: a modal loop here would hang the suite, which
    is the same hazard the dialog itself carries. Each constructed box is recorded, so "was the question
    asked?" is readable after the call.
    """
    from PySide6 import QtWidgets as widgets
    from PySide6.QtWidgets import QMessageBox

    from gui.main_window import MainWindow
    from launcher.net import downloader

    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.setattr(downloader, "active_download_count", lambda: 2)
    assert downloader.active_download_count() == 2, "the download state was not set up"

    made: list[QMessageBox] = []

    class _RecordingBox(QMessageBox):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

        def exec(self) -> int:
            return 0  # "no button clicked": the caller must refuse the quit

    monkeypatch.setattr(widgets, "QMessageBox", _RecordingBox)

    window = MainWindow()
    try:
        yield window, made
    finally:
        window.close()
        window.deleteLater()


def test_an_offscreen_window_does_not_build_the_quit_dialog(asking_quit, app, caplog):
    """The marked branch: no dialog, no block, no window - and the skip is logged, never silent."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    window, made = asking_quit
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    for _ in range(4):
        app.processEvents()
    assert window.isVisible() is True, "the window was not shown, so this proves nothing"
    assert window._ancestor_is_kept_off_screen() is True, "the marker was not found on the window itself"

    toplevels_before = len(QApplication.topLevelWidgets())
    with caplog.at_level(logging.INFO, logger="gui.main_window"):
        allowed = window._confirm_quit_while_downloading()

    assert allowed is False, (
        "an off-screen window was allowed to quit: with nobody to answer the question the conservative "
        "answer is to refuse, which is also what the dialog returns when nothing is clicked"
    )
    assert made == [], (
        f"the quit dialog was built for an off-screen window: {made!r}. It is a top-level window of its "
        f"own and a QMessageBox does not honour WA_DontShowOnScreen, so building it is what put a real "
        f"dialog on the desktop"
    )
    assert len(QApplication.topLevelWidgets()) == toplevels_before, (
        "a new top-level widget appeared during the close path"
    )
    messages = [record.getMessage() for record in caplog.records if record.name == "gui.main_window"]
    assert any("skipped" in message and "WA_DontShowOnScreen" in message for message in messages), (
        f"the skip was not logged, so it is silent: {messages}"
    )
    assert any("2 download" in message for message in messages), (
        f"the log line does not say why: {messages}"
    )


def test_a_marked_parent_above_the_window_is_found(asking_quit):
    """The marker lives on the window that was marked; a lookup that only read the window would miss it."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    window, _made = asking_quit
    assert window._ancestor_is_kept_off_screen() is False, "an unmarked window read as marked"

    parent = QWidget()
    parent.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.setParent(parent, Qt.WindowType.Window)
    try:
        assert window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen) is False, (
            "the window itself is marked, so this case is not testing the walk up the tree"
        )
        assert window._ancestor_is_kept_off_screen() is True, (
            "a marker on a parent window was not found - the dialog would still be built there"
        )
    finally:
        window.setParent(None)
        parent.deleteLater()


def test_a_normal_window_still_asks_the_question(asking_quit, app):
    """The negative control: an ordinary window keeps the dialog, its text and its safe default."""
    from gui.i18n import tr

    window, made = asking_quit
    window.show()  # not marked: this is what every real user has
    for _ in range(4):
        app.processEvents()
    assert window._ancestor_is_kept_off_screen() is False

    allowed = window._confirm_quit_while_downloading()

    assert len(made) == 1, f"the quit dialog was not built for a normal window: {made!r}"
    box = made[0]
    assert box.windowTitle() == tr("quit.busy.confirm"), box.windowTitle()
    assert box.text() == tr("quit.busy.message").format(2), box.text()
    assert allowed is False, (
        "the stand-in returns 'no button clicked', which must refuse the quit - if this is True the "
        "product would quit on an unanswered question"
    )
    # Role order, not insertion order - measured: buttons() returns AcceptRole first, so the two labels
    # are compared as a set and the *default* is what pins down which one is the safe choice.
    labels = sorted(button.text() for button in box.buttons())
    assert labels == sorted([tr("quit.busy.cancel"), tr("quit.busy.confirm")]), labels
    assert box.defaultButton() is not None and box.defaultButton().text() == tr("quit.busy.cancel"), (
        "the safe choice is no longer the default one"
    )


def test_an_offscreen_close_does_not_block(asking_quit, app):
    """Driving the real close path off screen must return, not sit in a modal loop with nobody to answer.

    The stand-in above is deliberately *not* used here: ``exec`` is left alone, so if the off-screen
    branch ever stopped being taken this test would hang rather than pass. It is bounded by the suite's
    own timeout behaviour, which is the point - a hang is the failure being ruled out.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    window, _made = asking_quit
    original_exec = QMessageBox.exec

    calls: list[str] = []

    def _must_not_run(self) -> int:  # pragma: no cover - running it is the failure
        calls.append("exec")
        return original_exec(self)

    QMessageBox.exec = _must_not_run
    try:
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        for _ in range(4):
            app.processEvents()
        window.close()  # the product's own close path, with a download in flight
        for _ in range(4):
            app.processEvents()
    finally:
        QMessageBox.exec = original_exec

    assert calls == [], (
        "the off-screen close path entered QMessageBox.exec(): with nobody to answer, that is the modal "
        "loop a person saw as a window on the desktop, and it does not return on its own"
    )
    assert window.isVisible() is True, "the refused close did not leave the window up"
