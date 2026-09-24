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

"""Overlay behaviour: cover the window, blur by snapshot, Esc closes, backdrop does not."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from gui.overlay import BLUR_DOWNSCALE, BlurOverlay


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _window(app, width: int = 640, height: int = 420) -> QWidget:
    parent = QWidget()
    parent.resize(width, height)
    parent.show()
    app.processEvents()
    return parent


def test_overlay_covers_the_window_and_esc_closes(app):
    parent = _window(app)
    overlay = None
    try:
        overlay = BlurOverlay(parent)
        overlay.content_layout.addWidget(QLabel("诊断"))
        overlay.show_overlay()
        app.processEvents()
        assert overlay.isVisible()
        assert overlay.geometry() == parent.rect()  # covers the whole window, card included
        QTest.keyClick(overlay, Qt.Key.Key_Escape)
        assert not overlay.isVisible()
    finally:
        if overlay is not None:
            overlay.hide_overlay()
        parent.close()


def test_backdrop_is_a_downscaled_snapshot(app):
    parent = _window(app)
    overlay = None
    try:
        overlay = BlurOverlay(parent)
        overlay.show_overlay()
        app.processEvents()
        snapshot = overlay.snapshot
        assert snapshot is not None
        # grab() returns device pixels (this display runs at 1.5x), so compare the
        # device-independent size instead of the raw pixmap width.
        size = snapshot.deviceIndependentSize()
        assert round(size.width()) == parent.width() // BLUR_DOWNSCALE
        assert round(size.height()) == parent.height() // BLUR_DOWNSCALE
    finally:
        if overlay is not None:
            overlay.hide_overlay()
        parent.close()


def test_blur_disabled_degrades_to_a_plain_scrim(app):
    """With the blur switched off the overlay must still open, just without a snapshot."""
    parent = _window(app)
    overlay = None
    try:
        overlay = BlurOverlay(parent, blur=False)
        overlay.show_overlay()
        app.processEvents()
        assert overlay.isVisible()
        assert overlay.snapshot is None
    finally:
        if overlay is not None:
            overlay.hide_overlay()
        parent.close()


def test_clicking_the_backdrop_does_not_dismiss(app):
    parent = _window(app)
    overlay = None
    try:
        overlay = BlurOverlay(parent)
        overlay.show_overlay()
        app.processEvents()
        QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
        app.processEvents()
        assert overlay.isVisible()  # a stray click must not close a diagnosis
    finally:
        if overlay is not None:
            overlay.hide_overlay()
        parent.close()


def test_card_is_centred_with_a_fixed_width(app):
    parent = _window(app)
    overlay = None
    try:
        overlay = BlurOverlay(parent, card_width=460)
        overlay.content_layout.addWidget(QLabel("内容"))
        overlay.show_overlay()
        app.processEvents()
        card = overlay.findChild(QWidget, "overlayCard")
        assert card is not None
        assert card.width() == 460
        assert abs(card.x() - (parent.width() - 460) // 2) <= 2
        assert card.y() > 0
    finally:
        if overlay is not None:
            overlay.hide_overlay()
        parent.close()


def test_resize_keeps_the_overlay_glued_to_the_window(app):
    parent = _window(app)
    overlay = None
    try:
        overlay = BlurOverlay(parent)
        overlay.show_overlay()
        app.processEvents()
        parent.resize(800, 500)
        app.processEvents()
        assert overlay.geometry() == parent.rect()
    finally:
        if overlay is not None:
            overlay.hide_overlay()
        parent.close()
