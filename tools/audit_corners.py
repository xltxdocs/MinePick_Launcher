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

# UI trial helper: render every page offscreen and audit the four corners of each
# panel-like widget. Qt style sheets produce a few corner artifacts that are hard to
# spot by eye (a rounded header section exposes the base style's light background, a
# thicker left border pokes out of a rounded corner), so this prints a verdict per
# corner: "round" (window background shows through), "SQUARE" (the widget's own
# background reaches the corner) or "ODD" (some third colour = an artifact).

"""Offscreen corner audit for the UI trial build."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Qt is imported inside the functions so the module stays import-light
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QWidget

sys.dont_write_bytecode = True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="dark", choices=["dark", "light"])
    args = parser.parse_args()

    root = Path(os.environ.get("TRIAL_ROOT", r"D:\dsh-workspace\MinePick_UI_Trial")).resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(root))
    os.chdir(root)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(root / "_preview" / "data")
    os.environ["MINECRAFT_GAME_DIR"] = str(root / "_preview" / "game")

    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import (
        QAbstractScrollArea,
        QComboBox,
        QFrame,
        QLineEdit,
        QPlainTextEdit,
    )

    from gui.pages import mods_page, versions_page
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit

    manifest = VersionManifest(
        latest={"release": "1.21.11", "snapshot": "26w02a"},
        versions=[
            ManifestVersion(
                id=f"1.{index}",
                type="release",
                url="",
                time="2025-01-01T00:00:00+00:00",
                release_time="2025-01-01T00:00:00+00:00",
            )
            for index in range(20)
        ],
    )
    versions_page.fetch_manifest = lambda cache_path=None: manifest  # type: ignore[assignment]
    mods_page.search_projects = lambda *a, **k: [  # type: ignore[assignment]
        ModSearchHit(slug=f"m{index}", title=f"Mod {index}", downloads=index)
        for index in range(20)
    ]

    from gui.main import create_app

    app = create_app([])
    for font_file in ("msyh.ttc", "simhei.ttf"):
        font_path = Path("C:/Windows/Fonts") / font_file
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))

    from gui.theme import apply_theme

    apply_theme(args.theme)  # audit one theme at a time

    from gui.main_window import MainWindow

    window = MainWindow()
    window.resize(1000, 600)
    window.show()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)

    kinds = (QAbstractScrollArea, QComboBox, QLineEdit, QPlainTextEdit, QFrame)
    problems = 0
    for index, key in enumerate(window.pages):
        window.sidebar.setCurrentRow(index)
        for _ in range(12):
            app.processEvents()
            time.sleep(0.05)
        image: QImage = window.grab().toImage()
        page = window.pages[key]
        window_bg = image.pixelColor(page.mapTo(window, QPoint(6, 6))).getRgb()[:3]
        print(f"--- {key} (page background {window_bg}) ---")
        for widget in _collect(page, kinds):
            verdicts = _audit(widget, window, image, window_bg)
            if verdicts is None:
                continue
            odd = "ODD" in [verdict for _name, _color, verdict in verdicts]
            if odd:
                problems += 1
            summary = " ".join(f"{name}:{verdict}" for name, _c, verdict in verdicts)
            mark = "   <== CHECK" if odd else ""
            print(f"  {type(widget).__name__:18} {widget.width():4}x{widget.height():<4} {summary}{mark}")
    print(f"\nartifacts found: {problems}")
    return 1 if problems else 0


def _collect(widget: QWidget, kinds: tuple) -> list[QWidget]:
    from PySide6.QtWidgets import QWidget as _QWidget

    found: list[QWidget] = []
    for child in widget.children():
        if isinstance(child, _QWidget):
            if isinstance(child, kinds):
                found.append(child)
            found.extend(_collect(child, kinds))
    return found


def _near(left, right, tolerance: int = 12) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _audit(widget: QWidget, window: QWidget, image: QImage, window_bg):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit

    if not widget.isVisible() or widget.width() < 40 or widget.height() < 24:
        return None
    # the inner line edit of a spin box / editable combo has no frame of its own
    if isinstance(widget, QLineEdit) and isinstance(widget.parent(), (QAbstractSpinBox, QComboBox)):
        return None
    top_left = widget.mapTo(window, QPoint(0, 0))
    x0, y0 = top_left.x(), top_left.y()
    x1, y1 = x0 + widget.width() - 1, y0 + widget.height() - 1
    if x0 < 2 or y0 < 2 or x1 >= image.width() - 2 or y1 >= image.height() - 2:
        return None
    own = image.pixelColor(x0 + 6, (y0 + y1) // 2).getRgb()[:3]
    # sample one pixel inside the frame: the outermost pixel is the 1px border, which is
    # a different colour on purpose and used to be reported as an artifact
    corners = {
        "TL": (x0 + 1, y0 + 1),
        "TR": (x1 - 1, y0 + 1),
        "BL": (x0 + 1, y1 - 1),
        "BR": (x1 - 1, y1 - 1),
    }
    verdicts = []
    for name, (x, y) in corners.items():
        color = image.pixelColor(x, y).getRgb()[:3]
        if _near(color, own):
            verdict = "SQUARE"
        elif _near(color, window_bg):
            verdict = "round"
        else:
            verdict = "ODD"
        verdicts.append((name, color, verdict))
    return verdicts


if __name__ == "__main__":
    raise SystemExit(main())
