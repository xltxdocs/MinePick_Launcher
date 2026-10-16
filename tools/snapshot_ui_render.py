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
# You should have received a copy of the GNU General Public License along
# with MinePick Launcher. If not, see <https://www.gnu.org/licenses/>.

"""Render every page and record every widget's geometry, for a before/after pixel comparison.

Why this exists: a stylesheet change that is meant to touch one control has to prove it did not touch
the other 1400. Two renders of the same build are not enough on their own - the ProgressBar rules are
read by every ``QProgressBar``, and a rule added at the wrong nesting level or a token that stops
resolving would show up somewhere else. So this writes, for one checkout state:

  * ``pages_<theme>_<state>.png``  - the eight pages, grabbed per page;
  * ``geometry_<theme>_<state>.json`` - type, objectName, class, geometry, font, and the text of every
    widget on each page, so a moved or resized control shows up as a number and not only as a diff.

Run once with the old stylesheet and once with the new one, then compare (tools/compare_ui_renders.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["PYTHONIOENCODING"] = "utf-8"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out", required=True)
    parser.add_argument("--theme", default="dark", choices=("dark", "light"))
    parser.add_argument("--state", required=True, help="label for this checkout state, e.g. before")
    parser.add_argument(
        "--data",
        default="",
        help="the data dir to render with. The settings page prints the game directory, so two states "
        "compared pixel for pixel must be given the *same* data dir - otherwise the only difference on "
        "that page is the path in a text field (measured: 1798 changed pixels that mean nothing)",
    )
    return parser.parse_args(argv)


def _describe(widget) -> dict:
    from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QProgressBar

    entry = {
        "type": type(widget).__name__,
        "object_name": widget.objectName(),
        "geometry": [widget.x(), widget.y(), widget.width(), widget.height()],
        "visible": widget.isVisibleTo(widget.parentWidget()),
        "enabled": widget.isEnabled(),
    }
    if isinstance(widget, (QLabel, QAbstractButton, QLineEdit, QProgressBar)):
        entry["text"] = widget.text()
    if isinstance(widget, QProgressBar):
        entry["value"] = widget.value()
        entry["text_visible"] = widget.isTextVisible()
        entry["format"] = widget.format()
    font = widget.font()
    entry["font"] = [font.family(), font.pointSizeF(), font.weight()]
    return entry


def _walk(widget) -> list[dict]:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    found = [_describe(widget)]
    children = widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    for child in children:
        found.extend(_walk(child))
    return found


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    root = Path(args.root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.chdir(root)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    data = Path(args.data).resolve() if args.data else out / "_data"
    (data / "game").mkdir(parents=True, exist_ok=True)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data)
    os.environ["MINECRAFT_GAME_DIR"] = str(data / "game")

    from PySide6.QtCore import Qt, QThreadPool
    from PySide6.QtWidgets import QApplication

    from gui import theme as theme_module
    from gui.main import create_app
    from launcher import config
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit
    from tools import shot_pages

    game_dir = data / "game"
    if hasattr(shot_pages, "ensure_preview"):
        shot_pages.ensure_preview(game_dir)

    from gui.pages import java_page, mods_page, versions_page

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
    platform = app.platformName()
    if platform == "offscreen":
        print("refusing to run: the offscreen platform renders a different style", file=sys.stderr)
        return 2

    cfg, cfg_path = config.load()
    cfg.game_dir = str(game_dir)
    config.save(cfg, cfg_path)

    theme_module.apply_theme(args.theme, None, None, "default")
    from gui.main_window import NAV_KEYS, MainWindow

    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(1000, 610)
    window.show()
    QApplication.processEvents()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 5.0)
    QApplication.processEvents()

    report = {
        "platform": platform,
        "theme": args.theme,
        "state": args.state,
        "window_px": [window.width(), window.height()],
        "pages": {},
    }
    target = out / f"geometry_{args.theme}_{args.state}.json"

    def checkpoint() -> None:
        """Write the report after every page.

        Not a nicety: closing this window hangs (measured - the eight pages are written, then
        ``window.close()`` never returns, so a report written only at the end is never written at all).
        Checkpointing means the files on disk are complete whether or not the teardown cooperates, and
        the final write after the loop is the same bytes.
        """
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for index, key in enumerate(NAV_KEYS):
        window.sidebar.setCurrentRow(index)
        QApplication.processEvents()
        shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 3.0)
        QApplication.processEvents()
        page = window.pages[key]
        image = out / f"pages_{args.theme}_{args.state}_{index}_{key}.png"
        page.grab().save(str(image))
        report["pages"][key] = {
            "widgets": _walk(page),
            "image": image.name,
            "size": [page.width(), page.height()],
        }
        checkpoint()
        print(f"  {key:10} {page.width()}x{page.height()} -> {image.name} "
              f"({len(report['pages'][key]['widgets'])} widgets)")

    # Every page is on disk by now; the teardown only has to not crash the exit status.
    checkpoint()
    print("wrote", target)
    sys.stdout.flush()
    sys.stderr.flush()
    # Leave without calling window.close(): see the checkpoint docstring above. Nothing after this point
    # can change the files, and the process does not need to shut Qt down to write them.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
