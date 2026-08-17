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

from pathlib import Path

import httpx
import respx

from launcher.meta.assets import (
    AssetIndex,
    AssetObject,
    asset_relative_path,
    fetch_asset_index,
    missing_assets,
)
from launcher.meta.version import AssetIndexInfo


def test_asset_relative_path():
    assert asset_relative_path("abc123def") == Path("ab") / "abc123def"


def test_missing_assets(ws_tmp):
    index = AssetIndex(
        objects={
            "a/b": AssetObject(hash="abc123", size=10),
            "c": AssetObject(hash="def456", size=20),
        }
    )
    objects = ws_tmp / "objects"
    (objects / "ab").mkdir(parents=True)
    (objects / "ab" / "abc123").write_bytes(b"0" * 10)  # correct size
    (objects / "de").mkdir(parents=True)
    (objects / "de" / "def456").write_bytes(b"0" * 5)  # size mismatch
    missing = missing_assets(index, objects)
    assert [name for name, _ in missing] == ["c"]


@respx.mock
def test_fetch_and_cache(ws_tmp):
    info = AssetIndexInfo(id="17", url="https://example.com/17.json")
    respx.get("https://example.com/17.json").mock(
        return_value=httpx.Response(200, json={"objects": {"x": {"hash": "h1", "size": 1}}})
    )
    cache = ws_tmp / "assets" / "17.json"
    index = fetch_asset_index(info, cache_path=cache)
    assert index.objects["x"].hash == "h1"
    assert cache.exists()
    index2 = fetch_asset_index(info, cache_path=cache)
    assert index2.objects["x"].hash == "h1"
