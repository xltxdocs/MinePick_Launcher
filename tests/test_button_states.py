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

"""The ring a filled button shows for keyboard focus, and the ring a dialog's default button shows.

T-0004 measured the old focus cue on an accent-filled button as `#2D8659 -> #287950`, i.e. 1.18:1:
a colour change the eye cannot resolve, which is not a focus indicator (WCAG 1.4.11 asks for 3:1).
These tests pin the two properties the fix rests on, because both are easy to lose in a later edit:

* the ring is at least MIN_RING_PX of a colour that clears 3:1 against what it is drawn on (the sheet
  draws 4px - the placeholder is 4px because the padding compensation has to stay on the spacing
  ladder, see the button rule in either sheet);
* the ring costs the unfocused button nothing - no size hint change, no layout shift, no repainted
  pixel. That last one cannot be asserted from inside one build (both versions would have to exist at
  once), so `tools/button_state_hashes.py` produces the before/after digest report instead; what is
  asserted here is its precondition - the border that the ring colours is present and transparent at
  rest, which is what makes the two states differ by colour alone and nothing else.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QWidget

from gui import theme

# The ring must be at least this wide to read as a ring rather than as an edge artefact.
MIN_RING_PX = 2
# WCAG 1.4.11 non-text contrast, the target T-0004's finding was measured against.
MIN_RING_CONTRAST = 3.0


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    yield application


@pytest.fixture()
def host(app):
    """Offscreen host with an opaque themed background, so a transparent border shows real pixels."""
    widget = QWidget()
    widget.resize(360, 240)
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    yield widget
    widget.hide()
    widget.deleteLater()
    QApplication.processEvents()


def _polish(widget: QWidget) -> None:
    """Re-evaluate the stylesheet after a state change; Qt otherwise reuses the computed style."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
    QApplication.processEvents()


def _grab(widget: QWidget) -> QImage:
    return widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def _edge_run(image: QImage, colour: str) -> int:
    """How many pixels of `colour` run inward from the left edge, on the middle row."""
    middle = image.height() // 2
    run = 0
    for x in range(image.width()):
        if image.pixelColor(x, middle).name().lower() != colour.lower():
            break
        run += 1
    return run


@pytest.mark.parametrize("mode", ("dark", "light"))
def test_a_focused_filled_button_draws_a_visible_ring(app, host, mode):
    """A focused primary button must show a ring of MIN_RING_PX in a colour that clears 3:1.

    The contrast is checked against the colour the ring actually adjoins - the fill it encloses - not
    against an abstract background token, because that is the pixel pair a user's eye resolves.
    """
    theme.apply_theme(mode, None, None, "default")
    tokens = theme.current_tokens()
    ring = tokens["FG_SELECTED"]

    button = QPushButton("Primary", host)
    button.move(10, 10)
    _polish(button)
    unfocused = _grab(button)

    button.setProperty("keyboardFocus", True)
    _polish(button)
    focused = _grab(button)

    assert focused.size() == unfocused.size(), (
        "focusing the button resized it; the ring must be paid for by the border that is already there"
    )
    assert bytes(focused.constBits()) != bytes(unfocused.constBits()), (
        "a focused filled button is pixel-identical to an unfocused one"
    )

    measured = _edge_run(focused, ring)
    assert measured >= MIN_RING_PX, (
        f"the focus ring is {measured}px of {ring}, not the {MIN_RING_PX}px the task asks for"
    )
    ratio = theme.contrast_ratio(ring, tokens["ACCENT_BUTTON"])
    assert ratio >= MIN_RING_CONTRAST, (
        f"the ring colour {ring} measures {ratio:.2f}:1 against the fill {tokens['ACCENT_BUTTON']}"
    )

    # The unfocused button keeps the transparent placeholder: the ring's whole cost is the border it
    # recolours, which must exist before it is coloured or the button would grow on focus.
    button.setProperty("keyboardFocus", False)
    _polish(button)
    rest = _grab(button)
    assert bytes(rest.constBits()) == bytes(unfocused.constBits()), (
        "clearing keyboardFocus did not restore the unfocused rendering"
    )
    assert _edge_run(rest, ring) == 0, "the unfocused button already shows the ring colour"


@pytest.mark.parametrize("mode", ("dark", "light"))
def test_the_old_focus_cue_alone_would_have_been_too_weak(app, mode):
    """The measurement the fix is based on, kept as a test so the numbers cannot quietly change.

    `ACCENT_HOVER` - the only thing a focused button used to change - has to stay below the non-text
    contrast target, and the ring colour has to stay above it. If a later theme edit makes the old cue
    strong enough, this test fails and the ring is no longer load-bearing; if it makes the ring weak,
    it fails before a user finds out.
    """
    theme.apply_theme(mode, None, None, "default")
    tokens = theme.current_tokens()
    old_cue = theme.contrast_ratio(tokens["ACCENT_HOVER"], tokens["ACCENT_BUTTON"])
    ring = theme.contrast_ratio(tokens["FG_SELECTED"], tokens["ACCENT_BUTTON"])
    assert old_cue < MIN_RING_CONTRAST, (
        f"the old cue already measures {old_cue:.2f}:1 - re-check whether the ring is still needed"
    )
    assert ring >= MIN_RING_CONTRAST


@pytest.mark.parametrize("mode", ("dark", "light"))
def test_the_ring_survives_every_accent_preset(app, mode):
    """A custom accent re-tints the fill, so the ring must clear 3:1 for all of them, not just the default.

    This is the property that makes `FG_SELECTED` the right token: the fill is `readable_fill(accent)`,
    i.e. the shade picked so this foreground is readable on it, so the guarantee holds by construction
    rather than by a table of exceptions.
    """
    from gui.pages.settings_page import ACCENT_PRESETS

    worst = None
    for accent in (theme.DEFAULT_ACCENTS[mode], *ACCENT_PRESETS):
        palette = theme.theme_palette(mode, accent)
        ratio = theme.contrast_ratio(palette["FG_SELECTED"], palette["ACCENT_BUTTON"])
        if worst is None or ratio < worst[0]:
            worst = (ratio, accent)
    assert worst is not None
    assert worst[0] >= MIN_RING_CONTRAST, f"accent {worst[1]} drops the ring to {worst[0]:.2f}:1"


@pytest.mark.parametrize("mode", ("dark", "light"))
def test_a_dialogs_default_button_is_marked_and_visibly_different(app, host, mode):
    """The quit confirmation's default button must not be pixel-identical to its sibling.

    T-0004 E8 step 3 measured exactly that: two buttons, no pixel between them, so nothing told the
    user which one Enter would activate. The marker is an explicit property because `QPushButton:default`
    does not identify this button in this build - measured, it matched the *non-default* one.
    """
    theme.apply_theme(mode, None, None, "default")
    ring = theme.current_tokens()["FG_SELECTED"]

    box = QMessageBox(host)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("仍有 1 个下载任务正在进行，确定要退出吗？")
    cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    confirm = box.addButton("退出", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(cancel)
    box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    box.show()
    _polish(cancel)
    _polish(confirm)

    before_cancel = _grab(cancel)
    before_confirm = _grab(confirm)
    assert bytes(before_cancel.constBits()) == bytes(before_confirm.constBits()), (
        "the probe is wrong: the dialog's two buttons were already visually different without a marker"
    )

    # What gui/main_window.py does for its default button.
    cancel.setProperty("defaultChoice", True)
    _polish(cancel)
    _polish(confirm)
    after_cancel = _grab(cancel)
    after_confirm = _grab(confirm)

    assert bytes(after_cancel.constBits()) != bytes(after_confirm.constBits()), (
        "the default button still looks exactly like the other one"
    )
    assert after_cancel.size() == before_cancel.size(), "marking the default button resized it"
    assert _edge_run(after_cancel, ring) >= MIN_RING_PX, "the default button's ring is not visible"
    # The other button must be untouched by the marker's rule.
    assert bytes(after_confirm.constBits()) == bytes(before_confirm.constBits()), (
        "the non-default button changed when its sibling was marked"
    )
    box.hide()
    box.deleteLater()
    QApplication.processEvents()


def test_a_disabled_button_drops_both_rings(app, host):
    """A dead button must not advertise itself as the default choice, nor as the focused one."""
    theme.apply_theme("dark", None, None, "default")
    ring = theme.current_tokens()["FG_SELECTED"]
    button = QPushButton("Disabled", host)
    button.move(10, 10)
    button.setProperty("defaultChoice", True)
    button.setProperty("keyboardFocus", True)
    button.setEnabled(False)
    _polish(button)
    assert _edge_run(_grab(button), ring) == 0, "a disabled button painted a live focus/default ring"


def test_the_marker_is_not_a_colour_literal(app, host):
    """The ring's colour must come from the token table, not from a hex string in the widget code."""
    import inspect
    import re

    from gui import main_window

    source = inspect.getsource(main_window.MainWindow._confirm_quit_while_downloading)
    assert 'setProperty("defaultChoice", True)' in source
    # Only comment lines may contain a '#'; any hex literal in the code itself would be a colour the
    # theme cannot re-tint.
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", code), (
        "the dialog appears to hardcode a colour; the ring belongs to the stylesheet"
    )
