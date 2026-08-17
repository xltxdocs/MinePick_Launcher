import json

from launcher.meta.version import (
    ArgumentItem,
    VersionJson,
    load_version_json,
    merge_raw,
    required_java_major,
)


def test_required_java_major_mapping():
    assert required_java_major("1.8.9") == 8
    assert required_java_major("1.16.5") == 8
    assert required_java_major("1.17") == 17
    assert required_java_major("1.20.4") == 17
    assert required_java_major("1.20.5") == 21
    assert required_java_major("1.21.8") == 21
    assert required_java_major("1.21.11") == 21
    assert required_java_major("26.1") == 25
    assert required_java_major("26.2") == 25
    assert required_java_major("26.3-snapshot-8") == 25  # 快照基线版本
    assert required_java_major("1.20.5-pre1") == 21  # 预发布按基线版本
    assert required_java_major("1.22") is None  # 区间外（理论上不存在）→ 回退声明值
    assert required_java_major("26.0") is None  # 不存在的版本 → None
    assert required_java_major("25w01a") is None  # 快照无法按 semver 解析
    # 声明值优先
    assert required_java_major("1.8.9", declared=21) == 21

LEGACY_RAW = {
    "id": "1.8.9",
    "type": "release",
    "time": "2015-12-09T09:19:28+00:00",
    "releaseTime": "2015-12-09T09:19:28+00:00",
    "mainClass": "net.minecraft.client.main.Main",
    "minecraftArguments": (
        "--username ${auth_player_name} --version ${version_name} "
        "--gameDir ${game_directory} --assetsDir ${assets_root} "
        "--assetIndex ${assets_index_name} --uuid ${auth_uuid} "
        "--accessToken ${auth_access_token} --userType ${user_type}"
    ),
    "assetIndex": {
        "id": "1.8",
        "sha1": "f6cd102f09dc6de1cfd9d0c57b2b0b1999c01313",
        "size": 94070,
        "totalSize": 145741083,
        "url": "https://example.com/1.8.json",
    },
    "libraries": [
        {
            "name": "org.lwjgl.lwjgl:lwjgl-platform:2.9.1",
            "natives": {"windows": "natives-windows", "osx": "natives-osx", "linux": "natives-linux"},
            "extract": {"exclude": ["META-INF/"]},
        },
        {
            "name": "com.mojang:netty:1.6",
            "rules": [{"action": "allow", "os": {"name": "osx"}}, {"action": "disallow"}],
        },
    ],
}

NEW_RAW = {
    "id": "1.21.8",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "arguments": {
        "game": [
            "--username",
            "${auth_player_name}",
            {"rules": [{"action": "allow", "features": {"is_demo_user": True}}], "value": "--demo"},
        ],
        "jvm": ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"],
    },
    "javaVersion": {"component": "java-runtime-delta", "majorVersion": 21},
    "assetIndex": {
        "id": "17",
        "sha1": "x",
        "size": 1,
        "totalSize": 2,
        "url": "https://example.com/17.json",
    },
    "libraries": [
        {
            "name": "org.lwjgl:lwjgl:3.3.3",
            "downloads": {
                "artifact": {
                    "path": "org/lwjgl/lwjgl/3.3.3/lwjgl-3.3.3.jar",
                    "sha1": "a",
                    "size": 1,
                    "url": "https://example.com/lwjgl.jar",
                },
                "classifiers": {
                    "natives-windows": {"sha1": "b", "size": 2, "url": "https://example.com/nw.jar"},
                    "natives-windows-arm64": {"sha1": "c", "size": 3, "url": "https://example.com/nwa.jar"},
                },
            },
        }
    ],
    "downloads": {"client": {"sha1": "d", "size": 4, "url": "https://example.com/client.jar"}},
}


def test_parse_legacy():
    v = VersionJson.model_validate(LEGACY_RAW)
    assert v.main_class == "net.minecraft.client.main.Main"
    assert v.is_legacy
    game = v.effective_game_arguments()
    assert game[0] == "--username"
    assert "${auth_player_name}" in game
    jvm = v.effective_jvm_arguments()
    assert "-cp" in jvm
    assert any("${natives_directory}" in a for a in jvm)
    assert v.java_version is None
    assert v.client_jar_name == "1.8.9.jar"


def test_parse_new():
    v = VersionJson.model_validate(NEW_RAW)
    assert not v.is_legacy
    assert v.java_version is not None and v.java_version.major_version == 21
    game = v.effective_game_arguments()
    assert "--username" in game
    items = [a for a in game if isinstance(a, ArgumentItem)]
    assert items and items[0].value == "--demo"
    assert items[0].rules[0].features == {"is_demo_user": True}
    assert v.client_jar_name == "1.21.8.jar"


def test_merge_raw():
    parent = {
        "id": "base",
        "mainClass": "base.Main",
        "libraries": [{"name": "p:lib1:1"}],
        "arguments": {"game": ["--base"], "jvm": ["-Xmx1G"]},
        "inheritsFrom": "x",
    }
    child = {
        "id": "child",
        "mainClass": "child.Main",
        "libraries": [{"name": "c:lib1:1"}],
        "arguments": {"game": ["--child"], "jvm": []},
        "inheritsFrom": "base",
    }
    merged = merge_raw(child, parent)
    assert merged["mainClass"] == "child.Main"
    assert [lib["name"] for lib in merged["libraries"]] == ["c:lib1:1", "p:lib1:1"]
    assert merged["arguments"]["game"] == ["--child", "--base"]
    assert "inheritsFrom" not in merged


def _write_version(versions_dir, version_id, raw):
    d = versions_dir / version_id
    d.mkdir(parents=True, exist_ok=True)
    (d / (version_id + ".json")).write_text(json.dumps(raw), encoding="utf-8")


def test_load_version_json_inheritance(ws_tmp):
    versions = ws_tmp / "versions"
    _write_version(
        versions,
        "base",
        {
            "id": "base",
            "mainClass": "base.Main",
            "assetIndex": {"id": "b", "url": "https://example.com/b.json"},
            "libraries": [{"name": "p:lib1:1"}],
            "arguments": {"game": ["--base"], "jvm": ["-Xmx1G"]},
        },
    )
    _write_version(
        versions,
        "child",
        {
            "id": "child",
            "mainClass": "child.Main",
            "assetIndex": {"id": "c", "url": "https://example.com/c.json"},
            "libraries": [{"name": "c:lib1:1"}],
            "arguments": {"game": ["--child"], "jvm": []},
            "inheritsFrom": "base",
        },
    )
    v = load_version_json("child", versions_dir=versions)
    assert v.main_class == "child.Main"
    assert [lib.name for lib in v.libraries] == ["c:lib1:1", "p:lib1:1"]
    assert v.asset_index.id == "c"
    assert v.effective_game_arguments() == ["--child", "--base"]
