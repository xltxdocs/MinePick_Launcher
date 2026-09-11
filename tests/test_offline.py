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

import uuid as uuidlib

import pytest

from launcher.auth.offline import create_offline_account, offline_uuid


def test_known_values():
    # expected values are cross-checked against an independent implementation (.NET MD5 + Java bit manipulation)
    assert offline_uuid("Notch") == "b50ad385-829d-3141-a216-7e7d7539ba7f"
    assert offline_uuid("Player") == "a01e3843-e521-3998-958a-f459800e4d11"


def test_uuid_properties():
    u = uuidlib.UUID(offline_uuid("steve"))
    assert u.version == 3
    assert u.variant == uuidlib.RFC_4122
    assert offline_uuid("steve") == offline_uuid("steve")
    assert offline_uuid("alice") != offline_uuid("bob")


def test_create_account():
    a = create_offline_account(" Steve ")
    assert a.username == "Steve"
    assert a.type == "offline"
    assert a.id == a.uuid == offline_uuid("Steve")
    assert a.tokens is None


def test_create_account_validation():
    with pytest.raises(ValueError):
        create_offline_account("")
    with pytest.raises(ValueError):
        create_offline_account("   ")
    with pytest.raises(ValueError):
        create_offline_account("a" * 17)
