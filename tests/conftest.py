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

"""pytest shared fixtures.

Note: this development sandbox locks writes inside mkdtemp-style (random-suffix) directories,
so it provides an ordinary mkdir directory via ws_tmp instead of pytest's built-in tmp_path.
"""

import os
import shutil
from pathlib import Path

import pytest

# Force the offscreen platform for the whole suite, before anything imports Qt. Six test files used to
# create windows on the real platform - visible on screen while the suite ran - because only a few
# modules set this themselves. `setdefault` keeps a deliberate override working
# (`QT_QPA_PLATFORM=windows pytest ...` when someone actually wants to watch the windows).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

WORK_DIR = Path(__file__).resolve().parent / ".work"
_counter = 0


@pytest.fixture()
def ws_tmp():
    """A writable ordinary temporary directory inside the workspace (function-scoped, auto-cleaned)."""
    global _counter
    WORK_DIR.mkdir(exist_ok=True)
    d = WORK_DIR / f"case{_counter:03d}"
    _counter += 1
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_startup_update_check(monkeypatch):
    """Keep the tests off the network and off slow real IO.

    Building the main window schedules an update check a couple of seconds later, and the Java page
    probes the machine for runtimes: both start workers that can outlive a closed window, which is
    the crash class described in the standard process document ([P9] - measured as 0xC0000005 inside
    ``launcher/java/locate.py`` from a worker while a test was tearing down). The real code paths stay
    covered by tests/test_updates.py and tests/test_locate.py.
    """
    monkeypatch.setattr("gui.pages.about_page.AboutPage.auto_check_on_start", lambda self: None)
    monkeypatch.setattr("gui.pages.java_page.list_java", lambda *args, **kwargs: [])


@pytest.fixture(autouse=True)
def _settle_background_work():
    """Let the worker pool finish, then destroy this test's windows - on the main thread.

    Two crash classes are covered, both recorded on Windows.

    The first is a test ending while a QThreadPool job from an earlier test was still running, so Qt
    later touched widgets that had already been destroyed (0xC0000005 at a fixed offset inside
    Qt6Widgets.dll). Draining the pool and flushing the event queue removes that overlap.

    The second is why the windows are closed and deleted here. A test that builds a window and lets the
    fixture go leaves a QWidget whose wrapper is unreachable but whose C++ object is still alive. That
    object is destroyed whenever some thread next collects garbage - and if that collection lands on a
    download worker thread, Qt destroys a widget off the GUI thread, which is undefined behaviour.
    Measured with gc.DEBUG_SAVEALL across the GUI test files: 1209 Qt wrappers with no C++ object behind
    them (QPushButton, QLabel, QLineEdit, entire QStackedWidget trees), every one of them a landmine of
    that kind. Destroying them here means those destructors run on the main thread, where they are legal.

    What this deliberately does not do is call gc.collect() per test. That was tried and made things
    worse - 476 errors in one run, with the crash moving into a fixture - because it reclaims objects
    that tests still expect to be alive. sendPostedEvents with DeferredDelete is the documented way to
    make deleteLater() actually happen, and it leaves everything else alone.
    """
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
        from PySide6.QtWidgets import QApplication
    except ImportError:  # no Qt in this environment: nothing to drain
        return
    QThreadPool.globalInstance().waitForDone(5000)
    application = QApplication.instance()
    if application is None:
        return
    application.processEvents()
    for widget in application.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
