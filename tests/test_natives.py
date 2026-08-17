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

import io
import zipfile

from launcher.launch.natives import LaunchError, prepare_natives
from launcher.meta.rules import ResolvedLibrary
from launcher.meta.version import Library


def _make_jar(entries: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _lib(name: str, classifier: str, path: str, exclude=None) -> ResolvedLibrary:
    downloads = {"classifiers": {classifier: {"path": path}}}
    extract = {"exclude": exclude} if exclude else None
    return ResolvedLibrary(
        library=Library(name=name, downloads=downloads, extract=extract),
        classifier=classifier,
    )


def test_prepare_natives_extracts_and_excludes(ws_tmp):
    libs_dir = ws_tmp / "libraries"
    (libs_dir / "rel").mkdir(parents=True)
    (libs_dir / "rel" / "one.jar").write_bytes(
        _make_jar(
            {
                "x64.dll": "DLL1",
                "sub/y64.dll": "DLL2",
                "META-INF/MANIFEST.MF": "m",
                "custom/skip.txt": "s",
            }
        )
    )
    resolved = [_lib("g:a:v", "natives-windows", "rel/one.jar", exclude=["custom/"])]
    natives_dir = ws_tmp / "natives"
    prepare_natives(resolved, libs_dir, natives_dir)
    assert (natives_dir / "x64.dll").read_bytes() == b"DLL1"
    assert (natives_dir / "sub" / "y64.dll").read_bytes() == b"DLL2"
    assert not (natives_dir / "META-INF").exists()
    assert not (natives_dir / "custom").exists()


def test_prepare_natives_wipes_dir(ws_tmp):
    libs_dir = ws_tmp / "libraries"
    (libs_dir / "rel").mkdir(parents=True)
    (libs_dir / "rel" / "one.jar").write_bytes(_make_jar({"a.dll": "A"}))
    resolved = [_lib("g:a:v", "natives-windows", "rel/one.jar")]
    natives_dir = ws_tmp / "natives"
    prepare_natives(resolved, libs_dir, natives_dir)
    (natives_dir / "stale.dll").write_text("old", encoding="utf-8")
    prepare_natives(resolved, libs_dir, natives_dir)
    assert (natives_dir / "a.dll").exists()
    assert not (natives_dir / "stale.dll").exists()


def test_prepare_natives_missing_jar_raises(ws_tmp):
    resolved = [_lib("g:a:v", "natives-windows", "rel/missing.jar")]
    try:
        prepare_natives(resolved, ws_tmp / "libraries", ws_tmp / "natives")
    except LaunchError as exc:
        assert "missing.jar" in str(exc)
    else:
        raise AssertionError("应抛出 LaunchError")
