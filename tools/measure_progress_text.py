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

"""Measure the download progress text on the real platform, without ever showing a window.

Why a tool and not just a test: the surface this text sits on is not a static colour pair, so the token
enumeration in tools/audit_ui_quality.py cannot see it. The percentage used to be painted by Qt *inside*
the bar, and a progress bar is two surfaces - the accent chunk growing from the left, the unfilled
background behind it - so which colour the text lands on depends on how far the download has got, and how
readable it is depends on the user's accent preset. Only a render answers that, and only the real platform
answers it for the style the user actually gets: the offscreen platform resolves the stylesheet against a
different palette and a different style.

It renders the real versions page with ``WA_DontShowOnScreen`` (laid out and grabbable, never on screen,
never focused), then per theme and per accent preset:
  * renders the progress row at several values and finds the accent chunk by colour;
  * proves not one text pixel lies over the chunk;
  * isolates the percentage label's glyphs by rendering the row with and without its text, and measures
    the WCAG ratio of every glyph pixel against the pixel that is really behind it;
  * writes each render as a PNG beside the JSON verdict.

Run:
    python tools/measure_progress_text.py --out D:\\dsh-workspace\\tmp\\progress
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["PYTHONIOENCODING"] = "utf-8"

# The values the report quotes. They straddle the bar's midpoint: 20/45 keep the chunk left of the
# centre, 50 splits it, 55/80 have it past the centre - which is exactly where a centred value used to
# end up on the accent fill.
PROGRESS_VALUES = (20, 45, 50, 55, 80)


def luminance(color) -> float:
    channels = []
    for value in color[:3]:
        srgb = value / 255
        channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground, background) -> float:
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _distance(a, b) -> int:
    return sum(abs(p - q) for p, q in zip(a, b))


def _pixels(image):
    """(x, y, rgb) for every logical pixel, so callers never deal with the device ratio."""
    dpr = image.devicePixelRatio() or 1.0
    width = round(image.width() / dpr)
    height = round(image.height() / dpr)
    for y in range(height):
        for x in range(width):
            color = image.pixelColor(
                min(int((x + 0.5) * dpr), image.width() - 1),
                min(int((y + 0.5) * dpr), image.height() - 1),
            )
            yield x, y, (color.red(), color.green(), color.blue())


def _text_pixels(with_text, without_text, tolerance: int = 8):
    """Pixels the text changed, as (x, y, text colour, colour behind it)."""
    before = {(x, y): rgb for x, y, rgb in _pixels(without_text)}
    found = []
    for x, y, rgb in _pixels(with_text):
        behind = before[(x, y)]
        if _distance(rgb, behind) > tolerance:
            found.append((x, y, rgb, behind))
    return found


def _median(values):
    return sorted(values)[len(values) // 2]


def _median_color(colors):
    return tuple(_median([color[index] for color in colors]) for index in range(3))


def analyse_row(with_text, without_text, tokens: dict, tag: str, out: Path) -> dict:
    """Split one progress row into its chunk, its unfilled part and its glyphs, then measure."""
    with_text.save(str(out / f"row_{tag}.png"))
    dpr = with_text.devicePixelRatio() or 1.0
    width = round(with_text.width() / dpr)
    height = round(with_text.height() / dpr)
    middle = height // 2
    row = [rgb for _x, y, rgb in _pixels(with_text) if y == middle]

    accent = hex_to_rgb(tokens["ACCENT"])
    unfilled = hex_to_rgb(tokens["BG_LIST"])
    # The chunk is the run of accent-coloured pixels starting at the left edge, border aside.
    chunk_end = 0
    for x in range(2, width):
        if _distance(row[x], accent) > 40:
            break
        chunk_end = x

    glyphs = _text_pixels(with_text, without_text)
    over_chunk = [p for p in glyphs if p[0] <= chunk_end]
    # The surface each glyph pixel covers: read from the text-free render, and required to be one colour.
    surfaces = {p[3] for p in glyphs}
    ratios = sorted(contrast_ratio(p[2], p[3]) for p in glyphs)
    body = [p for p in glyphs if _distance(p[2], p[3]) >= 0.6 * max(_distance(q[2], q[3]) for q in glyphs)]
    body_color = _median_color([p[2] for p in body]) if body else None
    surface = _median_color([p[3] for p in glyphs]) if glyphs else None
    xs = [p[0] for p in glyphs]
    ys = [p[1] for p in glyphs]
    return {
        "tag": tag,
        "row_px": [width, height],
        "chunk_ends_at_x": chunk_end,
        "chunk_pixel_sampled": row[max(0, chunk_end - 2)] if chunk_end else None,
        "unfilled_pixel_sampled": row[width - 3],
        "accent_token": list(accent),
        "bg_list_token": list(unfilled),
        "text_pixels": len(glyphs),
        "text_box": [min(xs), min(ys), max(xs), max(ys)] if glyphs else None,
        "text_pixels_over_chunk": len(over_chunk),
        "text_surface_colors": sorted(surfaces),
        "text_surface_is_one_color": len(surfaces) == 1,
        "text_surface": list(surface) if surface else None,
        "glyph_body_color": list(body_color) if body_color else None,
        "ratio_body_vs_surface": round(contrast_ratio(body_color, surface), 3) if body_color and surface else None,
        "ratio_worst_glyph_pixel": round(ratios[0], 3) if ratios else None,
        "ratio_median_glyph_pixel": round(ratios[len(ratios) // 2], 3) if ratios else None,
        "ratio_token_FG_HINT_vs_surface": round(contrast_ratio(hex_to_rgb(tokens["FG_HINT"]), surface), 3) if surface else None,
        "ratio_token_FG_HINT_vs_accent": round(contrast_ratio(hex_to_rgb(tokens["FG_HINT"]), accent), 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out", required=True, help="directory for the PNGs and the JSON verdict")
    parser.add_argument("--themes", default="dark,light")
    parser.add_argument("--accents", default="", help="extra accent presets, comma separated")
    parser.add_argument(
        "--values",
        default=",".join(str(value) for value in PROGRESS_VALUES),
        help="bar values to render, comma separated (percent)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.chdir(root)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # A scratch data dir: this must never read or write the user's real launcher data.
    data = out / "_data"
    (data / "game").mkdir(parents=True, exist_ok=True)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data)
    os.environ["MINECRAFT_GAME_DIR"] = str(data / "game")

    from PySide6.QtCore import Qt

    from gui import theme as theme_module

    try:
        from gui.main import create_app
    except ModuleNotFoundError as exc:  # wrong --root: say so instead of a bare traceback
        print(f"cannot import the launcher from {root}: {exc}", file=sys.stderr)
        return 2

    app = create_app([])
    platform = app.platformName()
    if platform == "offscreen":
        print("refusing to run: the offscreen platform is what this tool exists to avoid", file=sys.stderr)
        return 2

    from gui.main_window import MainWindow

    report = {"platform": platform, "qt": __import__("PySide6").__version__, "rows": []}
    accents = [None] + [accent for accent in args.accents.split(",") if accent]
    values = [int(value) for value in args.values.split(",") if value]
    for theme_name in args.themes.split(","):
        for accent in accents:
            # The theme must be in force before the window exists: the pages read the token table while
            # they are built, and a window built first would be polished against the previous theme.
            theme_module.apply_theme(theme_name, accent, None, "default")
            tokens = theme_module.theme_palette(theme_name, accent)
            window = MainWindow()
            window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            window.resize(1000, 610)
            window.show()
            keys = list(window.pages)
            window.sidebar.setCurrentRow(keys.index("versions"))
            for _ in range(10):
                app.processEvents()

            page = window.pages["versions"]
            row_widget = page.progress_row
            bar, label = page.progress_bar, page.progress_text
            row_widget.setVisible(True)
            bar.setRange(0, 1000)
            for _ in range(6):
                app.processEvents()
            window.grab().save(str(out / f"page_{theme_name}_{accent or 'default'}.png"))

            for value in values:
                bar.setValue(value * 10)
                for _ in range(5):
                    app.processEvents()
                tag = f"{theme_name}_{accent or 'default'}_p{value:03d}"
                with_text = row_widget.grab().toImage()
                real = label.text()
                label.setText("")
                for _ in range(4):
                    app.processEvents()
                without_text = row_widget.grab().toImage()
                label.setText(real)
                for _ in range(4):
                    app.processEvents()

                entry = analyse_row(with_text, without_text, tokens, tag, out)
                entry.update(
                    theme=theme_name,
                    accent=accent or tokens["ACCENT"],
                    value_pct=value,
                    bar_is_text_visible=bar.isTextVisible(),
                    bar_accessibility=bar.accessibleName(),
                    label_text=real,
                    label_visible=label.isVisible(),
                    row_visible=row_widget.isVisible(),
                    label_after_bar=label.x() >= bar.x() + bar.width(),
                )
                report["rows"].append(entry)
                print(json.dumps(entry, ensure_ascii=False))

            window.close()
            window.deleteLater()
            for _ in range(4):
                app.processEvents()

    (out / "progress_text.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("report:", out / "progress_text.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
