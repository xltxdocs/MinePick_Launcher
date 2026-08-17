"""Auth-related data models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class MicrosoftTokens(BaseModel):
    """Microsoft/Minecraft tokens (all nullable; layered refresh: refresh is persistent -> access is cached -> mc is short-lived)."""

    ms_access_token: str | None = None
    ms_refresh_token: str | None = None
    ms_expires_at: float | None = None
    mc_access_token: str | None = None
    mc_expires_at: float | None = None


class GameProfile(BaseModel):
    """Minecraft game profile (UUID with hyphens, username, skin info)."""

    uuid: str
    username: str
    skin_url: str = ""
    skin_model: str = ""  # classic / slim


class Account(BaseModel):
    """Launcher account: Microsoft premium or offline mode. tokens is used only by Microsoft accounts."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: Literal["microsoft", "offline"]
    username: str
    uuid: str
    created_at: float
    tokens: MicrosoftTokens | None = None
    skin_url: str = ""  # skin texture URL (empty for offline accounts)
