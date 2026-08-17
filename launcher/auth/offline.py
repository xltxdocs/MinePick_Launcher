"""Offline mode: username -> offline UUID (matches Java UUID.nameUUIDFromBytes)."""

from __future__ import annotations

import hashlib
import time
import uuid as uuidlib

from launcher.auth.models import Account


def offline_uuid(username: str) -> str:
    """MD5("OfflinePlayer:" + username) with the UUID v3 bits set, equivalent to the Java algorithm."""
    digest = hashlib.md5(f"OfflinePlayer:{username}".encode()).digest()
    return str(uuidlib.UUID(bytes=digest, version=3))


def create_offline_account(username: str) -> Account:
    """Create an offline account from a username. Username is 1~16 chars (same as Minecraft)."""
    name = username.strip()
    if not name:
        raise ValueError("用户名不能为空")
    if len(name) > 16:
        raise ValueError("用户名不能超过 16 个字符")
    uuid = offline_uuid(name)
    return Account(
        id=uuid, type="offline", username=name, uuid=uuid, created_at=time.time()
    )
