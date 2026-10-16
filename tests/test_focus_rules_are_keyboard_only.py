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
from PySide6.QtCore import QEvent, Qt
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

    The theme is applied here, before the widgets exist, because it is the application stylesheet that
    draws the focus ring at all: a rail built without one renders as its plain platform frame and paints
    the same picture marked and unmarked (measured: 0 bytes of difference, a uniform 0xb8b8b8 box,
    against 556 bytes of ring once the sheet is in place). The other tests in this module get the sheet
    from the ``line_edit`` fixture; the activation tests below must not depend on whether that test ran.
    """
    theme.apply_theme("light", None, None, "default")
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


# ---------------------------------------------------------------------------------------------------
# Activation changes: a window going away and coming back is not an input either.
#
# The original filter handled a key press, a mouse event and both focus events; it had no branch for the
# window or the application becoming (in)active. The reported sequence falls straight through that gap.
# Minimising reports only ``WindowStateChange`` - the control keeps its focus and no ``FocusOut`` is
# delivered - and coming back reports ``ApplicationActivate``, then ``WindowActivate``, then a
# ``FocusIn`` whose reason is ``ActiveWindowFocusReason``. With nothing to clear it, the answer from
# before the minimise was still standing when that ``FocusIn`` arrived, so the control was marked again
# and the ring came back for a window the user had merely restored: measured on the real platform,
# 16733 bytes against the unmarked baseline, where a mouse-only session differs by 39 bytes of noise.
#
# The fix is two branches. Deactivate clears the mark *and* the answer, because the flag is still the
# old answer while the marks go - the same pair of actions the mouse branch performs, and the same
# reason (the widget the platform focuses next can already be marked). Activate clears the answer only:
# deactivation has already taken every mark and cleared the flag that would put one back, so clearing
# marks again would be dead code, while clearing the answer is what stops the ring on the way back in.
# ---------------------------------------------------------------------------------------------------

# A ring's worth of changed pixels in a rail's outermost 8 scanlines, measured on this fixture: the
# tracker's own mark changes 556 bytes there (1280 non-zero bytes unmarked, 1836 marked). The bar sits
# well below that, so a ring fails it and the noise floor - antialiasing, a caret, a hover background,
# none of which is what these tests are about - does not.
RING_PIXELS = 64


def _unmarked_focused_ring(app, sidebar, other) -> bytes:
    """The rail's ring area while it is focused but carrying no mark - the baseline a ring shows up on.

    Focus is parked on the other view first, so the rail really does take focus on the next line and a
    repolish of a stale style cache cannot pass for a state change. The property reset is written out
    rather than left to the fixture: this module's ``app`` fixture is module-scoped and the suite shares
    one ``QApplication``, so the mark arrives here carrying whatever the test before it did.
    """
    app._focus_tracker._keyboard = False
    sidebar.clearFocus()
    QApplication.processEvents()
    sidebar.setProperty("keyboardFocus", False)
    _repolish(sidebar)
    sidebar.setFocus(Qt.FocusReason.TabFocusReason)
    QApplication.processEvents()
    assert sidebar.hasFocus(), "the rail did not take focus - the probe is wrong"
    assert not bool(sidebar.property("keyboardFocus")), "the baseline rail is marked, so it cannot show a ring"
    return _ring_area(sidebar)


def _mark_via_tracker(app, sidebar, other) -> bytes:
    """Put the mark on the rail the way the tracker does: a key press, then focus arriving.

    Returns the marked ring area. ``other`` takes the key press because any key press arms the tracker
    and Shift types nothing, so the rail's own picture is not disturbed by a keystroke landing on it.
    """
    app._focus_tracker._keyboard = False
    sidebar.clearFocus()
    QApplication.processEvents()
    QTest.keyClick(other, Qt.Key.Key_Shift)
    QApplication.processEvents()
    assert app._focus_tracker._keyboard, "the key press did not put the tracker in keyboard mode"
    sidebar.setFocus(Qt.FocusReason.TabFocusReason)
    QApplication.processEvents()
    assert bool(sidebar.property("keyboardFocus")), "the rail was not marked before the window went away"
    return _ring_area(sidebar)


def _activation_cycle(app, host, widget) -> None:
    """Drive the events the platform really sends when the window is minimised and restored.

    ``widget`` is marked and in keyboard mode when this is called; it is left focused and unmarked. The
    events go through ``QApplication.sendEvent``, the real delivery path, rather than a direct call into
    the filter, so a tracker that is not installed as a filter fails these tests instead of passing
    them. ``setFocus`` with a hand-picked reason is how a real focus move is reproduced here: the reason
    is the one the platform sends on a restore and offscreen there is no window manager to produce it.
    The tracker reacts to the event type alone - the reason is not read - but writing the platform's own
    reason keeps this from drifting from the sequence it models.
    """
    widget.clearFocus()  # the FocusOut a deactivate reports when it does move focus
    QApplication.processEvents()
    for kind in (QEvent.Type.WindowDeactivate, QEvent.Type.ApplicationDeactivate):
        QApplication.sendEvent(host, QEvent(kind))
    QApplication.processEvents()
    for kind in (QEvent.Type.ApplicationActivate, QEvent.Type.WindowActivate):
        QApplication.sendEvent(host, QEvent(kind))
    QApplication.processEvents()
    widget.setFocus(Qt.FocusReason.ActiveWindowFocusReason)  # the fresh FocusIn on the way back
    QApplication.processEvents()


def test_an_activation_change_does_not_mark_the_control_again(app, sidebar_host):
    """A key pressed before the window went away must not ring the control when it comes back.

    The rail is marked by the tracker first - the state the report starts from, and the state the old
    filter carried across the minimise - and the ring that mark paints is measured before it is trusted,
    so the comparison below is known to be able to see a ring at all. It is then put through the
    minimise/restore sequence and has to come back looking exactly like the same rail focused but
    unmarked. The property assertion is the cheap half; the pixels are the half that matters, because
    the reported bug leaves the property readable and it is the ring the user sees.
    """
    sidebar, other = sidebar_host["sidebar"], sidebar_host["other"]

    unmarked = _unmarked_focused_ring(app, sidebar, other)
    marked = _mark_via_tracker(app, sidebar, other)
    painted = sum(1 for a, b in zip(marked, unmarked) if a != b)
    assert painted >= RING_PIXELS, (
        f"the keyboard mark painted no ring on this fixture: only {painted} bytes differ between the "
        f"marked and the unmarked rail, so this test could not see the ring it is about"
    )

    _activation_cycle(app, sidebar_host["host"], sidebar)

    assert sidebar.hasFocus(), "the restore sequence left the rail unfocused - the probe is wrong"
    restored = _ring_area(sidebar)
    changed = sum(1 for a, b in zip(restored, unmarked) if a != b)
    assert not bool(sidebar.property("keyboardFocus")), (
        "the control was marked as keyboard focus again just because its window came back to the "
        "foreground - no key was pressed between the minimise and the restore "
        f"(its ring area differs from the unmarked rail by {changed} bytes, against {painted} for the "
        f"ring itself)"
    )
    assert app._focus_tracker._keyboard is False, (
        "the restore left the tracker still answering 'keyboard', so the next activation would ring again"
    )
    assert changed < RING_PIXELS, (
        f"the restored rail is not painted like an unmarked one: {changed} bytes of its ring area "
        f"differ, against {painted} for the ring this fixture really does draw"
    )


def test_a_tab_press_after_an_activation_change_still_paints_focus(app, sidebar_host):
    """The hard requirement: keyboard navigation must still be visible after the window comes back.

    Clearing the answer on an activation change is only safe because the next key press puts it back,
    so the first Tab after a restore has to ring its stop exactly as it did before. Both halves are
    asserted - the mark is on the stop that took focus, and that mark paints, against the stop's own
    unfocused rendering. A mark that never paints is the same defect as no mark, and the property alone
    would pass on a rule that never wins.
    """
    sidebar, other = sidebar_host["sidebar"], sidebar_host["other"]
    tracker = app._focus_tracker

    _mark_via_tracker(app, sidebar, other)
    _activation_cycle(app, sidebar_host["host"], sidebar)
    assert not tracker._keyboard, "the restore did not clear the answer, so this is not the state under test"

    QTest.keyClick(sidebar, Qt.Key.Key_Tab)
    QApplication.processEvents()
    focused = app.focusWidget()

    assert focused is not None, "Tab left no widget focused at all"
    assert tracker._keyboard, "the Tab press did not put the tracker back in keyboard mode"
    assert bool(focused.property("keyboardFocus")), (
        f"the first Tab after the window came back did not mark {type(focused).__name__}"
    )
    with_focus = _pixels(focused)
    focused.clearFocus()
    QApplication.processEvents()
    without_focus = _pixels(focused)

    changed = sum(1 for a, b in zip(with_focus, without_focus) if a != b)
    assert changed >= RING_PIXELS, (
        f"the Tab stop is invisible: only {changed} bytes differ between focused and unfocused "
        f"{type(focused).__name__}, so the keyboard mark painted no ring"
    )


@pytest.mark.parametrize("pair", ["Window", "Application"])
def test_the_application_level_activation_pair_clears_the_answer_too(app, sidebar_host, pair: str):
    """Both report pairs behave the same, so neither can be the one that was forgotten.

    The filter names four event types and the two halves of each pair do different jobs: the deactivate
    half clears the mark and the answer, the activate half clears the answer alone. A pair wired up for
    one level only - ``WindowDeactivate`` handled but ``ApplicationDeactivate`` not, or an activate
    branch that clears marks - would look correct in a test that drives the other level. This drives
    each pair on its own, and the assertion that says the half did its job is the rail's own picture:
    marked before, unmarked after, with the mark's ring measured first so the comparison is known to be
    able to see one.
    """
    sidebar, other = sidebar_host["sidebar"], sidebar_host["other"]
    host = sidebar_host["host"]
    tracker = app._focus_tracker

    unmarked = _unmarked_focused_ring(app, sidebar, other)
    marked = _mark_via_tracker(app, sidebar, other)
    painted = sum(1 for a, b in zip(marked, unmarked) if a != b)
    assert painted >= RING_PIXELS, (
        f"the keyboard mark painted no ring on this fixture: only {painted} bytes differ between the "
        f"marked and the unmarked rail, so this test could not see the ring it is about"
    )

    sidebar.clearFocus()
    QApplication.processEvents()
    deactivate = {"Window": QEvent.Type.WindowDeactivate, "Application": QEvent.Type.ApplicationDeactivate}[pair]
    activate = {"Window": QEvent.Type.WindowActivate, "Application": QEvent.Type.ApplicationActivate}[pair]

    QApplication.sendEvent(host, QEvent(deactivate))
    QApplication.processEvents()
    assert not bool(sidebar.property("keyboardFocus")), (
        f"{deactivate.name} did not clear the mark: the rail is still painted as keyboard focus"
    )
    assert tracker._keyboard is False, f"{deactivate.name} did not clear the tracker's answer"

    QApplication.sendEvent(host, QEvent(activate))
    QApplication.processEvents()
    assert tracker._keyboard is False, f"{activate.name} put the answer back, so the next focus event would ring"

    sidebar.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
    QApplication.processEvents()
    changed = sum(1 for a, b in zip(_ring_area(sidebar), unmarked) if a != b)
    assert changed < RING_PIXELS, (
        f"{activate.name} left the rail looking marked: {changed} bytes of its ring area differ from "
        f"the unmarked rail, against {painted} for the ring itself"
    )




