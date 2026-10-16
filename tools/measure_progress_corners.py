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

"""Sample the four corners of the download progress control at many values, on the REAL platform.

The user report is "the download progress bar is sometimes square, sometimes round". A download row is
two widgets sharing one outline - the bar, and the percentage label flush against its right edge - and
the bar is two rectangles: the control's frame (background + border + the two left radii the stylesheet
sets) and the accent ``::chunk`` inside it. What a corner looks like therefore depends on how wide the
chunk is, which is to say on how far the download has got, and that is a claim about rendered pixels that
only a render can settle.

Windows are marked ``WA_DontShowOnScreen``: laid out, styled and grabbable, never on screen, never
focused. The row stands on a two-colour plate, so "the plate shows through this pixel" is read rather
than assumed: a corner pixel that is the plate is a round corner, one that is the control's own paint is
a square one, and anything else is reported as ODD instead of being folded into either answer.

How this tool guarantees it never displays a window (the pattern the other capture tools can copy):

* every top-level widget it builds is marked ``WA_DontShowOnScreen`` *before* ``show()`` - the attribute
  only takes effect on a widget that is not mapped yet - and ``show()`` is still called, because that is
  what makes Qt lay the widget out and style it;
* an application event filter records the moment any top-level window is shown without that marker, and
  the next checkpoint aborts the run with it. It records rather than raises *inside* the filter on
  purpose: measured, an exception raised in a Qt event filter does not travel out of ``show()`` - Qt
  prints "Error calling Python override" and keeps dispatching, and the exception is re-entered by every
  later event;
* it refuses to start if the launcher already has a visible top-level window, and it refuses to run on the
  offscreen platform (which renders a different style and would make every number below meaningless).

The pixels are read at ``devicePixelRatio``: ``grab()`` paints at 1.5x on this screen, so a corner read
at logical coordinates alone lands a third of the way into the corner it is trying to describe.

To see the shape this tool was written to catch, put the old radius back on the chunk by hand and re-run
it: add ``border-radius: 7px;`` to the ``QProgressBar::chunk`` rule in ``gui/resources/style.qss`` (and in
``style_light.qss`` for the light theme). There is deliberately no flag for it - the shipped sheet has no
such rule, so a flag that swapped one in never matched anything and silently measured the shipped sheet
anyway. Measured that way at 500/1000 the fill's left edge is no longer straight (its first accent pixel
sits at offset 1 on the middle rows and at offset 6 on the top row) and its right edge finishes in a 5px
bevel, against a straight edge at offset 1 and across all 16 inner rows with the radius removed.

    python tools/measure_progress_corners.py --out D:\\dsh-workspace\\tmp\\progress_corners
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["PYTHONIOENCODING"] = "utf-8"

# The values the report quotes, in the 0-1000 scale the pages drive the bar with.
PROGRESS_VALUES = (0, 10, 50, 500, 950, 990, 1000)

# Two flat colours, split at the bar's midpoint. Whatever a corner pixel is, it is one of these, the
# control's own paint, or a defect worth reporting as ODD.
PLATE_LEFT = (255, 0, 255)
PLATE_RIGHT = (0, 255, 0)

# What the report calls a corner, from the colour that ended up there.
ROUND = "round"
SQUARE = "square"
ODD = "odd"


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _distance(a, b) -> int:
    return sum(abs(p - q) for p, q in zip(a, b))


def _near(a, b, tolerance: int = 30) -> bool:
    if a is None or b is None:
        return False
    return _distance(a, b) <= tolerance


class Palette:
    """The three colours that can legitimately appear at a corner, plus the plate behind it."""

    def __init__(self, tokens: dict, plate_left, plate_right, split_x: int) -> None:
        self.roles = {
            "chunk": _rgb(tokens["ACCENT"]),
            "bar_background": _rgb(tokens["BG_LIST"]),
            "frame_border": _rgb(tokens["BORDER_LIST"]),
            "page": _rgb(tokens["BG_WINDOW"]),
        }
        self.plate = {"plate_left": tuple(plate_left), "plate_right": tuple(plate_right)}
        self.split_x = split_x

    def role_at(self, rgb) -> str:
        for name, ref in self.roles.items():
            if _near(rgb, ref):
                return name
        for name, ref in self.plate.items():
            if _near(rgb, ref):
                return name
        return "unmatched"

    def plate_for(self, x: int) -> str:
        return "plate_left" if x < self.split_x else "plate_right"

    def verdict(self, rgb, x: int) -> str:
        """ROUND when the colour behind the control shows through, SQUARE when its own paint does."""
        role = self.role_at(rgb)
        if role in ("plate_left", "plate_right"):
            return ROUND
        if role == "unmatched":
            return ODD
        return SQUARE


def _pixel(image, x: float, y: float, dpr: float):
    """The colour of one logical pixel, read at its centre in device pixels."""
    px = min(max(round(x * dpr), 0), image.width() - 1)
    py = min(max(round(y * dpr), 0), image.height() - 1)
    return image.pixelColor(px, py)


def _corner_report(image, rect, fill_role: str, palette: Palette, dpr: float) -> dict:
    x0, y0, x1, y1 = rect
    spots = {"TL": (x0, y0), "TR": (x1, y0), "BL": (x0, y1), "BR": (x1, y1)}
    out = {}
    for name, (x, y) in spots.items():
        color = _pixel(image, x, y, dpr).getRgb()[:3]
        role = palette.role_at(color)
        out[name] = {
            "logical_pixel": [x, y],
            "device_pixel": [round(x * dpr), round(y * dpr)],
            "rgb": list(color),
            "role": role,
            "verdict": palette.verdict(color, round(x * dpr)),
            "is_the_fill_it_should_paint": role == fill_role,
        }
    return out


def _visible_right_edge(image, bar_rect, split_x: int, palette: Palette, dpr: float) -> dict:
    """Where the accent stops, and what the bar's last painted column looks like down its height.

    This is the read the corner samples cannot give: at the right end of the bar the interesting
    question is not a single pixel but the *shape* of the edge - a vertical line, or an arc.
    """
    x0, y0, x1, y1 = bar_rect
    middle_y = y0 + (y1 - y0) / 2
    # The last column of the bar that is not the plate behind it.
    edge_x = None
    for x in range(x1, x0, -1):
        if palette.role_at(_pixel(image, x, middle_y, dpr).getRgb()[:3]) not in (
            "plate_left",
            "plate_right",
        ):
            edge_x = x
            break
    if edge_x is None:
        return {"edge_x": None, "column_top_to_bottom": None, "chunk_right_x": None,
                "chunk_present_rows_at_that_column": []}
    column = []
    y = y0
    while y <= y1:
        column.append(palette.role_at(_pixel(image, edge_x, y, dpr).getRgb()[:3]))
        y += 1
    # The accent's rightmost column, sampled above the percentage text (which sits in the middle).
    accent_x = None
    for x in range(x1, x0, -1):
        if palette.role_at(_pixel(image, x, y0 + (y1 - y0) * 0.25, dpr).getRgb()[:3]) == "chunk":
            accent_x = x
            break
    accent_rows = []
    if accent_x is not None:
        for yy in range(y0, y1 + 1):
            if palette.role_at(_pixel(image, accent_x, yy, dpr).getRgb()[:3]) == "chunk":
                accent_rows.append(yy - y0)
    return {
        "edge_x": edge_x,
        "column_top_to_bottom": column,
        "chunk_right_x": accent_x,
        "chunk_present_rows_at_that_column": accent_rows,
    }


def _analyse(image, bar_rect, label_rect, row_rect, tokens, dpr: float, split_x: int) -> dict:
    palette = Palette(tokens, PLATE_LEFT, PLATE_RIGHT, split_x)
    return {
        "image_px": [image.width(), image.height()],
        "dpr": dpr,
        "bar_rect": list(bar_rect),
        "label_rect": list(label_rect),
        "row_rect": list(row_rect),
        "bar_corners": _corner_report(image, bar_rect, "chunk", palette, dpr),
        "label_corners": _corner_report(image, label_rect, "bar_background", palette, dpr),
        "row_corners": _corner_report(image, row_rect, "bar_background", palette, dpr),
        "right_edge": _visible_right_edge(image, bar_rect, split_x, palette, dpr),
    }


def _crop(image, rect, pad: int, dpr: float):
    def scale(value: int) -> int:
        return round(value * dpr)

    left = max(0, scale(rect[0]) - pad)
    top = max(0, scale(rect[1]) - pad)
    right = min(image.width(), scale(rect[2] + 1) + pad)
    bottom = min(image.height(), scale(rect[3] + 1) + pad)
    return image.copy(left, top, right - left, bottom - top)


def _plate_host():
    """A host that paints the two-colour plate behind the row, so a round corner is readable.

    The plate is painted by the widget itself rather than by a painter opened around a ``render()``
    call: a stylesheet-backed top-level window paints its own background over anything already on the
    pixmap, which silently replaced the plate in the first version of this tool - a painted magenta
    plate came back as the page colour, and every corner then read as "the control's own paint".
    """
    from PySide6.QtGui import QColor, QPainter
    from PySide6.QtWidgets import QWidget

    class PlateHost(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._split = 0

        def set_split(self, x: int) -> None:
            self._split = x
            self.update()

        def paintEvent(self, event) -> None:
            painter = QPainter(self)
            try:
                painter.fillRect(0, 0, self._split, self.height(), QColor(*PLATE_LEFT))
                painter.fillRect(
                    self._split, 0, self.width() - self._split, self.height(), QColor(*PLATE_RIGHT)
                )
            finally:
                painter.end()
            super().paintEvent(event)

    return PlateHost()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out", required=True, help="directory for the PNGs and the JSON verdict")
    parser.add_argument("--themes", default="dark,light")
    parser.add_argument(
        "--values",
        default=",".join(str(value) for value in PROGRESS_VALUES),
        help="bar values in 0-1000, comma separated",
    )
    parser.add_argument(
        "--variant",
        default="",
        help="label for a stylesheet variant to measure instead of the shipped one",
    )
    parser.add_argument(
        "--bar-width",
        type=int,
        default=452,
        help="the bar's pixel width; the shipped one is 452 at 1000x610 (measured from the pages)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.chdir(root)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    data = out / "_data"
    (data / "game").mkdir(parents=True, exist_ok=True)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data)
    os.environ["MINECRAFT_GAME_DIR"] = str(data / "game")

    from PySide6.QtCore import QEvent, QObject, Qt
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from gui import theme as theme_module
    from gui.widgets import build_download_progress

    # The row pictures this tool writes are evidence too, so they carry no focus ring (the shared rule
    # lives in tools/shot_pages.py, the same pair the README renderer uses).
    from tools import shot_pages

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

    # The constructive guarantee: nothing in this process may reach a desktop. `build_download_progress`
    # and the plate host are marked before show(), but a widget this tool has not marked - one the
    # launcher builds itself, say - would be mapped by show(). This refuses that instead of hoping it
    # does not happen.
    #
    # It records the violation and aborts at the next checkpoint rather than raising from the filter:
    # measured, a Python exception raised inside a Qt event filter does NOT travel out of show() - Qt
    # reports "Error calling Python override" and carries on dispatching, and the exception is re-entered
    # by every later event (a cascade that buries the real message). Detection is immediate; the abort is
    # a plain raise on the checkpoint, where it is ours to make.
    class _NoWindowMayReachTheDesktop(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.violation = ""

        def eventFilter(self, obj, event):
            if (
                not self.violation
                and event.type() is QEvent.Type.Show
                and isinstance(obj, QWidget)
                and obj.isWindow()
                and not obj.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
            ):
                self.violation = (
                    f"{type(obj).__name__}(objectName={obj.objectName()!r}, "
                    f"title={obj.windowTitle()!r}) was shown without WA_DontShowOnScreen"
                )
            return False

    # Held on the application so it is not collected while it is installed.
    guard = _NoWindowMayReachTheDesktop()
    app._no_window_guard = guard
    app.installEventFilter(guard)

    def settle(times: int) -> None:
        """Pump the event loop, then refuse to continue if a window reached the desktop."""
        for _ in range(times):
            app.processEvents()
        if guard.violation:
            raise RuntimeError(
                f"{guard.violation}: this tool may never put a window on a desktop, and it must not "
                f"measure one either. Mark the widget before show()."
            )

    already_visible = [w for w in app.topLevelWidgets() if w.isVisible()]
    if already_visible:
        print(
            f"refusing to run: the launcher already has visible top-level window(s) "
            f"{[type(w).__name__ for w in already_visible]} - this tool may not run next to a real window",
            file=sys.stderr,
        )
        return 2

    values = [int(value) for value in args.values.split(",") if value]
    report = {
        "platform": platform,
        "qt": __import__("PySide6").__version__,
        "screen_dpr": app.primaryScreen().devicePixelRatio(),
        "plate": {"left": list(PLATE_LEFT), "right": list(PLATE_RIGHT)},
        "variant": args.variant,
        "rows": [],
    }
    for theme_name in args.themes.split(","):
        theme_module.apply_theme(theme_name, None, None, "default")
        tokens = theme_module.theme_palette(theme_name)
        host = _plate_host()
        row, bar, label = build_download_progress("downloadProgress")
        bar.setRange(0, 1000)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(row)
        host.resize(520, 56)
        # show() is required - without it the HBox inside the row never lays the bar out and the grab
        # comes back empty - so both top-level widgets are marked WA_DontShowOnScreen first, which is what
        # makes show() lay out and style them without mapping a window. See the module docstring.
        host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        row.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        host.show()
        row.show()
        settle(6)

        # Every rect is a host coordinate: a widget's x()/y() are relative to its own parent, so the
        # bar's inset inside the row has to be added to the row's own offset.
        base_x, base_y = row.x() + bar.x(), row.y() + bar.y()
        bar_rect = (base_x, base_y, base_x + bar.width() - 1, base_y + bar.height() - 1)
        row_rect = (row.x(), row.y(), row.x() + row.width() - 1, row.y() + row.height() - 1)
        label_rect = (
            row.x() + label.x(),
            row.y() + label.y(),
            row.x() + label.x() + label.width() - 1,
            row.y() + label.y() + label.height() - 1,
        )

        # The plate splits at the bar's midpoint, which is known once the layout has run. It has to be
        # in place before a grab, or the plate in the image is split where the previous state left it.
        split_x = round((bar_rect[0] + bar_rect[2]) / 2)
        host.set_split(split_x)
        settle(4)

        for value in values:
            bar.setValue(value)
            settle(6)
            shot_pages.defocus_for_shot(host, row)
            shot_pages.assert_no_focus_mark(host, row)
            image = host.grab().toImage()
            dpr = image.devicePixelRatio() or 1.0

            entry = _analyse(image, bar_rect, label_rect, row_rect, tokens, dpr, split_x)
            tag = f"{args.variant + '_' if args.variant else ''}{theme_name}_{value:04d}"
            image.save(str(out / f"row_{tag}.png"))
            _crop(image, row_rect, 4, dpr).save(str(out / f"corners_{tag}.png"))
            _crop(image, (label_rect[0] - 18, bar_rect[1], label_rect[2], bar_rect[3]), 6, dpr).save(
                str(out / f"rightend_{tag}.png")
            )
            _crop(image, (bar_rect[0], bar_rect[1], bar_rect[0] + 24, bar_rect[3]), 6, dpr).save(
                str(out / f"leftend_{tag}.png")
            )
            entry.update(
                theme=theme_name,
                value=value,
                percent=round(value / 10),
                variant=args.variant,
                bar_px=[bar.width(), bar.height()],
                label_px=[label.width(), label.height()],
                gap_between_bar_and_label=label.x() - (bar.x() + bar.width()),
                tokens_used={key: tokens[key] for key in ("ACCENT", "BG_LIST", "BORDER_LIST")},
                shot=f"row_{tag}.png",
                crop=f"corners_{tag}.png",
                crop_left_end=f"leftend_{tag}.png",
                crop_right_end=f"rightend_{tag}.png",
            )
            report["rows"].append(entry)
            left = " ".join(f"{name}:{entry['bar_corners'][name]['verdict']}" for name in ("TL", "BL"))
            right = " ".join(
                f"{name}:{entry['label_corners'][name]['verdict']}" for name in ("TR", "BR")
            )
            edge = entry["right_edge"]
            print(
                f"{theme_name:5} {value:4}/1000  left(bar) {left}  right(label) {right}  "
                f"chunk_right_x={edge['chunk_right_x']} rows_at_that_column="
                f"{len(edge['chunk_present_rows_at_that_column'])}/{bar.height()}"
            )

        host.hide()
        host.deleteLater()
        settle(4)

    name = f"progress_corners{'_' + args.variant if args.variant else ''}.json"
    (out / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("report:", out / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
