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
            DownloadTask("https://x/a.jar", ws_tmp / "a.jar"),  # 重复目标
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
    # .part 已有一半内容：应发 Range 并收到 206 续传
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
    # .part 已完整（或超出）：服务器回 416，应删除 .part 从头下载
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
    # 流中断：.part 保留，失败信息为本地化网络错误，随后可用 Range 续传完成
    first = b"p" * 65536  # 一个完整 CHUNK，确保落盘后再断流
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
    assert (ws_tmp / "a.jar.part").read_bytes() == first  # .part 保留

    # 第二次下载：从断点续传完成
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
    # #10：100 KB/s 限制下 200 KB 下载至少耗时 ~1 秒
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


