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

"""Spacing-tier audit for the stylesheets (S2a: report first, converge afterwards).

The UI guideline fixes the spacing ladder at 4 / 8 / 12 / 16 / 24 px so that unrelated screens do not
each invent their own rhythm. This tool lists every `padding` / `margin` value that is off the ladder
(0 is fine - it means "no spacing") plus an inventory of `font-size` values, which S2b needs for the
page-title (17 -> 18px) and card-title token work.

It deliberately exits non-zero while violations exist: that is what makes it usable as a gate once
S2b has converged the values. Until then the exit code is expected to be 1.

Usage:
    python tools/audit_spacing.py [--quiet]
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ("gui/resources/style.qss", "gui/resources/style_light.qss")
TIERS = (4, 8, 12, 16, 24)
COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
# Every declaration, wherever it sits: selectors often carry one inline
# (`QLabel#title { font-size: 17px; }`), which a line-anchored pattern misses.
DECLARATION = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;{}]+);")
PX = re.compile(r"(-?\d+(?:\.\d+)?)px")
SPACING = re.compile(r"^(padding|margin)(-[a-z]+)?$")


def declarations(path: Path):
    """Yield (line number, property, value) for every declaration outside comments."""
    text = COMMENT_BLOCK.sub(lambda match: "\n" * match.group(0).count("\n"), path.read_text(encoding="utf-8"))
    for match in DECLARATION.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        yield line, match.group(1).lower(), match.group(2).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    args = parser.parse_args()

    violations: dict[str, list[tuple[int, str, str, list[int]]]] = defaultdict(list)
    off_ladder_values: Counter[str] = Counter()
    font_sizes: Counter[str] = Counter()

    for name in SHEETS:
        path = ROOT / name
        if not path.is_file():
            print(f"missing stylesheet: {name}")
            continue
        for number, prop, value in declarations(path):
            if prop == "font-size":
                font_sizes[value] += 1
                continue
            if not SPACING.match(prop):
                continue
            numbers = [float(px) for px in PX.findall(value)]
            off = [int(px) for px in numbers if px != 0 and int(px) not in TIERS]
            if off:
                violations[name].append((number, prop, value, off))
                off_ladder_values[value] += 1

    print(f"spacing ladder: {', '.join(f'{t}px' for t in TIERS)} (0 means 'no spacing' and is allowed)")
    print()
    for name in SHEETS:
        rows = violations.get(name, [])
        print(f"=== {name}: {len(rows)} off-ladder declaration(s) ===")
        if not args.quiet:
            for number, prop, value, off in rows:
                print(f"  line {number:4}  {prop:16} {value:20} off-ladder: {off}")
        print()

    print("=== summary ===")
    print(f"  off-ladder declarations: {sum(len(v) for v in violations.values())}")
    for value, count in off_ladder_values.most_common():
        numbers = sorted({int(px) for px in PX.findall(value) if int(px) not in TIERS and int(px) != 0})
        print(f"    {value:22} x{count:3}   off-ladder numbers: {numbers}")
    print()
    print("=== font-size inventory (for S2b) ===")
    for value, count in sorted(font_sizes.items(), key=lambda kv: -kv[1]):
        print(f"    {value:10} x{count}")

    failures = sum(len(v) for v in violations.values())
    print()
    if failures:
        print(f"FAIL: {failures} off-ladder spacing declaration(s) - expected until S2b converges them")
        return 1
    print("OK: every padding/margin value sits on the ladder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
