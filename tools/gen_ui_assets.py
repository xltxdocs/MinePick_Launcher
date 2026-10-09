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

"""Generate (and check) the small UI glyphs at 2x and 3x.

The combo arrow, the spin arrows and the checkbox tick are plain geometric shapes. The shipped 1x
bitmaps are hard-edged, so at 150% scaling Qt has to stretch a 10x6 bitmap to 15x9 and the arrow goes
soft with bitten edges. The fix is not a bigger interpolated bitmap but the same shape *drawn* at the
target size: gui/theme.py picks `@2x`/`@3x` by the screen's device pixel ratio and the stylesheets keep
the logical box (10x6 / 8x5 / 16x16), so the extra pixels land on the device grid 1:1.

The 1x files are never rewritten here: they are what a 100% display still uses, and redrawing them
would change the look at the most common scaling.

    python tools/gen_ui_assets.py           # write the @2x/@3x files
    python tools/gen_ui_assets.py --check   # verify they exist at the exact multiples (gate)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "gui" / "resources"
SCALES = (2, 3)


class Glyph:
    """One logical-size glyph, described by the shape that has to be drawn at any scale."""

    def __init__(self, stem: str, width: int, height: int, shape: str, colour: str) -> None:
        self.stem = stem
        self.width = width
        self.height = height
        self.shape = shape
        self.colour = colour

    def path(self, scale: int) -> Path:
        return ASSET_DIR / f"{self.stem}@{scale}x.png"

    def base_path(self) -> Path:
        return ASSET_DIR / f"{self.stem}.png"


GLYPHS = (
    Glyph("down_arrow", 10, 6, "triangle_down", "#8b9bb4"),
    Glyph("down_arrow_light", 10, 6, "triangle_down", "#5f6b7a"),
    Glyph("spin_up", 8, 5, "triangle_up", "#8a9ab3"),
    Glyph("spin_up_light", 8, 5, "triangle_up", "#5f6b7a"),
    Glyph("spin_down", 8, 5, "triangle_down", "#8a9ab3"),
    Glyph("spin_down_light", 8, 5, "triangle_down", "#5f6a79"),
    Glyph("check", 16, 16, "check", "#ffffff"),
)


def render(glyph: Glyph, scale: int) -> None:
    """Draw the shape at `scale` x the logical size, antialiased, on transparency."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

    image = QImage(glyph.width * scale, glyph.height * scale, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(scale, scale)
    colour = QColor(glyph.colour)

    if glyph.shape == "check":
        pen = QPen(colour, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath(QPointF(3.5, 8.5))
        path.lineTo(6.5, 11.5)
        path.lineTo(13.0, 4.0)
        painter.drawPath(path)
    else:
        path = QPainterPath()
        width, height = float(glyph.width), float(glyph.height)
        if glyph.shape == "triangle_down":
            path.moveTo(0.0, 0.0)
            path.lineTo(width, 0.0)
            path.lineTo(width / 2.0, height)
        else:  # triangle_up
            path.moveTo(0.0, height)
            path.lineTo(width, height)
            path.lineTo(width / 2.0, 0.0)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawPath(path)

    painter.end()
    image.save(str(glyph.path(scale)))


def check() -> int:
    """Every glyph must ship @2x/@3x at exactly the right pixel size."""
    from PySide6.QtGui import QImage

    problems: list[str] = []
    for glyph in GLYPHS:
        base = glyph.base_path()
        if not base.is_file():
            problems.append(f"missing base asset: {base.name}")
        for scale in SCALES:
            path = glyph.path(scale)
            if not path.is_file():
                problems.append(f"missing {path.name} (run without --check to generate)")
                continue
            image = QImage(str(path))
            expected = (glyph.width * scale, glyph.height * scale)
            actual = (image.width(), image.height())
            if actual != expected:
                problems.append(f"{path.name}: {actual[0]}x{actual[1]}, expected {expected[0]}x{expected[1]}")
            else:
                print(f"  ok  {path.name:28} {actual[0]:>3}x{actual[1]:<3} (logical {glyph.width}x{glyph.height} x{scale})")
    if problems:
        print()
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1
    print(f"\nOK: {len(GLYPHS)} glyphs x {len(SCALES)} scales all present at the exact size")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify only, write nothing")
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if not args.check:
        for glyph in GLYPHS:
            for scale in SCALES:
                render(glyph, scale)
                print(f"  wrote {glyph.path(scale).name}")
        print()
    return check()


if __name__ == "__main__":
    sys.exit(main())
