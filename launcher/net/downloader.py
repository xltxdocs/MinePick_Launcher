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

Segmented transfers are opt-in through config ``download_segments`` (default 1 = the historical
one-stream-per-file behaviour). A probe decides whether the server really serves byte ranges, and only
then is the file split into parallel Range requests. Every way that probe or a shard can go wrong
degrades to the single-stream path: a server that cannot do ranges ends up slower, never broken.

Packaging/sandbox compatibility notes:
- don't use tempfile.mkdtemp (the sandbox locks random-suffix directories); the temporary files are
  <target>.part (the single stream, or the merged result) and <target>.partN (shard N of a segmented run);
- on network failure the partial files are kept, so the next attempt resumes from each offset via Range
  (discarded on verification failure);
- only a thread pool is used (no multiprocessing.freeze_support needed under PyInstaller --onefile);
- all target paths are provided by the caller (the user data directory is resolved at runtime, not via __file__);
- the batches run on `concurrent.futures.ThreadPoolExecutor`, **not** on Qt's `QThreadPool`, so a caller that
  has to stop them before tearing its own objects down uses :func:`cancel_all_downloads` plus
  :func:`wait_for_downloads` - waiting on the Qt pool alone never reaches these threads.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import tenacity

from launcher.i18n import describe_network_error, tr_core
from launcher.meta.manifest import _new_client

CHUNK = 64 * 1024
# A shard shorter than this is not worth a request of its own: it only adds round trips
MIN_SEGMENT_BYTES = 1024 * 1024
# Upper bound on the shard pool of one file. The configured shard count is clamped to the batch
# concurrency for the same reason: a file's shards share that batch's worker slots.
MAX_SEGMENT_WORKERS = 8
# How often a segmented transfer re-reads the shard sizes to report progress
PROGRESS_INTERVAL = 0.2

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Download failure (user-facing message)."""


class DownloadCancelled(Exception):
    """The process is shutting down, so the transfer stopped where it was.

    Deliberately *not* a subclass of :class:`DownloadError`: a cancelled batch is not a failed download and
    must not be reported to the user as one. The bytes already on disk stay in the `.part` files, so the
    next launch resumes from them exactly like any other interrupted transfer.
    """


class _RangesUnsupported(Exception):
    """The server answered a Range request with the whole file, or not at all: shards cannot work here.

    Deliberately outside the retried exception types: retrying a server that ignores Range hands back
    the entire file again, so this has to fall back to a single stream right away.
    """


class _SegmentMismatch(Exception):
    """The shards do not add up to the announced length, so merging them would produce a broken file."""


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


@dataclass(frozen=True)
class _RangeInfo:
    """What the probe learned about one URL."""

    supported: bool = False
    total: int | None = None


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


def _content_length(headers: httpx.Headers) -> int | None:
    value = headers.get("Content-Length")
    return int(value) if (value or "").isdigit() else None


def _content_range_total(headers: httpx.Headers) -> int | None:
    """Total resource length from Content-Range ("bytes 0-0/1234"); None when it is "*" or absent."""
    _, _, total = (headers.get("Content-Range") or "").partition("/")
    total = total.strip()
    return int(total) if total.isdigit() else None


def _probe_ranges(client: httpx.Client, url: str) -> _RangeInfo:
    """Whether the server serves byte ranges, plus the resource length when one is announced.

    HEAD first (cheap, no body). When that is rejected, or answers without Content-Length, or does not
    advertise ``Accept-Ranges: bytes``, a one-byte GET decides it: a 206 there is proof enough even for
    a server that never advertises the capability, while a 200 is the answer we are looking for in the
    other direction. Every failure mode returns "not supported" and is not an error of the download.
    """
    try:
        head = client.head(url)
    except httpx.HTTPError:
        head = None
    if head is not None:
        accepts = "bytes" in (head.headers.get("Accept-Ranges") or "").lower()
        total = _content_length(head.headers)
        if accepts and total is not None:
            return _RangeInfo(supported=True, total=total)
    try:
        with client.stream("GET", url, headers={"Range": "bytes=0-0"}) as response:
            if response.status_code == 206:
                return _RangeInfo(supported=True, total=_content_range_total(response.headers))
            if response.status_code == 200:
                return _RangeInfo(supported=False, total=_content_length(response.headers))
    except httpx.HTTPError:
        pass
    return _RangeInfo()


def _segment_file(part: Path, index: int) -> Path:
    return part.with_name(part.name + str(index))


def _part_files(part: Path, segments: int) -> list[Path]:
    """Every temporary file a download of this target can leave behind.

    The single-stream `.part`, the shards `.part0..N-1`, and any shard number beyond the current
    setting: lowering the shard count must not strand the leftovers of a higher one, so the search
    widens rather than trusting `segments` alone.
    """
    bound = max(segments, MAX_SEGMENT_WORKERS) * 4
    found: list[Path] = []
    for candidate in part.parent.glob(part.name + "*"):
        suffix = candidate.name[len(part.name):]
        if suffix == "" or (suffix.isdigit() and int(suffix) < bound):
            found.append(candidate)
    return found


def _discard_parts(part: Path, segments: int) -> None:
    """Remove every temporary file of this target: a failed download must not leave garbage behind."""
    for path in _part_files(part, segments):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("无法清理临时分片: %s", path)


def _merge_segments(shards: list[Path], part: Path, total: int) -> None:
    """Concatenate the shards into `part` in order, or raise when they do not cover the announced length."""
    merged = 0
    for shard in shards:
        try:
            merged += shard.stat().st_size
        except OSError:
            break
    if merged != total:
        raise _SegmentMismatch(f"分片合计 {merged} != {total}")
    # Always start the merge from an empty `.part`: bytes left there by an older single-stream attempt
    # would otherwise be prepended to the merged file.
    part.unlink(missing_ok=True)
    with part.open("wb") as out:
        for shard in shards:
            with shard.open("rb") as src:
                shutil.copyfileobj(src, out, CHUNK)
    for shard in shards:
        try:
            shard.unlink(missing_ok=True)
        except OSError:
            logger.warning("无法清理临时分片: %s", shard)


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


_active_downloads = 0

# Cancellation and drain state. One process-wide flag is enough: quitting is not per-download, and a
# single flag cannot be left behind by a batch that ended abnormally. The count is the number of
# *worker threads* currently inside a transfer, so a waiter can tell "still writing to disk" from
# "finished" without guessing.
_cancelled = threading.Event()
_drain = threading.Condition()
_in_flight = 0
# Set only by cancel_all_downloads(): a "no new transfer may start" latch that outlives the flag above.
_shutting_down = False


class _CancelScope:
    """Run one unit of transfer work as a cancellable, countable unit.

    Entering bumps the public activity count, clears the cancellation flag - a flag left over from an
    earlier cancellation must not abort a batch that is only starting now (the GUI queues several
    downloads, and the first one to be cancelled can leave the flag set while the next one is still on
    its way) - and raises immediately when the process is already shutting down, so nothing is started
    just to be stopped.

    Leaving always releases the count, and turns a cancellation that arrived *during* the block into an
    exception, even when the block happened to reach its normal end: an update that finished streaming
    in the same instant the user quit must still not be installed.
    """

    def __enter__(self) -> None:
        global _active_downloads, _in_flight
        _cancelled.clear()
        with _drain:
            if _shutting_down:
                raise DownloadCancelled("shutting down")
            _active_downloads += 1
            _in_flight += 1

    def __exit__(self, exc_type, exc, tb) -> bool:
        global _active_downloads, _in_flight
        with _drain:
            _active_downloads -= 1
            _in_flight -= 1
            if _in_flight <= 0:
                _drain.notify_all()
        if exc_type is None and _cancelled.is_set():
            raise DownloadCancelled("cancelled")
        return False


@contextmanager
def download_activity():
    """Count one download for as long as the block runs, whatever way it ends.

    Every download path uses this - the downloader's own batches and the updater's streaming download -
    so there is exactly one counter behind active_download_count(), and the quit confirmation sees all
    of them. try/finally, so an exception cannot leave the counter stuck above zero and keep asking the
    user about downloads that are no longer running.

    It is also the cancellation and drain unit: everything that can still be writing to disk when the
    user quits registers here.
    """
    with _CancelScope():
        yield


def active_download_count() -> int:
    """How many download batches are running right now.

    Kept in the launcher layer because the GUI asks about it (the quit confirmation) while the core
    must stay UI-agnostic; a single integer is enough for that question.
    """
    return _active_downloads


def cancel_all_downloads() -> int:
    """Ask every transfer in flight to stop; return how many batches were running.

    Cooperative and bounded: a worker notices on its next chunk, so the call itself never waits. The
    bytes already on disk stay in the `.part` files and the next launch resumes from them. The latch it
    sets makes every transfer *after* this one refuse to start, because by then the caller is tearing
    the process - including Qt - down and a fresh download would be writing into that.
    """
    global _shutting_down
    with _drain:
        _shutting_down = True
    _cancelled.set()
    return _active_downloads


def is_cancelled() -> bool:
    """Whether the process has decided to stop transferring. One event read, safe from any thread."""
    return _cancelled.is_set()


def wait_for_downloads(timeout: float) -> bool:
    """Wait up to `timeout` seconds for every transfer thread to leave; True when none is left.

    Bounded on purpose: the caller is closing the application, and "the disk is busy" must never turn
    into "the program will not close". A `False` return is the honest answer - a thread is still inside
    a blocking socket read and cannot be interrupted - and the caller then closes anyway, having
    cancelled first so that thread's next action is to stop rather than to touch anything of the
    caller's.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    with _drain:
        while _in_flight > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _drain.wait(remaining)
        return True


def reset_cancellation_for_tests() -> None:
    """Only for tests: the latch is process-global, so a test suite must be able to clear it.

    Never called by the application - once the process has decided to quit, nothing may un-decide it.
    """
    global _shutting_down
    with _drain:
        _shutting_down = False
        _cancelled.clear()


class _Progress:
    """Turn "bytes now on disk" into monotonic progress deltas, from any number of shard threads.

    A segmented file is written by several threads at once, so a single completion-time callback would
    freeze the bar (and the GUI's rate estimate) for the whole transfer; each of them reports its own
    shard position instead. The delta is computed under a lock against what was already reported for
    this target, so overlapping shard readers can never add the same byte twice or move the total
    backwards. Kept thread-safe but cheap: the caller reads the sizes at most every PROGRESS_INTERVAL.
    """

    def __init__(
        self,
        progress: Callable[[DownloadProgress], None] | None,
        state: DownloadProgress,
        lock: threading.Lock,
    ) -> None:
        self._progress = progress
        self._state = state
        self._lock = lock
        self._reported: dict[Path, int] = {}
        self._last_tick: dict[Path, float] = {}

    def written(self, dest: Path, written: int, current: str) -> None:
        """Report `written` bytes for `dest` as done, adding only the part that is new."""
        if self._progress is None or _cancelled.is_set():
            return
        with self._lock:
            delta = written - self._reported.get(dest, 0)
            if delta <= 0:
                return
            self._reported[dest] = written
            self._state.done_bytes += delta
            self._state.current = current
            snapshot = DownloadProgress(
                done_bytes=self._state.done_bytes,
                total_bytes=self._state.total_bytes,
                done_files=self._state.done_files,
                total_files=self._state.total_files,
                current=self._state.current,
            )
        self._progress(snapshot)

    def files_done(self, current: str, count: int = 1) -> None:
        """Report whole files as finished (a skipped file, a failure, a completed download)."""
        if self._progress is None or _cancelled.is_set():
            return
        with self._lock:
            self._state.done_files += count
            self._state.current = current
            snapshot = DownloadProgress(
                done_bytes=self._state.done_bytes,
                total_bytes=self._state.total_bytes,
                done_files=self._state.done_files,
                total_files=self._state.total_files,
                current=self._state.current,
            )
        self._progress(snapshot)

    def tick(self, dest: Path, part: Path, segments: int) -> None:
        """Report the shard file sizes of `dest`, at most once per PROGRESS_INTERVAL.

        A caller that stalls (a slow shard) may keep its last delta unreported until the file finishes;
        `_download` therefore reports the final size once more after completion.
        """
        if self._progress is None or segments <= 1:
            return
        now = time.monotonic()
        if now - self._last_tick.get(dest, 0.0) < PROGRESS_INTERVAL:
            return
        self._last_tick[dest] = now
        written = 0
        for index in range(segments):
            try:
                written += _segment_file(part, index).stat().st_size
            except OSError:
                continue
        self.written(dest, written, dest.name)


class Downloader:
    """Download a list of tasks concurrently; files that already exist and pass verification are skipped, and failed tasks are reported in aggregate.

    Resumable transfers: downloads write to <dest>.part, and on network failure the .part is kept so the next attempt resumes via Range;
    a verification failure is treated as corruption, so the .part (and any shard) is discarded and re-downloaded.
    Rate limiting: when speed_limit_kb is None, read config download_speed_limit_kb.
    Segmented transfers: when segments is None, read config download_segments (1 = one stream per file).
    Only a server that passes the probe is segmented, and any shard failure falls back to one stream.
    """

    def __init__(
        self,
        concurrency: int = 4,
        client: httpx.Client | None = None,
        retries: int = 3,
        retry_wait: float = 1.0,
        force: bool = False,
        speed_limit_kb: int | None = None,
        segments: int | None = None,
    ) -> None:
        self.concurrency = concurrency
        self._client = client
        self._owns_client = client is None
        self.retries = retries
        self.retry_wait = retry_wait
        self.force = force
        if speed_limit_kb is None or segments is None:
            from launcher import config

            cfg, _ = config.load()
            if speed_limit_kb is None:
                speed_limit_kb = cfg.download_speed_limit_kb
            if segments is None:
                segments = cfg.download_segments
        # One limiter for the whole downloader: a segmented file draws its budget from the same bucket
        # as every other file in flight, instead of handing each shard an allowance of its own.
        self._limiter = _SpeedLimiter(speed_limit_kb or 0)
        self._segments = max(1, int(segments or 1))

    def download(
        self,
        tasks: list[DownloadTask],
        progress: Callable[[DownloadProgress], None] | None = None,
    ) -> DownloadResult:
        client = self._client or _new_client()
        try:
            # The scope is the batch's registration for cancellation *and* its place in the activity
            # count: a batch raising because the process is shutting down is a cancellation, not a
            # failed download, so the caller can tell the two apart.
            with download_activity():
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
        reporter = _Progress(progress, state, lock)
        failed: list[tuple[str, str]] = []

        def run_one(task: DownloadTask) -> None:
            if not self.force and _verify(task.dest, task.sha1, task.size, task.sha256):
                with lock:
                    result.skipped += 1
                reporter.files_done(task.dest.name)
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
                # `_download_segmented` answers "is the file already waiting in `part`?": False when the
                # shard path finished it (only verification is left), True when a single stream still
                # has to do the work - no shards configured, the probe refused, or a run that failed
                # with nothing worth resuming.
                done = self._segments > 1 and not self._download_segmented(
                    client, task, part, reporter
                )
                if not done:
                    # One stream: the default path, and the fallback for every shard failure.
                    retryer(self._one_attempt, client, task, part, reporter)
                if not _verify(part, task.sha1, task.size, task.sha256):
                    raise DownloadError(tr_core("error.verify_failed", task.dest.name))
                part.replace(task.dest)
                part_size = task.dest.stat().st_size
                with lock:
                    result.downloaded += 1
                    result.bytes += part_size
                # Close the progress gap a throttled tick may have left open (and count the bytes of a
                # plain single-stream download, which does not tick per chunk).
                reporter.written(task.dest, part_size, task.dest.name)
                reporter.files_done(task.dest.name)
            except DownloadError:
                # corrupt data: discard the temporary files (resuming would amplify the bad data)
                _discard_parts(part, max(self._segments, MAX_SEGMENT_WORKERS))
                with lock:
                    failed.append((task.url, tr_core("error.verify_failed", task.dest.name)))
                reporter.files_done(task.dest.name)
            except (httpx.HTTPError, OSError) as exc:
                # network/disk error: keep the partial files for the next Range resume
                with lock:
                    failed.append((task.url, describe_network_error(exc)))
                reporter.files_done(task.dest.name)

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(run_one, t) for t in tasks]
            for future in as_completed(futures):
                future.result()  # run_one already catches exceptions; this just waits for completion

        result.failed.extend(failed)
        return result

    def _download_segmented(
        self,
        client: httpx.Client,
        task: DownloadTask,
        part: Path,
        reporter: _Progress,
    ) -> bool:
        """Run the parallel-shard path; return True when the caller has to fall back to a single stream.

        Returns False when the file sits complete in `part`, ready for verification. A server that
        cannot do ranges is a probe result here, never an error.
        """
        plan = self._plan_segments(client, task, part)
        if plan is None:
            return True
        segments, total = plan
        shards = [_segment_file(part, index) for index in range(segments)]
        spans = [
            (total * index // segments, (total * (index + 1) // segments) - 1)
            for index in range(segments)
        ]
        # Bytes already on disk from an earlier attempt: a resume worth keeping. Only a run that
        # started from nothing may throw everything away and re-download as one stream.
        resumed = sum(shard.stat().st_size for shard in shards if shard.exists())
        workers = max(1, min(len(shards), self.concurrency, MAX_SEGMENT_WORKERS))

        def shard_job(shard: Path, first: int, last: int) -> None:
            self._segment_attempt(client, shard, task.url, first, last)
            reporter.tick(task.dest, part, segments)

        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(shard_job, shard, *span) for shard, span in zip(shards, spans)]
                for future in as_completed(futures):
                    future.result()
            _merge_segments(shards, part, total)
        except _RangesUnsupported:
            # The server refuses ranges, or answered with the whole file: one stream is the answer.
            if not resumed:
                _discard_parts(part, self._segments)
                return True
            raise
        except _SegmentMismatch:
            # The shards do not add up to the announced length, so nothing here can be trusted or
            # resumed; a run that had resumed bytes keeps its failure instead of silently re-fetching.
            _discard_parts(part, self._segments)
            return resumed == 0
        except (httpx.HTTPError, OSError):
            # A shard ran out of retries. Same rule: fresh start falls back, a resume keeps its bytes.
            if not resumed:
                _discard_parts(part, self._segments)
                return True
            raise
        return False

    def _plan_segments(
        self, client: httpx.Client, task: DownloadTask, part: Path
    ) -> tuple[int, int] | None:
        """(shard count, total length) when shards are worth trying, else None for a single stream."""
        info = _probe_ranges(client, task.url)
        total = task.size or info.total
        # Size decides before the flag does: a resource without a length cannot be split at all, and
        # one too small to split is served faster by a single stream.
        if not info.supported or not total or total <= 0:
            logger.debug("未启用分片下载（探测未通过）: %s", task.url)
            return None
        try:
            if part.exists():
                # Shards carry their own offsets, so a leftover shard resumes fine; a leftover `.part`
                # means an older single-stream attempt, and its byte count would be read as shard data.
                logger.debug("清除单流残留 .part 以便分片: %s", part.name)
                part.unlink()
        except OSError:
            return None
        return min(self._segments, max(1, total // MIN_SEGMENT_BYTES)), total

    def _segment_attempt(
        self, client: httpx.Client, shard: Path, url: str, first: int, last: int
    ) -> None:
        retryer = tenacity.Retrying(
            stop=tenacity.stop_after_attempt(self.retries),
            wait=tenacity.wait_exponential(
                multiplier=self.retry_wait, min=self.retry_wait, max=self.retry_wait * 8
            ),
            retry=tenacity.retry_if_exception_type((httpx.HTTPError, OSError)),
            reraise=True,
        )
        retryer(self._segment_piece, client, shard, url, first, last)

    def _segment_piece(
        self, client: httpx.Client, shard: Path, url: str, first: int, last: int
    ) -> None:
        span = last - first + 1
        try:
            offset = shard.stat().st_size if shard.exists() else 0
        except OSError:
            offset = 0
        if offset > span:
            # Longer than the span it belongs to: corrupt, or from a different resource - start over
            shard.unlink(missing_ok=True)
            offset = 0
        if offset >= span:
            return  # this shard is already complete
        if _cancelled.is_set():
            raise DownloadCancelled(url)
        headers = {"Range": f"bytes={first + offset}-{last}"}
        with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 416:
                # Not satisfiable. Unlike the single-stream case this cannot mean "already complete",
                # so ask the caller to fall back rather than loop on it.
                raise _RangesUnsupported("HTTP 416 for " + url)
            if resp.status_code == 200:
                # The server sent the whole resource: ranges are off, retrying would just repeat it.
                raise _RangesUnsupported("HTTP 200 for a Range request on " + url)
            resp.raise_for_status()
            mode = "ab" if offset else "wb"
            with shard.open(mode) as f:
                for chunk in resp.iter_bytes(CHUNK):
                    if _cancelled.is_set():
                        raise DownloadCancelled(url)
                    f.write(chunk)
                    self._limiter.throttle(len(chunk))

    def _one_attempt(
        self,
        client: httpx.Client,
        task: DownloadTask,
        part: Path,
        reporter: _Progress | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        try:
            offset = part.stat().st_size if part.exists() else 0
        except OSError:
            offset = 0
        if offset:
            headers["Range"] = "bytes=" + str(offset) + "-"
        if _cancelled.is_set():
            raise DownloadCancelled(task.url)
        with client.stream("GET", task.url, headers=headers) as resp:
            if resp.status_code == 416 and offset:
                # server considers the range invalid (.part may already be complete/too large): re-download from scratch
                part.unlink(missing_ok=True)
                self._one_attempt(client, task, part, reporter)
                return
            resp.raise_for_status()
            mode = "ab" if resp.status_code == 206 else "wb"  # non-206 means the server ignored the Range header
            with part.open(mode) as f:
                for chunk in resp.iter_bytes(CHUNK):
                    # The chunk boundary is the cancellation point: nothing is written after the flag is
                    # set, and the bytes already flushed stay in the `.part` for the next launch. The
                    # default path (no shutdown, no speed limit) costs one event check per 64 KB.
                    if _cancelled.is_set():
                        raise DownloadCancelled(task.url)
                    f.write(chunk)
                    self._limiter.throttle(len(chunk))
