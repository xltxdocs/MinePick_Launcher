"""launcher/mods/curseforge.py 单测：搜索解析、Key 优先级、文件过滤。"""

import httpx

from launcher.mods import curseforge as cf
from launcher.mods.models import ModSearchHit


def _client(payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_search_parses_hits() -> None:
    payload = {
        "data": [
            {
                "id": 394468,
                "name": "Sodium",
                "summary": "A modern rendering engine",
                "downloadCount": 142812847,
                "logo": {"thumbnailUrl": "https://x/thumb.png"},
            }
        ]
    }
    hits = cf.search_projects("sodium", limit=10, client=_client(payload))
    assert len(hits) == 1
    h = hits[0]
    assert isinstance(h, ModSearchHit)
    assert h.slug == "394468"
    assert h.title == "Sodium"
    assert h.downloads == 142812847
    assert h.icon_url == "https://x/thumb.png"


def test_search_params_include_filters() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"data": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cf.search_projects("x", limit=5, kind="resourcepack", game_version="1.20.1", client=client)
    assert seen["classId"] == "12"
    assert seen["gameVersion"] == "1.20.1"
    assert seen["sortField"] == "TotalDownloads"


def test_list_files_keeps_release_only() -> None:
    payload = {
        "data": [
            {"id": 1, "releaseType": 1, "displayName": "A", "downloadUrl": "https://x/a.jar", "fileLength": 100},
            {"id": 2, "releaseType": 2, "displayName": "B", "downloadUrl": "https://x/b.jar", "fileLength": 100},
            {"id": 3, "releaseType": 1, "displayName": "C", "downloadUrl": None, "fileLength": 100},
            {"id": 4, "releaseType": 1, "displayName": "D", "downloadUrl": "https://x/d.jar", "fileLength": 200},
        ]
    }
    files = cf.list_files(1, client=_client(payload))
    assert [f.name for f in files] == ["D", "A"]  # 新文件在前


def test_effective_key_prefers_config(monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp))
    monkeypatch.setattr(cf, "_bundled_key", lambda: "bundled-key")
    from launcher import config

    cfg, cfg_path = config.load()
    cfg.curseforge_api_key = "user-key"
    config.save(cfg, cfg_path)
    assert cf.effective_api_key() == "user-key"
    cfg.curseforge_api_key = ""
    config.save(cfg, cfg_path)
    assert cf.effective_api_key() == "bundled-key"

