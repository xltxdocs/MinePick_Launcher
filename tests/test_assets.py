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
    (objects / "ab" / "abc123").write_bytes(b"0" * 10)  # 大小正确
    (objects / "de").mkdir(parents=True)
    (objects / "de" / "def456").write_bytes(b"0" * 5)  # 大小不符
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
