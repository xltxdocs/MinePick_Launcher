"""线程桥：把核心同步函数放到 QThreadPool，用信号回传结果/进度/错误。

另含下载速率/剩余时间估算（#7）。
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
    """可调用对象：工作线程调用时以队列信号回传主线程。"""

    progress = Signal(object)

    def __call__(self, value: Any) -> None:
        self.progress.emit(value)


class RateTracker:
    """按 done_bytes 采样估算下载速率与剩余时间（#7）。"""

    def __init__(self) -> None:
        self.last_bytes = 0
        self.last_time: float | None = None
        self.rate_bps = 0.0

    def update(self, done_bytes: int) -> tuple[float, float | None]:
        """返回 (rate_bps, eta_seconds)；数据不足时 eta 为 None。"""
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
        except Exception as exc:  # noqa: BLE001 - 统一转发给 UI 展示
            self._safe_emit(self.signals.error, str(exc))
        finally:
            self._safe_emit(self.signals.finished)

    @staticmethod
    def _safe_emit(signal, *args) -> None:
        """接收方（页面）已销毁时忽略发射错误。"""
        try:
            signal.emit(*args)
        except RuntimeError:
            pass


# 强引用登记：QRunnable 由线程池以 autoDelete 管理，Python 侧的 Worker/
# signals QObject 若被 GC，排队中的 result/error/finished 事件会被丢弃。
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
        # finished 信号在所有回调之后于主线程触发，此时可安全释放引用
        _alive.discard(worker)

    worker.signals.finished.connect(_release)
    QThreadPool.globalInstance().start(worker)
    return worker
