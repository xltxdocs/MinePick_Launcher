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

"""Account persistence: accounts.json under the launcher data directory.

Token storage: when token_encryption=False, tokens are saved in plaintext (same as
mainstream open-source launchers); when enabled, they are encrypted with a password
(cryptography Fernet + PBKDF2, see launcher.auth.secure), and a Microsoft account's
tokens field is replaced by tokens_enc (enc:v1:<b64> ciphertext).
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
