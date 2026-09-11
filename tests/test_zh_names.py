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

"""Unit tests for launcher/mods/zh_names.py: Chinese name table loading, CJK detection, local search."""

from launcher.mods.zh_names import has_cjk, search_local, zh_name, zh_names


def test_zh_names_loads_dict() -> None:
    table = zh_names()
    assert isinstance(table, dict)
    assert all(k and v for k, v in table.items())


def test_has_cjk() -> None:
    assert has_cjk("钠") is True
    assert has_cjk("优化 钠") is True
    assert has_cjk("sodium") is False
    assert has_cjk("") is False


def test_search_local_roundtrip() -> None:
    """Any entry in the table: it can find itself by both its Chinese name and slug."""
    assert search_local("") == []
    for slug, name in list(zh_names().items())[:20]:
        assert slug in search_local(slug), slug
        assert slug in search_local(name), name


def test_zh_name_unknown_returns_empty() -> None:
    assert zh_name("__definitely_not_a_mod__") == ""

