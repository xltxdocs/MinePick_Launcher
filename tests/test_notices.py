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

"""Credits and notices tests: the generated file must not drift and the legal sentence must survive."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from gui import i18n
from launcher import notices

# One phrase per language that must be present: the "no upstream source code" statement is licence
# hygiene, so a translation is not allowed to soften or drop it (see the standard process document).
INDEPENDENT_MARKERS = {
    "zh_cn": "未包含上游源代码",
    "zh_tw": "未包含上游原始碼",
    "en_us": "contains none of the upstream source code",
    "ja_jp": "上流のソースコードを一切含みません",
    "ko_kr": "상위 소스 코드를 포함하지 않습니다",
    "ru_ru": "не содержит исходного кода upstream",
    "fr_fr": "ne contient aucun code source de l'amont",
    "es_es": "no contiene código fuente del proyecto original",
    "de_de": "enthält keinen Quellcode des Ursprungsprojekts",
}


def test_notices_file_matches_generator() -> None:
    """THIRD_PARTY_NOTICES.md is generated: it must equal the generator's current output."""
    import build_third_party_notices as generator

    expected = generator.render()
    actual = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert actual == expected, "run: python tools/build_third_party_notices.py"


def test_every_credit_has_a_translated_description() -> None:
    """Every entry renders in every language (the About page shows them all)."""
    for entry in notices.all_entries():
        for code, table in i18n.TRANSLATIONS.items():
            assert table.get(entry.detail_key), f"{entry.name}: missing {entry.detail_key} in {code}"


def test_community_credit_keeps_the_legal_sentence() -> None:
    """The 'independent implementation, no upstream source code' statement survives translation."""
    key = "about.credit.pcl"
    for code, marker in INDEPENDENT_MARKERS.items():
        value = i18n.TRANSLATIONS[code][key]
        assert marker in value, f"{code}: the legal sentence was weakened or dropped"
    assert "independently implemented" in i18n.TRANSLATIONS["en_us"][key]


def test_credits_include_the_mandated_names() -> None:
    """The acknowledgment list must keep the projects the user asked to credit."""
    names = " | ".join(entry.name for entry in notices.all_entries())
    for expected in ("PCL2", "PCL CE", "MinePick Launcher Classic", "TheDarkLord234", "Prism Launcher"):
        assert expected in names, f"missing credit: {expected}"
