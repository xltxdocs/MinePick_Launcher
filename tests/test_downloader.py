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

import hashlib
import time

import httpx
import respx

from launcher.net.downloader import Downloader, DownloadTask


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


@respx.mock
def test_download_success_with_sha1(ws_tmp):
    data = b"hello world"
    respx.get("https://x/a.jar").mock(return_value=httpx.Response(200, content=data))
    result = Downloader(concurrency=2).download(
        [DownloadTask("https://x/a.jar", ws_tmp / "a.jar", sha1=_sha1(data), size=len(data))]
    )
    assert result.downloaded == 1
    assert result.failed == []
    assert (ws_tmp / "a.jar").read_bytes() == data


@respx.mock
def test_skip_existing_valid(ws_tmp):
    data = b"cached"
    dest = ws_tmp / "a.jar"
    dest.write_bytes(data)
    respx.get("https://x/a.jar").mock(return_value=httpx.Response(200, content=data))
    result = Downloader().download(
        [DownloadTask("https://x/a.jar", dest, sha1=_sha1(data), size=len(data))]
    )
    assert result.skipped == 1
    assert result.downloaded == 0


@respx.mock
def test_bad_sha1_fails_and_cleans_part(ws_tmp):
    respx.get("https://x/a.jar").mock(return_value=httpx.Response(200, content=b"wrong"))
    result = Downloader(retries=1, retry_wait=0.01).download(
        [DownloadTask("https://x/a.jar", ws_tmp / "a.jar", sha1="0" * 40)]
    )
    assert result.downloaded == 0
    assert len(result.failed) == 1
    assert not (ws_tmp / "a.jar").exists()
    assert not (ws_tmp / "a.jar.part").exists()


@respx.mock
def test_retry_then_success(ws_tmp):
    data = b"ok"
    respx.get("https://x/a.jar").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, content=data)]
    )
    result = Downloader(retries=2, retry_wait=0.01).download(
        [DownloadTask("https://x/a.jar", ws_tmp / "a.jar", sha1=_sha1(data), size=2)]
    )
    assert result.downloaded == 1
    assert result.failed == []


@respx.mock
def test_dedupe_and_progress(ws_tmp):
    respx.get("https://x/a.jar").mock(return_value=httpx.Response(200, content=b"x"))
    events = []
    result = Downloader(concurrency=2).download(
        [
            DownloadTask("https://x/a.jar", ws_tmp / "a.jar"),
            DownloadTask("https://x/a.jar", ws_tmp / "a.jar"),  # duplicate target
        ],
        progress=events.append,
    )
    assert result.downloaded + result.skipped == 1
    assert events
    assert events[-1].done_files == 1
    assert events[-1].total_files == 1


@respx.mock
def test_force_redownload(ws_tmp):
    data = b"new-content"
    dest = ws_tmp / "a.jar"
    dest.write_bytes(b"old")
    respx.get("https://x/a.jar").mock(return_value=httpx.Response(200, content=data))
    result = Downloader(force=True).download(
        [DownloadTask("https://x/a.jar", dest, sha1=_sha1(data), size=len(data))]
    )
    assert result.downloaded == 1
    assert dest.read_bytes() == data


@respx.mock
def test_resume_sends_range_and_completes(ws_tmp):
    # .part already has half the content: should send Range and receive a 206 resume
    data = b"hello-resume-world"
    dest = ws_tmp / "a.jar"
    part = ws_tmp / "a.jar.part"
    part.write_bytes(data[:6])
    seen_headers = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("Range"))
        offset = int(request.headers["Range"].removeprefix("bytes=").removesuffix("-"))
        return httpx.Response(206, content=data[offset:])

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = Downloader(client=client).download(
        [DownloadTask("https://x/a.jar", dest, sha1=_sha1(data), size=len(data))]
    )
    assert seen_headers == ["bytes=6-"]
    assert result.downloaded == 1
    assert dest.read_bytes() == data
    assert not part.exists()


@respx.mock
def test_416_restarts_full_download(ws_tmp):
    # .part already complete (or beyond): the server returns 416, so delete .part and download from scratch
    data = b"full-content"
    dest = ws_tmp / "a.jar"
    (ws_tmp / "a.jar.part").write_bytes(data)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("Range"))
        if request.headers.get("Range"):
            return httpx.Response(416)
        return httpx.Response(200, content=data)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = Downloader(client=client).download(
        [DownloadTask("https://x/a.jar", dest, sha1=_sha1(data), size=len(data))]
    )
    assert calls == ["bytes=12-", None]
    assert result.downloaded == 1
    assert dest.read_bytes() == data


@respx.mock
def test_network_failure_keeps_part_for_resume(ws_tmp):
    # stream interrupted: .part is kept, the failure info is the localized network error, then a Range resume can complete it
    first = b"p" * 65536  # one full CHUNK, ensures it is flushed to disk before the stream drops
    tail = b"q" * 100
    dest = ws_tmp / "a.jar"

    class PartialBody:
        def __iter__(self):
            yield first
            raise httpx.ReadTimeout("mid-stream drop")

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PartialBody())

    client = httpx.Client(transport=httpx.MockTransport(failing_handler))
    result = Downloader(client=client, retries=1, retry_wait=0.01).download(
        [DownloadTask("https://x/a.jar", dest, size=len(first) + len(tail))]
    )
    assert result.downloaded == 0
    assert len(result.failed) == 1
    assert "超时" in result.failed[0][1]
    assert (ws_tmp / "a.jar.part").read_bytes() == first  # .part is kept

    # second download: completes via resume
    seen = []

    def resume_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Range"))
        offset = int(request.headers["Range"].removeprefix("bytes=").removesuffix("-"))
        return httpx.Response(206, content=(first + tail)[offset:])

    client2 = httpx.Client(transport=httpx.MockTransport(resume_handler))
    data = first + tail
    result2 = Downloader(client=client2).download(
        [DownloadTask("https://x/a.jar", dest, sha1=_sha1(data), size=len(data))]
    )
    assert seen == ["bytes=65536-"]
    assert result2.downloaded == 1
    assert dest.read_bytes() == data
    assert not (ws_tmp / "a.jar.part").exists()

def test_speed_limit_throttles(ws_tmp):
    # 100 KB/s limit: a 200 KB download takes at least ~1 second
    data = b"x" * (200 * 1024)
    dest = ws_tmp / "big.jar"
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=data)))
    started = time.monotonic()
    result = Downloader(client=client, speed_limit_kb=100).download(
        [DownloadTask("https://x/big.jar", dest, size=len(data))]
    )
    elapsed = time.monotonic() - started
    assert result.failed == []
    assert dest.read_bytes() == data
    assert elapsed >= 1.0, "限速未生效: " + str(elapsed)


# --- segmented transfers (config download_segments; 1 = the historical single stream) ---

SEG_DATA = bytes(range(256)) * (16 * 1024)  # 4 MiB: 4 shards of 1 MiB at segments=4


def _no_parts(ws_tmp, name="big.jar"):
    """No temporary file of that target is left behind - neither .part nor any shard."""
    return [p.name for p in ws_tmp.iterdir() if p.name.startswith(name + ".part")] == []


def _default_config(**overrides):
    """A default config carrying `overrides` (the downloader reads download_segments from it)."""
    from launcher.config import LauncherConfig

    return LauncherConfig().model_copy(update=overrides)


def _range_transport(data: bytes, fail_ranges: object = (), fail_times: int = 1):
    """A MockTransport that serves byte ranges; `fail_ranges` are (first, last) spans to fail.

    Returns (transport, ranges_seen, failed_requests).
    """
    spans = list(fail_ranges) if fail_ranges else []
    seen: list[str] = []
    failures: dict[tuple[int, int], int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        header = request.headers.get("Range")
        if header is None:
            return httpx.Response(200, content=data)  # a full request ignores the spans on purpose
        seen.append(header)
        first, last = (int(part) for part in header.removeprefix("bytes=").split("-"))
        for span in spans:
            if first == span[0] and failures.get(span, 0) < fail_times:
                failures[span] = failures.get(span, 0) + 1
                return httpx.Response(500)
        if first > last or first >= len(data):
            return httpx.Response(416)
        return httpx.Response(206, content=data[first:last + 1])

    return httpx.MockTransport(handler), seen, failures


@respx.mock
def test_segmented_download_merges_and_verifies(ws_tmp, monkeypatch):
    """A Range-capable server: the shards are fetched in parallel, merged in order and verified."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    transport, ranges, _ = _range_transport(SEG_DATA)
    dest = ws_tmp / "big.jar"
    events = []
    result = Downloader(client=httpx.Client(transport=transport), concurrency=4).download(
        [
            DownloadTask(
                "https://x/big.jar",
                dest,
                sha1=hashlib.sha1(SEG_DATA).hexdigest(),
                sha256=hashlib.sha256(SEG_DATA).hexdigest(),
                size=len(SEG_DATA),
            )
        ],
        progress=events.append,
    )
    assert result.failed == []
    assert result.downloaded == 1
    assert result.bytes == len(SEG_DATA)
    assert dest.read_bytes() == SEG_DATA
    # the one-byte probe, then four disjoint shard ranges - nothing else
    assert ranges[0] == "bytes=0-0", ranges
    assert sorted(ranges[1:]) == [
        "bytes=0-1048575",
        "bytes=1048576-2097151",
        "bytes=2097152-3145727",
        "bytes=3145728-4194303",
    ], ranges
    assert _no_parts(ws_tmp), "分片下载留下了临时文件"
    assert events[-1].done_bytes == len(SEG_DATA)
    assert events[-1].done_files == 1


@respx.mock
def test_segments_one_is_the_single_stream(ws_tmp, monkeypatch):
    """The default (segments=1) must not split anything and must not probe for ranges."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=1), None))
    requests: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers.get("Range"))
        return httpx.Response(200, content=SEG_DATA)

    result = Downloader(client=httpx.Client(transport=httpx.MockTransport(handler))).download(
        [DownloadTask("https://x/big.jar", ws_tmp / "big.jar", size=len(SEG_DATA))]
    )
    assert result.downloaded == 1
    assert requests == [None], "segments=1 still sent a probe or a Range request"
    assert _no_parts(ws_tmp)


@respx.mock
def test_no_accept_ranges_falls_back_to_single_stream(ws_tmp, monkeypatch):
    """A server that advertises no Range support: the download succeeds without any sharding."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.headers.get("Range")))
        return httpx.Response(200, content=SEG_DATA)

    result = Downloader(client=httpx.Client(transport=httpx.MockTransport(handler))).download(
        [DownloadTask("https://x/big.jar", ws_tmp / "big.jar", size=len(SEG_DATA))]
    )
    assert result.failed == []
    assert result.downloaded == 1
    assert (ws_tmp / "big.jar").read_bytes() == SEG_DATA
    # the probe is allowed to ask for one byte; after it reports "no ranges", no shard may be requested
    gets = [r for method, r in requests if method == "GET"]
    assert gets == ["bytes=0-0", None], "回退后仍发出了分片请求"
    assert _no_parts(ws_tmp)


@respx.mock
def test_server_returning_200_for_a_range_falls_back(ws_tmp, monkeypatch):
    """A server that claims Accept-Ranges but answers 200 with the whole file: fall back, keep nothing."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    shard_ranges: list[str] = []
    full_streams = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal full_streams
        if request.method == "HEAD":
            return httpx.Response(
                200, headers={"Accept-Ranges": "bytes", "Content-Length": str(len(SEG_DATA))}
            )
        header = request.headers.get("Range")
        if header is None:
            full_streams += 1
        else:
            shard_ranges.append(header)
        return httpx.Response(200, content=SEG_DATA)  # ignores Range completely

    result = Downloader(
        client=httpx.Client(transport=httpx.MockTransport(handler)), retries=1, retry_wait=0.01
    ).download([DownloadTask("https://x/big.jar", ws_tmp / "big.jar", size=len(SEG_DATA))])
    assert result.failed == []
    assert (ws_tmp / "big.jar").read_bytes() == SEG_DATA
    # the HEAD advertised ranges, so the shards went out; each of them came back 200 (not 206, which is
    # the signal), and the file was finished by the single stream that followed
    assert len(shard_ranges) == 4, shard_ranges
    assert full_streams == 1, "the fallback stream ran " + str(full_streams) + " times"
    assert _no_parts(ws_tmp)


@respx.mock
def test_head_rejected_probe_get_finds_ranges(ws_tmp, monkeypatch):
    """HEAD is refused (405), but a one-byte GET answers 206: sharding still works."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    ranges: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(405)
        header = request.headers.get("Range")
        if header is None:
            return httpx.Response(200, content=SEG_DATA)
        ranges.append(header)
        first, last = (int(part) for part in header.removeprefix("bytes=").split("-"))
        return httpx.Response(
            206,
            content=SEG_DATA[first:last + 1],
            headers={"Content-Range": f"bytes {first}-{last}/{len(SEG_DATA)}"},
        )

    result = Downloader(
        client=httpx.Client(transport=httpx.MockTransport(handler)), concurrency=4
    ).download([DownloadTask("https://x/big.jar", ws_tmp / "big.jar", size=len(SEG_DATA))])
    assert result.failed == []
    assert (ws_tmp / "big.jar").read_bytes() == SEG_DATA
    assert "bytes=0-0" in ranges, "the one-byte probe GET never ran"
    assert len(ranges) == 5, ranges  # the probe plus four shards
    assert _no_parts(ws_tmp)


@respx.mock
def test_a_failing_shard_retries_then_completes(ws_tmp, monkeypatch):
    """One shard fails its first attempt: it is retried and the merged file still checks out."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    # the second shard (1 MiB..2 MiB) fails once, whatever order the pool reaches it in
    transport, ranges, failures = _range_transport(SEG_DATA, fail_ranges=[(1048576, 2097151)])
    result = Downloader(
        client=httpx.Client(transport=transport), concurrency=4, retries=3, retry_wait=0.01
    ).download(
        [
            DownloadTask(
                "https://x/big.jar",
                ws_tmp / "big.jar",
                sha1=hashlib.sha1(SEG_DATA).hexdigest(),
                size=len(SEG_DATA),
            )
        ]
    )
    assert failures == {(1048576, 2097151): 1}, "the failing shard was not retried exactly once"
    assert result.failed == []
    assert (ws_tmp / "big.jar").read_bytes() == SEG_DATA
    assert ranges.count("bytes=1048576-2097151") == 2
    assert _no_parts(ws_tmp)


@respx.mock
def test_a_shard_that_never_succeeds_leaves_no_garbage(ws_tmp, monkeypatch):
    """A shard keeps failing: the shard path gives up, the single stream finishes the file."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    ranges: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        header = request.headers.get("Range")
        if header is None:
            ranges.append(None)
            return httpx.Response(200, content=SEG_DATA)
        ranges.append(header)
        first, last = (int(part) for part in header.removeprefix("bytes=").split("-"))
        if first == 1048576:
            return httpx.Response(500)
        return httpx.Response(206, content=SEG_DATA[first:last + 1])

    result = Downloader(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        concurrency=4,
        retries=1,
        retry_wait=0.01,
    ).download(
        [
            DownloadTask(
                "https://x/big.jar",
                ws_tmp / "big.jar",
                sha1=hashlib.sha1(SEG_DATA).hexdigest(),
                size=len(SEG_DATA),
            )
        ]
    )
    assert result.failed == []
    assert (ws_tmp / "big.jar").read_bytes() == SEG_DATA
    # the probe (0-0) is not a shard: after the sharding gave up, the last request is the raw stream
    assert None in ranges, "the single-stream fallback never ran"
    assert next(r for r in ranges if r is not None) == "bytes=0-0", ranges
    assert _no_parts(ws_tmp)


@respx.mock
def test_both_paths_failing_reports_the_error_and_leaves_nothing(ws_tmp, monkeypatch):
    """Neither the shards nor the fallback stream can finish: one failure, no leftovers."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = Downloader(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        concurrency=4,
        retries=1,
        retry_wait=0.01,
    ).download([DownloadTask("https://x/big.jar", ws_tmp / "big.jar", size=len(SEG_DATA))])
    assert result.downloaded == 0
    assert len(result.failed) == 1
    assert not (ws_tmp / "big.jar").exists()
    assert not list(ws_tmp.iterdir()), "失败后留下了临时文件"


@respx.mock
def test_verification_failure_discards_the_shards_too(ws_tmp, monkeypatch):
    """A merged file that fails its digest must not leave a .part or a shard behind."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    transport, _, _ = _range_transport(SEG_DATA)
    result = Downloader(
        client=httpx.Client(transport=transport), concurrency=4, retries=1, retry_wait=0.01
    ).download(
        [DownloadTask("https://x/big.jar", ws_tmp / "big.jar", sha1="0" * 40, size=len(SEG_DATA))]
    )
    assert result.downloaded == 0
    assert len(result.failed) == 1
    assert not (ws_tmp / "big.jar").exists()
    assert not list(ws_tmp.iterdir()), "校验失败后留下了临时文件"


def test_segmented_speed_limit_is_still_global(ws_tmp, monkeypatch):
    """The shards share one budget: a segmented download is no faster than the limit allows.

    256 KB of shards at 100 KB/s must take about 2.5 s. Four separate per-shard allowances would
    finish it in about 0.64 s, and no limit at all would be instant.
    """
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    monkeypatch.setattr("launcher.net.downloader.MIN_SEGMENT_BYTES", 64 * 1024)
    data = b"x" * (256 * 1024)
    transport, ranges, _ = _range_transport(data)
    dest = ws_tmp / "big.jar"
    downloader = Downloader(client=httpx.Client(transport=transport), concurrency=4, speed_limit_kb=100)
    started = time.monotonic()
    result = downloader.download([DownloadTask("https://x/big.jar", dest, size=len(data))])
    elapsed = time.monotonic() - started
    assert result.failed == []
    assert dest.read_bytes() == data
    assert len([r for r in ranges if r != "bytes=0-0"]) == 4, ranges  # the segmented path really ran
    # one limiter for the whole downloader, so every shard throttles through the same bucket
    assert downloader._limiter.limit == 100 * 1024
    assert elapsed >= 1.0, "分片绕过了全局限速: " + str(elapsed)


def test_segmented_progress_never_goes_backwards(ws_tmp, monkeypatch):
    """Progress is monotonic while several shards report at once, and ends at the full size."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    transport, ranges, _ = _range_transport(SEG_DATA)
    events = []
    result = Downloader(client=httpx.Client(transport=transport), concurrency=4).download(
        [DownloadTask("https://x/big.jar", ws_tmp / "big.jar", size=len(SEG_DATA))],
        progress=events.append,
    )
    assert result.failed == []
    assert len(ranges) == 5, ranges  # the probe plus four shards
    seen = [event.done_bytes for event in events]
    assert seen == sorted(seen), "进度回调倒退了: " + str(seen)
    # the same byte count may only be reported once per file state: the completion report that carries
    # the finished-file count is a new event, a repeat of the same state would be a double count
    states = [(event.done_bytes, event.done_files) for event in events]
    assert len(states) == len(set(states)), "同一进度被回调了两次: " + str(states)
    assert seen[-1] == len(SEG_DATA)
    assert events[-1].done_files == 1
    assert events[-1].total_files == 1


def test_a_resumed_segment_failure_keeps_its_bytes(ws_tmp, monkeypatch):
    """With shard bytes already on disk, a failing shard is a failure - not a silent full restart."""
    monkeypatch.setattr("launcher.config.load", lambda *a, **k: (_default_config(download_segments=4), None))
    dest = ws_tmp / "big.jar"
    part = ws_tmp / "big.jar.part"
    (ws_tmp / "big.jar.part0").write_bytes(SEG_DATA[:1024])  # a previous attempt's first shard
    ranges: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        header = request.headers.get("Range")
        if header is None:
            return httpx.Response(200, content=SEG_DATA)
        ranges.append(header)
        first, last = (int(part) for part in header.removeprefix("bytes=").split("-"))
        if first == 1048576:
            return httpx.Response(500)
        return httpx.Response(206, content=SEG_DATA[first:last + 1])

    result = Downloader(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        concurrency=4,
        retries=1,
        retry_wait=0.01,
    ).download([DownloadTask("https://x/big.jar", dest, size=len(SEG_DATA))])
    assert result.downloaded == 0
    assert len(result.failed) == 1
    assert None not in ranges, "有分片进度时不该整份重下"
    # the resumed shard keeps its bytes and even grows: a retry continues from what was already there
    assert (ws_tmp / "big.jar.part0").stat().st_size > 1024, "已下载的分片被丢弃了"
    assert not part.exists()



