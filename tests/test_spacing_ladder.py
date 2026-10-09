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

"""Spacing ladder guard (S2b): padding and margin must sit on 4/8/12/16/24 px.

Unrelated screens used to invent their own rhythm (12 distinct values across the two sheets), which
is what the UI guideline's fixed ladder exists to prevent. This reuses the audit tool's parser rather
than re-implementing it, so the gate and the report can never disagree about what a declaration is.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import audit_spacing as audit


def _off_ladder(prop: str, value: str) -> list[int]:
    if not audit.SPACING.match(prop):
        return []
    return [
        int(px)
        for px in audit.PX.findall(value)
        if float(px) != 0 and int(px) not in audit.TIERS  # 0 means "no spacing" and is allowed
    ]


def test_every_spacing_declaration_sits_on_the_ladder():
    offenders: list[str] = []
    for name in audit.SHEETS:
        path = ROOT / name
        for number, prop, value in audit.declarations(path):
            off = _off_ladder(prop, value)
            if off:
                offenders.append(f"{name}:{number}  {prop}: {value}  off-ladder: {off}")

    ladder = "/".join(str(tier) for tier in audit.TIERS)
    assert not offenders, (
        f"spacing must stay on the {ladder} px ladder (0 = no spacing):\n  " + "\n  ".join(offenders)
    )
