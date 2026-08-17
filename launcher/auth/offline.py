"""离线模式：用户名 -> 离线 UUID（与 Java UUID.nameUUIDFromBytes 一致）。"""

from __future__ import annotations

import hashlib
import time
import uuid as uuidlib

from launcher.auth.models import Account


def offline_uuid(username: str) -> str:
    """MD5("OfflinePlayer:" + 用户名) 并设置 UUID v3 位，等价于 Java 算法。"""
    digest = hashlib.md5(f"OfflinePlayer:{username}".encode()).digest()
    return str(uuidlib.UUID(bytes=digest, version=3))


def create_offline_account(username: str) -> Account:
    """由用户名创建离线账号。用户名 1~16 字符（与 Minecraft 一致）。"""
    name = username.strip()
    if not name:
        raise ValueError("用户名不能为空")
    if len(name) > 16:
        raise ValueError("用户名不能超过 16 个字符")
    uuid = offline_uuid(name)
    return Account(
        id=uuid, type="offline", username=name, uuid=uuid, created_at=time.time()
    )
