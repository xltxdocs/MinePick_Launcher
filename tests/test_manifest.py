import json

import httpx
import respx

from launcher.meta.manifest import fetch_manifest

MANIFEST_RAW = {
    "latest": {"release": "1.21.8", "snapshot": "25w01a"},
    "versions": [
        {
            "id": "1.21.8",
            "type": "release",
            "url": "https://example.com/v/1.21.8.json",
            "time": "2026-01-01T00:00:00+00:00",
            "releaseTime": "2026-01-01T00:00:00+00:00",
        },
        {"id": "25w01a", "type": "snapshot", "url": "https://example.com/v/25w01a.json"},
    ],
}

PISTON = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
LAUNCHERMETA = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"


@respx.mock
def test_fetch_and_cache(ws_tmp):
    respx.get(PISTON).mock(return_value=httpx.Response(200, json=MANIFEST_RAW))
    cache = ws_tmp / "version_manifest.json"
    m = fetch_manifest(cache_path=cache)
    assert m.latest["release"] == "1.21.8"
    assert m.find("1.21.8") is not None
    assert m.find("nope") is None
    assert cache.exists()
    # 缓存生效：不发新请求
    m2 = fetch_manifest(cache_path=cache)
    assert m2 == m


@respx.mock
def test_force_refresh(ws_tmp):
    route = respx.get(PISTON)
    route.mock(return_value=httpx.Response(200, json=MANIFEST_RAW))
    cache = ws_tmp / "version_manifest.json"
    fetch_manifest(cache_path=cache)
    new_raw = dict(MANIFEST_RAW)
    new_raw["latest"] = {"release": "1.22.0", "snapshot": "25w99z"}
    route.mock(return_value=httpx.Response(200, json=new_raw))
    m = fetch_manifest(cache_path=cache, force=True)
    assert m.latest["release"] == "1.22.0"


@respx.mock
def test_expired_cache_refetches(ws_tmp):
    respx.get(PISTON).mock(return_value=httpx.Response(200, json=MANIFEST_RAW))
    cache = ws_tmp / "version_manifest.json"
    cache.write_text(
        json.dumps({"fetched_at": 0, "manifest": {"latest": {}, "versions": []}}),
        encoding="utf-8",
    )
    m = fetch_manifest(cache_path=cache)
    assert m.latest["release"] == "1.21.8"


@respx.mock
def test_fallback_url(ws_tmp):
    respx.get(PISTON).mock(return_value=httpx.Response(500))
    respx.get(LAUNCHERMETA).mock(return_value=httpx.Response(200, json=MANIFEST_RAW))
    m = fetch_manifest(cache_path=ws_tmp / "m.json")
    assert m.latest["release"] == "1.21.8"
