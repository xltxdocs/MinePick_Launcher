"""M1：账号登录（微软 OAuth 设备码流程 + 离线模式）。"""

from launcher.auth.microsoft import (
    AuthError,
    MicrosoftSession,
    NeedsLoginError,
    NoOwnershipError,
    NoProfileError,
    XboxAuthError,
)
from launcher.auth.models import Account, GameProfile, MicrosoftTokens
from launcher.auth.offline import create_offline_account, offline_uuid
from launcher.auth.storage import AccountStore

__all__ = [
    "Account",
    "AccountStore",
    "AuthError",
    "GameProfile",
    "MicrosoftSession",
    "MicrosoftTokens",
    "NeedsLoginError",
    "NoOwnershipError",
    "NoProfileError",
    "XboxAuthError",
    "create_offline_account",
    "offline_uuid",
]
