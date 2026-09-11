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

import json

import pytest

from launcher.instances import (
    InstancesError,
    create_instance,
    default_instance_name,
    delete_instance,
    instance_dir,
    list_instances,
    rename_instance,
    validate_name,
)


@pytest.fixture(autouse=True)
def _isolated_game_dir(monkeypatch, ws_tmp):
    """Point the configured game dir at a temp folder so instance helpers never touch the real .minecraft."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    from launcher import config as config_mod

    cfg, cfg_path = config_mod.load()
    cfg.game_dir = ws_tmp / "mc"
    config_mod.save(cfg, cfg_path)


VERSION_RAW = {
    "id": "1.20.1",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "minecraftArguments": "--demo",
    "assetIndex": {"id": "5", "url": "https://x/5.json"},
    "libraries": [],
    "downloads": {"client": {"sha1": "a", "size": 1, "url": "https://x/client.jar"}},
}


def test_default_instance_name():
    assert default_instance_name("1.20.1") == "1.20.1"  # vanilla: just the version number
    assert default_instance_name("fabric-loader-0.19.3-1.21.11") == "1.21.11_fabric_0.19.3"
    assert default_instance_name("1.20.1-forge-47.4.22") == "1.20.1_forge_47.4.22"
    assert default_instance_name("neoforge-20.2.93") == "1.20.2_neoforge_20.2.93"
    assert default_instance_name("neoforge-26.1.2.95") == "26.1.2_neoforge_26.1.2.95"


def test_validate_name():
    assert validate_name("红石测试") == "红石测试"
    assert validate_name("my instance 1") == "my instance 1"
    with pytest.raises(InstancesError):
        validate_name("")
    with pytest.raises(InstancesError):
        validate_name("a/b")
    with pytest.raises(InstancesError):
        validate_name("x" * 40)


def test_folder_meta_roundtrip(ws_tmp):
    from launcher.instances import (
        INSTANCE_META_FILENAME,
        Instance,
        _load_folder_meta,
        _write_folder_meta,
    )

    folder = ws_tmp / "instances" / "test"
    inst = Instance(name="test", version_id="1.20.1", created_at=1.0, note="note")
    _write_folder_meta(folder, inst)
    loaded = _load_folder_meta(folder)
    assert loaded.version_id == "1.20.1"
    assert loaded.note == "note"
    assert (folder / INSTANCE_META_FILENAME).exists()


def _prepare_game(ws_tmp):
    game = ws_tmp / "mc"
    vdir = game / "versions" / "1.20.1"
    vdir.mkdir(parents=True)
    (vdir / "1.20.1.json").write_text(json.dumps(VERSION_RAW), encoding="utf-8")
    (vdir / "1.20.1.jar").write_bytes(b"jar")
    return game


def test_rename_instance(ws_tmp, monkeypatch):
    game = _prepare_game(ws_tmp)
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    create_instance("old", "1.20.1", game)
    old_dir = instance_dir(game, "old")
    (old_dir / "saves").mkdir(parents=True)
    renamed = rename_instance("old", "new name", game)
    assert renamed.name == "new name"
    assert not old_dir.exists()
    assert (instance_dir(game, "new name") / "saves").is_dir()
    assert "new name" in list_instances()
    with pytest.raises(InstancesError):
        rename_instance("missing", "x", game)  # does not exist
    with pytest.raises(InstancesError):
        rename_instance("new name", "new name", game)  # duplicate name


def test_create_and_delete_instance(ws_tmp, monkeypatch):
    game = _prepare_game(ws_tmp)
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    inst = create_instance("红石测试", "1.20.1", game)
    assert inst.name == "红石测试"
    target = instance_dir(game, "红石测试")
    assert (target / "versions" / "1.20.1" / "1.20.1.json").exists()
    assert (target / "versions" / "1.20.1" / "1.20.1.jar").read_bytes() == b"jar"
    assert list_instances()["红石测试"].version_id == "1.20.1"
    with pytest.raises(InstancesError):
        create_instance("红石测试", "1.20.1", game)  # duplicate name
    delete_instance("红石测试", game)
    remaining = list_instances()
    assert "红石测试" not in remaining
    assert "1.20.1" in remaining  # the base version from the global versions folder remains
    assert remaining["1.20.1"].base is True
    assert not target.exists()

def test_note_export_import(ws_tmp, monkeypatch):
    import zipfile

    from launcher.instances import export_instance, import_instance, update_instance_note

    game = _prepare_game(ws_tmp)
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    create_instance("note-test", "1.20.1", game)
    inst = update_instance_note("note-test", "红石测试")
    assert inst.note == "红石测试"
    assert list_instances()["note-test"].note == "红石测试"
    # export after writing saves
    saves = instance_dir(game, "note-test") / "saves"
    saves.mkdir(parents=True)
    (saves / "world.txt").write_text("data", encoding="utf-8")
    dest = export_instance("note-test", ws_tmp / "out.zip", game)
    assert dest.exists()
    delete_instance("note-test", game)
    imported = import_instance(dest, game)
    assert imported.name == "note-test"
    assert imported.note == "红石测试"
    assert (instance_dir(game, "note-test") / "saves" / "world.txt").read_text(encoding="utf-8") == "data"
    with pytest.raises(InstancesError):
        import_instance(dest, game)  # already exists
    bad = ws_tmp / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("x.txt", "x")
    with pytest.raises(InstancesError):
        import_instance(bad, game)  # missing instance.json

def test_import_instance_corrupt_meta(ws_tmp, monkeypatch):
    """Raises InstancesError when instance.json is corrupt, not a pydantic exception."""
    import zipfile

    from launcher.instances import import_instance

    game = _prepare_game(ws_tmp)
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    bad = ws_tmp / "corrupt.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("instance.json", "{not json")
    with pytest.raises(InstancesError):
        import_instance(bad, game)


