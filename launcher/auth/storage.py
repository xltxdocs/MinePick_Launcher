"""账号持久化：launcher 数据目录下的 accounts.json。

令牌存储：配置 token_encryption=False 时明文保存（与主流开源启动器一致）；
开启后用密码加密（cryptography Fernet + PBKDF2，见 launcher.auth.secure），
微软账号的 tokens 字段替换为 tokens_enc（enc:v1:<b64> 密文）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from launcher import paths
from launcher.auth.models import Account

ACCOUNTS_FILENAME = "accounts.json"


class AccountStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.launcher_dir() / ACCOUNTS_FILENAME

    def load(self) -> dict[str, Account]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "accounts" in raw:
            raw = raw["accounts"]
        if not isinstance(raw, dict):
            return {}
        accounts: dict[str, Account] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            entry = dict(value)
            if "tokens_enc" in entry and entry.get("tokens") is None:
                from launcher.auth.secure import VaultError, decrypt_token_blob
                from launcher.i18n import tr_core

                try:
                    entry["tokens"] = json.loads(
                        decrypt_token_blob(str(entry["tokens_enc"]))
                    )
                except VaultError as exc:
                    raise VaultError(
                        tr_core("vault.account_decrypt_failed", key, str(exc))
                    ) from exc
            entry.pop("tokens_enc", None)
            try:
                accounts[str(key)] = Account.model_validate(entry)
            except ValidationError:
                logging.getLogger(__name__).warning("忽略损坏的账号记录: %s", key)
        return accounts

    def save(self, accounts: dict[str, Account]) -> Path:
        from launcher import config as config_mod
        from launcher.auth.secure import encrypt_token_blob

        cfg, _ = config_mod.load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload_accounts: dict[str, dict] = {}
        for key, account in accounts.items():
            dump = account.model_dump(mode="json")
            if (
                cfg.token_encryption
                and account.type == "microsoft"
                and account.tokens is not None
            ):
                blob = json.dumps(dump.pop("tokens"), ensure_ascii=False)
                dump["tokens_enc"] = encrypt_token_blob(blob)
            else:
                dump.pop("tokens_enc", None)
            payload_accounts[key] = dump
        payload = {"version": 1, "accounts": payload_accounts}
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return self.path
