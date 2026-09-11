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
