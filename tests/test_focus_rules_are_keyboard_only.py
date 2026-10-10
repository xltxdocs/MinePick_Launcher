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

"""Focus may only be visible when it came from the keyboard.

The launcher's convention (gui.widgets.KeyboardFocusTracker) is that nothing shows a focus indicator
unless the user is navigating by Tab, the arrow keys or assistive technology. A plain ``:focus`` rule
breaks that: with a mouse, clicking a field gives it focus too, so the ring appears for a click that was
never keyboard navigation. These tests pin both halves - the stylesheets may not contain such a rule,
and clicking with the mouse really does not change any pixels.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from gui import theme

REPO = Path(__file__).resolve().parent.parent
SHEETS = (REPO / "gui" / "resources" / "style.qss", REPO / "gui" / "resources" / "style_light.qss")

COMMENTS = re.compile(r"/\*.*?\*/", re.DOTALL)
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)

# Declarations that do not paint a focus indicator. `outline: none` removes the platform's ring; it
# cannot be the reason a user sees one.
NON_VISUAL = re.compile(r"^\s*outline\s*:\s*(none|0(px)?)\s*;?\s*$", re.IGNORECASE)
VISUAL_PROPS = ("border", "background", "color", "outline-color", "outline-width", "outline-style")


def _rules(path: Path):
    """Yield (selectors, declarations) for every rule in a stylesheet."""
    text = COMMENTS.sub(" ", path.read_text(encoding="utf-8"))
    for selectors, body in RULE.findall(text):
        yield [part.strip() for part in selectors.split(",") if part.strip()], body


def _paints_focus(declarations: str) -> bool:
    """True when the declaration block paints something a user can see."""
    for line in declarations.split(";"):
        stripped = line.strip()
        if not stripped:
            continue
        if NON_VISUAL.match(stripped + ";"):
            continue
        if any(stripped.lower().startswith(prop) for prop in VISUAL_PROPS):
            return True
    return False


def _has_unconditional_sibling(selector: str, siblings: list[str]) -> bool:
    """True when the same element is styled identically without focus, so focus cannot look different."""
    stripped = selector.replace(':focus', '')
    for other in siblings:
        if other == selector:
            continue
        if other.replace(':!focus', '') == stripped or other == stripped:
            return True
    return False


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda path: path.name)
def test_no_focus_visual_without_the_keyboard_condition(sheet: Path):
    offenders = []
    for selectors, declarations in _rules(sheet):
        if not _paints_focus(declarations):
            continue
        for selector in selectors:
            if ":focus" not in selector:
                continue
            if "keyboardFocus" in selector:
                continue
            if _has_unconditional_sibling(selector, selectors):
                continue  # same block also styles the unfocused state, so nothing changes
            offenders.append(selector)
    assert not offenders, (
        f"{sheet.name}: these selectors paint a focus indicator for any focus, including a mouse click. "
        f'Gate them on [keyboardFocus="true"] like the rest of the sheet: {offenders}'
    )


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    # create_app() installs exactly this; doing it here keeps the test free of config writes and network
    # stubs, and the stylesheet rule is what is under test.
    from gui.widgets import KeyboardFocusTracker

    application._focus_tracker = KeyboardFocusTracker(application)
    application.installEventFilter(application._focus_tracker)  # create_app() does this too
    yield application


@pytest.fixture()
def line_edit(app):
    """A themed QLineEdit on its own, so a border change is isolated from the rest of the window."""
    widget = QLineEdit()
    widget.setObjectName("focusRuleProbe")
    widget.resize(220, 32)
    theme.apply_theme("light", None, None, "default")
    widget.show()
    QApplication.processEvents()
    yield widget
    widget.hide()
    widget.deleteLater()
    QApplication.processEvents()


def _top_border(widget) -> bytes:
    """The widget's outermost top row - the border. The caret lives further in, so it cannot interfere."""
    image = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    return bytes(image.constBits())[: image.width() * 4]


def test_clicking_with_the_mouse_does_not_paint_focus(app, line_edit):
    before = _top_border(line_edit)
    QTest.mouseClick(line_edit, Qt.MouseButton.LeftButton)
    QApplication.processEvents()

    assert line_edit.hasFocus(), "the click did not even focus the widget - the probe is wrong"
    assert not bool(line_edit.property("keyboardFocus")), "a mouse click marked the widget as keyboard focus"
    assert _top_border(line_edit) == before, "clicking with the mouse painted a focus ring"


def test_keyboard_navigation_still_paints_focus(app, line_edit):
    """The other half of the rule: a keyboard user must still see where they are.

    The tracker is driven with a synthetic key press and a real focus change, in that order, because
    that is the sequence it reacts to - pressing Tab and then focusing the widget. Doing it through the
    tracker rather than through QTest keeps the test about the rule instead of about focus mechanics.
    """
    from PySide6.QtGui import QKeyEvent

    line_edit.clearFocus()
    QApplication.processEvents()
    before = _top_border(line_edit)

    press = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    app._focus_tracker.eventFilter(line_edit, press)
    line_edit.setFocus(Qt.FocusReason.TabFocusReason)
    QApplication.processEvents()

    assert bool(line_edit.property("keyboardFocus")), "keyboard navigation did not mark the widget"
    assert _top_border(line_edit) != before, "keyboard focus is invisible now"
