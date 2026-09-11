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

"""Generic downloader: concurrency, resumable transfers (Range + keeping .part), sha1/sha256 verification, retry, progress callbacks.

Packaging/sandbox compatibility notes:
- don't use tempfile.mkdtemp (the sandbox locks random-suffix directories); the temp file is <target>.part;
- on network failure keep the .part, so the next attempt resumes from the offset via Range (discarded on verification failure);
- only a thread pool is used (no multiprocessing.freeze_support needed under PyInstaller --onefile);
- all target paths are provided by the caller (the user data directory is resolved at runtime, not via __file__).
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
    """Download failure (user-facing message)."""


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
    """Whether the file exists and passes verification (a single read computes the needed digests)."""
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
    """Global rate limit: sleep by write volume to top up the budget (token-bucket approximation, shared across threads)."""

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
    """Download a list of tasks concurrently; files that already exist and pass verification are skipped, and failed tasks are reported in aggregate.

    Resumable transfers: downloads write to <dest>.part, and on network failure the .part is kept so the next attempt resumes via Range;
    a verification failure is treated as corruption, so the .part is discarded and re-downloaded.
    Rate limiting: when speed_limit_kb is None, read config download_speed_limit_kb.
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
        # dedupe by target (only download the first)
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
                # corrupt data: discard the .part (resuming would amplify the bad data)
                part.unlink(missing_ok=True)
                with lock:
                    failed.append((task.url, tr_core("error.verify_failed", task.dest.name)))
                report(task.dest.name, add_files=1)
            except (httpx.HTTPError, OSError) as exc:
                # network/disk error: keep the .part for the next Range resume
                with lock:
                    failed.append((task.url, describe_network_error(exc)))
                report(task.dest.name, add_files=1)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(run_one, t) for t in tasks]
            for future in as_completed(futures):
                future.result()  # run_one already catches exceptions; this just waits for completion

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
                # server considers the range invalid (.part may already be complete/too large): re-download from scratch
                part.unlink(missing_ok=True)
                self._one_attempt(client, task, part)
                return
            resp.raise_for_status()
            mode = "ab" if resp.status_code == 206 else "wb"  # non-206 means the server ignored the Range header
            with part.open(mode) as f:
                for chunk in resp.iter_bytes(CHUNK):
                    f.write(chunk)
                    self._limiter.throttle(len(chunk))
