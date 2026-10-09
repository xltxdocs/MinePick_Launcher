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

"""Motion: timing invariants, reduced-motion degradation, and a clean exit.

"Looks fine" is not a test. These assertions encode the rules the UI guideline states as numbers -
interactive animations stay under 200ms, entries come from Out* curves, the fade never finishes before
the movement does - and they check that honouring reduced motion really drops movement while keeping
the transparency feedback, instead of quietly disabling feedback altogether.
"""

from __future__ import annotations

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget

from gui import motion
from gui.overlay import EXIT_MS, FADE_MS, SLIDE_MS, BlurOverlay


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def window(app):
    parent = QWidget()
    parent.resize(640, 420)
    parent.show()
    app.processEvents()
    yield parent
    parent.close()
    parent.deleteLater()
    app.processEvents()


@pytest.fixture(autouse=True)
def _no_motion_override_leaks():
    motion.set_override_for_tests(None)
    yield
    motion.set_override_for_tests(None)


def _settle(app, milliseconds: int) -> None:
    QTest.qWait(milliseconds)
    app.processEvents()


def test_timings_respect_the_interactive_ceiling():
    assert FADE_MS <= 200
    assert SLIDE_MS <= 200
    assert EXIT_MS <= 200
    # R-QT-5: the movement lands first. If the fade were the shorter one, the card would read as
    # "already solid but still drifting".
    assert SLIDE_MS <= FADE_MS
    # Exits must be quicker than entrances.
    assert EXIT_MS < FADE_MS


def test_entry_starts_near_opaque_and_lands_on_target(app, window):
    motion.set_override_for_tests(True)
    overlay = BlurOverlay(window)
    overlay.show_overlay()

    card = overlay._card
    target = overlay._card_rect()
    effect = card.graphicsEffect()

    # R-QT-6: an element fades in from near-opaque, not from nothing.
    assert isinstance(effect, QGraphicsOpacityEffect)
    assert effect.opacity() == pytest.approx(0.9, abs=0.06)
    # The slide starts above its resting place...
    assert card.pos() != target.topLeft()

    _settle(app, FADE_MS + 150)
    # ...and ends exactly there, with the effect detached (R-QT-1).
    assert card.pos() == target.topLeft()
    assert card.graphicsEffect() is None
    assert overlay.isVisible()

    overlay.hide_overlay()
    _settle(app, EXIT_MS + 150)
    assert not overlay.isVisible()
    overlay.deleteLater()


def test_reduced_motion_drops_the_movement_but_keeps_the_fade(app, window):
    motion.set_override_for_tests(False)
    overlay = BlurOverlay(window)
    overlay.show_overlay()

    card = overlay._card
    # No slide at all: the card is already where it belongs...
    assert card.pos() == overlay._card_rect().topLeft()
    # ...while the fade still runs, so the state change stays legible (guideline §5.2).
    effect = card.graphicsEffect()
    assert isinstance(effect, QGraphicsOpacityEffect)
    assert effect.opacity() < 1.0

    _settle(app, FADE_MS + 150)
    assert card.graphicsEffect() is None
    overlay.hide_overlay()
    _settle(app, EXIT_MS + 150)
    overlay.deleteLater()


def test_reduced_motion_never_produces_an_intermediate_position(app, window):
    """Regression guard: with motion off there is no frame in which the card has moved."""
    motion.set_override_for_tests(False)
    overlay = BlurOverlay(window)
    overlay.show_overlay()

    positions = set()
    for _ in range(6):
        card = overlay._card
        positions.add((card.x(), card.y()))
        QTest.qWait(30)
        app.processEvents()

    assert len(positions) == 1, f"the card moved despite reduced motion: {positions}"
    overlay.hide_overlay()
    _settle(app, EXIT_MS + 150)
    overlay.deleteLater()


def test_show_and_hide_repeat_without_residue(app, window):
    overlay = BlurOverlay(window)
    for _ in range(3):
        overlay.show_overlay()
        _settle(app, FADE_MS + 150)
        assert overlay.isVisible()
        overlay.hide_overlay()
        _settle(app, EXIT_MS + 150)
        assert not overlay.isVisible()
        # A leftover opacity effect would slow every later repaint of the card's subtree.
        assert overlay._card.graphicsEffect() is None
    overlay.deleteLater()
