"""认证相关数据模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class MicrosoftTokens(BaseModel):
    """微软/Minecraft 令牌（全部可空；分层刷新：refresh 持久 → access 缓存 → mc 短命）。"""

    ms_access_token: str | None = None
    ms_refresh_token: str | None = None
    ms_expires_at: float | None = None
    mc_access_token: str | None = None
    mc_expires_at: float | None = None


class GameProfile(BaseModel):
    """Minecraft 游戏档案（UUID 带连字符，用户名，皮肤信息 #4）。"""

    uuid: str
    username: str
    skin_url: str = ""
    skin_model: str = ""  # classic / slim


class Account(BaseModel):
    """启动器账号：微软正版或离线模式。tokens 仅微软账号使用。"""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: Literal["microsoft", "offline"]
    username: str
    uuid: str
    created_at: float
    tokens: MicrosoftTokens | None = None
    skin_url: str = ""  # 皮肤纹理地址（#4，离线账号为空）
