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

"""The opt-in accessibility trace: what it records, and that being off costs nothing.

The status line goes quiet for two opposite reasons - a reader is not attached, or the escape hatch
was set - and from the outside they look identical: no announcement. ``MCLAUNCHER_A11Y_TRACE=1`` is
what tells them apart, and the tests here pin both the facts it writes and the one thing that matters
more than the facts: with the switch off it must not write, must not query and must not change a
single decision.

Everything is asserted from the log file itself, read back the way the colleague who receives it will
read it, because a trace that only exists in memory diagnoses nothing.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QApplication

from gui import a11y_trace
from gui.widgets import StatusLabel

DOWNLOADING = "正在下载"
READY = "准备就绪"


class Log:
    """The trace file, parsed into records: one per ``timestamp | tag#n | name=value`` line.

    The lines of an event share a tag and its ``#n``, so a filter is by tag prefix and a record is
    what the file will show whoever receives it.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def records(self, tag: str) -> list[dict[str, str]]:
        """All records with this tag, in file order, each a dict of its merged fields.

        The ``#n`` in the tag is what keeps two separate events with the same tag apart.
        """
        events: dict[str, dict[str, str]] = {}
        for line in self.lines():
            parts = line.split(" | ")
            if len(parts) != 3:
                continue
            raw = parts[1]
            if raw.split("#", 1)[0] != tag:
                continue
            name, _, value = parts[2].partition("=")
            events.setdefault(raw, {})[name] = value
        return list(events.values())

    def only(self, tag: str) -> dict[str, str]:
        """The single record for this tag: most assertions are about a case with exactly one."""
        found = self.records(tag)
        assert len(found) == 1, f"expected one {tag!r} record, got {len(found)}:\n" + self.text()
        return found[0]

    def field(self, tag: str, name: str) -> str:
        """The value of one field, failing the test rather than the lookup when it is absent."""
        for record in self.records(tag):
            if name in record:
                return record[name]
        raise AssertionError(f"no {name!r} in any {tag!r} record of:\n" + self.text())

    def text(self) -> str:
        return "\n".join(self.lines())


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def reader_running(monkeypatch):
    """The gate thinks a screen reader is attached, so the announcement reaches the send step."""
    monkeypatch.setattr(a11y_trace, "_probe_isActive", lambda: True)


@pytest.fixture()
def no_reader(monkeypatch):
    monkeypatch.setattr(a11y_trace, "_probe_isActive", lambda: False)


@pytest.fixture()
def announcements(monkeypatch):
    """Collect every accessibility update the label sends, instead of handing it to Qt."""
    seen: list[tuple[object, object]] = []
    monkeypatch.setattr(
        QAccessible,
        "updateAccessibility",
        staticmethod(lambda event: seen.append((event.object(), event.type()))),
    )
    return seen


@pytest.fixture()
def trace_file(ws_tmp, monkeypatch):
    """Point the trace at a file inside the test workspace and keep the real launcher data out of it."""
    path = ws_tmp / "a11y_trace.log"
    monkeypatch.setenv(a11y_trace.TRACE_FILE_ENV, str(path))
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.delenv(a11y_trace.TRACE_ENV, raising=False)
    monkeypatch.delenv("MCLAUNCHER_NO_A11Y_ALERT", raising=False)
    return Log(path)


@pytest.fixture()
def trace_off(trace_file):
    """The same file target with the switch off - the state every real user is in."""
    return trace_file


@pytest.fixture()
def tracing(trace_file, monkeypatch):
    """The switch on: MCLAUNCHER_A11Y_TRACE=1 writes to this test's file."""
    monkeypatch.setenv(a11y_trace.TRACE_ENV, "1")
    return trace_file


@pytest.fixture()
def file_activity(monkeypatch):
    """Every open() and every trace-path lookup the trace module performs, in order."""
    import builtins

    opened: list[str] = []
    looked_up: list[str] = []
    real_open = builtins.open
    real_path = a11y_trace.trace_path

    def spy_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def spy_path():
        looked_up.append("trace_path")
        return real_path()

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(a11y_trace, "trace_path", spy_path)
    return opened, looked_up


# ------------------------------------------------------------------ switch on: the log answers "why"

def test_a_status_change_is_logged_with_both_gates_and_the_outcome(
    app, announcements, reader_running, tracing
):
    """The core record: old text -> new text, each gate's verdict, and that the event went out."""
    label = StatusLabel("")
    label.set_error("导入失败：文件损坏")

    announce = tracing.records("announce/sent")
    assert len(announce) == 1, tracing.text()
    assert announce[0]["before"] == "''"
    assert announce[0]["after"] == repr("导入失败：文件损坏")
    assert announce[0]["gate1_force_silence"] == "PASS (MCLAUNCHER_NO_A11Y_ALERT not set)"
    assert announce[0]["gate2_reader"] == "PASS (QAccessible.isActive() == True)"
    assert announce[0]["sent"] == "True"
    assert len(announcements) == 1
    # The log says the reader question was asked, when, and what it answered.
    assert tracing.field("isActive", "isActive") == "True"
    assert tracing.field("isActive", "moment") == "status change"


def test_the_log_records_the_environment_and_the_windows_it_belongs_to(app, reader_running, tracing):
    """A trace that cannot say whether it was muted, or whether a window existed, diagnoses nothing."""
    os.environ["QT_ACCESSIBILITY"] = "1"
    try:
        assert a11y_trace.init("test") == tracing.path
    finally:
        os.environ.pop("QT_ACCESSIBILITY", None)

    session = tracing.records("session")
    assert session, tracing.text()
    # Our own process, not a probe process: the pid and the entry point are both in the header.
    assert tracing.field("session", "pid") == str(os.getpid())
    assert tracing.field("session", "argv0") == Path(sys.argv[0]).name
    assert tracing.field("session", "env QT_ACCESSIBILITY") == "1"
    assert tracing.field("session", "env MCLAUNCHER_NO_A11Y_ALERT") == "<unset>"
    assert tracing.field("session", "isActive_at_init") in {"True", "False"}
    # The window counts are the reason an empty probe process answers False: it has nothing to attach to.
    assert tracing.field("session", "top_level_windows").isdigit()
    assert tracing.field("session", "visible_top_level_windows").isdigit()


def test_no_reader_and_forced_silence_are_told_apart(
    app, announcements, reader_running, tracing, monkeypatch
):
    """Two silences, one symptom: matching most of the log but for the gate that closed."""
    label = StatusLabel("")

    # Silence 1: the escape hatch, with a reader attached.
    monkeypatch.setenv("MCLAUNCHER_NO_A11Y_ALERT", "1")
    label.setText(DOWNLOADING)
    blocked = tracing.records("announce/blocked")
    assert len(blocked) == 1, tracing.text()
    assert blocked[0]["gate1_force_silence"] == "BLOCK (FORCED-SILENT by MCLAUNCHER_NO_A11Y_ALERT=1)"
    # The reader gate is not consulted on this path, which is exactly what "not-consulted" means.
    assert blocked[0]["gate2_reader"] == "not-consulted"
    assert blocked[0]["sent"] == "False"
    assert len(announcements) == 0

    # Silence 2: no escape hatch, but nothing is listening.
    monkeypatch.delenv("MCLAUNCHER_NO_A11Y_ALERT")
    monkeypatch.setattr(a11y_trace, "_probe_isActive", lambda: False)
    label.setText(READY)
    blocked = tracing.records("announce/blocked")
    assert len(blocked) == 2, tracing.text()
    assert blocked[1]["before"] == repr(DOWNLOADING)
    assert blocked[1]["gate1_force_silence"] == "PASS (MCLAUNCHER_NO_A11Y_ALERT not set)"
    assert blocked[1]["gate2_reader"] == "BLOCK (QAccessible.isActive() == False: no reader attached)"
    assert blocked[1]["sent"] == "False"
    assert len(announcements) == 0

    # And the two records really do differ in the gate that closed, which is the whole point.
    assert blocked[0]["gate1_force_silence"] != blocked[1]["gate1_force_silence"]
    assert blocked[0]["gate2_reader"] != blocked[1]["gate2_reader"]


def test_the_send_failure_is_recorded_rather_than_swallowed(app, reader_running, tracing, monkeypatch):
    """The announcement is allowed to fail; failing silently in a diagnostic build is not."""

    def boom(_event):
        raise RuntimeError("no accessibility bridge")

    monkeypatch.setattr(QAccessible, "updateAccessibility", staticmethod(boom))
    StatusLabel("").setText(DOWNLOADING)

    assert tracing.field("announce/error", "sent") == "False"
    assert tracing.field("announce/error", "gate2_reader") == "PASS (QAccessible.isActive() == True)"


def test_a_repeated_message_is_not_logged_as_a_change(app, reader_running, tracing):
    """The once-per-message rule is unchanged: a repeat is not an announcement, so it is not a record."""
    label = StatusLabel("")
    label.setText(DOWNLOADING)
    label.setText(DOWNLOADING)
    assert len(tracing.records("announce/sent")) == 1
    assert len(tracing.records("isActive")) == 1  # and the gate was asked only once


def test_the_default_path_is_the_documented_one():
    """%TEMP%\\minepick_a11y_trace.log unless MCLAUNCHER_A11Y_TRACE_FILE overrides it."""
    assert a11y_trace.DEFAULT_TRACE_NAME == "minepick_a11y_trace.log"
    assert a11y_trace.trace_path().name == "minepick_a11y_trace.log"
    assert a11y_trace.trace_path().parent == Path(tempfile.gettempdir())


# ------------------------------------------------------------- switch off: the promises that matter

def test_off_writes_no_file_and_does_no_extra_work(
    app, announcements, no_reader, trace_off, file_activity, monkeypatch
):
    """Off means off: one environment lookup, no file ever opened, no query the gate would not make.

    This is the guard for the claim that the switch costs nothing when it is off. It counts the
    queries Qt is asked (exactly the one the gate needs, same as before this feature existed), the
    file opens (none) and the trace-path lookups (none), with the status line going through every
    branch of the announcement path.
    """
    opened, looked_up = file_activity
    env_reads: list[str] = []
    real_getenv = os.environ.get

    def counting_getenv(key, *args):
        env_reads.append(key)
        return real_getenv(key, *args)

    monkeypatch.setattr(os.environ, "get", counting_getenv)
    tries: list[int] = []

    def counting_probe():
        tries.append(1)
        return False

    monkeypatch.setattr(a11y_trace, "_probe_isActive", counting_probe)

    label = StatusLabel("")
    label.setText(DOWNLOADING)  # gate 2 closes: no reader
    label.set_error("导入失败")  # same branch, different text
    label.setText("")  # empty text: the early return that precedes every gate

    assert trace_off.exists is False, trace_off.text()
    assert opened == []
    assert looked_up == []
    # The exact off-path cost: the switch is read once on the announce path and once for the gate,
    # and the trace-file variable is not consulted at all (it could only matter if the switch were on).
    assert env_reads.count(a11y_trace.TRACE_ENV) == 4
    assert a11y_trace.TRACE_FILE_ENV not in env_reads
    # The gate asks Qt exactly once per status change, as it did before the trace existed.
    assert len(tries) == 2
    assert announcements == []
    assert label.text() == ""


def test_off_adds_no_measurable_time_to_the_announcement(app, no_reader, monkeypatch):
    """The off path is a read, a branch and a call: measured against the pre-change code path.

    A generous ceiling (20 us per announcement, some 25x the observed cost) so the test states "this
    cannot become a bottleneck" without turning scheduler noise into a failure.
    """
    import statistics
    import time

    from gui.widgets import a11y_alerts_enabled

    monkeypatch.setattr(a11y_trace, "_probe_isActive", lambda: False)

    def pre_change_announce(label, text, state):
        """The announcement step exactly as it was before this feature."""
        text = text or ""
        if text == state[0]:
            return
        state[0] = text
        if not text:
            return
        if not a11y_alerts_enabled():
            return
        try:
            if not a11y_trace._probe_isActive():
                return
        except Exception:  # noqa: BLE001 - the original guard
            return

    def measure(call, n=3000):
        runs = []
        for _ in range(5):
            start = time.perf_counter()
            for i in range(n):
                call(i)
            runs.append((time.perf_counter() - start) / n * 1e6)
        return min(runs), statistics.median(runs)

    label = StatusLabel("")
    state = [""]
    new_min, new_median = measure(lambda i: label._announce(f"progress {i}"))
    old_min, old_median = measure(lambda i: pre_change_announce(label, f"progress {i}", state))

    delta = new_median - old_median
    assert delta < 20.0, (
        f"the off path costs {delta:.2f} us per announcement "
        f"(new {new_median:.2f} us vs pre-change {old_median:.2f} us, min {new_min:.2f}/{old_min:.2f})"
    )


def test_off_does_not_change_what_is_decided_or_sent(app, announcements, reader_running, trace_off):
    """Same decisions with the switch off: a reader still hears every distinct message."""
    label = StatusLabel("")
    label.setText(DOWNLOADING)
    label.set_error("导入失败")
    label.setText("")  # silent
    label.setText(READY)

    assert len(announcements) == 3
    assert trace_off.exists is False


def test_off_keeps_the_escape_hatch_working(app, announcements, reader_running, trace_off, monkeypatch):
    """MCLAUNCHER_NO_A11Y_ALERT=1 keeps winning, trace or no trace - and writes nothing."""
    monkeypatch.setenv("MCLAUNCHER_NO_A11Y_ALERT", "1")
    StatusLabel("").setText(DOWNLOADING)
    assert announcements == []
    assert trace_off.exists is False


def test_off_makes_init_a_no_op(app, trace_off, file_activity, monkeypatch):
    """The startup hook costs one environment lookup when the switch is off."""
    opened, looked_up = file_activity
    env_reads: list[str] = []
    real_getenv = os.environ.get

    def counting_getenv(key, *args):
        env_reads.append(key)
        return real_getenv(key, *args)

    monkeypatch.setattr(os.environ, "get", counting_getenv)
    assert a11y_trace.init("test") is None
    assert opened == []
    assert looked_up == []
    assert env_reads == [a11y_trace.TRACE_ENV]
    assert trace_off.exists is False


def test_trace_enabled_reads_only_its_own_variable(monkeypatch):
    monkeypatch.setenv(a11y_trace.TRACE_ENV, "1")
    assert a11y_trace.trace_enabled() is True
    monkeypatch.setenv(a11y_trace.TRACE_ENV, "no")
    assert a11y_trace.trace_enabled() is False
    monkeypatch.delenv(a11y_trace.TRACE_ENV)
    assert a11y_trace.trace_enabled() is False


def test_the_environment_facts_are_the_gate_variables():
    """The three variables a colleague needs in order to explain a silent status line."""
    snapshot = a11y_trace.env_snapshot()
    assert set(snapshot) == {
        "QT_ACCESSIBILITY",
        "QT_LINUX_ACCESSIBILITY_ALWAYS_ON",
        "MCLAUNCHER_NO_A11Y_ALERT",
    }


# ------------------------------------------------------------------------- on: the startup wiring

def test_the_entry_point_writes_the_header_at_startup(app, trace_file, monkeypatch):
    """main() opens the log before the first window exists, and reports where it went.

    Launching the real entry point is not an option (it ends in app.exec()), so the build steps are
    stubbed. The stub for the window is what proves the ordering: it refuses to build, so reaching the
    assertions at all means the trace hook had already run, before any window existed.
    """
    import logging as real_logging

    import gui.main as gui_main

    logged: list[tuple[str, object]] = []

    class _Logger:
        def info(self, message, *args):
            logged.append((message, args[0] if args else ""))

        def __getattr__(self, name):  # anything else the entry point logs through
            return lambda *a, **k: None

    class _Logging:
        def getLogger(self, name=None):
            return _Logger()

        def __getattr__(self, name):
            return getattr(real_logging, name)

    class _WindowRefused(Exception):
        pass

    def _refuse_window():
        raise _WindowRefused("no window in this test")

    monkeypatch.setattr(gui_main, "configure_logging", lambda **kwargs: _Logger())
    monkeypatch.setattr(gui_main, "logging", _Logging())
    monkeypatch.setattr(gui_main.paths, "cleanup_stale_extraction_dirs", lambda: 0)
    monkeypatch.setattr(gui_main, "create_app", _refuse_window)
    monkeypatch.setenv(a11y_trace.TRACE_ENV, "1")

    try:
        with pytest.raises(_WindowRefused):
            gui_main.main()
    finally:
        # The entry point's logging module is the real one: never leave a stub sitting on it, or every
        # later test that logs through pytest goes looking for handlers that are not there.
        monkeypatch.undo()

    assert trace_file.exists, "the entry point did not open the trace"
    assert trace_file.field("session", "reason") == "gui.main.main()"
    assert ("accessibility trace: %s", trace_file.path) in logged, logged
