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

# UI trial helper: quality audit for the interface itself.
#   1. text overflow  - does any label/button/header text not fit in 9 languages (ru/de are longest)?
#   2. contrast       - WCAG ratio of the colour pairs defined in the theme module
#   3. high DPI       - does the window still fit at 125% / 150% scaling?

"""UI quality audit: text overflow per language, colour contrast, high-DPI behaviour."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 600


def contrast_ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    def luminance(color: tuple[int, int, int]) -> float:
        channels = []
        for value in color:
            srgb = value / 255
            channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def check_contrast() -> int:
    from gui.theme import DEFAULT_ACCENTS, readable_fill

    pairs = [
        ("dark muted text / panel", "#8fa2b8", "#161d27", 4.5),
        ("dark normal text / panel", "#e6ecf5", "#161d27", 4.5),
        ("dark empty state / panel", "#7b8ca3", "#161d27", 4.5),
        ("dark disabled text / input", "#6b7c92", "#131a23", 3.0),
        ("dark danger text / panel", "#e5787f", "#161d27", 4.5),
        ("dark warning text / panel", "#e5c07b", "#161d27", 4.5),
        ("dark white on filled button", "#ffffff", readable_fill(DEFAULT_ACCENTS["dark"]), 4.5),
        ("light muted text / panel", "#64748b", "#ffffff", 4.5),
        ("light normal text / panel", "#1f2a36", "#ffffff", 4.5),
        ("light empty state / panel", "#677585", "#ffffff", 4.5),
        ("light disabled text / input", "#78838f", "#f4f6f9", 3.0),
        ("light danger text / panel", "#b03a2e", "#ffffff", 4.5),
        ("light white on filled button", "#ffffff", readable_fill(DEFAULT_ACCENTS["light"]), 4.5),
    ]
    failures = 0
    print("--- contrast (WCAG AA: 4.5 normal text, 3.0 large/disabled) ---")
    for label, foreground, background, minimum in pairs:
        ratio = contrast_ratio(hex_to_rgb(foreground), hex_to_rgb(background))
        ok = ratio >= minimum
        failures += 0 if ok else 1
        print(f"  {'OK  ' if ok else 'FAIL'} {ratio:5.2f} (min {minimum})  {label}")

    # every accent preset must keep white text readable on it
    print("  accent presets with white text:")
    for accent in ("#35a06a", "#3b82f6", "#a855f7", "#e0703a", "#e05a5a", "#14b8a6", "#ec4899", "#f59e0b"):
        ratio = contrast_ratio((255, 255, 255), hex_to_rgb(readable_fill(accent)))
        print(f"    {'OK  ' if ratio >= 4.5 else 'LOW '} {ratio:5.2f}  {accent} -> {readable_fill(accent)}")
    return failures


def check_text_overflow() -> int:
    root = Path(os.environ.get("TRIAL_ROOT", r"D:\dsh-workspace\MinePick_UI_Trial")).resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(root))
    os.chdir(root)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(root / "_preview" / "data")
    os.environ["MINECRAFT_GAME_DIR"] = str(root / "_preview" / "game")

    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QWidget

    from gui import i18n
    from gui.main import create_app
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
        ModSearchHit(slug=f"m{index}", title=f"Mod {index}", downloads=index) for index in range(20)
    ]

    app = create_app([])
    for font_file in ("msyh.ttc", "simhei.ttf", "malgun.ttf", "YuGothM.ttc"):
        path = Path("C:/Windows/Fonts") / font_file
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))

    from gui.main_window import MainWindow

    problems = 0
    for code, name in i18n.UI_LANGUAGES:
        i18n.set_language(code)
        window = MainWindow()
        window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        window.show()
        for _ in range(8):
            app.processEvents()
            time.sleep(0.05)
        for page_index, (page_key, page) in enumerate(window.pages.items()):
            window.sidebar.setCurrentRow(page_index)  # hidden pages are not laid out
            for _ in range(6):
                app.processEvents()
                time.sleep(0.03)
            for widget in _text_widgets(page, (QLabel, QPushButton, QComboBox, QWidget)):
                if not isinstance(widget, (QLabel, QPushButton, QComboBox)) or not widget.isVisible():
                    continue
                text = widget.text() if not isinstance(widget, QComboBox) else widget.currentText()
                if not text or "\n" in text:
                    continue
                if isinstance(widget, QLabel) and widget.wordWrap():
                    continue
                available = widget.contentsRect().width()  # usable width, padding already excluded
                needed = widget.fontMetrics().horizontalAdvance(text)
                if needed > available and widget.width() > 0:
                    problems += 1
                    print(f"  {code:6} {page_key:10} {type(widget).__name__:12} needs {needed:4}px, has {available:4}px  {text[:40]!r}")
        window.close()
        print(f"  checked {code} ({name})")
    print(f"text overflow problems: {problems}")
    return problems


def _text_widgets(widget, kinds):
    from PySide6.QtWidgets import QWidget

    found = []
    for child in widget.children():
        if isinstance(child, QWidget):
            if isinstance(child, kinds):
                found.append(child)
            found.extend(_text_widgets(child, kinds))
    return found


def check_high_dpi(scale: float) -> int:
    """Render at a scaled factor in a fresh process (a QApplication cannot be recreated)."""
    import subprocess

    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env.update(
        {
            "QT_SCALE_FACTOR": str(scale),
            "QT_QPA_PLATFORM": "offscreen",
            "TRIAL_ROOT": str(root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--dpi"], env=env, cwd=str(root), check=False)
    return 0


def _dpi_probe() -> int:
    """Worker mode: report the window size under the QT_SCALE_FACTOR set by the caller."""
    root = Path(os.environ.get("TRIAL_ROOT", r"D:\dsh-workspace\MinePick_UI_Trial")).resolve()
    sys.path.insert(0, str(root))
    os.chdir(root)
    # never touch the user's real launcher data: always use the trial preview folders
    os.environ["MCLAUNCHER_DATA_DIR"] = str(root / "_preview" / "data")
    os.environ["MINECRAFT_GAME_DIR"] = str(root / "_preview" / "game")

    from PySide6.QtGui import QFontDatabase

    from gui.main import create_app
    from gui.main_window import MainWindow

    app = create_app([])
    for font_file in ("msyh.ttc", "simhei.ttf", "malgun.ttf", "YuGothM.ttc"):
        path = Path("C:/Windows/Fonts") / font_file
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    window = MainWindow()
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    shot = window.grab()
    print(
        f"  scale {os.environ.get('QT_SCALE_FACTOR', '1')}: window {window.width()}x{window.height()}"
        f"  grab {shot.width()}x{shot.height()}  min-height {window.minimumSizeHint().height()}"
    )
    return 0


def main() -> int:
    sys.stdout.reconfigure(errors="replace")  # never crash on console encoding
    if "--dpi" in sys.argv:  # worker mode: no QApplication may exist yet
        return _dpi_probe()
    wants_json = "--json" in sys.argv
    root = Path(os.environ.get("TRIAL_ROOT", r"D:\dsh-workspace\MinePick_UI_Trial")).resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(root))
    os.chdir(root)

    print("=== 1. contrast ===")
    contrast_failures = check_contrast()
    print("\n=== 2. text overflow (9 languages) ===")
    overflow = check_text_overflow()
    print("\n=== 3. high DPI ===")
    check_high_dpi(1.25)
    print("\nsummary: contrast failures =", contrast_failures, "| overflow =", overflow)
    if wants_json:
        # machine-readable verdict: callers should judge by this, not by the exit code
        print(
            json.dumps(
                {
                    "contrast_failures": contrast_failures,
                    "overflow": overflow,
                    "ok": not (contrast_failures or overflow),
                }
            )
        )
        return 0
    return 1 if (contrast_failures or overflow) else 0


if __name__ == "__main__":
    raise SystemExit(main())
