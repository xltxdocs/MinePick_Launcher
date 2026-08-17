import json

import pytest

from launcher.auth import create_offline_account
from launcher.launch.orchestrate import JavaMissingError, prepare_launch

VERSION_RAW = {
    "id": "testv",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "minecraftArguments": "--demo",
    "javaVersion": {"component": "jre-legacy", "majorVersion": 8},
    "assetIndex": {"id": "idx1", "url": "https://x/idx1.json"},
    "libraries": [],
    "downloads": {"client": {"sha1": "a", "size": 1, "url": "https://x/client.jar"}},
}


def _prepare(ws_tmp):
    cache = ws_tmp / "cache"
    (cache / "versions").mkdir(parents=True)
    (cache / "versions" / "testv.json").write_text(json.dumps(VERSION_RAW), encoding="utf-8")
    return ws_tmp / "game", cache


def test_prepare_launch_raises_java_missing(ws_tmp, monkeypatch):
    import launcher.launch.orchestrate as orch

    game, cache = _prepare(ws_tmp)
    monkeypatch.setattr(orch, "list_java", lambda probe_dir=None: [])
    with pytest.raises(JavaMissingError) as ei:
        prepare_launch(
            "testv",
            game_dir=game,
            cache_dir=cache,
            account=create_offline_account("Steve"),
        )
    assert ei.value.required_major == 8
    assert "需要 Java 8" in str(ei.value)

def test_resolve_launch_account_offline_locked(ws_tmp, monkeypatch):
    """When not verified (and not in English): explicit offline launch / no-account fallback both raise OfflineLockedError."""
    from launcher.auth import AccountStore
    from launcher.launch import OfflineLockedError, resolve_launch_account

    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.setattr("launcher.config.offline_mode_allowed", lambda: False)
    store = AccountStore()
    with pytest.raises(OfflineLockedError):
        resolve_launch_account(store, None, "Steve")  # explicit offline
    with pytest.raises(OfflineLockedError):
        resolve_launch_account(store, None, None)  # no account falls back to Player
    # works after unlock
    monkeypatch.setattr("launcher.config.offline_mode_allowed", lambda: True)
    account = resolve_launch_account(store, None, "Steve")
    assert account.username == "Steve"
    assert account.type == "offline"

