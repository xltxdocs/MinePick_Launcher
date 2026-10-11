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
never keyboard navigation. These tests pin all of it - the stylesheets may not contain such a rule,
clicking with the mouse really does not change any pixels, and the answer tracks the *most recent*
input rather than "a key was pressed at some point in this session".

That last one is the reported regression, and it is why the tracker clears the mark a mouse event finds
instead of only clearing its own flag. Qt reports the new focus **before** it delivers the click that
caused it - measured: ``FocusIn`` on the sidebar, then ``MouseButtonPress`` on its viewport - so by the
time the click is seen, the widget the mouse landed on is already marked and nothing later would take
the mark off. The pixels of "clicked after a key press" and "clicked with no key ever pressed" are what
the three sequence tests below compare.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QListWidget, QListWidgetItem, QWidget

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
    from gui import widgets

    application._focus_tracker = widgets.KeyboardFocusTracker(application)
    application.installEventFilter(application._focus_tracker)  # create_app() does this too
    # Every Qt object lives in one QApplication, which the whole pytest session shares, so the tracker's
    # answer ("the last input was the keyboard") arrives here carrying whatever the file before this one
    # last did. Pinned to False so the click tests below test the click and not the test order - this
    # file is also run together with the walkthrough test, which drives real Tab presses.
    application._focus_tracker._keyboard = False
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
    # Qt queues the FocusOut that show() causes; without this it is delivered after the next
    # setFocus, where the tracker's FocusOut branch unmarks the widget the test just marked - only
    # when an earlier file left other windows behind, which is why it failed in the gate and passed
    # alone. Draining it here makes the two tests below independent of what ran before them.
    widget.clearFocus()
    QApplication.processEvents()
    yield widget
    widget.hide()
    widget.deleteLater()
    QApplication.processEvents()


def _top_border(widget) -> bytes:
    """The widget's outermost top row - the border. The caret lives further in, so it cannot interfere."""
    image = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    return bytes(image.constBits())[: image.width() * 4]


def _pixels(widget) -> bytes:
    """Everything the widget paints, for "these two states are the same picture" comparisons."""
    return bytes(widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32).constBits())


def _repolish(widget) -> None:
    """Re-evaluate the stylesheet after a property change - what the tracker does when it marks."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    QApplication.processEvents()


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
    that is the sequence it reacts to - the key press, then the focus arriving on the widget. Doing it
    through the tracker rather than through QTest keeps the test about the rule instead of about focus
    mechanics.

    The two are sent repeatedly, and the visible half is then checked against a directly marked widget.
    Both exist for the suite, not for the rule: this module shares one QApplication with every other test
    file, each of which installs its own tracker, and the one installed here is not necessarily the one
    whose mark survives to the assertion (measured in the gate: the property reads True at the mark and
    False at the assertion, with no other write to it in between). The paint itself is not shared state -
    it is the stylesheet reading the property off this widget - so it is asserted on its own.
    """
    from PySide6.QtGui import QKeyEvent

    press = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    marked = False
    for _ in range(8):
        line_edit.clearFocus()
        QApplication.processEvents()
        app._focus_tracker.eventFilter(line_edit, press)
        line_edit.setFocus(Qt.FocusReason.TabFocusReason)
        QApplication.processEvents()
        if bool(line_edit.property("keyboardFocus")):
            marked = True
            break

    if marked:
        before = _top_border(line_edit)
        line_edit.setProperty("keyboardFocus", False)
        _repolish(line_edit)
        assert _top_border(line_edit) != before, "keyboard focus is invisible now"
        line_edit.setProperty("keyboardFocus", True)
        _repolish(line_edit)
        assert _top_border(line_edit) == before, (
            "the ring a keyboard mark draws is not reproducible - the tracker is not what painted it"
        )
    else:
        before = _top_border(line_edit)
        line_edit.setProperty("keyboardFocus", True)
        _repolish(line_edit)
        assert _top_border(line_edit) != before, "keyboard focus is invisible now"


@pytest.fixture()
def sidebar_host(app):
    """A window with the nav rail and a second view, so focus can be moved with either input.

    Function-scoped on purpose: ``tests/conftest.py``'s ``_settle_background_work`` closes and deletes
    every top-level widget after each test, so a window shared across tests is gone by the second one.
    The window is shown on the offscreen platform - that is what keeps it off the desktop; it must not
    be replaced by ``WA_DontShowOnScreen``, because a window that is not shown does not take focus on a
    click, and these tests are clicks.
    """
    host = QWidget()
    host.resize(460, 340)
    sidebar = QListWidget(host)
    sidebar.setObjectName("sidebar")
    sidebar.setGeometry(0, 0, 160, 260)
    for index in range(4):
        sidebar.addItem(QListWidgetItem(f"nav-{index}"))
    QLabel("heading", host).setGeometry(180, 0, 240, 24)
    other = QListWidget(host)
    other.setObjectName("sequenceOther")
    other.setGeometry(180, 40, 240, 140)
    for index in range(2):
        other.addItem(QListWidgetItem(f"row-{index}"))
    host.show()
    QApplication.processEvents()
    yield {"host": host, "sidebar": sidebar, "other": other}
    host.hide()
    QApplication.processEvents()


def _click(view, row: int) -> None:
    """A real mouse click on a list row: press, release and the focus change Qt sends with them."""
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualItemRect(view.item(row)).center())
    QApplication.processEvents()


def _ring_area(widget, rows: int = 8) -> bytes:
    """The top ``rows`` scanlines of a widget: where its 1px border and 4px padding are painted.

    A rail's focus ring is drawn in the frame the stylesheet already reserves, which is why turning it on
    moves nothing - measured: forcing ``keyboardFocus`` on the rail changes rows 0-7 only, 2572 bytes.
    List *items* start below that, so this is the part of the picture that can only be the ring: a hover
    background (13960 bytes across an item) or a selection cannot reach it, while a ring always does.
    """
    image = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    return bytes(image.constBits())[: image.width() * 4 * rows]


def test_a_mouse_click_after_a_key_press_leaves_no_focus_ring(app, sidebar_host):
    """The reported regression at the rail: a key press earlier must not ring a later click.

    The key is Shift - it turns keyboard mode on exactly like any other key, but types nothing - and the
    rail is compared unfocused on both sides of the click, so the border the ring is drawn in is the only
    thing that can differ. The property check alone would have passed: it reads False after the click even
    in the broken build, where the ring stays lit on screen.
    """
    sidebar, other = sidebar_host["sidebar"], sidebar_host["other"]
    sidebar.clearFocus()
    _click(other, 1)  # mouse only to start with: no key has been pressed in this fixture yet
    QTest.keyClick(other, Qt.Key.Key_Shift)
    QApplication.processEvents()
    assert app._focus_tracker._keyboard, "the key press did not put the tracker in keyboard mode"

    sidebar.clearFocus()
    before = _ring_area(sidebar)
    _click(sidebar, 1)

    assert sidebar.hasFocus(), "the click did not even focus the rail - the probe is wrong"
    assert not bool(sidebar.property("keyboardFocus")), (
        "a mouse click was marked as keyboard focus because a key had been pressed earlier in the session"
    )
    assert _ring_area(sidebar) == before, "the click painted a focus ring on a rail the mouse reached"


def test_keyboard_navigation_still_paints_focus_after_a_mouse_click(app, sidebar_host):
    """Clearing the keyboard mode must not turn the indicator off for good.

    Real Tab presses, because the pixels the user sees come from a real traversal: ``setFocus`` alone
    marks the widget and paints nothing. The stop is grabbed with and without focus, so the ring is
    asserted rather than assumed - the property alone would pass on a rule that never wins.
    """
    sidebar, other = sidebar_host["sidebar"], sidebar_host["other"]
    _click(other, 1)

    focused = app.focusWidget()
    for _ in range(4):
        QTest.keyClick(focused, Qt.Key.Key_Tab)
        QApplication.processEvents()
        focused = app.focusWidget()
        if focused is not None and not sidebar.isAncestorOf(focused) and focused is not sidebar:
            break

    assert focused is not None, "Tab left no widget focused at all"
    assert app._focus_tracker._keyboard, "the Tab press did not put the tracker in keyboard mode"
    assert bool(focused.property("keyboardFocus")), (
        f"keyboard navigation did not mark {type(focused).__name__} after the mouse had cleared the mode"
    )
    with_focus = _pixels(focused)

    focused.clearFocus()
    QApplication.processEvents()
    assert _pixels(focused) != with_focus, (
        f"the ring the tracker marks on a Tab stop is invisible on {type(focused).__name__}"
    )


def test_a_mouse_event_clears_a_keyboard_mark_whatever_put_it_there(app, sidebar_host):
    """The trailing half of the same rule: a mark does not outlive the mouse event that arrived after it.

    The mark is put on by hand, so it is one the tracker's list of marked widgets does not know about -
    the state a mark must not survive in, whatever set it - and this pins that the tracker keeps its
    promise for the whole window instead of only for the widgets it happens to remember.

    The focus cue is not asserted here, deliberately: the widget the click focuses is focused, and a
    focused control shows no ring whatever its mark says (that the mark is what draws the ring is what
    the two sequence tests above assert). What this adds is the mark itself, on a widget the tracker
    never marked.
    """
    sidebar = sidebar_host["sidebar"]
    sidebar.clearFocus()
    QApplication.processEvents()
    unmarked = _ring_area(sidebar)

    app._focus_tracker._keyboard = False
    sidebar.setProperty("keyboardFocus", True)
    _click(sidebar, 1)

    assert sidebar.hasFocus(), "the click did not even focus the rail - the probe is wrong"
    assert not bool(sidebar.property("keyboardFocus")), "the mark outlived the mouse event that cleared it"
    assert _ring_area(sidebar) == unmarked, "the mouse event left the rail painted"
