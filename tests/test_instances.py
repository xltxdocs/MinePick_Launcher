import json

import pytest

from launcher.instances import (
    InstancesError,
    InstanceStore,
    create_instance,
    default_instance_name,
    delete_instance,
    instance_dir,
    list_instances,
    rename_instance,
    validate_name,
)

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
    assert default_instance_name("1.20.1") == "1.20.1"
    assert default_instance_name("fabric-loader-0.19.3-1.21.11") == "1.21.11-Fabric_0.19.3"
    assert default_instance_name("1.20.1-forge-47.4.22") == "1.20.1-Forge_47.4.22"
    assert default_instance_name("neoforge-20.2.93") == "1.20.2-NeoForge_20.2.93"
    assert default_instance_name("neoforge-26.1.2.95") == "26.1.2-NeoForge_26.1.2.95"


def test_validate_name():
    assert validate_name("红石测试") == "红石测试"
    assert validate_name("my instance 1") == "my instance 1"
    with pytest.raises(InstancesError):
        validate_name("")
    with pytest.raises(InstancesError):
        validate_name("a/b")
    with pytest.raises(InstancesError):
        validate_name("x" * 40)


def test_store_roundtrip(ws_tmp):
    store = InstanceStore(ws_tmp / "instances.json")
    from launcher.instances import Instance

    inst = Instance(name="test", version_id="1.20.1", created_at=1.0)
    store.save({"test": inst})
    assert InstanceStore(ws_tmp / "instances.json").load() == {"test": inst}


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
        rename_instance("missing", "x", game)  # 不存在
    with pytest.raises(InstancesError):
        rename_instance("new name", "new name", game)  # 重名


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
        create_instance("红石测试", "1.20.1", game)  # 重名
    delete_instance("红石测试", game)
    assert list_instances() == {}
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
    # 写入存档后导出
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
        import_instance(dest, game)  # 已存在
    bad = ws_tmp / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("x.txt", "x")
    with pytest.raises(InstancesError):
        import_instance(bad, game)  # 缺 instance.json

def test_import_instance_corrupt_meta(ws_tmp, monkeypatch):
    """instance.json 损坏时抛 InstancesError，而不是 pydantic 异常。"""
    import zipfile

    from launcher.instances import import_instance

    game = _prepare_game(ws_tmp)
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    bad = ws_tmp / "corrupt.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("instance.json", "{not json")
    with pytest.raises(InstancesError):
        import_instance(bad, game)


