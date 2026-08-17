"""令牌加密保险库与 AccountStore 加解密测试。"""

import json

from launcher import config as config_mod
from launcher.auth import secure
from launcher.auth.models import Account, MicrosoftTokens
from launcher.auth.storage import AccountStore


def test_vault_roundtrip(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.delenv(secure.ENV_PASSWORD, raising=False)
    secure.forget_password()
    secure.create_vault("secret")
    assert secure.vault_exists()
    assert secure.verify_password("secret")
    assert not secure.verify_password("wrong")
    blob = secure.encrypt_token_blob('{"a":1}')
    assert blob.startswith(secure.CIPHER_PREFIX)
    assert secure.decrypt_token_blob(blob) == '{"a":1}'


def test_vault_env_password(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data2"))
    monkeypatch.setenv(secure.ENV_PASSWORD, "pw")
    secure.forget_password()
    secure.create_vault("pw")
    secure.forget_password()  # 仅靠环境变量
    blob = secure.encrypt_token_blob("hello")
    assert secure.decrypt_token_blob(blob) == "hello"


def test_account_store_encryption_roundtrip(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data3"))
    monkeypatch.delenv(secure.ENV_PASSWORD, raising=False)
    secure.forget_password()
    cfg, cfg_path = config_mod.load()
    cfg.token_encryption = True
    config_mod.save(cfg, cfg_path)
    secure.create_vault("pw")
    store = AccountStore()
    account = Account(
        id="id1",
        type="microsoft",
        username="Steve",
        uuid="u-1",
        created_at=1.0,
        tokens=MicrosoftTokens(ms_access_token="ms-tok", mc_access_token="mc-tok"),
    )
    store.save({"id1": account})
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    entry = raw["accounts"]["id1"]
    assert "tokens" not in entry
    assert entry["tokens_enc"].startswith(secure.CIPHER_PREFIX)
    loaded = store.load()
    assert loaded["id1"].tokens is not None
    assert loaded["id1"].tokens.ms_access_token == "ms-tok"
    # 关闭加密后写回明文
    cfg.token_encryption = False
    config_mod.save(cfg, cfg_path)
    store.save(loaded)
    raw2 = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw2["accounts"]["id1"]["tokens"]["ms_access_token"] == "ms-tok"


def test_cli_vault_error_no_traceback(ws_tmp, monkeypatch, capsys):
    """令牌加密开启但未提供密码时，CLI 输出友好错误并返回 1（不抛堆栈）。"""
    from launcher import config as config_mod
    from launcher.auth.models import Account, MicrosoftTokens
    from launcher.cli import main

    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data5"))
    monkeypatch.delenv(secure.ENV_PASSWORD, raising=False)
    secure.forget_password()
    cfg, cfg_path = config_mod.load()
    cfg.token_encryption = True
    config_mod.save(cfg, cfg_path)
    secure.create_vault("pw")
    store = AccountStore()
    account = Account(
        id="id1",
        type="microsoft",
        username="Steve",
        uuid="u-1",
        created_at=1.0,
        tokens=MicrosoftTokens(ms_access_token="ms-tok"),
    )
    store.save({"id1": account})
    secure.forget_password()  # 模拟未解锁状态

    code = main(["whoami"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err
    assert "错误" in captured.err


def test_offline_account_stays_plaintext(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data4"))
    monkeypatch.delenv(secure.ENV_PASSWORD, raising=False)
    secure.forget_password()
    cfg, cfg_path = config_mod.load()
    cfg.token_encryption = True
    config_mod.save(cfg, cfg_path)
    secure.create_vault("pw")
    store = AccountStore()
    offline = Account(
        id="off", type="offline", username="Player", uuid="u-2", created_at=1.0
    )
    store.save({"off": offline})
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert "tokens_enc" not in raw["accounts"]["off"]
    loaded = store.load()
    assert loaded["off"].username == "Player"

def test_cli_offline_login_locked(ws_tmp, monkeypatch, capsys):
    """离线登录被门槛拦截：退出码 1 + 友好提示（不创建账号）。"""
    from launcher import config as config_mod
    from launcher.cli import main

    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data6"))
    monkeypatch.setattr(config_mod, "offline_mode_allowed", lambda: False)
    code = main(["login", "--offline", "Steve"])
    captured = capsys.readouterr()
    assert code == 1
    assert "离线模式" in captured.err
    assert AccountStore().load() == {}  # 未创建账号

