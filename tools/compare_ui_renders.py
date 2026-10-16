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

"""Compare two ui-render snapshots (tools/snapshot_ui_render.py) and say what moved or changed.

Prints, per page: whether the two renders are byte-identical, and if not, how many pixels differ and
where they are grouped. It also diffs the geometry/text/font record, so a change that moves a control
without repainting it cannot pass as "identical".

    python tools/compare_ui_renders.py --a <dir> --b <dir> --theme dark --state-a before --state-b after
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["PYTHONIOENCODING"] = "utf-8"


def _load_image(path: Path):
    from PySide6.QtGui import QImage

    image = QImage(str(path))
    if image.isNull():
        raise SystemExit(f"cannot read {path}")
    return image


def _diff(a, b) -> dict:
    if a.width() != b.width() or a.height() != b.height():
        return {"size_changed": [[a.width(), a.height()], [b.width(), b.height()]]}
    changed = []
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                changed.append((x, y))
    if not changed:
        return {"identical": True, "changed_pixels": 0}
    xs = [point[0] for point in changed]
    ys = [point[1] for point in changed]
    return {
        "identical": False,
        "changed_pixels": len(changed),
        "bounding_box": [min(xs), min(ys), max(xs), max(ys)],
        "rows_touched": sorted({point[1] for point in changed})[:8],
    }


def _walk_differences(a: list[dict], b: list[dict], path: str = "page") -> list[str]:
    """Compare two flat widget records positionally, reporting the first few differences."""
    problems: list[str] = []
    if len(a) != len(b):
        problems.append(f"{path}: widget count {len(a)} -> {len(b)}")
    for index, (left, right) in enumerate(zip(a, b)):
        if left == right:
            continue
        label = f"{path}[{index}] {left['type']}#{left['object_name']}"
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                problems.append(f"{label}.{key}: {left.get(key)!r} -> {right.get(key)!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--a", required=True, help="snapshot directory of the first state")
    parser.add_argument("--b", required=True, help="snapshot directory of the second state")
    parser.add_argument("--theme", default="dark")
    parser.add_argument("--state-a", default="before")
    parser.add_argument("--state-b", default="after")
    args = parser.parse_args(argv)

    dir_a, dir_b = Path(args.a).resolve(), Path(args.b).resolve()
    geo_a = json.loads((dir_a / f"geometry_{args.theme}_{args.state_a}.json").read_text(encoding="utf-8"))
    geo_b = json.loads((dir_b / f"geometry_{args.theme}_{args.state_b}.json").read_text(encoding="utf-8"))

    from PySide6.QtWidgets import QApplication

    QApplication([])

    total_changed = 0
    geometry_problems: list[str] = []
    for key, page_a in geo_a["pages"].items():
        page_b = geo_b["pages"].get(key)
        if page_b is None:
            print(f"{key:10} MISSING in the second snapshot")
            continue
        image_a = _load_image(dir_a / page_a["image"])
        image_b = _load_image(dir_b / page_b["image"])
        result = _diff(image_a, image_b)
        geometry_problems.extend(
            _walk_differences(page_a["widgets"], page_b["widgets"], path=key)
        )
        if result.get("identical"):
            print(f"{key:10} identical ({page_a['size'][0]}x{page_a['size'][1]})")
        else:
            total_changed += result.get("changed_pixels", 0)
            print(f"{key:10} {result}")

    print(f"\npixels changed across all pages: {total_changed}")
    if geometry_problems:
        print(f"geometry/text differences: {len(geometry_problems)}")
        for line in geometry_problems[:20]:
            print("  " + line)
    else:
        print("geometry/text differences: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
