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

"""Icon-only buttons must actually draw something: a painter mistake fails silently."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from gui import icons


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_every_glyph_paints_pixels(app):
    for kind in icons.KINDS:
        qicon = icons.icon(kind, 20, color="#ffffff")
        assert not qicon.isNull(), f"{kind}: no icon"
        image = qicon.pixmap(20, 20).toImage()
        painted = sum(
            1
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 0
        )
        assert painted > 12, f"{kind} painted almost nothing ({painted} pixels)"


def test_unknown_kind_returns_a_blank_icon_instead_of_raising(app):
    """Unknown kinds must not raise; they paint nothing (a blank pixmap, not a null icon)."""
    image = icons.icon("does-not-exist", 20, color="#ffffff").pixmap(20, 20).toImage()
    painted = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert painted == 0
