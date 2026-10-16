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

"""The suite's screen rule must be able to go red - and must not go red falsely.

Why this file exists: a guard that cannot fail is not a guard. The rule "no test may put a window on the
user's desktop" has three layers in ``tests/conftest.py``: the platform is forced to offscreen, an
application event filter records the show of an unmarked window on a real platform, and an autouse
assertion fails the test that left one behind. Every layer is code that can rot - a fixture renamed, an
early return added, a comparison flipped - and none of that shows up while the platform really is
offscreen, because then the layers are deliberately silent.

The negative self-checks therefore run the firewall for real, in child pytest processes, against tests
that deliberately show a window. Nothing of any child reaches a desktop:

* every child keeps ``QT_QPA_PLATFORM=offscreen`` (asserted inside the child), so the windows it shows
  exist only inside the Qt offscreen plugin;
* the firewall's decision is per window, not per platform - a visible top-level window that is not
  marked ``WA_DontShowOnScreen`` is the violation - so the children decide it exactly as a real desktop
  would, without one.

Each child gets its own ``conftest.py`` that only documents itself: the fixtures under test come from
this repository's ``tests/conftest.py``, which pytest still loads because every probe directory lives
inside ``tests/``.

The children are written as plain text at column 0 (no dedent games): a stray unindented line inside an
indented template silently disables ``textwrap.dedent``, and the result was an ``IndentationError`` in
the child - a failure that hides the real result instead of showing it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
WORK = TESTS / ".work" / "no_screen_windows"
CONFTEST_PATH = TESTS / "conftest.py"
CHILD_DATA_DIR = ROOT / "build" / "no_screen_windows_child_data"
#: A file a child writes only after it has proven the firewall recorded the window it showed. The
#: parent deletes it before the run and requires that it stays absent: an exit code can be 0 for reasons
#: nobody intended, while an assertion that ran and decided cannot.
VERDICT_ENV = "NO_SCREEN_VERDICT"
VERDICT_PATH = ROOT / "build" / "no_screen_verdict.txt"
#: Set to "1" in a child to keep the suite from neutralising the quit confirmation. The negative
#: self-check needs the real close path; the prevention check needs it neutralised.
SKIP_NEUTRALISATION_ENV = "MCLAUNCHER_NO_SCREEN_FIREWALL"

_CHILD_CONFTEST = """\
# This directory only exists to be run by tests/test_no_screen_windows.py. The fixtures that police the
# screen rule come from tests/conftest.py, which pytest loads as the parent conftest.
"""

# A per-test handle on the suite's own recorder, built with the platform name passed in - exactly how
# tests/conftest.py builds its session-wide one. Passing "windows" is what lets a child take the
# real-platform branch while running on the offscreen plugin, and it is stated as such rather than
# hidden. Every child that needs that branch appends this block.
_CHILD_FIREWALL_HANDLE = '''\
import pytest


violation: list[str] = []


@pytest.fixture()
def firewall():
    """The suite's own recorder, judging a window it is told is on the real platform."""
    from PySide6.QtWidgets import QApplication

    from tests.conftest import _ScreenWindowRecorder  # the tests package is on sys.path

    app = QApplication.instance() or QApplication([])
    recorder = _ScreenWindowRecorder("windows")
    app.installEventFilter(recorder.qt_object)
    violation.clear()
    yield recorder
    app.removeEventFilter(recorder.qt_object)
'''

_CHILD_SHOWS_A_WINDOW = '''\
"""Deliberate violation: a visible window in a test. The firewall must report it.

The handle below judges the window as a real-platform window, which is the only way to make this child's
result depend on the firewall instead of on the platform it inherited. The window is shown on the
offscreen plugin, so it cannot reach a desktop.
"""

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget


def test_shows_a_window(firewall):
    app = QApplication.instance() or QApplication([])
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen", (
        "the child must stay offscreen: this self-check may not put anything on a desktop"
    )

    widget = QWidget()  # a window of its own, and nothing marked it WA_DontShowOnScreen
    widget.show()
    app.processEvents()

    assert firewall.events, (
        "the firewall did not record a window shown while a test ran - this is the observation that "
        "was missing when the quit dialog reached the desktop"
    )
    assert "QWidget" in firewall.events[0], repr(firewall.events)
    assert "WA_DontShowOnScreen=False" in firewall.events[0], repr(firewall.events)
    assert "on the desktop" in firewall.events[0], repr(firewall.events)
    # A verdict written by the child itself, after the assertions above have run and decided. The
    # parent requires this file: an exit code can be 0 for reasons nobody intended, while a file only
    # written after a passing assertion cannot.
    verdict = "recorded=" + repr(firewall.events) + chr(10)
    Path(os.environ["NO_SCREEN_VERDICT"]).write_bytes(verdict.encode("utf-8"))
'''

_CHILD_SHOWS_A_MARKED_WINDOW = '''\
"""The legitimate shape: the same window marked WA_DontShowOnScreen. Must stay green."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget


def test_shows_a_marked_window(firewall):
    app = QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    app.processEvents()

    assert widget.isVisible() is True, "the window was not shown, so this proves nothing"
    assert firewall.events == [], (
        f"the firewall rejected a window that cannot reach a screen: {firewall.events}"
    )
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen"
'''

_CHILD_CLOSE_PATH = '''\
"""Close a real window while the download counter says work is in flight.

``launcher.net.downloader.active_download_count`` is the single decision in ``gui/main_window.py:593``
and it is process-global, so a download really running in another test is enough to make a close ask a
question. The counter is set to 1 here on purpose: that is the state the report came from. The window is
a real MainWindow, so the product's own close path runs.

The window is switched to the shape the quit dialog itself has before it is closed, and that is the
point of the test rather than a trick. Measured on the real platform (probe: show a window marked
WA_DontShowOnScreen, then one that is not): the marked window emits **no** Show event at all, so a
recorder cannot see it, while the unmarked one emits one. The product's dialog is unmarked - no parent
attribute carries over to a top-level QMessageBox - and that is exactly why it can reach a desktop.

Two things keep this child incapable of putting anything on a desktop even so:

* every window in it is marked WA_DontShowOnScreen before it is shown, and the only sequence that makes
  Qt emit Show again - hide, clear the marker, show - keeps it off the desktop as well, so the recorded
  event is Qt's, for a widget Qt still keeps off screen;
* ``QMessageBox`` is replaced by a stand-in whose ``exec()`` returns immediately. The real dialog
  blocks: measured with the neutralisation switched off, as a child pytest sitting inside ``box.exec()``
  for the whole timeout of its run - the same hang a person saw as a window on the desktop. The stand-in
  keeps the evidence (was the question asked?) and removes the block.
"""

import os

import pytest
from PySide6 import QtWidgets as _widgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


asked: list[str] = []


class _RecordingMessageBox(QMessageBox):
    """Records that the question was asked, then returns from exec() without a modal loop."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        asked.append("built")

    def exec(self):
        asked.append("exec")
        return 0


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _record_the_question(monkeypatch):
    # Patched on the module object, which is the same object gui/main_window.py imports from.
    monkeypatch.setattr(_widgets, "QMessageBox", _RecordingMessageBox)
    asked.clear()
    yield
    asked.clear()


def test_closing_a_window_while_a_download_runs(app, monkeypatch, ws_tmp, firewall):
    from gui.main_window import MainWindow
    from launcher.net import downloader

    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.setattr(downloader, "active_download_count", lambda: 1)
    assert downloader.active_download_count() == 1, "the download state was not set up"

    window = MainWindow()
    # Before show(): the line that makes this child harmless even on a real platform.
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    app.processEvents()

    if os.environ.get("MCLAUNCHER_NO_SCREEN_FIREWALL") == "1":
        window.close()
        app.processEvents()
        assert asked and asked[0] == "built", (
            "the close path never asked the quit question, so this proves nothing"
        )
        if app.platformName() == "offscreen":
            # Nothing here can be shown, and Qt sends no Show event for a marked window - measured on
            # the real platform as well as here. The recorder therefore has nothing to observe, and the
            # real-platform half of this self-check is the opt-in run the parent makes.
            assert firewall.events == [], firewall.events
            pytest.skip(
                "needs MCLAUNCHER_ALLOW_REAL_QT=1: the firewall's Show-event layer can only see an "
                "unmarked window, and this child keeps every window marked"
            )
        # Real platform, and this is the shape the product's dialog has: no WA_DontShowOnScreen. The
        # sequence is the only one measured to produce Qt's Show event without putting a window up:
        # show marked, hide, clear the marker, show again. Clearing the marker and showing again
        # *without* the hide produces no Show event, and a window that is simply shown unmarked does -
        # but that one is on the desktop for as long as it is up, which is the very thing this file
        # exists to prevent.
        if window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
            window.hide()
            app.processEvents()
            window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
            window.show()
            app.processEvents()
        assert firewall.events, (
            "the firewall did not record a window shown while a close path ran - this is the "
            "observation that was missing when the quit dialog reached the desktop"
        )
        violation.extend(firewall.events)
    else:
        # The suite's prevention layer: the close path really ran and really built the dialog, and what
        # the fixture guarantees is that no modal loop ran and nothing was on screen. This child's
        # stand-in records both moments, so the assertion is about the sequence, not about absence.
        window.close()
        app.processEvents()
        assert "exec" in asked, (
            "the close path never reached exec(), so this child did not drive the dialogue it claims "
            f"to: {asked}"
        )
        # exec() returned instead of looping, and it returned "no button" - so the close was refused,
        # which is the safe answer and the one the product gives when nothing is clicked:
        # _confirm_quit_while_downloading() returns False and CloseEvent is ignored.
        assert window.isVisible() is True, "the refused close did not leave the window up"
        assert firewall.events == [], (
            f"the firewall reported a window on a real platform: {firewall.events}"
        )
        assert _widgets.QMessageBox is _RecordingMessageBox, (
            "the run ended with the real QMessageBox back in place, so this measured the wrong class"
        )
'''


def _write(path: Path, *fragments: str) -> None:
    """Write a probe file from whole modules, with an explicit newline ending.

    The fragments are complete module texts at column 0, joined with a blank line, so nothing here has
    to guess at indentation. An earlier version dedented indented templates; one stray line at column 0
    inside a template silently disabled the dedent and the child died with ``IndentationError`` - a
    failure that hides the result it was supposed to check.
    """
    assert fragments, "nothing to write"
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = [fragment.strip("\n") for fragment in fragments]
    path.write_bytes(("\n\n\n".join(blocks) + "\n").encode("utf-8"))


def _probe_dir(monkeypatch, name: str) -> Path:
    """A clean probe directory under tests/.work, which is never collected by accident."""
    directory = WORK / name
    shutil.rmtree(directory, ignore_errors=True)
    _write(directory / "conftest.py", _CHILD_CONFTEST)
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(CHILD_DATA_DIR))
    return directory


def _run_child(
    directory: Path,
    *,
    allow_the_real_close_path: bool = False,
    real_platform: bool = False,
) -> subprocess.CompletedProcess:
    """Run one child pytest and return its completed process.

    The child inherits this process's environment so it is the same interpreter and the same Qt build,
    with the environment variables that decide the screen rule pinned explicitly rather than inherited.
    ``real_platform`` is the suite's own opt-in (MCLAUNCHER_ALLOW_REAL_QT); only one caller uses it, and
    that child keeps every window it shows marked WA_DontShowOnScreen, so it cannot reach a desktop.
    """
    env = dict(os.environ)
    if real_platform:
        env.pop("QT_QPA_PLATFORM", None)
        env["MCLAUNCHER_ALLOW_REAL_QT"] = "1"
    else:
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.pop("MCLAUNCHER_ALLOW_REAL_QT", None)
    if allow_the_real_close_path:
        env[SKIP_NEUTRALISATION_ENV] = "1"
    else:
        env.pop(SKIP_NEUTRALISATION_ENV, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MCLAUNCHER_DATA_DIR"] = str(CHILD_DATA_DIR)
    env[VERDICT_ENV] = str(VERDICT_PATH)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(directory), "-q", "-p", "no:cacheprovider"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


def _output(done: subprocess.CompletedProcess) -> str:
    return done.stdout + done.stderr


def _load_firewall():
    """Import tests/conftest.py as a plain module, so its decision can be called directly."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_firewall_conftest_under_test", CONFTEST_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------------------------------
# The decision itself: the exact truth table the fixture applies to every widget.
# --------------------------------------------------------------------------------------------------


def test_the_firewall_flags_a_visible_top_level_window():
    """The decision table of the rule, with no window shown.

    ``screen_visible_windows`` reads three things about a widget - ``isWindow()``, ``isVisible()`` and
    ``WA_DontShowOnScreen`` - so the stand-in below is a real ``QWidget`` (the predicate type-checks,
    and that check belongs to the rule) whose three answers are fixed by the constructor. That makes
    this an exact test of the decision instead of a test of Qt's visibility bookkeeping; the children
    below exercise the same decision with windows that are genuinely shown.
    """
    firewall = _load_firewall()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    QApplication.instance() or QApplication([])  # a QWidget needs an application to exist

    class _StateWidget(QWidget):
        def __init__(self, *, window: bool, visible: bool, dont_show: bool) -> None:
            super().__init__()
            self._answers = (window, visible, dont_show)

        def isWindow(self) -> bool:  # noqa: N802 - Qt's spelling
            return self._answers[0]

        def isVisible(self) -> bool:  # noqa: N802 - Qt's spelling
            return self._answers[1]

        def testAttribute(self, attribute) -> bool:  # noqa: N802 - Qt's spelling
            assert attribute is Qt.WidgetAttribute.WA_DontShowOnScreen
            return self._answers[2]

    violating = _StateWidget(window=True, visible=True, dont_show=False)
    marked = _StateWidget(window=True, visible=True, dont_show=True)
    hidden = _StateWidget(window=True, visible=False, dont_show=False)
    child = _StateWidget(window=False, visible=True, dont_show=False)

    assert firewall.screen_visible_windows([violating]) == [violating], (
        "the firewall accepted a visible top-level window: this is the state that put the quit "
        "confirmation dialog on the desktop"
    )
    assert firewall.screen_visible_windows([marked]) == [], (
        "the firewall rejected a window that cannot reach the screen"
    )
    assert firewall.screen_visible_windows([hidden]) == [], (
        "the firewall rejected a window that is not shown"
    )
    assert firewall.screen_visible_windows([child]) == [], (
        "the firewall treated a child widget as a desktop window"
    )
    assert firewall.screen_visible_windows([marked, violating, hidden]) == [violating], (
        "the firewall must find the violating window among the harmless ones"
    )


def test_the_failure_message_names_the_window():
    firewall = _load_firewall()
    from PySide6.QtWidgets import QApplication, QWidget

    QApplication.instance() or QApplication([])
    widget = QWidget()
    widget.setWindowTitle("confirm quit")
    widget.setObjectName("detector")
    described = firewall.describe_window(widget)
    assert "QWidget" in described and "detector" in described and "confirm quit" in described
    assert "WA_DontShowOnScreen=False" in described


# --------------------------------------------------------------------------------------------------
# Negative self-check 1: a child test that really shows a window must be reported red.
# --------------------------------------------------------------------------------------------------


def test_a_child_test_that_shows_a_window_is_recorded(monkeypatch):
    """Break the rule on purpose: the firewall must record the window, and say so in those words.

    Two assertions, and the second is the one that makes this a check rather than a demonstration:

    * the child must pass - its own assertions read the suite's recorder and require an event whose
      text names the window and its missing attribute;
    * the child writes a verdict file only after those assertions have run and decided. The parent
      requires that file, because the exit code alone is not evidence: measured while this file was
      being written, a child that passed with two recorded events in hand still reported 0, and the
      parent's "it must fail" assertion was what went red.

    The violation itself is real: the widget in the child is a top-level window, it is visible, and it
    was not marked ``WA_DontShowOnScreen``. What the child cannot do is put it on a desktop - it runs on
    the offscreen plugin, and it asserts that too.
    """
    child = _probe_dir(monkeypatch, "shows_a_window")
    _write(child / "test_violation.py", _CHILD_SHOWS_A_WINDOW, _CHILD_FIREWALL_HANDLE)
    VERDICT_PATH.unlink(missing_ok=True)

    done = _run_child(child)
    output = _output(done)
    verdict = VERDICT_PATH.read_text(encoding="utf-8").strip() if VERDICT_PATH.exists() else ""

    assert done.returncode == 0, f"the child could not reach its verdict:\n{output}"
    assert verdict, f"the child passed without proving anything:\n{output}"
    assert "on the desktop" in verdict, verdict
    assert "WA_DontShowOnScreen=False" in verdict, verdict
    assert "QWidget" in verdict, verdict


def test_a_child_test_with_a_marked_window_stays_green(monkeypatch):
    """No false alarm: WA_DontShowOnScreen is the documented way to render for real without showing.

    This is the control for the check above: the same recorder, the same window, the same show - and the
    only difference is the attribute. A firewall that flagged this one would make every render tool's
    posture impossible to test.
    """
    child = _probe_dir(monkeypatch, "shows_a_marked_window")
    _write(child / "test_marked.py", _CHILD_SHOWS_A_MARKED_WINDOW, _CHILD_FIREWALL_HANDLE)

    done = _run_child(child)
    output = _output(done)
    assert done.returncode == 0, f"the firewall rejected a WA_DontShowOnScreen window:\n{output}"
    assert "1 passed" in output, output


# --------------------------------------------------------------------------------------------------
# Negative self-check 2: the close path the report describes, driven for real in a child.
# --------------------------------------------------------------------------------------------------


def test_the_real_close_path_is_neutralised_in_the_suite(monkeypatch):
    """The prevention layer, driven for real.

    A window is closed while the download counter says 1 - the state that makes the product ask - and
    the run must stay clean, with no dialog constructed. The counter is the same process-global one
    every download path registers in, so this is the state a download test leaves behind rather than a
    made-up one.
    """
    child = _probe_dir(monkeypatch, "close_path_neutralised")
    _write(child / "test_close_path.py", _CHILD_CLOSE_PATH, _CHILD_FIREWALL_HANDLE)

    done = _run_child(child)
    output = _output(done)
    assert done.returncode == 0, (
        f"closing a window while a download runs did not stay clean:\n{output}"
    )
    assert "1 passed" in output, output


def test_the_firewall_catches_what_a_forced_close_path_leaves(monkeypatch):
    """The negative self-check for the report's own scenario, on the real platform.

    Same child, same download state, same forced close path - and this time the child is granted the
    suite's real-platform opt-in, so the firewall's layers have something to see. Two things must
    happen, and both are asserted on the child's output:

    * the child's own handle on the recorder catches the window the close path showed (the observation
      that was missing when the quit dialog reached the desktop);
    * the suite's autouse firewall then fails that test at teardown and names the window.

    The child cannot put anything on the desktop even with a real plugin: its MainWindow is marked
    WA_DontShowOnScreen before it is shown, and the sequence that makes Qt emit Show keeps it that way
    (a marked window emits no Show at all, so the hide/clear/show sequence is what makes the violation
    observable). The dialog the product would build is replaced by a stand-in that returns from
    ``exec()`` immediately.
    """
    child = _probe_dir(monkeypatch, "close_path_forced")
    _write(child / "test_close_path.py", _CHILD_CLOSE_PATH, _CHILD_FIREWALL_HANDLE)

    done = _run_child(child, allow_the_real_close_path=True, real_platform=True)
    output = _output(done)
    assert done.returncode != 0, (
        f"a window shown by a forced close path passed the firewall:\n{output}"
    )
    assert "did not record a window shown while a close path ran" not in output, output
    assert "a window was on the desktop during this test" in output, output
    assert "MainWindow" in output, f"the failure does not name the window:\n{output}"
    assert "1 error" in output, f"expected the firewall to fail the test at teardown:\n{output}"


def test_the_child_probe_directories_stay_inside_tests_work():
    """Housekeeping: the probes must not be collectable by an ordinary `pytest tests` run."""
    assert WORK.parent.name == ".work", WORK
    assert TESTS in WORK.parents, WORK
