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

# UI trial helper: render every page offscreen to PNG so the redesign can be compared
# side by side with the released build. Reads a project tree read-only; all preview
# config/data live inside the trial folder.

"""Offscreen page renderer for the UI trial build."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # never drop __pycache__ into the tree being rendered


FAKE_MODS = [
    ("sodium", "Sodium", "Modern rendering engine and client-side optimization mod", 231_450_000),
    ("iris", "Iris Shaders", "A modern shaders mod compatible with OptiFine shaderpacks", 48_120_000),
    ("lithium", "Lithium", "No-compromises game logic and performance optimization mod", 92_300_000),
    ("fabric-api", "Fabric API", "Lightweight and modular API providing common hooks and intercompatibility", 187_900_000),
    ("jei", "Just Enough Items", "View items and recipes for anything in the game", 210_770_000),
    ("modmenu", "Mod Menu", "Adds a mod menu to view the list of mods you have installed", 120_540_000),
    ("cloth-config", "Cloth Config API", "Configuration screen API used by many fabric mods", 165_880_000),
    ("roughly-enough-items", "Roughly Enough Items", "Recipe viewer with a modern look and feel", 61_230_000),
    ("create", "Create", "Aesthetic technology mod with rotational power and contraptions", 74_610_000),
    ("xaeros-minimap", "Xaero's Minimap", "Minimap with waypoints, entity radar and cave mode", 88_940_000),
    ("appleskin", "AppleSkin", "Food-related HUD information: hunger, saturation and exhaustion", 57_330_000),
    ("journeymap", "JourneyMap", "Real-time mapping in game or in a web browser", 69_150_000),
]

FAKE_VERSIONS = [
    ("1.21.11", "release", "2025-12-09"),
    ("1.21.10", "release", "2025-11-25"),
    ("1.21.9", "release", "2025-11-11"),
    ("1.21.8", "release", "2025-09-30"),
    ("1.21.7", "release", "2025-08-19"),
    ("1.21.6", "release", "2025-07-15"),
    ("1.21.5", "release", "2025-06-03"),
    ("1.21.4", "release", "2025-03-25"),
    ("1.21.3", "release", "2025-02-11"),
    ("1.21.1", "release", "2024-08-08"),
    ("1.21", "release", "2024-06-13"),
    ("1.20.6", "release", "2024-04-29"),
    ("1.20.4", "release", "2023-12-07"),
    ("1.20.2", "release", "2023-09-21"),
    ("1.20.1", "release", "2023-06-12"),
    ("1.19.4", "release", "2023-03-14"),
    ("1.18.2", "release", "2022-02-28"),
    ("1.16.5", "release", "2021-01-15"),
    ("1.12.2", "release", "2017-09-18"),
    ("1.8.9", "release", "2015-12-09"),
    ("26w02a", "snapshot", "2026-01-13"),
    ("25w45a", "snapshot", "2025-11-04"),
    ("24w14potato", "snapshot", "2024-04-01"),
    ("23w13a_or_b", "snapshot", "2023-04-01"),
    ("22w13oneblockatatime", "snapshot", "2022-04-01"),
    ("20w14infinite", "snapshot", "2020-04-01"),
    ("1.RV-Pre1", "snapshot", "2016-03-31"),
    ("b1.7.3", "old_beta", "2011-07-08"),
    ("a1.2.6", "old_alpha", "2010-12-02"),
]


def ensure_preview(root: Path) -> tuple[Path, Path]:
    """Create the preview data/game directories used by the renderer."""
    preview = root / "_preview"
    data = preview / "data"
    game = preview / "game"
    # Managed Java runtimes are detected by directory only (runtime/java-<major>), so the
    # preview never plants a fake java.exe: the launcher would probe it and Windows would
    # pop "unsupported 16-bit application" dialogs for the bogus executable.
    (data / "runtime" / "java-8" / "bin").mkdir(parents=True, exist_ok=True)
    (data / "runtime" / "java-21" / "bin").mkdir(parents=True, exist_ok=True)
    (data / "runtime" / "java-8" / "release").write_text(
        "IMPLEMENTOR=\"Preview\"\nJAVA_VERSION=\"1.8.0_999\"\n", encoding="utf-8"
    )
    (data / "runtime" / "java-21" / "release").write_text(
        "IMPLEMENTOR=\"Preview\"\nJAVA_VERSION=\"21.0.9\"\n", encoding="utf-8"
    )
    (data / "runtime" / "java-8" / "bin" / "preview-placeholder.txt").write_text(
        "Preview stub: no executable here on purpose (see tools/shot_pages.py).\n",
        encoding="utf-8",
    )
    (data / "runtime" / "java-21" / "bin" / "preview-placeholder.txt").write_text(
        "Preview stub: no executable here on purpose (see tools/shot_pages.py).\n",
        encoding="utf-8",
    )

    versions = [
        "1.20.1",
        "1.21.11",
        "fabric-loader-0.19.3-1.21.11",
        "1.20.1-forge-47.4.22",
        "neoforge-21.1.5",
    ]
    for vid in versions:
        vdir = game / "versions" / vid
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / f"{vid}.json").write_text(
            json.dumps({"id": vid, "mainClass": "net.minecraft.client.main.Main"}),
            encoding="utf-8",
        )

    instances = [
        ("整合包演示", "fabric-loader-0.19.3-1.21.11", "Fabulously Optimized 整合包，含性能模组"),
        ("生存存档", "1.20.1", "长期存档，装了 JEI 和 Create"),
    ]
    for name, vid, note in instances:
        idir = game / "instances" / name
        (idir / "mods").mkdir(parents=True, exist_ok=True)
        (idir / "saves").mkdir(parents=True, exist_ok=True)
        (idir / "versions" / vid).mkdir(parents=True, exist_ok=True)
        (idir / "versions" / vid / f"{vid}.json").write_text(
            json.dumps({"id": vid}), encoding="utf-8"
        )
        (idir / "instance.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "version_id": vid,
                    "created_at": time.time() - 86400 * 9,
                    "note": note,
                    "base": False,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    for jar in ("sodium-fabric-0.6.5.jar", "lithium-fabric-0.15.3.jar", "iris-fabric-1.8.1.jar"):
        (game / "instances" / "整合包演示" / "mods" / jar).write_bytes(b"PK\x03\x04trial")
    return data, game


def wait_for_workers(app, pool, seconds: float = 20.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        if pool.waitForDone(120):
            break
    for _ in range(6):
        app.processEvents()
        time.sleep(0.05)


def _scroll_page_to_bottom(page) -> None:
    """Scroll a page's QScrollArea to the end (settings page) so the lower rows are visible."""
    from PySide6.QtWidgets import QScrollArea

    for area in page.findChildren(QScrollArea):
        bar = area.verticalScrollBar()
        bar.setValue(bar.maximum())


def main() -> int:
    sys.stdout.reconfigure(errors="replace")  # never crash on console encoding
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="project tree to import from")
    parser.add_argument("--out", required=True, help="output directory for PNGs")
    parser.add_argument("--theme", default="dark", choices=["dark", "light"])
    parser.add_argument("--label", default="", help="filename prefix")
    parser.add_argument("--accent", default="", help="custom accent color, e.g. #3b82f6")
    parser.add_argument("--font", default="", help="custom UI font family")
    parser.add_argument("--radius", default="", help="corner radius preset: compact / default / round")
    parser.add_argument(
        "--scroll-bottom", action="store_true", help="scroll the page to the bottom before grabbing"
    )
    parser.add_argument("--pages", default="", help="comma separated page subset, e.g. launch,settings")
    parser.add_argument(
        "--preview",
        default="",
        help="where to keep _preview data (defaults to --root; point at the trial folder when rendering the released tree)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(root))
    os.chdir(root)

    data_dir, game_dir = ensure_preview(Path(args.preview).resolve() if args.preview else root)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data_dir)
    os.environ["MINECRAFT_GAME_DIR"] = str(game_dir)

    from PySide6.QtCore import QThreadPool

    from gui.pages import java_page, mods_page, versions_page
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit

    manifest = VersionManifest(
        latest={"release": "1.21.11", "snapshot": "26w02a"},
        versions=[
            ManifestVersion(
                id=vid,
                type=vtype,  # type: ignore[arg-type]
                url="https://example.invalid/version.json",
                time=f"{date}T12:00:00+00:00",
                release_time=f"{date}T12:00:00+00:00",
            )
            for vid, vtype, date in FAKE_VERSIONS
        ],
    )
    hits = [
        ModSearchHit(slug=slug, title=title, description=desc, downloads=dl)
        for slug, title, desc, dl in FAKE_MODS
    ]

    # offline stubs so rendering never waits on the network
    versions_page.fetch_manifest = lambda cache_path=None: manifest  # type: ignore[assignment]
    mods_page.search_projects = lambda *a, **k: list(hits)  # type: ignore[assignment]
    java_page.list_java = lambda *a, **k: []  # type: ignore[assignment]

    from gui.main import create_app
    from gui.pages.wizard import FirstRunWizard  # noqa: F401  (import check only)
    from gui.theme import apply_theme

    app = create_app([])
    apply_theme(args.theme, args.accent, args.font, args.radius or "default")

    # the offscreen platform ships almost no font families: register the system CJK fonts
    # explicitly, otherwise every Chinese label renders as tofu boxes
    from PySide6.QtGui import QFontDatabase

    for font_file in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/deng.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
    ):
        if Path(font_file).exists():
            QFontDatabase.addApplicationFont(font_file)

    from launcher import config
    from launcher.auth import AccountStore, create_offline_account

    cfg, cfg_path = config.load()
    cfg.game_dir = str(game_dir)
    cfg.theme = args.theme
    cfg.accent_color = args.accent
    cfg.ui_font = args.font
    if args.radius:
        cfg.ui_radius = args.radius
    # wizard_done is left untouched on purpose: rendering must not decide whether the
    # first-run wizard still shows in the preview
    config.save(cfg, cfg_path)
    apply_theme(args.theme, args.accent, args.font, cfg.ui_radius)
    store = AccountStore()
    accounts = store.load()
    if not accounts:
        account = create_offline_account("Steve")
        store.save({account.uuid: account})

    from gui.main_window import MainWindow

    window = MainWindow()
    window.resize(1000, 600)
    window.apply_window_mode()
    window.show()
    wait_for_workers(app, QThreadPool.globalInstance(), 3.0)

    # load page data through the real code paths (background workers, stubbed sources)
    window.pages["versions"].refresh()
    wait_for_workers(app, QThreadPool.globalInstance(), 15.0)
    window.pages["java"].refresh()
    wait_for_workers(app, QThreadPool.globalInstance(), 15.0)

    names = ["launch", "instances", "versions", "java", "account", "mods", "settings"]
    if args.pages:
        wanted = [item.strip() for item in args.pages.split(",") if item.strip()]
        names = [name for name in names if name in wanted]
    prefix = f"{args.label}_" if args.label else ""
    for name in names:
        index = ["launch", "instances", "versions", "java", "account", "mods", "settings"].index(name)
        window.sidebar.setCurrentRow(index)
        for _ in range(8):
            app.processEvents()
            time.sleep(0.05)
        wait_for_workers(app, QThreadPool.globalInstance(), 8.0)
        if args.scroll_bottom:
            _scroll_page_to_bottom(window.pages[name])
            for _ in range(4):
                app.processEvents()
                time.sleep(0.05)
        pixmap = window.grab()
        target = out_dir / f"{prefix}{index}_{name}.png"
        pixmap.save(str(target))
        print(f"saved {target} ({pixmap.width()}x{pixmap.height()})")

    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
