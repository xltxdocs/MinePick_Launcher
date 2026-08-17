"""通用下载器：并发、断点续传（Range + .part 保留）、sha1/sha256 校验、重试、进度回调。

打包/沙箱兼容说明：
- 不使用 tempfile.mkdtemp（沙箱锁定随机后缀目录），临时文件为 <目标>.part；
- 网络失败时保留 .part，下次尝试用 Range 从断点继续（校验失败则丢弃）；
- 仅使用线程池（PyInstaller --onefile 下无需 multiprocessing.freeze_support）；
- 所有目标路径由调用方提供（用户数据目录运行时解析，不依赖 __file__）。
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import tenacity

from launcher.i18n import describe_network_error, tr_core
from launcher.meta.manifest import _new_client

CHUNK = 64 * 1024


class DownloadError(Exception):
    """下载失败（消息面向用户）。"""


@dataclass(frozen=True)
class DownloadTask:
    url: str
    dest: Path
    sha1: str | None = None
    size: int | None = None
    sha256: str | None = None


@dataclass
class DownloadProgress:
    done_bytes: int = 0
    total_bytes: int = 0
    done_files: int = 0
    total_files: int = 0
    current: str = ""


@dataclass
class DownloadResult:
    downloaded: int = 0
    skipped: int = 0
    bytes: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path: Path, sha1: str | None, size: int | None, sha256: str | None = None) -> bool:
    """文件存在且校验通过（单次读取同时计算所需摘要）。"""
    try:
        if size is not None and path.stat().st_size != size:
            return False
        if sha1 is None and sha256 is None:
            return True
        digest1 = hashlib.sha1() if sha1 is not None else None
        digest256 = hashlib.sha256() if sha256 is not None else None
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                if digest1 is not None:
                    digest1.update(chunk)
                if digest256 is not None:
                    digest256.update(chunk)
        if digest1 is not None and digest1.hexdigest() != sha1:
            return False
        if digest256 is not None and digest256.hexdigest() != sha256:
            return False
    except OSError:
        return False
    return True


class _SpeedLimiter:
    """全局速率限制（#10）：按写入量休眠补足预算（令牌桶近似，跨线程共享）。"""

    def __init__(self, limit_kb: int) -> None:
        self.limit = limit_kb * 1024
        self.lock = threading.Lock()
        self.last = time.monotonic()

    def throttle(self, nbytes: int) -> None:
        if self.limit <= 0:
            return
        with self.lock:
            now = time.monotonic()
            elapsed = max(now - self.last, 1e-6)
            self.last = now
            budget = elapsed * self.limit
            overshoot = nbytes - budget
            if overshoot > 0:
                time.sleep(min(overshoot / self.limit, 5.0))


class Downloader:
    """并发下载任务列表；已存在且校验通过的文件跳过，失败任务汇总上报。

    断点续传（#6）：下载写到 <dest>.part，网络失败保留 .part 供下次 Range 续传；
    校验失败视为数据损坏，丢弃 .part 重新下载。
    限速（#10）：speed_limit_kb 为 None 时读取配置 download_speed_limit_kb。
    """

    def __init__(
        self,
        concurrency: int = 4,
        client: httpx.Client | None = None,
        retries: int = 3,
        retry_wait: float = 1.0,
        force: bool = False,
        speed_limit_kb: int | None = None,
    ) -> None:
        self.concurrency = concurrency
        self._client = client
        self._owns_client = client is None
        self.retries = retries
        self.retry_wait = retry_wait
        self.force = force
        if speed_limit_kb is None:
            from launcher import config

            cfg, _ = config.load()
            speed_limit_kb = cfg.download_speed_limit_kb
        self._limiter = _SpeedLimiter(speed_limit_kb or 0)

    def download(
        self,
        tasks: list[DownloadTask],
        progress: Callable[[DownloadProgress], None] | None = None,
    ) -> DownloadResult:
        client = self._client or _new_client()
        try:
            return self._download(client, tasks, progress)
        finally:
            if self._owns_client:
                client.close()

    def _download(
        self,
        client: httpx.Client,
        tasks: list[DownloadTask],
        progress: Callable[[DownloadProgress], None] | None,
    ) -> DownloadResult:
        # 同目标去重（只下第一个）
        unique: dict[Path, DownloadTask] = {}
        for task in tasks:
            unique.setdefault(task.dest, task)
        tasks = list(unique.values())

        result = DownloadResult()
        state = DownloadProgress(
            total_bytes=sum(t.size or 0 for t in tasks),
            total_files=len(tasks),
        )
        lock = threading.Lock()
        failed: list[tuple[str, str]] = []

        def report(current: str, add_bytes: int = 0, add_files: int = 0) -> None:
            if progress is None:
                return
            with lock:
                state.done_bytes += add_bytes
                state.done_files += add_files
                state.current = current
                snapshot = DownloadProgress(
                    done_bytes=state.done_bytes,
                    total_bytes=state.total_bytes,
                    done_files=state.done_files,
                    total_files=state.total_files,
                    current=state.current,
                )
            progress(snapshot)

        def run_one(task: DownloadTask) -> None:
            if not self.force and _verify(task.dest, task.sha1, task.size, task.sha256):
                with lock:
                    result.skipped += 1
                report(task.dest.name, add_files=1)
                return
            task.dest.parent.mkdir(parents=True, exist_ok=True)
            part = task.dest.with_name(task.dest.name + ".part")
            try:
                retryer = tenacity.Retrying(
                    stop=tenacity.stop_after_attempt(self.retries),
                    wait=tenacity.wait_exponential(
                        multiplier=self.retry_wait, min=self.retry_wait, max=self.retry_wait * 8
                    ),
                    retry=tenacity.retry_if_exception_type((httpx.HTTPError, OSError)),
                    reraise=True,
                )
                retryer(self._one_attempt, client, task, part)
                if not _verify(part, task.sha1, task.size, task.sha256):
                    raise DownloadError(tr_core("error.verify_failed", task.dest.name))
                part.replace(task.dest)
                part_size = task.size or task.dest.stat().st_size
                with lock:
                    result.downloaded += 1
                    result.bytes += part_size
                report(task.dest.name, add_bytes=part_size, add_files=1)
            except DownloadError:
                # 数据损坏：丢弃 .part（断点续传会放大错误数据）
                part.unlink(missing_ok=True)
                with lock:
                    failed.append((task.url, tr_core("error.verify_failed", task.dest.name)))
                report(task.dest.name, add_files=1)
            except (httpx.HTTPError, OSError) as exc:
                # 网络/磁盘错误：保留 .part 供下次 Range 断点续传
                with lock:
                    failed.append((task.url, describe_network_error(exc)))
                report(task.dest.name, add_files=1)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(run_one, t) for t in tasks]
            for future in as_completed(futures):
                future.result()  # run_one 已捕获异常，这里仅为等待完成

        result.failed.extend(failed)
        return result

    def _one_attempt(
        self, client: httpx.Client, task: DownloadTask, part: Path
    ) -> None:
        headers: dict[str, str] = {}
        try:
            offset = part.stat().st_size if part.exists() else 0
        except OSError:
            offset = 0
        if offset:
            headers["Range"] = "bytes=" + str(offset) + "-"
        with client.stream("GET", task.url, headers=headers) as resp:
            if resp.status_code == 416 and offset:
                # 服务器认为范围无效（.part 可能已完整/超出）：从头重新下载
                part.unlink(missing_ok=True)
                self._one_attempt(client, task, part)
                return
            resp.raise_for_status()
            mode = "ab" if resp.status_code == 206 else "wb"  # 非 206 说明服务器忽略 Range
            with part.open(mode) as f:
                for chunk in resp.iter_bytes(CHUNK):
                    f.write(chunk)
                    self._limiter.throttle(len(chunk))
