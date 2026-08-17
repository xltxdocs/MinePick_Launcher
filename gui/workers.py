"""Thread bridge: run core synchronous functions on QThreadPool, reporting results/progress/errors via signals.

Also includes download rate / remaining time estimation.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class ProgressBridge(QObject):
    """Callable object: emits a queued signal back to the main thread when called from a worker thread."""

    progress = Signal(object)

    def __call__(self, value: Any) -> None:
        self.progress.emit(value)


class RateTracker:
    """Estimate download rate and remaining time by sampling done_bytes."""

    def __init__(self) -> None:
        self.last_bytes = 0
        self.last_time: float | None = None
        self.rate_bps = 0.0

    def update(self, done_bytes: int) -> tuple[float, float | None]:
        """Return (rate_bps, eta_seconds); eta is None when there is not enough data."""
        now = time.monotonic()
        if self.last_time is not None and now > self.last_time:
            elapsed = now - self.last_time
            self.rate_bps = (done_bytes - self.last_bytes) / elapsed
        self.last_bytes = done_bytes
        self.last_time = now
        return self.rate_bps, self.eta(done_bytes)

    def eta(self, done_bytes: int) -> float | None:
        if self.rate_bps <= 0:
            return None
        return max(0.0, (self.total_bytes - done_bytes) / self.rate_bps)

    def set_total(self, total_bytes: int) -> None:
        self.total_bytes = total_bytes


def format_rate(rate_bps: float) -> str:
    if rate_bps >= 1 << 20:
        return f"{rate_bps / (1 << 20):.1f} MB/s"
    if rate_bps >= 1 << 10:
        return f"{rate_bps / (1 << 10):.0f} KB/s"
    return f"{rate_bps:.0f} B/s"


def format_eta(eta_seconds: float | None) -> str:
    if eta_seconds is None:
        return "--:--"
    minutes, seconds = divmod(int(eta_seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
            self._safe_emit(self.signals.result, result)
        except Exception as exc:  # noqa: BLE001 - forward uniformly for UI display
            self._safe_emit(self.signals.error, str(exc))
        finally:
            self._safe_emit(self.signals.finished)

    @staticmethod
    def _safe_emit(signal, *args) -> None:
        """Ignore emit errors when the receiver (page) has been destroyed."""
        try:
            signal.emit(*args)
        except RuntimeError:
            pass


# Strong-reference registry: QRunnable is autoDelete-managed by the thread pool; if the
# Python-side Worker/signals QObject gets GC'd, queued result/error/finished events are dropped.
_alive: set[Worker] = set()


def run_in_background(
    fn: Callable[..., Any],
    *args: Any,
    on_result: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_finished: Callable[[], None] | None = None,
    **kwargs: Any,
) -> Worker:
    worker = Worker(fn, *args, **kwargs)
    if on_result is not None:
        worker.signals.result.connect(on_result)
    if on_error is not None:
        worker.signals.error.connect(on_error)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)

    _alive.add(worker)

    def _release() -> None:
        # The finished signal fires on the main thread after all callbacks, so it is safe to release the reference here
        _alive.discard(worker)

    worker.signals.finished.connect(_release)
    QThreadPool.globalInstance().start(worker)
    return worker
