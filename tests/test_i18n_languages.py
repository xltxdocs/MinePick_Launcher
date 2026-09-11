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

"""Localization integrity tests: key sets, placeholders and system locale mapping."""

from gui import i18n
from launcher import i18n as ci18n


def test_all_languages_have_complete_keys() -> None:
    """Every language must expose exactly the same key set as English."""
    codes = [code for code, _name in i18n.UI_LANGUAGES]
    base = set(i18n.TRANSLATIONS["en_us"])
    for code in codes:
        assert set(i18n.TRANSLATIONS[code]) == base, f"gui {code} key mismatch"
    cbase = set(ci18n.CORE_TRANSLATIONS["en_us"])
    for code in codes:
        assert set(ci18n.CORE_TRANSLATIONS[code]) == cbase, f"core {code} key mismatch"


def test_placeholder_counts_match_zh() -> None:
    """Translated values must keep the same {} placeholder count as Simplified Chinese."""
    codes = [code for code, _name in i18n.UI_LANGUAGES]
    zh = i18n.TRANSLATIONS["zh_cn"]
    for code in codes:
        table = i18n.TRANSLATIONS[code]
        for key, value in table.items():
            assert value.count("{}") == zh[key].count("{}"), f"{code} {key}: {value}"


def test_detect_system_language_mapping() -> None:
    assert i18n.detect_system_language("zh_CN") == "zh_cn"
    assert i18n.detect_system_language("zh_TW") == "zh_tw"
    assert i18n.detect_system_language("zh-HK") == "zh_tw"  # HK Traditional Chinese
    assert i18n.detect_system_language("en_GB") == "en_us"
    assert i18n.detect_system_language("en-US") == "en_us"
    assert i18n.detect_system_language("ja_JP") == "ja_jp"
    assert i18n.detect_system_language("ko_KR") == "ko_kr"
    assert i18n.detect_system_language("ru_RU") == "ru_ru"
    assert i18n.detect_system_language("fr_FR") == "fr_fr"
    assert i18n.detect_system_language("es_MX") == "es_es"
    assert i18n.detect_system_language("de_DE") == "de_de"
    assert i18n.detect_system_language("pl_PL") == "zh_cn"  # unsupported locale falls back to zh_cn
    assert i18n.detect_system_language("C") == "zh_cn"
    assert i18n.detect_system_language("") == "zh_cn"
