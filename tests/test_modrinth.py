import httpx
import pytest
import respx

from launcher.mods.loaders import ModsError
from launcher.mods.modrinth import (
    delete_installed_content,
    fetch_versions,
    find_profile_id,
    install_mod,
    list_installed_content,
    pick_file,
    resolve_mods_dir,
    resolve_slugs,
    search_projects,
)

VERSIONS_RAW = [
    {
        "id": "OihdIimA",
        "version_number": "mc1.20.1-0.5.13-fabric",
        "loaders": ["fabric", "quilt"],
        "game_versions": ["1.20.1"],
        "files": [
            {
                "filename": "sodium-fabric-0.5.13.jar",
                "url": "https://cdn.modrinth.com/data/AANobbMI/versions/OihdIimA/sodium.jar",
                "size": 8192,
                "hashes": {"sha1": "b" * 40, "sha512": "c" * 128},
                "primary": False,
            },
            {
                "filename": "sodium-extra.jar",
                "url": "https://cdn.modrinth.com/data/AANobbMI/versions/OihdIimA/sodium-extra.jar",
                "size": 11,
                "hashes": {},
                "primary": True,
            },
        ],
        "dependencies": [
            {"project_id": "P7dR8mSH", "dependency_type": "required"},
            {"project_id": "XmZQzqQq", "dependency_type": "optional"},
        ],
    }
]
PROJECT_RAW = {"id": "AANobbMI", "slug": "sodium", "title": "Sodium", "description": "渲染优化"}


@respx.mock
def test_fetch_versions_and_pick():
    respx.get(
        "https://api.modrinth.com/v2/project/sodium/version",
        params={"loaders": '["fabric"]', "game_versions": '["1.20.1"]'},
    ).mock(return_value=httpx.Response(200, json=VERSIONS_RAW))
    versions = fetch_versions("sodium", loader="fabric", game_version="1.20.1")
    assert len(versions) == 1
    assert versions[0].files[0].sha1 == "b" * 40
    assert pick_file(versions[0]).primary is True
    assert pick_file(versions[0]).filename == "sodium-extra.jar"


@respx.mock
def test_resolve_slugs_batch():
    respx.get(
        "https://api.modrinth.com/v2/projects", params={"ids": '["P7dR8mSH", "XmZQzqQq"]'}
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "P7dR8mSH", "slug": "fabric-api"},
                {"id": "XmZQzqQq", "slug": "indium"},
            ],
        )
    )
    slugs = resolve_slugs(["P7dR8mSH", "XmZQzqQq"])
    assert slugs == {"P7dR8mSH": "fabric-api", "XmZQzqQq": "indium"}


@respx.mock
def test_install_mod_full_flow(ws_tmp):
    respx.get(
        "https://api.modrinth.com/v2/project/sodium/version",
        params={"loaders": '["fabric"]', "game_versions": '["1.20.1"]'},
    ).mock(return_value=httpx.Response(200, json=VERSIONS_RAW))
    respx.get("https://api.modrinth.com/v2/project/sodium").mock(
        return_value=httpx.Response(200, json=PROJECT_RAW)
    )
    respx.get(
        "https://api.modrinth.com/v2/projects", params={"ids": '["P7dR8mSH", "XmZQzqQq"]'}
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "P7dR8mSH", "slug": "fabric-api"},
                {"id": "XmZQzqQq", "slug": "indium"},
            ],
        )
    )
    respx.get("https://cdn.modrinth.com/data/AANobbMI/versions/OihdIimA/sodium-extra.jar").mock(
        return_value=httpx.Response(200, content=b"jar-content")
    )
    info = install_mod(
        "sodium",
        game_dir=ws_tmp / "mc",
        loader="fabric",
        game_version="1.20.1",
        isolated=False,
    )
    assert info.title == "Sodium"
    assert info.depends == ["fabric-api"]
    assert info.optional_depends == ["indium"]
    assert (ws_tmp / "mc" / "mods" / "sodium-extra.jar").read_bytes() == b"jar-content"


SEARCH_RAW = {
    "hits": [
        {
            "project_id": "AANobbMI",
            "slug": "sodium",
            "title": "Sodium",
            "description": "渲染优化",
            "downloads": 123456,
            "icon_url": "https://cdn.modrinth.com/data/AANobbMI/icon.png",
        }
    ]
}


@respx.mock
def test_search_projects():
    respx.get(
        "https://api.modrinth.com/v2/search",
        params={
            "query": "sod",
            "limit": "20",
            "index": "downloads",
            "facets": '[["project_type:mod"]]',
        },
    ).mock(return_value=httpx.Response(200, json=SEARCH_RAW))
    hits = search_projects("sod")
    assert len(hits) == 1
    assert hits[0].slug == "sodium"
    assert hits[0].downloads == 123456


@respx.mock
def test_search_projects_empty():
    respx.get("https://api.modrinth.com/v2/search").mock(
        return_value=httpx.Response(200, json={"hits": []})
    )
    assert search_projects("nope") == []


def test_list_and_delete_installed_content(ws_tmp):
    game = ws_tmp / "mc"
    (game / "mods").mkdir(parents=True)
    (game / "mods" / "a.jar").write_bytes(b"1234")
    (game / "mods" / "b.jar").write_bytes(b"12")
    items = list_installed_content(game, "mods", isolated=False)
    assert [i.name for i in items] == ["a.jar", "b.jar"]
    assert items[0].size == 4
    delete_installed_content(game, "mods", "a.jar", isolated=False)
    assert [i.name for i in list_installed_content(game, "mods", isolated=False)] == ["b.jar"]
    with pytest.raises(ModsError):
        delete_installed_content(game, "mods", "missing.jar", isolated=False)


@respx.mock
def test_search_projects_resourcepack_type():
    respx.get(
        "https://api.modrinth.com/v2/search",
        params={
            "query": "fresh",
            "limit": "20",
            "index": "downloads",
            "facets": '[["project_type:resourcepack"]]',
        },
    ).mock(return_value=httpx.Response(200, json={"hits": []}))
    assert search_projects("fresh", project_type="resourcepack") == []


def test_list_installed_content_missing_dir(ws_tmp):
    assert list_installed_content(ws_tmp / "mc", "shaderpacks", isolated=False) == []


def test_resolve_mods_dir_and_profile(ws_tmp):
    game = ws_tmp / "mc"
    # non-isolated: global mods
    assert resolve_mods_dir(game, isolated=False) == game / "mods"
    # isolated but no profile installed: error
    with pytest.raises(ModsError):
        resolve_mods_dir(game, isolated=True, loader="fabric", game_version="1.20.1")
    # after installing the profile
    profile = game / "versions" / "fabric-loader-0.19.3-1.20.1"
    profile.mkdir(parents=True)
    assert find_profile_id(game, "fabric", "1.20.1") == "fabric-loader-0.19.3-1.20.1"
    target = resolve_mods_dir(game, isolated=True, loader="fabric", game_version="1.20.1")
    assert target == profile / "mods"
    assert target.is_dir()
