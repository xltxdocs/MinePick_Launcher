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

"""Account login (Microsoft OAuth device-code flow + offline mode)."""

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
