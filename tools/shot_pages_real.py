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

"""Render the eight pages on the REAL Qt platform, without ever putting a window on screen.

`tools/shot_pages.py` forces `QT_QPA_PLATFORM=offscreen`, which uses a different Qt style, has no native
popups, and - the reason this tool exists - starts from a different default palette. The light theme's
"everything looks wrong" bug lived precisely in that gap: the platform palette followed the system's dark
colour scheme while the stylesheet said light, so every surface Qt drew itself came out dark.

Here the default platform stays in place (so the platform palette and the native popup code paths are the
real ones) but every window is marked `WA_DontShowOnScreen`: it is laid out, styled and grabbable while
never appearing on the user's screen.

    python tools/shot_pages_real.py --root . --theme light --out D:\\dsh-workspace\\tmp\\realplat
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Must happen before Qt is imported: keep the platform default, only make sure it is not offscreen.
os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["PYTHONIOENCODING"] = "utf-8"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render pages on the real platform, invisibly.")
    parser.add_argument("--theme", choices=("dark", "light"), default="light")
    parser.add_argument("--out", required=True, help="directory for the PNGs")
    parser.add_argument("--root", default=".", help="repository root (resource path base)")
    parser.add_argument("--data", default="", help="data dir; a temp one is used when omitted")
    parser.add_argument("--popup", action="store_true", help="also grab one dropdown popup")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    root = Path(args.root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    data = Path(args.data) if args.data else root.parent / "tmp" / "shot_pages_real_data"
    data.mkdir(parents=True, exist_ok=True)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data)

    from PySide6.QtCore import Qt, QThreadPool
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication, QComboBox

    from gui.main import create_app
    from gui.pages import java_page, mods_page, versions_page
    from gui.theme import apply_theme
    from launcher import config
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit
    from tools import shot_pages

    game_dir = data / "game"
    game_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(shot_pages, "ensure_preview"):
        shot_pages.ensure_preview(game_dir)

    # The same deterministic content the offscreen renderer uses, so the two are comparable.
    versions_page.fetch_manifest = lambda cache_path=None: VersionManifest(  # type: ignore[assignment]
        latest={"release": "1.21.11", "snapshot": "26w02a"},
        versions=[
            ManifestVersion(
                id=vid,
                type=vtype,  # type: ignore[arg-type]
                url="https://example.invalid/version.json",
                time=f"{date}T12:00:00+00:00",
                release_time=f"{date}T12:00:00+00:00",
            )
            for vid, vtype, date in shot_pages.FAKE_VERSIONS
        ],
    )
    mods_page.search_projects = lambda *a, **k: [  # type: ignore[assignment]
        ModSearchHit(slug=slug, title=title, description=desc, downloads=dl)
        for slug, title, desc, dl in shot_pages.FAKE_MODS
    ]
    java_page.list_java = lambda *a, **k: []  # type: ignore[assignment]

    app = create_app([])
    for font_file in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"):
        if Path(font_file).exists():
            QFontDatabase.addApplicationFont(font_file)

    platform = app.platformName()
    if platform == "offscreen":
        print("refusing to run: the offscreen platform is what this tool exists to avoid", file=sys.stderr)
        return 2

    cfg, cfg_path = config.load()
    cfg.game_dir = str(game_dir)
    config.save(cfg, cfg_path)

    from gui.main_window import NAV_KEYS, MainWindow

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    apply_theme(args.theme, None, None, "default")
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(1000, 610)
    window.show()
    QApplication.processEvents()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 5.0)
    QApplication.processEvents()

    print(f"platform={platform}  colourScheme={app.styleHints().colorScheme()}")
    for index, key in enumerate(NAV_KEYS):
        window.sidebar.setCurrentRow(index)
        QApplication.processEvents()
        shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 3.0)
        QApplication.processEvents()
        target = out / f"{index}_{key}.png"
        window.grab().save(str(target))
        print(f"  {args.theme} {key:10} -> {target.name}")

    if args.popup:
        for combo in window.findChildren(QComboBox):
            if not combo.isVisible() or combo.count() == 0:
                continue
            popup = combo.view().window()
            popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            combo.showPopup()
            QApplication.processEvents()
            target = out / f"popup_{combo.objectName() or 'combo'}.png"
            popup.grab().save(str(target))
            print(f"  {args.theme} popup     -> {target.name}")
            combo.hidePopup()
            QApplication.processEvents()
            break

    window.close()
    window.deleteLater()
    QApplication.processEvents()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
