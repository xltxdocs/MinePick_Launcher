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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("MCLAUNCHER_MEASURE_DIR", r"D:\dsh-workspace\tmp\measure_preview"))
LANGUAGES = ("en_us", "zh_cn", "zh_tw", "ja_jp", "ko_kr", "ru_ru", "fr_fr", "es_es", "de_de")
FONTS = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/seguiemj.ttf", "C:/Windows/Fonts/consola.ttf")


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
    args = parser.parse_args()

    app = _prepare()
    from pathlib import Path as _Path

    from PySide6.QtWidgets import QWidget

    from gui import i18n
    from gui.main_window import NAV_KEYS, MainWindow
    from launcher import config

    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    print(f"{'language':10} {'window':>8} {'widest page':>12}   top pages")
    worst = ("", 0, "")
    worst_window = None
    for language in languages:
        cfg, cfg_path = config.load()
        cfg.ui_language = language
        config.save(cfg, cfg_path)
        i18n.set_language(language)

        window = MainWindow()
        window.apply_window_mode()
        app.processEvents()
        window_min = window.minimumSizeHint().width()

        per_page = []
        for key in NAV_KEYS:
            page = window.pages.get(key)
            if page is not None:
                per_page.append((page.minimumSizeHint().width(), key))
        per_page.sort(reverse=True)
        widest = per_page[0] if per_page else (0, "-")
        print(
            f"{language:10} {window_min:>8} {widest[1]:>12}   "
            + ", ".join(f"{key}={value}" for value, key in per_page[:3])
        )
        if window_min > worst[1]:
            worst = (language, window_min, widest[1])
            worst_window = window
        else:
            window.close()
            window.deleteLater()
        app.processEvents()

    print(f"\nworst: {worst[0]} -> {worst[1]}px, driven by page '{worst[2]}'")

    if args.children and worst_window is not None:
        i18n.set_language(worst[0])
        page = worst_window.pages.get(worst[2])
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
            print(f"\nwidest children of '{worst[2]}' ({worst[0]}):")
            for minimum, hint, kind, name, text in rows[: args.limit]:
                print(f"  min={minimum:>5} hint={hint:>5}  {kind:22} {name:16} {text}")

    _ = _Path  # kept for readers of the imports above
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
