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

The flag and the pool wait cover everything that runs on Qt's `QThreadPool`. They never covered the
transfer threads themselves, because the downloader runs its batches on Python's
`concurrent.futures.ThreadPoolExecutor` (see `launcher/net/downloader.py`): waiting on the Qt pool does
not reach them, and they kept writing to disk after the last window was gone. On the reporter's machine
that ended in an access violation inside Qt6Core (`0xc0000005`, WER AppCrash report for PID 16576). The
tests below pin the part that was missing: by the time the shutdown path returns, no transfer thread
exists any more, and none can be started afterwards.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from PySide6.QtCore import QRunnable, QThreadPool

from gui import workers
from launcher.net import downloader


@pytest.fixture(autouse=True)
def _clear_shutdown_flag():
    workers.reset_shutdown_for_tests()
    downloader.reset_cancellation_for_tests()
    yield
    workers.reset_shutdown_for_tests()
    downloader.reset_cancellation_for_tests()


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


# --------------------------------------------------------------------------------------------------
# The transfer threads themselves: the downloader's own executor, which no Qt wait ever reached.
# --------------------------------------------------------------------------------------------------

TOTAL_CHUNKS = 48  # 48 * 64 KB = 3 MB per file, delivered slowly enough to be cancelled mid-flight
# Per-chunk pacing, measured: 0.02s still finished a 3 MB file in well under a second on this machine
# (the body arrives faster than one chunk per pause), so this is deliberately generous. A batch that
# cannot be cancelled takes ~7s per file here - far longer than the 5s the tests allow for it - which is
# what makes "the transfer stopped" a real observation instead of a race the transfer could win.
CHUNK_DELAY = 0.15


class _SlowResponse:
    """A streaming response that hands back its body one chunk at a time, with a pause in between.

    Long enough that the download is certainly still running when the test cancels it, and finite so a
    missing cancellation shows up as a slow test rather than a hung suite.
    """

    def __init__(self, url: str, size: int, body: bytes) -> None:
        self.status_code = 200
        self.url = url
        self.headers = httpx.Headers({"Content-Length": str(size)})
        self._body = body

    def __enter__(self) -> _SlowResponse:  # noqa: PYI034 - matches httpx' own __enter__ shape
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, size: int):
        for offset in range(0, len(self._body), size):
            time.sleep(CHUNK_DELAY)
            yield self._body[offset : offset + size]


class _SlowClient:
    """Just enough of httpx.Client for the single-stream download path."""

    chunk_size = 64 * 1024
    chunks = TOTAL_CHUNKS

    def __init__(self) -> None:
        self._body = b"m" * (self.chunk_size * self.chunks)

    @property
    def size(self) -> int:
        return len(self._body)

    def stream(self, method: str, url: str, **kwargs) -> _SlowResponse:
        return _SlowResponse(url, len(self._body), self._body)


def _pool_thread_names() -> set[str]:
    """Names of live `ThreadPoolExecutor` worker threads - the downloader's transfer threads.

    Matched on the name prefix `concurrent.futures` gives its workers, so the assertion below is about
    the executor the downloader uses and not about any thread this test started.
    """
    return {
        thread.name
        for thread in threading.enumerate()
        if thread.is_alive() and thread.name.startswith("ThreadPoolExecutor")
    }


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _start_slow_download(ws_tmp, files: int = 3) -> tuple[dict, list[tuple[str, str]], threading.Thread]:
    """Start a real download batch on the downloader's own pool and return (result box, failures, thread).

    The destination is unique per call and empty: a `.part` left by an earlier attempt would be resumed
    (and a finished file would be skipped), which would test the resume path instead of the shutdown one.
    """
    import uuid

    dest = ws_tmp / uuid.uuid4().hex[:8]
    dest.mkdir()
    client = _SlowClient()
    instance = downloader.Downloader(client=client, concurrency=files)
    # The size matters: a task with no size and no digest is "already verified" and is skipped without
    # ever touching the network, which would make every assertion below vacuous.
    tasks = [
        downloader.DownloadTask(f"https://x/slow{i}.jar", dest / f"slow{i}.jar", size=client.size)
        for i in range(files)
    ]
    outcome: dict = {}
    failures: list[tuple[str, str]] = []

    def run() -> None:
        try:
            outcome["result"] = instance.download(tasks)
        except BaseException as exc:  # noqa: BLE001 - the test asserts on what came out
            outcome["error"] = exc
            failures.append((type(exc).__name__, str(exc)))

    thread = threading.Thread(target=run, name="test-slow-download", daemon=True)
    thread.start()
    # The caller needs the paths, so they travel back with the box rather than being recomputed.
    outcome["dest"] = dest
    return outcome, failures, thread


def _part_paths(outcome: dict, files: int = 3) -> list:
    return [outcome["dest"] / f"slow{i}.jar.part" for i in range(files)]


def test_a_download_in_flight_registers_for_cancellation(ws_tmp):
    """The activity count and the drain counter are the same registration: one is not forgotten."""
    before = downloader.active_download_count()
    outcome, _failures, thread = _start_slow_download(ws_tmp, files=2)
    try:
        assert _wait_until(lambda: downloader.active_download_count() > before), (
            "a running download was not visible to the quit confirmation"
        )
        assert downloader.is_cancelled() is False, "a fresh batch must not start out cancelled"
        assert downloader.wait_for_downloads(0.0) is False, (
            "the drain claimed there was nothing in flight while a download was running"
        )
    finally:
        downloader.cancel_all_downloads()
        thread.join(timeout=10)
        assert not thread.is_alive(), "the download thread ignored the cancellation"
    assert outcome, "the download thread produced no outcome at all"
    assert downloader.active_download_count() == before, "the activity count leaked"
    assert downloader.wait_for_downloads(0.0) is True, "the drain did not settle after cancellation"


def test_cancelling_stops_every_transfer_thread_before_the_wait_returns(ws_tmp):
    """The E9 fix itself: after the shutdown sequence, no transfer thread exists any more.

    This is the assertion the old shutdown path could not make. `QThreadPool.waitForDone` returned
    immediately here - the download never ran on that pool - while the batch below kept writing to disk
    for as long as the body took to stream. What is pinned is the guarantee, not a timing: once
    `wait_for_downloads` reports success, the executor threads are gone.
    """
    before_threads = _pool_thread_names()
    before_count = downloader.active_download_count()
    outcome, failures, thread = _start_slow_download(ws_tmp, files=3)
    assert _wait_until(lambda: downloader.active_download_count() > before_count)

    # The shutdown sequence gui/main.py runs, in its order: stop callbacks, cancel the transfers, drain
    # them, and only then let Qt tear down.
    workers.begin_shutdown()
    downloader.cancel_all_downloads()
    drained = downloader.wait_for_downloads(5.0)

    assert drained is True, "the drain gave up while the download was still running"
    assert downloader.wait_for_downloads(0.0) is True, "the drain reported success without settling"
    assert _wait_until(lambda: thread.is_alive() is False), "the download call never returned"
    assert _wait_until(lambda: not (_pool_thread_names() - before_threads)), (
        "a transfer thread outlived the shutdown wait: "
        f"{sorted(_pool_thread_names() - before_threads)}"
    )
    assert outcome, "the download thread produced no outcome at all"
    assert isinstance(outcome.get("error"), downloader.DownloadCancelled), (
        f"a cancelled download must not look like a failure or a success: {outcome.get('error')!r}"
    )
    assert failures and failures[0][0] == "DownloadCancelled", (
        "the batch ended in a way the caller cannot tell apart from a broken download"
    )
    assert downloader.active_download_count() == before_count, "the activity count leaked"


def test_nothing_is_written_to_disk_after_the_shutdown_wait(ws_tmp):
    """The bytes stop, not just the threads: a transfer that is cancelled writes nothing further.

    The reporter's evidence for the crash was files under `.minecraft` still being written seconds after
    the window disappeared. The `.part` files here are the same thing, one layer down.
    """
    outcome, _failures, thread = _start_slow_download(ws_tmp, files=2)
    parts = _part_paths(outcome, files=2)
    # The `.part` file is created before the first chunk arrives, so waiting for it to exist would let
    # this test cancel at zero bytes and then "prove" that nothing grew. Wait for bytes on disk.
    assert _wait_until(lambda: all(part.exists() and part.stat().st_size > 0 for part in parts),
                       timeout=15.0), "the download never wrote anything to disk"

    workers.begin_shutdown()
    downloader.cancel_all_downloads()
    assert downloader.wait_for_downloads(5.0) is True
    assert _wait_until(lambda: thread.is_alive() is False)

    settled = {part: part.stat().st_size for part in parts}
    time.sleep(0.5)  # long enough for three more chunks, i.e. for a straggler to be seen writing
    assert {part: part.stat().st_size for part in parts} == settled, (
        "a transfer thread kept writing to disk after the shutdown wait returned"
    )
    assert settled and all(size > 0 for size in settled.values()), (
        "nothing was on disk, so this proved nothing about stopping it"
    )
    assert outcome, "the download thread produced no outcome at all"


def test_the_wait_is_bounded_even_when_a_transfer_cannot_stop(ws_tmp):
    """A stuck transfer must not turn into a program that will not close.

    The drain counter is bumped by hand here: the point is the bound itself, and a real un-interruptible
    socket read cannot be produced on demand.
    """
    scope = downloader._CancelScope()
    scope.__enter__()
    started = time.monotonic()
    try:
        assert downloader.wait_for_downloads(0.3) is False, "a stuck transfer was reported as drained"
        elapsed = time.monotonic() - started
        assert 0.25 <= elapsed < 2.0, f"the bounded wait returned after {elapsed:.2f}s"
    finally:
        scope.__exit__(None, None, None)
    assert downloader.wait_for_downloads(1.0) is True, "the drain never noticed the thread had left"


def test_a_download_cannot_start_once_shutdown_began(ws_tmp):
    """After the cancellation latch is set, a new batch refuses to start instead of writing during teardown.

    Downloads are queued one after another (a version install, then its assets), so "the one that was
    running has stopped" is not enough - the next one must not begin.
    """
    downloader.cancel_all_downloads()
    instance = downloader.Downloader(client=_SlowClient())
    with pytest.raises(downloader.DownloadCancelled):
        instance.download([downloader.DownloadTask("https://x/never.jar", ws_tmp / "never.jar", size=1)])
    assert not (ws_tmp / "never.jar.part").exists(), "a transfer started after shutdown began"
    assert downloader.active_download_count() == 0, "the refused batch left the activity count raised"


def test_an_idle_shutdown_costs_nothing(app):
    """The path the reporter measured as clean: no downloads, so both waits are empty and instant."""
    time.sleep(0.05)  # let any executor thread of an earlier test finish dying
    started = time.monotonic()
    workers.begin_shutdown()
    assert downloader.cancel_all_downloads() == 0
    assert downloader.wait_for_downloads(4.0) is True, "an idle application failed to drain"
    QThreadPool.globalInstance().waitForDone(2500)
    QThreadPool.globalInstance().clear()
    elapsed = time.monotonic() - started
    assert elapsed < 0.5, f"an idle shutdown waited {elapsed:.2f}s"
    assert not _pool_thread_names(), f"leftover transfer threads: {sorted(_pool_thread_names())}"


def test_the_update_stream_stops_on_cancellation(app, ws_tmp, monkeypatch):
    """The updater streams the release EXE itself: it has to stop by the same signal.

    A half-downloaded update is discarded rather than installed - the partial file is removed, which is
    the existing behaviour for an abandoned update.
    """
    from launcher.updates import ReleaseInfo, download_release_exe

    class _StreamingClient:
        def __init__(self) -> None:
            self.chunks = 0

        def stream(self, method, url, **kwargs):
            body = b"x" * (1 << 16)
            client = self

            class _Response:
                status_code = 200
                headers = httpx.Headers({"Content-Length": str(len(body) * 8)})

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def iter_bytes(self, size):
                    for _ in range(8):
                        client.chunks += 1
                        downloader.cancel_all_downloads()  # the user quits mid-stream
                        time.sleep(0.01)
                        yield body

            return _Response()

    release = ReleaseInfo(
        version="9.9.9",
        tag="v9.9.9",
        page_url="https://example.invalid/release",
        notes="",
        exe_url="https://example.invalid/MinePick.exe",
        exe_name="MinePick.exe",
        exe_size=1 << 16,
    )
    client = _StreamingClient()
    with pytest.raises(downloader.DownloadCancelled):
        download_release_exe(release, ws_tmp, client=client)
    assert client.chunks < 8, "the update stream ran to the end after the cancellation"
    assert not (ws_tmp / "MinePick.exe").exists(), "a cancelled update was installed anyway"
    assert not (ws_tmp / "MinePick.exe.part").exists(), "a cancelled update left its partial file behind"
    assert downloader.active_download_count() == 0, "the cancelled update leaked its activity count"

