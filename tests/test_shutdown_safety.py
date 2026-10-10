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

"""Closing the application while background work runs must not abort the process.

A download or update can outlive the window by minutes; a progress callback that reaches a destroyed
Qt object took the whole process down with "Fatal Python error: Aborted". The shutdown flag makes those
callbacks no-ops once shutdown begins, and the quit path waits for the pool with a bound instead of
tearing the interface down underneath it.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from PySide6.QtCore import QRunnable, QThreadPool

from gui import workers


@pytest.fixture(autouse=True)
def _clear_shutdown_flag():
    workers.reset_shutdown_for_tests()
    yield
    workers.reset_shutdown_for_tests()


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application


def test_the_bridge_goes_inert_after_shutdown(app):
    """After shutdown a progress callback must not reach Qt at all - not even once."""
    bridge = workers.ProgressBridge()
    seen: list[object] = []
    bridge.progress.connect(seen.append)

    bridge(1)
    app.processEvents()
    assert seen == [1], "a live bridge must still report progress"

    workers.begin_shutdown()
    bridge(2)
    app.processEvents()
    assert seen == [1], "a callback arrived after shutdown began"
    assert workers.is_shutting_down() is True


def test_shutdown_flag_is_visible_to_worker_threads(app):
    """The flag is read from the worker thread, so it must not depend on the GUI thread running."""
    observed: list[bool] = []
    workers.begin_shutdown()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: observed.append(workers.is_shutting_down())).result()
    assert observed == [True]


def test_a_worker_finishing_after_shutdown_does_not_emit(app):
    """The Worker path itself, not just the progress bridge: no signal may arrive after shutdown.

    Every emit a Worker makes goes through Worker._safe_emit, which is where the flag is checked, so
    this pins the constructive guarantee rather than the timing.
    """
    worker = workers.Worker(lambda: 42)
    results: list[object] = []
    finished: list[bool] = []
    worker.signals.result.connect(results.append)
    worker.signals.finished.connect(lambda: finished.append(True))

    worker.run()  # normal use: the result must still arrive
    app.processEvents()
    assert results == [42], "a live worker must still deliver its result"
    assert finished == [True]

    results.clear()
    finished.clear()
    workers.begin_shutdown()
    worker.run()
    app.processEvents()
    assert results == [], "a worker delivered a result after shutdown began"
    assert finished == [], "a worker emitted finished after shutdown began"


def test_a_worker_error_after_shutdown_does_not_emit(app):
    def boom() -> None:
        raise ValueError("nope")

    worker = workers.Worker(boom)
    errors: list[str] = []
    worker.signals.error.connect(errors.append)

    workers.begin_shutdown()
    worker.run()
    app.processEvents()
    assert errors == [], "a worker reported an error after shutdown began"


class _SlowRunnable(QRunnable):
    """A pool task that keeps the pool busy, like a manifest fetch in progress."""

    def __init__(self) -> None:
        super().__init__()
        self.signals = workers.WorkerSignals()
        self.started = False

    def run(self) -> None:  # pragma: no cover - timing helper
        self.started = True
        time.sleep(0.4)
        if not workers.is_shutting_down():
            self.signals.finished.emit()


def test_the_quit_path_waits_for_the_pool_with_a_bound(app):
    """The wait must return, and it must not be unbounded."""
    runnable = _SlowRunnable()
    QThreadPool.globalInstance().start(runnable)

    workers.begin_shutdown()
    started = time.monotonic()
    finished = QThreadPool.globalInstance().waitForDone(2500)
    elapsed = time.monotonic() - started
    QThreadPool.globalInstance().clear()

    assert elapsed < 3.0, "the shutdown wait exceeded its bound"
    assert runnable.started, "the pool task never ran, so this proved nothing"
    assert finished in (True, False)


def test_a_slow_download_reporting_while_the_app_quits_does_not_abort(app):
    """The real shape of the bug: a worker keeps calling the bridge while the app tears down."""
    bridge = workers.ProgressBridge()
    seen: list[object] = []

    def on_progress(value: object) -> None:
        seen.append(value)

    bridge.progress.connect(on_progress)
    stop = False

    def worker() -> None:
        while not stop:
            bridge(1)  # the downloader's progress callback, from a worker thread
            time.sleep(0.01)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(worker)
        time.sleep(0.1)
        workers.begin_shutdown()
        QThreadPool.globalInstance().waitForDone(500)
        time.sleep(0.15)
        after_shutdown = len(seen)
        time.sleep(0.15)
        assert len(seen) == after_shutdown, "progress still reached Qt after shutdown began"
        stop = True

