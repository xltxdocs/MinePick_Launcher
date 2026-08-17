from pathlib import Path

import pytest

from launcher.java import JavaRuntime
from launcher.mods.installer import install_loader, installer_args
from launcher.mods.loaders import ModsError
from launcher.mods.models import LoaderVersion

FABRIC = LoaderVersion(
    loader="fabric", version="0.19.3", game_version="1.20.1", installer_url="https://x/fabric.jar"
)
FORGE = LoaderVersion(
    loader="forge", version="47.4.22", game_version="1.20.1", installer_url="https://x/forge.jar"
)
NEOFORGE = LoaderVersion(
    loader="neoforge", version="20.2.88", game_version="1.20.2", installer_url="https://x/neo.jar"
)


def test_installer_args():
    game = Path("D:/mc")
    game_str = str(game)
    assert installer_args(FABRIC, game) == [
        "client",
        "-dir",
        game_str,
        "-mcversion",
        "1.20.1",
        "-loader",
        "0.19.3",
        "-noprofile",
    ]
    assert installer_args(FORGE, game) == ["--installClient", game_str]
    assert installer_args(NEOFORGE, game) == ["--installClient", game_str]


def test_install_loader_detects_new_version(ws_tmp, monkeypatch):
    import launcher.mods.installer as inst

    game = ws_tmp / "mc"
    versions = game / "versions"
    versions.mkdir(parents=True)

    def fake_list_java(probe_dir=None):
        return [JavaRuntime(path=Path("/fake/java"), major=21, provider="system")]

    def fake_download(loader_version, cache_dir, progress=None):
        jar = cache_dir / "loaders" / "fake.jar"
        jar.parent.mkdir(parents=True, exist_ok=True)
        jar.write_text("fake", encoding="utf-8")
        return jar

    def fake_run(jar, args, *, java_path, work_dir, temp_dir, timeout_s=3600):
        (work_dir / "versions" / "fabric-loader-0.19.3-1.20.1").mkdir(parents=True)
        return 0

    monkeypatch.setattr(inst, "list_java", fake_list_java)
    monkeypatch.setattr(inst, "download_installer", fake_download)
    monkeypatch.setattr(inst, "run_installer_jar", fake_run)

    version_id = install_loader(FABRIC, game, cache_dir=ws_tmp / "cache")
    assert version_id == "fabric-loader-0.19.3-1.20.1"


def test_install_loader_nonzero_exit(ws_tmp, monkeypatch):
    import launcher.mods.installer as inst

    monkeypatch.setattr(
        inst, "list_java", lambda probe_dir=None: [JavaRuntime(path=Path("/fake/java"), major=21, provider="system")]
    )
    monkeypatch.setattr(
        inst,
        "download_installer",
        lambda lv, cache_dir, progress=None: Path("/fake.jar"),
    )
    monkeypatch.setattr(
        inst, "run_installer_jar", lambda *a, **k: 1
    )
    with pytest.raises(ModsError, match="退出码 1"):
        install_loader(FABRIC, ws_tmp / "mc", cache_dir=ws_tmp / "cache")
