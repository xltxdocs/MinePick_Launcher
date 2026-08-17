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

from launcher.meta.manifest import APRIL_FOOLS_IDS, version_category


def test_april_fools_ids_known() -> None:
    for vid in ("2.0", "15w14a", "1.RV-Pre1", "3D Shareware v1.34", "20w14infinite",
                "22w13oneblockatatime", "23w13a_or_b", "24w14potato", "25w14craftmine",
                "26w14a"):
        assert vid in APRIL_FOOLS_IDS


def test_version_category_release_snapshot() -> None:
    assert version_category("1.21.8", "release") == "release"
    assert version_category("25w14a", "snapshot") == "snapshot"


def test_version_category_april_fools_overrides_type() -> None:
    # april-fools versions are categorized by id, ignoring the release/snapshot type in the manifest
    assert version_category("24w14potato", "snapshot") == "april_fools"
    assert version_category("2.0", "release") == "april_fools"
    assert version_category("26w14a", "snapshot") == "april_fools"
    assert version_category("20w14infinite", "snapshot") == "april_fools"
    assert version_category("22w13oneblockatatime", "snapshot") == "april_fools"


def test_version_category_legacy() -> None:
    assert version_category("b1.7.3", "old_beta") == "old_beta"
    assert version_category("a1.0.4", "old_alpha") == "old_alpha"
