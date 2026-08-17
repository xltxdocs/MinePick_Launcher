import hashlib
import json

import httpx
import respx

from launcher.install import install_version
from launcher.meta.rules import Platform

WIN = Platform(os="windows", arch="x64", version="10.0.26100")


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


CLIENT = b"client-jar-data"
LIB1 = b"lib1-data"
NAT = b"natives-data"
LOGCFG = b"log4j-config"
ASSET1 = b"asset-icon-1"
ASSET2 = b"asset-sound-2"
HASH1 = _sha1(ASSET1)
HASH2 = _sha1(ASSET2)

VERSION_RAW = {
    "id": "testv",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "minecraftArguments": "--demo",
    "javaVersion": {"component": "jre-legacy", "majorVersion": 8},
    "assetIndex": {"id": "idx1", "url": "https://x/idx1.json"},
    "libraries": [
        {
            "name": "com.example:lib1:1.0",
            "downloads": {
                "artifact": {
                    "path": "com/example/lib1/1.0/lib1-1.0.jar",
                    "sha1": _sha1(LIB1),
                    "size": len(LIB1),
                    "url": "https://x/lib1.jar",
                }
            },
        },
        {
            "name": "org.lwjgl.lwjgl:lwjgl-platform:2.9.4",
            "natives": {"windows": "natives-windows"},
            "downloads": {
                "classifiers": {
                    "natives-windows": {
                        "path": "org/lwjgl/lwjgl/lwjgl-platform/2.9.4/lwjgl-platform-2.9.4-natives-windows.jar",
                        "sha1": _sha1(NAT),
                        "size": len(NAT),
                        "url": "https://x/nat.jar",
                    }
                }
            },
        },
    ],
    "downloads": {"client": {"sha1": _sha1(CLIENT), "size": len(CLIENT), "url": "https://x/client.jar"}},
    "logging": {
        "client": {
            "argument": "-Dlog4j.configurationFile=x",
            "file": {"id": "cfg1", "sha1": _sha1(LOGCFG), "size": len(LOGCFG), "url": "https://x/log.xml"},
            "type": "log4j2-xml",
        }
    },
}

ASSET_INDEX_RAW = {
    "objects": {
        "icons/icon.png": {"hash": HASH1, "size": len(ASSET1)},
        "sounds/s.ogg": {"hash": HASH2, "size": len(ASSET2)},
    }
}


def _mock_all():
    respx.get("https://x/client.jar").mock(return_value=httpx.Response(200, content=CLIENT))
    respx.get("https://x/lib1.jar").mock(return_value=httpx.Response(200, content=LIB1))
    respx.get("https://x/nat.jar").mock(return_value=httpx.Response(200, content=NAT))
    respx.get("https://x/log.xml").mock(return_value=httpx.Response(200, content=LOGCFG))
    respx.get("https://x/idx1.json").mock(
        return_value=httpx.Response(200, json=ASSET_INDEX_RAW)
    )
    respx.get("https://resources.download.minecraft.net/" + HASH1[:2] + "/" + HASH1).mock(
        return_value=httpx.Response(200, content=ASSET1)
    )
    respx.get("https://resources.download.minecraft.net/" + HASH2[:2] + "/" + HASH2).mock(
        return_value=httpx.Response(200, content=ASSET2)
    )


def _prepare(ws_tmp):
    cache = ws_tmp / "cache"
    (cache / "versions").mkdir(parents=True)
    (cache / "versions" / "testv.json").write_text(
        json.dumps(VERSION_RAW), encoding="utf-8"
    )
    return ws_tmp / "game", cache


@respx.mock
def test_install_full_layout(ws_tmp):
    game, cache = _prepare(ws_tmp)
    _mock_all()
    result = install_version(
        "testv", game_dir=game, cache_dir=cache, concurrency=2, platform=WIN
    )
    assert result.failed == []
    assert result.downloaded == 6  # client + lib1 + natives + log + 2 assets

    assert (game / "versions" / "testv" / "testv.json").exists()
    assert (game / "versions" / "testv" / "testv.jar").read_bytes() == CLIENT
    assert (game / "libraries" / "com" / "example" / "lib1" / "1.0" / "lib1-1.0.jar").read_bytes() == LIB1
    assert (
        game
        / "libraries"
        / "org"
        / "lwjgl"
        / "lwjgl"
        / "lwjgl-platform"
        / "2.9.4"
        / "lwjgl-platform-2.9.4-natives-windows.jar"
    ).read_bytes() == NAT
    assert (game / "assets" / "indexes" / "idx1.json").exists()
    assert (game / "assets" / "objects" / HASH1[:2] / HASH1).read_bytes() == ASSET1
    assert (game / "assets" / "objects" / HASH2[:2] / HASH2).read_bytes() == ASSET2
    assert (game / "assets" / "log_configs" / "idx1").read_bytes() == LOGCFG


def test_modern_natives_task_uses_artifact():
    # 现代格式（库名第 4 段分类器）：任务应使用 downloads.artifact 的 url/sha1
    from pathlib import Path as _Path

    from launcher.install import _library_task
    from launcher.meta.rules import ResolvedLibrary
    from launcher.meta.version import Library

    lib = Library(
        name="org.lwjgl:lwjgl-glfw:3.3.1:natives-windows",
        downloads={
            "artifact": {
                "path": "org/lwjgl/lwjgl-glfw/3.3.1/lwjgl-glfw-3.3.1-natives-windows.jar",
                "sha1": "abc123",
                "size": 99,
                "url": "https://piston-data.mojang.com/x.jar",
            }
        },
    )
    task = _library_task(
        ResolvedLibrary(library=lib, classifier="natives-windows"),
        _Path("/libs"),
    )
    assert task.url == "https://piston-data.mojang.com/x.jar"
    assert task.sha1 == "abc123"
    assert task.size == 99
    assert task.dest.name == "lwjgl-glfw-3.3.1-natives-windows.jar"


@respx.mock
def test_install_auto_downloads_java(ws_tmp, monkeypatch):
    # VERSION_RAW 无 javaVersion -> 用声明值 8 验证自动下载分支
    import launcher.java as java_mod

    game, cache = _prepare(ws_tmp)
    _mock_all()
    installed: list[int] = []

    def fake_list_java(probe_dir=None):
        return []

    def fake_install_java(major, *, runtime_dir=None, probe_dir=None, progress=None):
        installed.append(major)

    monkeypatch.setattr(java_mod, "list_java", fake_list_java)
    monkeypatch.setattr(java_mod, "install_java", fake_install_java)

    result = install_version(
        "testv",
        game_dir=game,
        cache_dir=cache,
        concurrency=2,
        platform=WIN,
        auto_install_java=True,
    )
    assert result.failed == []
    assert installed == [8]  # 缺失 Java 8 -> 自动触发下载
    # 关闭自动下载：不触发
    installed.clear()
    install_version(
        "testv",
        game_dir=game,
        cache_dir=cache,
        concurrency=2,
        platform=WIN,
        auto_install_java=False,
    )
    assert installed == []


@respx.mock
def test_reinstall_skips_everything(ws_tmp):
    game, cache = _prepare(ws_tmp)
    _mock_all()
    install_version("testv", game_dir=game, cache_dir=cache, concurrency=2, platform=WIN)
    result = install_version(
        "testv", game_dir=game, cache_dir=cache, concurrency=2, platform=WIN
    )
    # 资源已存在不会进入任务列表；client+lib+natives+log 共 4 个任务全部跳过
    assert result.downloaded == 0
    assert result.skipped == 4
    assert result.failed == []
