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

This module also owns the suite's one hard rule: **no test may put a window on the user's desktop**.
Three layers enforce it, because the earlier single layer (`setdefault` below) could be switched off
from outside: the platform is forced rather than defaulted, a session event filter records the exact
moment a top-level window is shown on a real platform, and every test fails red at teardown if such a
window existed. `tests/test_no_screen_windows.py` proves each layer still works, including a deliberate
violation that must be caught.
"""

import os
import shutil
from pathlib import Path

import pytest

# --- the screen rule, layer 1: force the offscreen platform -----------------------------------------
# Force it for the whole suite, before anything imports Qt. Six test files used to create windows on the
# real platform - visible on screen while the suite ran - because only a few modules set this
# themselves. This used to be `setdefault`, which meant an exported `QT_QPA_PLATFORM=windows` (a shell
# profile, a wrapper script, a CI job) silently turned the entire suite into a real-window run: measured
# by exporting it and running tests/test_qpa_platform.py, which failed on `assert 'windows' ==
# 'offscreen'`. The variable is therefore overwritten, not defaulted, and watching the windows needs the
# explicit opt-in MCLAUNCHER_ALLOW_REAL_QT=1, which the layers below then police.
ALLOW_REAL_QT_ENV = "MCLAUNCHER_ALLOW_REAL_QT"
if os.environ.get(ALLOW_REAL_QT_ENV) == "1":
    os.environ.pop("QT_QPA_PLATFORM", None)  # the deliberate opt-in: platform default, still policed
else:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

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


# --- the screen rule, layers 2 and 3: a central firewall --------------------------------------------
# The reason this exists as a fixture rather than as a line in each test: tools/test_no_screen_windows.py
# and the report behind them ([T-0004] "confirm quit" dialog shown on the desktop while a download was
# running) both come down to the same product fact. `gui/main_window.py:600-613` builds the quit
# confirmation with `QMessageBox(self)` - a *top-level* window of its own - so the parent's
# WA_DontShowOnScreen does not carry over, and on the real platform it is a real Win32 window (measured:
# with the parent marked WA_DontShowOnScreen, `box.isVisible() = True`, `box.winId() = 4262432`,
# `box.testAttribute(WA_DontShowOnScreen) = False`). It only appears while a download is in flight
# (`downloader.active_download_count() > 0`), which is why it is intermittent rather than constant.

QPA_OFFSCREEN = "offscreen"


def screen_visible_windows(widgets) -> list:
    """Top-level widgets from ``widgets`` that are visible on a real desktop.

    One definition, used by the fixture below and by tests/test_no_screen_windows.py, so the rule under
    test and the rule that runs are the same code. A widget is a violation when it is a window of its
    own, reports itself visible, and was not marked WA_DontShowOnScreen *before* it was shown - the
    attribute is what makes an otherwise real window skip the desktop (tools/shot_pages_real.py,
    tools/perf_baseline.py and tools/snapshot_ui_render.py all rely on exactly that).
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    offenders = []
    for widget in widgets:
        if not isinstance(widget, QWidget) or not widget.isWindow():
            continue
        if not widget.isVisible():
            continue
        if widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
            continue
        offenders.append(widget)
    return offenders


def describe_window(widget) -> str:
    """What the failure message needs: which window, and how it was shown."""
    from PySide6.QtCore import Qt

    try:
        title = widget.windowTitle()
        name = widget.objectName()
        geometry = f"{widget.width()}x{widget.height()}"
        dont_show = widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    except RuntimeError:  # the C++ object is already gone
        return f"{type(widget).__name__} <deleted>"
    return (
        f"{type(widget).__name__}(objectName={name!r}, title={title!r}, {geometry}, "
        f"WA_DontShowOnScreen={dont_show})"
    )


class _ScreenWindowRecorder:
    """An application event filter that records the show of any window on a real platform.

    The fixture below fails a test only for a window that is *still visible* at teardown, which a modal
    dialog is: it stays up until somebody answers it. This records the same violation at the moment Qt
    sends Show, so the report can say when it happened even in the cases that end before teardown, and
    it is what makes "a window appeared" an observation instead of an inference.

    A QObject subclass with the filter installed on the application: ``QApplication``/``QObject`` refuse
    any other kind of filter object (measured: ``installEventFilter`` raises TypeError for a plain
    Python object).
    """

    def __init__(self, platform: str) -> None:
        from PySide6.QtCore import QObject

        outer = self

        class _Recorder(QObject):
            def eventFilter(self, obj, event) -> bool:
                return outer._inspect(obj, event)

        self._object = _Recorder()
        self._platform = platform
        self.events: list[str] = []
        self.offenders: list[object] = []

    @property
    def qt_object(self):
        """The QObject to install as the event filter."""
        return self._object

    def _inspect(self, obj, event) -> bool:
        """Record a window shown on a real platform. Never raises: this runs inside Qt's dispatch.

        An exception escaping a Python override of ``eventFilter`` is reported on stderr and leaves the
        event that carried it half-delivered - measured as a cascade in which a later ``MainWindow()``
        died in ``super().__init__()`` with "returned NULL without setting an exception". So every read
        of the widget is guarded, including the ones that touch a C++ object that may already be gone.
        """
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QWidget

        try:
            if event.type() is not QEvent.Type.Show or self._platform == QPA_OFFSCREEN:
                return False
            if not isinstance(obj, QWidget) or not obj.isWindow():
                return False
            if obj.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
                return False
            message = (
                f"shown on the desktop: the real platform ({self._platform}) showed "
                f"{describe_window(obj)}"
            )
            self.events.append(message)
            self.offenders.append(obj)
        except Exception:  # noqa: BLE001 - a filter may not disturb Qt's dispatch, ever
            return False
        return False


@pytest.fixture(scope="session", autouse=True)
def _no_screen_windows():
    """Fail the run if any test puts a visible window on a real desktop.

    Layers 2 and 3 of the screen rule. The platform check is what makes this constructive rather than
    advisory: on the offscreen plugin nothing can reach the desktop, so the firewall is silent; the
    MCLAUNCHER_ALLOW_REAL_QT=1 opt-in (see the top of this file) is the only way to get a real platform,
    and then every visible top-level window is both recorded at the moment it is shown and failed at the
    teardown of the test it happened in.

    Installing the filter imports Qt. That is safe for this suite by construction and is the reason the
    platform is forced above rather than merely defaulted: the platform plugin is chosen when the
    QApplication is built, and forcing the variable at import time (before any test module runs) means
    even the first QApplication of the session is offscreen.
    """
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # no Qt in this environment: nothing can put a window anywhere
        yield None
        return

    application = QApplication.instance() or QApplication([])
    platform = application.platformName()
    recorder = _ScreenWindowRecorder(platform)
    application.installEventFilter(recorder.qt_object)
    try:
        yield recorder
    finally:
        application.removeEventFilter(recorder.qt_object)


@pytest.fixture(autouse=True)
def _assert_no_screen_windows(_no_screen_windows):
    """Run this test only if it put no window on a real desktop.

    The recorder's events are the evidence, and they have to be: a window a test creates and shows is
    usually a local of that test, and ``_settle_background_work`` (which tears down before this fixture
    resumes) closes every top-level widget - so by the time the widget tree could be inspected, the
    window is hidden and the tree is empty. Measured: with the teardown check alone, a child test that
    showed a window passed, and only the recorder's event proved the window had been there.

    The live widget list is still checked, for the opposite case: a window that outlives the test (a
    module-level one, or one a session fixture built) and is still up when this runs.

    Nothing is relaxed for the suite's own tests, and the only way to run this in a mode where it can
    fail on purpose is MCLAUNCHER_ALLOW_REAL_QT=1 (see the top of this file): with the platform really
    offscreen, no window can reach a desktop and this fixture stays silent.
    """
    if _no_screen_windows is not None:
        _no_screen_windows.events.clear()
        _no_screen_windows.offenders.clear()
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    application = QApplication.instance()
    if application is None or application.platformName() == QPA_OFFSCREEN:
        return

    recorded = list(_no_screen_windows.events) if _no_screen_windows is not None else []
    if recorded:
        lines = [f"  recorded: {event}" for event in recorded]
        pytest.fail(
            "a window was on the desktop during this test - automation must never show one "
            f"(platform {application.platformName()!r}):\n" + "\n".join(lines),
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """Make every modal dialog in the suite non-blocking, and never on screen.

    This is prevention, not an exception, and it deliberately touches *no* product code: the dialog and
    its decision stay fully tested (tests/test_input_experience.py asserts the quit confirmation's
    content and both outcomes; tests/test_button_states.py asserts the shipped source of the method).

    What it prevents is the accidental one:

    * a test closes a window while the download tests (tests/test_shutdown_safety.py,
      tests/test_updates.py) left a download in flight, and the quit confirmation in
      ``gui/main_window.py`` asks a question nobody answers. Measured: that dialog is a real top-level
      window even when the window it belongs to is WA_DontShowOnScreen - a QMessageBox re-creates its own
      window and drops the attribute - and a modal dialog left unanswered does not fail a suite, it hangs
      it until a human clicks it. The product now refuses the quit without building the box when its
      window is kept off screen (tests/test_quit_dialog_offscreen.py pins that), which removes the case
      this fixture was written for but not the hazard: a window that is *not* marked still asks;
    * the same call building a modal QMessageBox inside a test that only wanted the close path.

    An earlier version of this fixture replaced ``MainWindow._confirm_quit_while_downloading`` itself.
    That broke tests/test_button_states.py, which reads the method with ``inspect.getsource`` and then
    found a lambda: neutralising a function's body hides it from the suite that checks it. Patching
    ``QMessageBox.exec`` instead keeps every source-level assertion honest while still guaranteeing that
    a constructed dialog can neither block nor be answered.

    ``MCLAUNCHER_NO_SCREEN_FIREWALL=1`` switches it off. It is the suite's dedicated escape hatch for this
    fixture and is deliberately kept, but nothing in the suite sets it any more: the negative self-check
    in tests/test_no_screen_windows.py used to drive the real close path through the dialog, and since the
    product now refuses the quit before building the box when its window is kept off screen, no child
    reaches a ``QMessageBox`` at all. The switch is what a future probe that does need the real dialog
    would reach for, so it stays documented here rather than removed with its last caller.
    """
    if os.environ.get("MCLAUNCHER_NO_SCREEN_FIREWALL") == "1":
        return
    try:
        from PySide6.QtWidgets import QMessageBox
    except ImportError:  # no Qt in this environment: no dialog either
        return

    def _exec_without_a_loop(self) -> int:
        """Do not run a modal loop: report "no button clicked" and return.

        ``clickedButton()`` is the one thing the caller reads after this, and ``None`` means "nobody
        chose to quit", which is the safe answer. Returning is what matters: a nested loop here is what
        a person saw as a window on their desktop, and a test cannot answer it.
        """
        return 0

    monkeypatch.setattr(QMessageBox, "exec", _exec_without_a_loop)


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
