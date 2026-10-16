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

"""How wide does the window have to be, per language, and which page forces it?

Long-text languages decide the floor: the same layout that fits Korean at 1002px needs 1224px in
Spanish. This measures each language offscreen and names the widest page, then - with --children -
lists the widest widgets inside that page, which is how a width regression gets a cause instead of a
number. It writes nothing into the repository: the preview tree lives in the workspace temp folder.

Usage:
    python tools/measure_min_width.py [--languages es_es,fr_fr] [--children] [--limit 12]
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("MCLAUNCHER_MEASURE_DIR", r"D:\dsh-workspace\tmp\measure_preview"))
LANGUAGES = ("en_us", "zh_cn", "zh_tw", "ja_jp", "ko_kr", "ru_ru", "fr_fr", "es_es", "de_de")
FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/seguiemj.ttf", "C:/Windows/Fonts/consola.ttf")
# The A3 target: the window must fit the longest language without the user resizing anything.
MAX_ACCEPTED_WIDTH = 1180


@dataclass
class Measurement:
    """One language's floor: the window's minimum width and which page forces it."""

    language: str
    window_min: int
    widest_page: str
    per_page: list[tuple[int, str]] = field(default_factory=list)


def measure_languages(languages: Iterable[str] = LANGUAGES) -> list[Measurement]:
    """Measure every language in one QApplication (the caller must not have created one yet)."""
    app = _prepare()
    return _measure_with_app(app, languages)


def _measure_with_app(app, languages: Iterable[str]) -> list[Measurement]:
    from PySide6.QtCore import Qt

    from gui import i18n
    from gui.main_window import NAV_KEYS, MainWindow
    from launcher import config

    results: list[Measurement] = []
    for language in languages:
        cfg, cfg_path = config.load()
        cfg.ui_language = language
        config.save(cfg, cfg_path)
        i18n.set_language(language)

        window = MainWindow()
        window.apply_window_mode()
        # Every page first, then one real layout pass. The window states its floor from the layout, and
        # Qt only refreshes a top-level's minimum size hint on a layout pass: a window that is never
        # shown keeps reporting the launch page's own width (measured: 657px for fr_fr instead of the
        # 1164px the layout needs once all eight pages exist). WA_DontShowOnScreen is the attribute the
        # render tools and tests/conftest.py use to lay out and paint a real window without putting it
        # on the desktop, so nothing here can reach a screen.
        for key in NAV_KEYS:
            window.pages.get(key)
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        for _ in range(8):
            app.processEvents()
        per_page = []
        for key in NAV_KEYS:
            page = window.pages.get(key)
            if page is not None:
                per_page.append((page.minimumSizeHint().width(), key))
        per_page.sort(reverse=True)
        results.append(
            Measurement(
                language=language,
                window_min=window.minimumSizeHint().width(),
                widest_page=per_page[0][1] if per_page else "-",
                per_page=per_page,
            )
        )
        window.close()
        window.deleteLater()
        app.processEvents()
    return results


def worst(measurements: Iterable[Measurement]) -> Measurement | None:
    return max(measurements, key=lambda item: item.window_min, default=None)


def _prepare():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tools"))
    os.chdir(ROOT)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    import shot_pages

    data_dir, game_dir = shot_pages.ensure_preview(WORK, Path("%APPDATA%\\.minecraft"))
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data_dir)
    os.environ["MINECRAFT_GAME_DIR"] = str(game_dir)

    from PySide6.QtGui import QFontDatabase

    from gui.main import create_app
    from gui.theme import apply_theme
    from launcher import config
    from launcher.auth import AccountStore, create_offline_account

    app = create_app([])
    for font_file in FONTS:
        if Path(font_file).exists():
            QFontDatabase.addApplicationFont(font_file)

    cfg, cfg_path = config.load()
    cfg.game_dir = str(game_dir)
    config.save(cfg, cfg_path)
    apply_theme("dark", None, None, "default")

    store = AccountStore()
    if not store.load():
        account = create_offline_account("Steve")
        store.save({account.uuid: account})
    return app


def _label(widget) -> str:
    for getter in ("text", "currentText", "title", "accessibleName", "placeholderText"):
        attr = getattr(widget, getter, None)
        value = attr() if callable(attr) else None
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", " ")[:48]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--languages", default=",".join(LANGUAGES), help="comma-separated language codes")
    parser.add_argument("--children", action="store_true", help="also list the widest widgets per page")
    parser.add_argument("--limit", type=int, default=12, help="rows in the children listing")
    parser.add_argument(
        "--max-width",
        type=int,
        default=MAX_ACCEPTED_WIDTH,
        help="fail when the widest language exceeds this (0 disables the check)",
    )
    args = parser.parse_args()

    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    app = _prepare()
    results = _measure_with_app(app, languages)

    print(f"{'language':10} {'window':>8} {'widest page':>12}   top pages")
    for item in results:
        print(
            f"{item.language:10} {item.window_min:>8} {item.widest_page:>12}   "
            + ", ".join(f"{key}={value}" for value, key in item.per_page[:3])
        )
    worst_item = worst(results)
    if worst_item is not None:
        print(f"\nworst: {worst_item.language} -> {worst_item.window_min}px, driven by page '{worst_item.widest_page}'")

    if args.children and worst_item is not None:
        from PySide6.QtWidgets import QWidget

        from gui import i18n
        from gui.main_window import MainWindow

        i18n.set_language(worst_item.language)
        window = MainWindow()
        window.apply_window_mode()
        app.processEvents()
        page = window.pages.get(worst_item.widest_page)
        if page is not None:
            rows = []
            for child in [page, *page.findChildren(QWidget)]:
                rows.append(
                    (
                        child.minimumSizeHint().width(),
                        child.sizeHint().width(),
                        type(child).__name__,
                        child.objectName() or "-",
                        _label(child),
                    )
                )
            rows.sort(reverse=True)
            print(f"\nwidest children of '{worst_item.widest_page}' ({worst_item.language}):")
            for minimum, hint, kind, name, text in rows[: args.limit]:
                print(f"  min={minimum:>5} hint={hint:>5}  {kind:22} {name:16} {text}")

    if args.max_width and worst_item is not None and worst_item.window_min > args.max_width:
        print(
            f"\nFAIL: {worst_item.language} needs {worst_item.window_min}px, above the {args.max_width}px budget"
        )
        return 1
    if args.max_width:
        print(f"\nOK: every language fits inside {args.max_width}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
