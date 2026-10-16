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

"""The download progress bar must be the same shape at every value, in both themes.

The user report was "the download progress bar is sometimes square, sometimes round". The cause was not
a corner radius chosen badly but *two* of them: the frame carried ``border-radius: RADIUS_LG`` on its
left, and the accent ``::chunk`` carried ``border-radius: 7px`` of its own. A chunk is a rectangle whose
width is the value, so an independent radius on it lines up with the frame only by accident, and it
stopped lining up at both ends - measured on the real platform with tools/measure_progress_corners.py,
and independently re-measured with a hidden-host harness that reads the fill's bounding box:

  * left end: the chunk's own curve sits inside the frame's, so the fill's left edge is not straight. At
    500/1000 the first fill pixel is at offset 1 on the middle rows and at offset 6 on the top row - and
    the profile is the *same* at 1000/1000, so this end never settles into one shape while a download
    runs. (An earlier version of this docstring claimed the crescent is gone at 100% because the fill's
    rounded corner is 0.45px wide there. Measurement does not support that: the left-edge profile is
    identical at 50/1000 and 1000/1000, and the profile is the same on the offscreen platform.)
  * right end: the fill finishes in a bevel instead of a straight edge, so the fill's right edge changes
    shape with the value - at 1000/1000 the outermost measured row puts it at offset 449 against 451 in
    the middle, a 5px spread across the rows at every non-trivial value.

The fix drops the chunk's radius: the frame is the only thing that draws a corner now, and the fill is a
straight edge inside it. These tests pin that down on the pixels, at ten values, in both themes:

  * the control's four outer corners are the same verdict at every value;
  * the fill's right edge is one column at every row - a straight edge, not a bevel.

Both hold for the shipped sheet. Restoring ``border-radius: 7px`` on the chunk turns the second one red
from 50/1000 (measured on the offscreen platform; at 5/1000 the fill is 3px wide and the radius is clipped
away, so that value cannot see it) together with the stylesheet read below. The first one stays green
either way, and that is worth knowing rather than assuming: the control's outer corners belong to the
frame on the left and to the label on the right, so the chunk's radius never reached them. The corner
verdicts are a regression guard for the control's outline, not the gate for this defect - the fill's
geometry is, and that is what the other two tests read.

tools/measure_progress_corners.py measures the same thing on the real platform and writes screenshots;
this file is the part that runs anywhere, offscreen, in a couple of seconds.
"""

from __future__ import annotations

import pytest

from gui import theme

# Ten values for the corner read. 0 and 1 are where a rounded chunk is invisible rather than absent,
# 950-1000 is where the old bevel reshaped the right end, and the rest are the ordinary middle.
VALUES = (0, 1, 5, 50, 250, 500, 750, 950, 990, 1000)

# The same sweep minus 1/1000 for the fill's edge read: at that value the fill is 0.45px wide and the
# renderer resolves it to nothing at all (measured: no accent pixel in any row), which is a property of
# a sub-pixel fill rather than a shape. The corner read above still covers it.
FILL_VALUES = (0, 5, 50, 250, 500, 750, 950, 990, 1000)

# The plate the row is grabbed on: two flat colours split at the bar's midpoint, so "the corner pixel is
# the colour behind the control" is read rather than assumed. Neither is a colour the theme uses.
PLATE_LEFT = (255, 0, 255)
PLATE_RIGHT = (0, 255, 0)

TOLERANCE = 30


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _near(a, b, tolerance: int = TOLERANCE) -> bool:
    return sum(abs(p - q) for p, q in zip(a, b)) <= tolerance


class _PlateHost:
    """A host that paints the plate behind the row, so a baked-in corner shows as plate vs paint.

    Made here rather than at module level so this file still imports no Qt until a test needs it.
    """

    def __new__(cls):
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


class _Row:
    """A shown download row on the plate, with every rect the tests need in host coordinates."""

    def __init__(self, app, theme_name: str) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QVBoxLayout

        from gui.widgets import build_download_progress

        theme._last_applied = None
        theme.apply_theme(theme_name, None, None, "default")
        self.tokens = theme.theme_palette(theme_name)
        self.theme = theme_name
        self.app = app

        self.host = _PlateHost()
        self.host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.row, self.bar, self.label = build_download_progress("downloadProgress")
        self.bar.setRange(0, 1000)
        layout = QVBoxLayout(self.host)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.row)
        self.host.resize(520, 56)
        self.host.show()
        self.row.setVisible(True)
        self._settle(8)

        base_x, base_y = self.row.x() + self.bar.x(), self.row.y() + self.bar.y()
        self.bar_rect = [
            base_x,
            base_y,
            base_x + self.bar.width() - 1,
            base_y + self.bar.height() - 1,
        ]
        self.row_rect = [
            self.row.x(),
            self.row.y(),
            self.row.x() + self.row.width() - 1,
            self.row.y() + self.row.height() - 1,
        ]
        self.label_rect = [
            self.row.x() + self.label.x(),
            self.row.y() + self.label.y(),
            self.row.x() + self.label.x() + self.label.width() - 1,
            self.row.y() + self.label.y() + self.label.height() - 1,
        ]
        self.host.set_split((self.bar_rect[0] + self.bar_rect[2]) // 2)
        self._settle(4)

    def _settle(self, times: int) -> None:
        for _ in range(times):
            self.app.processEvents()

    def at(self, value: int):
        """The row's render at one value, as an (x, y) -> rgb reader in host coordinates."""
        self.bar.setValue(value)
        self._settle(6)
        image = self.host.grab().toImage()
        dpr = image.devicePixelRatio() or 1.0
        assert dpr == 1.0, (
            f"device pixel ratio {dpr}: this test reads one pixel per logical pixel, which only holds "
            f"at 1.0 (the offscreen platform). tools/measure_progress_corners.py handles a scaled screen"
        )

        def pixel(x: int, y: int):
            color = image.pixelColor(x, y)
            return (color.red(), color.green(), color.blue())

        return pixel

    def close(self) -> None:
        self.host.hide()
        self.host.deleteLater()
        self._settle(4)


@pytest.fixture()
def app():
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def rows(app):
    """Both themes, built and torn down by the conftest settle fixture."""
    made = []
    try:
        for name in ("dark", "light"):
            made.append(_Row(app, name))
        yield made
    finally:
        for row in made:
            row.close()


def _plate_for(row: _Row, x: int):
    return PLATE_LEFT if x < (row.bar_rect[0] + row.bar_rect[2]) // 2 else PLATE_RIGHT


def _verdict(row: _Row, rgb) -> str:
    """round: the plate shows through. square: the control's own paint does. A third colour is odd.

    The three tokens are matched at a tighter tolerance than the plate is. ``BG_LIST`` and
    ``BORDER_LIST`` are one step apart in both themes, so at the plate's tolerance a border pixel would
    read as the fill and a wrong one as the border - and a corner that is *not* the plate would then be
    reported as odd rather than as the square corner it is.
    """
    accent = _rgb(row.tokens["ACCENT"])
    label_fill = _rgb(row.tokens["BG_LIST"])
    border = _rgb(row.tokens["BORDER_LIST"])
    if any(_near(rgb, colour, 12) for colour in (accent, label_fill, border)):
        return "square"
    if _near(rgb, PLATE_LEFT) or _near(rgb, PLATE_RIGHT):
        return "round"
    return "odd"


@pytest.mark.parametrize("value", VALUES)
def test_the_control_keeps_the_same_corners_at_every_value(rows, value):
    """The control's four outer corners must read the same at every value, in both themes.

    This is the user's report as a test. The control is the bar plus the label flush against its right
    edge, so its left corners are the bar's and its right corners are the label's. On the old stylesheet
    the fill covered the bar's left corner from the first non-zero value on, so the verdict at the very
    same patch of screen went plate -> paint -> plate again as the download ran.

    Read that way it is a guard on the control's *outline*, and it is worth being explicit that it is not
    the gate for this defect: these four patches sit on the frame's radius and on the label's, so the
    chunk's own radius never reached them and this test stayed green on the old stylesheet at every value
    (measured). The fill's edges are what the chunk's radius moved, and the two tests below read those.
    """
    for row in rows:
        pixel = row.at(value)
        corners = {
            "left_top": (row.bar_rect[0], row.bar_rect[1]),
            "left_bottom": (row.bar_rect[0], row.bar_rect[3]),
            "right_top": (row.label_rect[2], row.label_rect[1]),
            "right_bottom": (row.label_rect[2], row.label_rect[3]),
        }
        verdicts = {name: _verdict(row, pixel(x, y)) for name, (x, y) in corners.items()}
        assert set(verdicts.values()) == {"round"}, (
            f"{row.theme} at {value}/1000: the control's corners are {verdicts}, not all round - "
            f"something is painting into a corner that should be the background"
        )


@pytest.mark.parametrize("theme_name", ("dark", "light"))
def test_the_fill_has_a_straight_edge_at_every_value(app, theme_name):
    """The accent fill's right edge is one column wide at every row, from 1% to 100%.

    A rounded chunk finishes in a bevel: its rightmost accent pixel walks left as the row approaches the
    bar's top and bottom edge. Measured on the real platform before the fix, that walk spanned five
    columns (at 1000/1000 the outermost measured row puts the edge at offset 449 against 451 in the
    middle), so the fill's right edge changes shape with the value. Rows where the percentage text covers
    the fill are skipped: the text is a different colour, so the fill's edge is not readable there.
    """
    from gui.widgets import PROGRESS_TEXT_MIN_WIDTH

    assert PROGRESS_TEXT_MIN_WIDTH > 0  # the label is what keeps the text off the fill
    row = _Row(app, theme_name)
    try:
        for value in FILL_VALUES:
            pixel = row.at(value)
            edge_per_row = []
            for y in range(row.bar_rect[1], row.bar_rect[3] + 1):
                edge = None
                for x in range(row.bar_rect[0], row.label_rect[0]):
                    if _near(pixel(x, y), _rgb(row.tokens["ACCENT"])):
                        edge = x
                if edge is not None:  # rows the percentage text crosses are not readable
                    edge_per_row.append(edge)

            if value == 0:
                assert not edge_per_row, (
                    f"{theme_name} at 0/1000: {len(edge_per_row)} row(s) already show accent, "
                    f"the fill should be empty"
                )
                continue
            assert edge_per_row, f"{theme_name} at {value}/1000: the bar drew no fill at all"
            spread = max(edge_per_row) - min(edge_per_row)
            assert spread == 0, (
                f"{theme_name} at {value}/1000: the fill's right edge is not straight - the rows put it "
                f"at columns {sorted(set(edge_per_row))} (a {spread}px spread), which is a bevel: the "
                f"chunk still has a radius of its own"
            )
    finally:
        row.close()


@pytest.mark.parametrize("theme_name", ("dark", "light"))
def test_the_frame_not_the_fill_draws_the_control_s_corners(theme_name):
    """One corner radius, and it belongs to the frame; the fill is a plain rectangle.

    Read from the sheet rather than the pixels so a re-introduced radius fails here even at a value
    where it happens to be invisible - at 0/1000 and at 1000/1000 a 7px chunk radius leaves the corners
    looking exactly like this. This is the assertion that would have caught the defect.
    """
    from launcher import paths

    filename = "style_light.qss" if theme_name == "light" else "style.qss"
    sheet = paths.resource_path(f"gui/resources/{filename}").read_text(encoding="utf-8")
    marker = "QProgressBar::chunk"
    start = sheet.find(marker)
    assert start != -1, f"{theme_name}: the stylesheet has no {marker} rule at all"
    chunk = sheet[start : sheet.find("}", start)]
    assert "border-radius" not in chunk, (
        f"{theme_name}: the chunk carries a radius of its own again ({chunk.strip()!r}). The frame's "
        f"radius is the control's radius; a second one on a rectangle whose width is the value cannot "
        f"stay aligned with it, which is the defect these tests exist for"
    )
    bar_start = sheet.find("QProgressBar {")
    assert bar_start != -1, f"{theme_name}: the stylesheet has no QProgressBar rule"
    bar = sheet[bar_start : sheet.find("}", bar_start)]
    assert "border-top-left-radius" in bar and "border-top-right-radius: 0px" in bar, (
        f"{theme_name}: the frame's outline changed - the left corners are its radius and the right end "
        f"is flat so the label continues it ({bar.strip()!r})"
    )
