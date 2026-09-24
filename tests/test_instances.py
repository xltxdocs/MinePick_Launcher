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

"""Instance model: version folders as instances, sidecar metadata, isolation, resolution."""

from __future__ import annotations

import json
import zipfile

import pytest

from launcher import config as config_mod
from launcher.instances import (
    INSTANCE_META_FILENAME,
    ISOLATION_OFF,
    ISOLATION_ON,
    InstancesError,
    create_instance,
    default_instance_name,
    delete_instance,
    export_instance,
    import_instance,
    instance_dir,
    isolation_enabled,
    legacy_instances_dir,
    list_instances,
    rename_instance,
    reset_instance_settings,
    resolve_instance,
    set_instance_settings,
    update_instance_note,
    validate_name,
)


def _write_version(game, version_id: str, *, jar: bool = True) -> None:
    folder = game / "versions" / version_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (version_id + ".json")).write_text(
        json.dumps(
            {
                "id": version_id,
                "type": "release",
                "mainClass": "net.minecraft.client.main.Main",
                "assetIndex": {"id": "5", "url": "https://example.invalid/5.json"},
                "assets": "5",
                "libraries": [],
                "downloads": {
                    "client": {
                        "url": "https://example.invalid/c.jar",
                        "sha1": "0" * 40,
                        "size": 1,
                        "path": "c.jar",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    if jar:
        (folder / (version_id + ".jar")).write_bytes(b"jar")


def _cfg(game, **overrides):
    data = {"game_dir": game, "memory_gb": 6.0, "jvm_args": "-Dglobal=1"}
    data.update(overrides)
    return config_mod.LauncherConfig(**data)


def test_default_instance_name():
    assert default_instance_name("1.20.1") == "1.20.1"  # vanilla: just the version number
    assert default_instance_name("fabric-loader-0.19.3-1.21.11") == "1.21.11_fabric_0.19.3"
    assert default_instance_name("1.20.1-forge-47.4.22") == "1.20.1_forge_47.4.22"
    assert default_instance_name("neoforge-20.2.93") == "1.20.2_neoforge_20.2.93"


def test_validate_name():
    assert validate_name(" 红石 测试 ") == "红石 测试"
    for bad in ("", "  ", "a/b", "a\\b", "x" * 40):
        with pytest.raises(InstancesError):
            validate_name(bad)


def test_list_instances_only_counts_version_folders(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    (game / "versions" / "broken").mkdir(parents=True)  # no <id>.json -> not an instance
    (game / "instances" / "legacy").mkdir(parents=True)  # pre-0.3.0 layout is ignored

    found = list_instances(game)
    assert list(found) == ["1.20.1"]
    inst = found["1.20.1"]
    assert inst.id == "1.20.1"
    assert inst.version_id == "1.20.1"  # version id == instance id
    assert inst.name == "1.20.1"  # display name falls back to the id


def test_sidecar_roundtrip_and_corrupt_tolerance(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    update_instance_note("1.20.1", "红石测试", game)
    sidecar = instance_dir(game, "1.20.1") / INSTANCE_META_FILENAME
    assert json.loads(sidecar.read_text(encoding="utf-8"))["note"] == "红石测试"

    sidecar.write_text("{ not json", encoding="utf-8")
    inst = list_instances(game)["1.20.1"]  # corrupt metadata must not hide the instance
    assert inst.id == "1.20.1" and inst.note == ""


def test_isolation_tri_state_and_auto_rule(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    folder = instance_dir(game, "1.20.1")
    inst = list_instances(game)["1.20.1"]

    assert isolation_enabled(inst, folder, True) is True  # follow -> default policy
    assert isolation_enabled(inst, folder, False) is False
    (folder / "mods").mkdir()
    (folder / "mods" / "a.jar").write_bytes(b"x")
    assert isolation_enabled(inst, folder, False) is True  # existing mods -> own folder

    shared = inst.model_copy(update={"isolated": ISOLATION_OFF})
    assert isolation_enabled(shared, folder, True) is False  # explicit off wins
    forced = inst.model_copy(update={"isolated": ISOLATION_ON})
    assert isolation_enabled(forced, folder, False) is True  # explicit on wins


def test_resolve_instance_paths_and_overrides(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    cfg = _cfg(game)
    resolved = resolve_instance("1.20.1", cfg, game)
    assert resolved.launch_dir == instance_dir(game, "1.20.1")  # isolated by default
    assert resolved.mods_dir == instance_dir(game, "1.20.1") / "mods"
    assert resolved.memory_gb == 6.0 and resolved.memory_from_instance is False
    assert resolved.java_path is None and resolved.jvm_args == "-Dglobal=1"

    java = ws_tmp / "java" / "bin" / "java.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"exe")
    set_instance_settings(
        "1.20.1",
        game_dir=game,
        java=str(java),
        memory_gb=12.0,
        jvm_args="-Dinst=1",
        game_args="--width 800",
    )
    resolved2 = resolve_instance("1.20.1", cfg, game)
    assert resolved2.java_path == java
    assert resolved2.memory_gb == 12.0 and resolved2.memory_from_instance is True
    assert resolved2.jvm_args == "-Dglobal=1 -Dinst=1"
    assert resolved2.game_args == "--width 800"

    set_instance_settings("1.20.1", game_dir=game, java=str(ws_tmp / "missing-java.exe"))  # gone -> auto-detect
    assert resolve_instance("1.20.1", cfg, game).java_path is None

    reset_instance_settings("1.20.1", game)
    resolved3 = resolve_instance("1.20.1", cfg, game)
    assert resolved3.memory_gb == 6.0 and resolved3.jvm_args == "-Dglobal=1"
    assert resolved3.java_path is None

    with pytest.raises(InstancesError):
        resolve_instance("nope", cfg, game)


def test_shared_launch_dir_when_not_isolated(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    resolved = resolve_instance("1.20.1", _cfg(game, default_isolation=False), game)
    assert resolved.isolated is False
    assert resolved.launch_dir == game
    assert resolved.mods_dir == game / "mods"


def test_create_rename_delete(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    inst = create_instance("红石测试", "1.20.1", game)
    target = instance_dir(game, "红石测试")
    assert inst.id == "红石测试" and inst.display_name == "红石测试"
    assert json.loads((target / "红石测试.json").read_text(encoding="utf-8"))["id"] == "红石测试"
    assert list(target.glob("*.jar"))
    with pytest.raises(InstancesError):
        create_instance("红石测试", "1.20.1", game)  # duplicate id
    with pytest.raises(InstancesError):
        create_instance("x", "missing-version", game)  # source not installed

    renamed = rename_instance("红石测试", "生存档", game)
    assert renamed.id == "生存档"
    assert not target.exists()
    moved = instance_dir(game, "生存档")
    assert json.loads((moved / "生存档.json").read_text(encoding="utf-8"))["id"] == "生存档"
    assert list(moved.glob("*.jar"))
    with pytest.raises(InstancesError):
        rename_instance("生存档", "生存档", game)

    delete_instance("生存档", game)
    assert list(list_instances(game)) == ["1.20.1"]  # only the copied instance is gone
    with pytest.raises(InstancesError):
        delete_instance("生存档", game)


def test_export_import_roundtrip(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    create_instance("note-test", "1.20.1", game)
    update_instance_note("note-test", "红石测试", game)
    saves = instance_dir(game, "note-test") / "saves"
    saves.mkdir(parents=True)
    (saves / "world.txt").write_text("data", encoding="utf-8")

    dest = export_instance("note-test", ws_tmp / "out.zip", game)
    import zipfile as _zip

    with _zip.ZipFile(dest) as zf:
        assert INSTANCE_META_FILENAME in zf.namelist()
    delete_instance("note-test", game)

    imported = import_instance(dest, game)
    assert imported.id == "note-test" and imported.note == "红石测试"
    world = instance_dir(game, "note-test") / "saves" / "world.txt"
    assert world.read_text(encoding="utf-8") == "data"
    with pytest.raises(InstancesError):
        import_instance(dest, game)  # already exists

    bad = ws_tmp / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("readme.txt", "nothing")
    with pytest.raises(InstancesError):
        import_instance(bad, game)


def test_import_corrupt_metadata(ws_tmp):
    game = ws_tmp / "mc"
    game.mkdir(parents=True)
    bad = ws_tmp / "corrupt.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr(INSTANCE_META_FILENAME, "{ not json")
    with pytest.raises(InstancesError):
        import_instance(bad, game)


def test_legacy_instances_dir_is_only_reported(ws_tmp):
    game = ws_tmp / "mc"
    _write_version(game, "1.20.1")
    legacy = game / "instances" / "old"
    legacy.mkdir(parents=True)
    (legacy / "saves").mkdir()

    assert legacy_instances_dir(game) == game / "instances"
    assert list(list_instances(game)) == ["1.20.1"]  # never merged automatically
    assert not (game / "versions" / "old").exists()
