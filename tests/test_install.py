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
    # modern format (the 4th segment of the library name is the classifier): tasks should use the downloads.artifact url/sha1
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
    # VERSION_RAW has no javaVersion -> use the declared value 8 to verify the auto-download branch
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
    assert installed == [8]  # missing Java 8 -> auto-triggers download
    # auto-download off: not triggered
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
    # existing assets do not enter the task list; all 4 tasks (client+lib+natives+log) are skipped
    assert result.downloaded == 0
    assert result.skipped == 4
    assert result.failed == []
