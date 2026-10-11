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

"""Keyboard-only walkthrough: record where keyboard focus can land on every page.

The UI guideline requires "unplug the mouse, then walk the whole main flow with Tab and the arrow
keys, confirming every step shows where focus is". A claim like that is worth little in a changelog;
what is worth something is a record that can be regenerated on demand and diffed between commits.

This tool drives the real window offscreen and walks each page's focus chain - the order Qt's own Tab
navigation follows - then writes a Markdown report:

* the focus stops per page (class, object name, readable label, focus policy, where the name comes from);
* pages with no focusable control at all (a hard failure - exit code 1);
* interactive widgets that are explicitly *not* focusable, i.e. the exception list that has to stay
  short and deliberate;
* for each stop, whether focusing it changes the pixels around it (the focus cue is visible);
* every `:focus` selector in the stylesheets, so a missing focus visual can be spotted by eye.

The per-page numbers are counts of focusable controls, reproducible run to run. They are a property of
one build's interface, not a claim to quote in user-facing documents.

Usage:
    python tools/keyboard_walkthrough.py --out <report.md> [--theme dark]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _qss_focus_selectors(root: Path) -> list[str]:
    """Every selector a focused widget can be styled by, in either stylesheet.

    Two shapes count. `:focus` rules are the obvious one. The other is the
    `[keyboardFocus="true"]` block: this launcher deliberately shows focus only for keyboard
    navigation (see gui.widgets.KeyboardFocusTracker), so the keyboard ring lives there and carries no
    `:focus` pseudo-state at all. Looking only for `:focus` reported a missing rule for every control
    whose visual had moved to that block.
    """
    selectors: list[str] = []
    for name in ("style.qss", "style_light.qss"):
        path = root / "gui" / "resources" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"([^{}]*)\{", text):
            for part in block.split(","):
                part = part.strip()
                if part and (":focus" in part or "keyboardFocus" in part):
                    selectors.append(part)
    return selectors


def _widget_text(widget) -> str:
    """The control's own visible text, if it has any."""
    for getter in ("text", "currentText"):
        attr = getattr(widget, getter, None)
        try:
            value = attr() if callable(attr) else None
        except Exception:  # noqa: BLE001 - a widget without that getter is normal
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", " ")
    return ""


def accessible_name_of(widget) -> str:
    """What a screen reader announces for this widget: explicit name, else what Qt reports.

    The second half is what WCAG 4.1.2 actually asks about, and Qt answers it for more than just text
    widgets: a QCheckBox is named by its own label, a QSpinBox or QComboBox by the QFormLayout row it
    sits in, a QPushButton by its text. A tooltip and a placeholder are *not* part of that answer
    (measured: ``QAccessible.text(Name)`` returns "" for a button that only has a toolTip and for a
    field that only has a placeholderText). This module and tests/test_accessible_names.py both ask the
    question through this one function, so the report and the gate cannot drift apart on what "named"
    means.
    """
    explicit = (widget.accessibleName() or "").strip()
    if explicit:
        return explicit
    try:
        from PySide6.QtGui import QAccessible
    except ImportError:  # tooling without Qt: fall back to the widget's own text
        return _widget_text(widget)
    interface = QAccessible.queryAccessibleInterface(widget)
    if interface is None:
        return ""
    try:
        return (interface.text(QAccessible.Text.Name) or "").strip()
    except Exception:  # noqa: BLE001 - an interface that refuses the question names nothing
        return ""


def name_source_of(widget) -> str:
    """Where a screen reader gets this control's name from (WCAG 4.1.2).

    `accessible` - an explicit setAccessibleName, the only source that reaches UIA on every platform.
    `text`       - the accessible interface reports a name derived from the widget's own text or its
                   form label, which Qt answers for checkboxes, buttons, spin boxes and combos. Usable.
    `placeholder`/`tooltip` - weak: a placeholder disappears once the field has content, and a tooltip
                   written as an instruction ("switch account") is read out as an order (C4). Qt does
                   not pass either on as a name, so these need an explicit one.
    `none`       - nothing at all.
    """
    explicit = (widget.accessibleName() or "").strip()
    if explicit:
        return "accessible"
    name = accessible_name_of(widget)
    own_text = _widget_text(widget)
    if name and (own_text.startswith(name) or name.startswith(own_text) or own_text == name):
        return "text"
    if name:
        return "text"  # a name Qt derived from a form label rather than from the widget itself
    placeholder = getattr(widget, "placeholderText", None)
    if callable(placeholder) and (placeholder() or "").strip():
        return "placeholder"
    if (widget.toolTip() or "").strip():
        return "tooltip"
    return "none"


def _readable(widget) -> str:
    """What a human (or a screen reader) would call this widget."""
    for candidate in (accessible_name_of(widget), _widget_text(widget)):
        if candidate:
            return candidate.replace("\n", " ")[:60]
    for getter in ("placeholderText", "title", "toolTip"):
        value = None
        try:
            attr = getattr(widget, getter, None)
            value = attr() if callable(attr) else None
        except Exception:  # noqa: BLE001 - a widget without that getter is normal
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", " ")[:60]
    return ""


_name_source = name_source_of  # the name the two call sites below have used since before unification


def _describe(widget) -> tuple[str, str, str, str]:
    return (
        type(widget).__name__,
        widget.objectName() or "-",
        _readable(widget),
        str(widget.focusPolicy()).replace("Qt.FocusPolicy.", ""),
    )


def _selector_target(selector: str) -> str:
    """The widget part of a selector, with pseudo-states and sub-controls stripped.

    `QListWidget::item:selected:focus` -> `QListWidget`; `QPushButton#dangerButton:focus` keeps the
    id so an object-name rule can be told apart from a class rule.
    """
    base = selector.split("::")[0]
    base = re.sub(r"\[[^\]]*\]", "", base)  # drop attribute conditions like [keyboardFocus="true"]
    return base.split(":")[0].strip()


def _has_focus_rule(widget, selectors: list[str]) -> bool:
    """Does any stylesheet `:focus` selector apply to this widget?

    Qt style-sheet type selectors match the class **and its subclasses** (a `QDoubleSpinBox:focus`
    rule does apply to a custom subclass), so the whole MRO counts - checking only the concrete class
    name produces false alarms.
    """
    names = {cls.__name__ for cls in type(widget).__mro__}
    obj = widget.objectName()
    for selector in selectors:
        base = _selector_target(selector)
        if not base:
            continue
        if "#" in base:
            if base.split("#", 1)[1].strip() == obj:
                return True
        elif base.split()[-1] in names or base.split()[-1] == "*":
            return True
    return False


INTERACTIVE = (
    "QAbstractButton",
    "QLineEdit",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QCheckBox",
    "QRadioButton",
    "QAbstractItemView",
    "QTextEdit",
    "QPlainTextEdit",
    "QSlider",
    "QTabBar",
)

# Bound on one page's focus chain. The chain is circular, so the walk stops when it comes back to where
# it started; the limit only exists so a chain that never returns cannot hang the tool.
FOCUS_CHAIN_LIMIT = 20_000

# Tab presses allowed per focus stop of a page. Presses that land outside the page (on the sidebar or on
# another page's widgets on the way around) consume presses but are not recorded, so the walk needs more
# than one per stop; the page's own count is the bound that keeps an unclosed chain finite.
TAB_PRESSES_PER_STOP = 4

# Stops a real Tab press actually reached in this run. The visual pass reads it: the focus ring is only
# painted for focus that arrives with a key event, so a stop no press reached cannot be judged by
# focusing it programmatically, and saying "no visible focus" about it would describe the tool rather
# than the interface. Filled by :func:`_tab_reach`.
_TAB_REACHED: set[int] = set()

# Qt's own sub-widgets of a compound control. They are focus stops in the chain but a user never addresses
# them: the spin box beside the line edit is what Tab reaches, the line edit inside it carries the same
# value and the same (absent) name, and the tab bar inside a QTabWidget is driven by the widget itself.
# Counting them reports the same control twice and reports a name defect the user can never meet.
INTERNAL_OBJECT_NAMES = frozenset(
    {
        "qt_spinbox_lineedit",
        "qt_tableview_cornerbutton",
        "qt_scrollarea_hcontainer",
        "qt_scrollarea_vcontainer",
        "qt_tabbar",
        "qt_editable_combobox",
    }
)


def _is_internal(widget) -> bool:
    """A Qt-internal part of a compound control, not a control of its own."""
    if widget.objectName() in INTERNAL_OBJECT_NAMES:
        return True
    parent = widget.parent()
    parent_class = type(parent).__name__ if parent is not None else ""
    return type(widget).__name__ == "QLineEdit" and parent_class in (
        "QComboBox",
        "QAbstractSpinBox",
        "QSpinBox",
        "QDoubleSpinBox",
        "NoWheelSpinBox",
        "NoWheelDoubleSpinBox",
    )


def _find_non_focusable(page) -> list[tuple[str, str, str]]:
    """Interactive children that cannot take focus - the exception list must stay deliberate."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    out: list[tuple[str, str, str]] = []
    for child in page.findChildren(QWidget):
        if child.focusPolicy() != Qt.FocusPolicy.NoFocus:
            continue
        if not any(child.inherits(name) for name in INTERACTIVE):
            continue
        if not child.isVisibleTo(page):
            continue
        kind, name, label, _ = _describe(child)
        out.append((kind, name, label))
    return out


def _page_focus_stops(page) -> list:
    """Every widget inside ``page`` that can take keyboard focus, in the page's focus-chain order.

    This is the list the walk has to cover. Focus within one page follows the focus chain
    (``nextInFocusChain``), which is the order Qt's own Tab navigation walks, so walking the chain and
    walking with Tab visit the same controls - but only the chain is bounded on both ends. A simulated
    Tab press cannot be contained: it leaves the page once it reaches the last control, and the page's
    own position in that journey depends on layout, so the number of presses needed to come back is not
    known in advance. The chain is a property of the widget tree instead, it is finite, and it visits
    every focusable control exactly once - which is what makes a stop count reproducible.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    stops: list = []
    seen: set[int] = set()
    node = page
    for _ in range(FOCUS_CHAIN_LIMIT):
        node = node.nextInFocusChain()
        if node is None or node is page or id(node) in seen:
            break  # the chain is circular and has come back to where it started
        seen.add(id(node))
        if not isinstance(node, QWidget):
            continue  # a QAction carries no focus of its own
        if not (node is page or page.isAncestorOf(node)):
            break  # left the page subtree: everything from here belongs to another page
        if _is_internal(node):
            continue  # Qt's part of a compound control, not a stop a user reaches on its own
        if node.focusPolicy() == Qt.FocusPolicy.NoFocus:
            continue
        if not node.isVisibleTo(page) or not node.isEnabled():
            continue
        stops.append(node)
    return stops


def _tab_reach(app, page) -> list:
    """The stops of ``page`` that real Tab presses actually reach, for the visual pass.

    Returns ``(widgets, closed)``: the widgets focus entered, in the order it entered them, and whether
    the traversal came back to its starting stop. The list can be shorter than the page's stop list -
    Qt's Tab order is geometric, so a control laid out inside a collapsed scroll area is skipped - and
    ``closed`` says whether that happened.

    The visual pass needs real Tab presses rather than ``setFocus``: the focus ring is only painted for
    focus that arrives with a key event. The tracker marks the widget either way - the ``keyboardFocus``
    property reads True under ``setFocus`` too - but the pixels do not change at all. Measured on the
    instances page's sort combo: a whole-window diff of 0 bytes with ``setFocus`` (with or without a
    repolish and an explicit repaint) against 1245 bytes when focus arrived by Tab.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    stops = _page_focus_stops(page)
    if not stops:
        return [], True
    start = stops[0]
    start.setFocus(Qt.FocusReason.OtherFocusReason)
    app.processEvents()
    if not start.hasFocus():
        return [], True
    _TAB_REACHED.add(id(start))  # the press below leaves it, but focus did start there
    QTest.keyClick(start, Qt.Key.Key_Tab)  # keyboard-navigation mode on, and one step taken
    app.processEvents()

    reached: list = []
    seen: set[int] = set()
    for _ in range(len(stops) * TAB_PRESSES_PER_STOP):
        widget = app.focusWidget()
        if widget is start:
            return reached, True  # focus came back to the first stop
        if widget is not None and page.isAncestorOf(widget) and id(widget) not in seen:
            seen.add(id(widget))
            _TAB_REACHED.add(id(widget))
            reached.append(widget)
        QTest.keyClick(widget or start, Qt.Key.Key_Tab)
        app.processEvents()
    return reached, False


def _walk(
    app, page, selectors: list[str]
) -> tuple[list[tuple[str, str, str, str, bool, str]], list, list, bool]:
    """Record every focus stop of ``page``; also return the stops a Tab press reached, and `closed`.

    The stop list comes from the page's focus chain (see :func:`_page_focus_stops`), which is what makes
    the count a property of the interface instead of a property of the walk. This is the fix for the count
    that made "58 focus stops" quotable: the walk used to end at the *first repeated description*, and
    class + objectName + label + focus policy cannot tell two similar controls apart (two "浏览…" buttons,
    two like-sized spin boxes, the two QLineEdits inside a spin box). The second of such a pair therefore
    read as "already visited" and cut the walk short - on a page whose chain visits eight controls, the old
    rule stopped after two.

    The two lists are returned separately because they answer different questions: the first is "how many
    controls can take keyboard focus here", the second is "which of them did this offscreen run actually
    paint a focus cue for". The flag says whether the Tab traversal closed on itself.
    """
    stops = _page_focus_stops(page)
    if not stops:
        return [], [], [], True
    path = [
        (*_describe(widget), _has_focus_rule(widget, selectors), _name_source(widget))
        for widget in stops
    ]
    reached, closed = _tab_reach(app, page)
    return path, stops, reached, closed


GRAB_PAD = 4  # pixels of margin around the widget, so a ring drawn outside its rect is visible


NEUTRAL_RETRIES = 3  # how many times the neutral frame may be re-taken before calling it unstable

# How many times a non-`yes` verdict is re-measured before it is believed. Painting is asynchronous, so
# one unlucky grab is not evidence of a missing focus cue.
FOCUS_VISUAL_ATTEMPTS = 3


def _repolish(app, *widgets) -> None:
    """Force a fresh stylesheet evaluation after a focus change.

    Changing focus alone can leave Qt re-using the style it already computed, which made two grabs of
    supposedly different states byte-identical - and made this whole check report "no visible focus"
    for controls whose appearance does change.
    """
    for widget in widgets:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
    app.processEvents()


def _focus_visual(app, window, widget, neutral, measured: bool) -> str:
    """Does focusing this widget change the pixels around it?

    Returns `yes`, `no`, `unknown:moved` (the widget shifted between the grabs, e.g. focus scrolling it
    into view), `unknown:out_of_view` (the widget is clipped by the window, so part of it - possibly the
    part carrying the focus cue - is not rendered at all), `unknown:not_focused` (the widget did not take
    focus, so nothing was measured), `unknown:not_painted_by_setfocus` (the widget was not reached by a
    Tab press, so this path cannot paint its ring - see below) or `unknown:unstable` (the neutral frame
    never settled - async status text is the usual culprit). `unknown` is never a defect, and `no` is
    only reported where the comparison is known to be meaningful.

    That last restriction is the important one, and ``measured`` is what carries it. This check focuses a
    widget with ``setFocus``, and the focus ring is drawn from the ``[keyboardFocus="true"]`` block when
    focus *arrives* with a key event. Under ``setFocus`` the tracker still marks the widget - the
    ``keyboardFocus`` property reads True - but the ring is not painted: measured one control at a time on
    a freshly built window, the settings page's theme combo, spin box and game-directory field all showed
    0 bytes of window change while the checkbox beside them, reached by a real Tab press, showed 315. So a
    `no` here would be an announcement about the measurement, not about the interface, and the caller
    reports how many stops the real Tab traversal covered instead.
    """
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtTest import QTest

    top_left = widget.mapTo(window, QPoint(0, 0))
    # A partially visible widget cannot be judged: grabbing only the visible strip made a button that
    # had merely scrolled out of view look like "no visible focus". Any clipping means unknown.
    if not window.rect().contains(QRect(top_left, widget.size())):
        return "unknown:out_of_view"

    # The grab is taken of the *widget*, not of a window region around it. `window.grab(rect)` was the
    # tool's blind spot: in this environment it hands back pixels that do not include a child's fresh
    # paint, so it reported **0 bytes for an unconditional 2px red border** on a checkbox while
    # `widget.grab()` on the same widget reported 4767 bytes - and the same blindness made 17 controls
    # look as if they had no focus cue at all. The widget grab is also the tighter comparison: same
    # control, same rectangle, nothing else in frame.
    _repolish(app, widget, neutral)
    app.processEvents()
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    # The key press goes to the *neutral* widget, not to this one: any key press re-arms the tracker, and
    # pressing it on the widget under test makes the comparison meaningless (the press itself repaints the
    # widget, so the focused frame stops being a frame of "focused, nothing else").
    QTest.keyClick(neutral, Qt.Key.Key_F13)
    app.processEvents()
    if not widget.hasFocus():
        return "unknown:not_focused"
    if not measured:
        return "unknown:not_painted_by_setfocus"
    if widget.mapTo(window, QPoint(0, 0)) != top_left:
        return "unknown:moved"
    # The grab must stay alive while its buffer is read: `widget.grab().toImage().constBits()`
    # in one expression hands back a view into an already-destroyed image (access violation).
    focused_image = widget.grab().toImage()
    focused = bytes(focused_image.constBits())

    for _attempt in range(NEUTRAL_RETRIES):
        neutral.setFocus(Qt.FocusReason.OtherFocusReason)
        _repolish(app, neutral, widget)
        QTest.keyClick(neutral, Qt.Key.Key_F13)  # keeps keyboard mode armed on the neutral side too
        app.processEvents()
        if widget.mapTo(window, QPoint(0, 0)) != top_left:
            return "unknown:moved"
        baseline_image = widget.grab().toImage()
        baseline = bytes(baseline_image.constBits())
        app.processEvents()
        repeat_image = widget.grab().toImage()
        repeat = bytes(repeat_image.constBits())
        if baseline == repeat:
            return "yes" if focused != baseline else "no"
    return "unknown:unstable"


def _focus_visual_confirmed(app, window, widget, neutral, measured: bool) -> str:
    """Re-test a `no` before believing it, and never turn a `yes` into a defect.

    A single `no` is not evidence here: the same control can answer `no` on one attempt and `yes` on the
    next within one run (measured - three accent-swatch buttons reported `no` while five identical ones
    beside them reported `yes`). Painting is asynchronous, so the retries exist to catch the attempt that
    did paint. Only a control that never once painted while focused is reported as having no visible focus
    cue, and only controls a Tab press actually reached are judged at all (``measured``).
    """
    verdicts: list[str] = []
    for _attempt in range(FOCUS_VISUAL_ATTEMPTS):
        verdict = _focus_visual(app, window, widget, neutral, measured)
        if verdict == "yes":
            return "yes"
        verdicts.append(verdict)
    first = verdicts[0]
    if all(verdict == first for verdict in verdicts):
        return first
    for verdict in verdicts:
        if verdict.startswith("unknown"):
            return verdict
    return "no" if "no" in verdicts else "flaky"


def _has_focus_rule_name(kind: str, object_name: str, selectors: list[str]) -> bool:
    """Same as :func:`_has_focus_rule` but from the recorded (class name, object name) pair.

    Kept for callers that only have the recorded names; the walkthrough itself decides the flag from
    the live widget so that base-class rules are honoured.
    """
    for selector in selectors:
        base = _selector_target(selector)
        if not base:
            continue
        if "#" in base:
            if base.split("#", 1)[1].strip() == object_name:
                return True
        elif base.split()[-1] == kind or base.split()[-1] == "*":
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a keyboard-only walkthrough of every page.")
    parser.add_argument("--root", default=".", help="checkout root (default: current directory)")
    parser.add_argument("--out", required=True, help="where to write the Markdown report")
    parser.add_argument("--theme", default="dark", choices=["dark", "light"])
    parser.add_argument("--preview", default=None, help="where to keep _preview data (default: root)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_path = Path(args.out).resolve()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "tools"))
    os.chdir(root)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    import shot_pages

    data_dir, game_dir = shot_pages.ensure_preview(
        Path(args.preview).resolve() if args.preview else root,
        Path("%APPDATA%\\.minecraft"),
    )
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data_dir)
    os.environ["MINECRAFT_GAME_DIR"] = str(game_dir)

    from PySide6.QtCore import QThreadPool
    from PySide6.QtGui import QFontDatabase

    from gui.main import create_app
    from gui.pages import java_page, mods_page, versions_page
    from gui.theme import apply_theme
    from launcher import config
    from launcher.auth import AccountStore, create_offline_account
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit

    versions_page.fetch_manifest = lambda cache_path=None: VersionManifest(  # type: ignore[assignment]
        latest={"release": "1.21.11", "snapshot": "26w02a"},
        versions=[
            ManifestVersion(
                id=vid,
                type=vtype,  # type: ignore[arg-type]
                url="https://example.invalid/version.json",
                time=f"{date}T12:00:00+00:00",
                release_time=f"{date}T12:00:00+00:00",
            )
            for vid, vtype, date in shot_pages.FAKE_VERSIONS
        ],
    )
    mods_page.search_projects = lambda *a, **k: [  # type: ignore[assignment]
        ModSearchHit(slug=slug, title=title, description=desc, downloads=dl)
        for slug, title, desc, dl in shot_pages.FAKE_MODS
    ]
    java_page.list_java = lambda *a, **k: []  # type: ignore[assignment]

    app = create_app([])
    apply_theme(args.theme, None, None, "default")
    for font_file in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/consola.ttf",
    ):
        if Path(font_file).exists():
            QFontDatabase.addApplicationFont(font_file)

    cfg, cfg_path = config.load()
    cfg.game_dir = str(game_dir)
    cfg.theme = args.theme
    config.save(cfg, cfg_path)
    apply_theme(args.theme, None, None, cfg.ui_radius)
    store = AccountStore()
    if not store.load():
        account = create_offline_account("Steve")
        store.save({account.uuid: account})

    from gui.main_window import NAV_KEYS, MainWindow

    window = MainWindow()
    window.resize(1000, 600)
    window.apply_window_mode()
    window.show()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 5.0)
    for key in ("versions", "java"):
        page = window.pages.get(key)
        if page is not None and hasattr(page, "refresh"):
            page.refresh()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 15.0)

    selectors = list(dict.fromkeys(_qss_focus_selectors(root)))  # both stylesheets, duplicates merged
    lines: list[str] = []
    failures: list[str] = []
    total = 0
    visual_covered = 0
    visual_total = 0
    visual_gaps: list[str] = []
    invisible: list[tuple[str, str, str, str, str]] = []  # page, class, objectName, label, rect
    visual_tally: dict[str, int] = {"yes": 0, "no": 0, "unknown": 0, "flaky": 0}
    not_measured: list[tuple[str, str, str, str, str]] = []  # page, class, name, label, cause
    unknown_causes: dict[str, int] = {}
    neutral = window.stack  # a container with no :focus rule, used to park focus for the comparison

    lines.append("# MinePick 键盘走查记录")
    lines.append("")
    lines.append("> 由 `tools/keyboard_walkthrough.py` 自动生成:离屏启动真实窗口,记录每个页面的焦点落点")
    lines.append("> (逐个控件统计,不是「按到重复就停」的截断结果),并对能到达的落点做焦点可见性实测。")
    lines.append("> 重新生成即可与上一次对比(界面改动后必须重出)。")
    lines.append("")
    lines.append(f"- 主题:`{args.theme}`;窗口:`1000x600`;页面数:`{len(NAV_KEYS)}`")
    lines.append("")

    detail: list[str] = []
    for index, key in enumerate(NAV_KEYS):
        page = window.pages.get(key)
        if page is None:
            failures.append(f"页面 `{key}` 不存在")
            continue
        window.stack.setCurrentIndex(index)
        app.processEvents()
        path, stops, widgets, closed = _walk(app, page, selectors)
        total += len(path)
        if not path:
            failures.append(f"页面 `{key}`:没有任何可获得焦点的控件")
        visuals_by_id: dict[int, str] = {}
        visuals: list[str] = []
        reached_ids = {id(widget) for widget in widgets}
        for widget in stops:
            verdict = _focus_visual_confirmed(app, window, widget, neutral, id(widget) in reached_ids)
            visuals_by_id[id(widget)] = verdict
            visuals.append(verdict)
            bucket = "unknown" if verdict.startswith("unknown") else verdict
            visual_tally[bucket] = visual_tally.get(bucket, 0) + 1
            if verdict.startswith("unknown:"):
                cause = verdict.split(":", 1)[1]
                unknown_causes[cause] = unknown_causes.get(cause, 0) + 1
            if verdict == "no":
                from PySide6.QtCore import QPoint

                point = widget.mapTo(window, QPoint(0, 0))
                rect = f"{point.x()},{point.y()} {widget.width()}x{widget.height()}"
                kind, name, label, _policy, _has_rule, _source = _describe(widget) + (
                    _has_focus_rule(widget, selectors),
                    _name_source(widget),
                )
                invisible.append((key, kind, name, label, rect))
            elif verdict.startswith("unknown:") and verdict.split(":", 1)[1] in (
                "not_painted_by_setfocus",
                "out_of_view",
            ):
                # Measure-nothing cases stay visible in the report instead of being folded into a count:
                # "the tool could not see this" must never read as "this control is fine".
                kind, name, label, _policy, _has_rule, _source = _describe(widget) + (
                    _has_focus_rule(widget, selectors),
                    _name_source(widget),
                )
                not_measured.append((key, kind, name, label, verdict.split(":", 1)[1]))
        # How much of the page the visual pass could see. Qt's Tab order is geometric, so a control that
        # sits inside a collapsed scroll area is skipped by a press; the row is then reported without a
        # visual verdict instead of being counted as "no visible focus".
        visual_covered += len(widgets)
        visual_total += len(stops)
        if not closed:
            visual_gaps.append(f"{key}(走查 {len(widgets)}/{len(stops)})")
        without_rule = [
            f"`{kind}` `{name}`"
            for kind, name, _label, _policy, has_rule, _source in path
            if not has_rule
        ]
        weak_names = [
            f"`{kind}` `{name}`({source})"
            for kind, name, _label, _policy, _rule, source in path
            if source in ("none", "placeholder", "tooltip")
        ]
        detail.append(f"### {key}({len(path)} 个落点)")
        detail.append("")
        if without_rule:
            detail.append(f"- ⚠️ 未在样式表里找到 `:focus` 规则:{', '.join(without_rule)}")
            detail.append("")
        if weak_names:
            # Deliberately not the ⚠️ marker: that one means "no :focus rule", and an existing test
            # asserts it never appears. This is a different, weaker finding.
            detail.append(
                f"- ❗ 可读名称缺失或过弱({len(weak_names)} 个,WCAG 4.1.2):{', '.join(weak_names)}"
            )
            detail.append("")
        detail.append("| # | 控件 | objectName | 可读名称 | 名称来源 | 焦点策略 | 焦点样式 | 焦点可见 |")
        detail.append("|---|---|---|---|---|---|---|---|")
        for step_index, (kind, name, label, policy, has_rule, source) in enumerate(path):
            mark = "✅" if has_rule else "⚠️"
            widget = widgets[step_index] if step_index < len(widgets) else None
            visual = visuals_by_id.get(id(widget), "—") if widget is not None else "—"
            visual_mark = {"yes": "✅", "no": "❌", "unknown": "❓", "flaky": "〰️"}.get(visual, "—")
            source_mark = {"accessible": "✅ accessible", "text": "✅ text"}.get(source, f"❗ {source}")
            detail.append(
                f"| {step_index + 1} | `{kind}` | `{name}` | {label or '—'} | {source_mark} | {policy} "
                f"| {mark} | {visual_mark} {visual} |"
            )
        detail.append("")

        exceptions = _find_non_focusable(page)
        if exceptions:
            detail.append(f"- 不可获得焦点的交互控件({len(exceptions)} 个,须为有意为之):")
            for kind, name, label in exceptions:
                detail.append(f"  - `{kind}` `{name}` {label}")
            detail.append("")

    lines.append("## 概览")
    lines.append("")
    lines.append(f"- 焦点落点总数:`{total}`(逐控件统计:每页数的是该页可获得焦点的控件,不是走查走到哪算哪)")
    lines.append(f"- 硬失败:`{len(failures)}`")
    for failure in failures:
        lines.append(f"  - ❌ {failure}")
    unknown_detail = ", ".join(f"{name} `{count}`" for name, count in sorted(unknown_causes.items()))
    lines.append(
        f"- 焦点可见性实测(覆盖 `{visual_covered}` / `{visual_total}` 个落点):可见"
        f" `{visual_tally.get('yes', 0)}` / **不可见 `{visual_tally.get('no', 0)}`** /"
        f" 无法判定 `{visual_tally.get('unknown', 0)}`"
        + (f"({unknown_detail})" if unknown_detail else "")
        + f" / 不稳定 `{visual_tally.get('flaky', 0)}`"
    )
    if visual_gaps:
        lines.append(
            "- 焦点可见性未覆盖的页面:"
            + ", ".join(visual_gaps)
            + " — Qt 的 Tab 顺序是几何顺序,折叠滚动区内的控件按不到;这些行不写可见性结论"
        )
    lines.append("")
    lines.append(f"## 无可辨焦点效果的控件({len(invisible)} 个)")
    lines.append("")
    lines.append("> 判据:把焦点放到该控件与把焦点移开后,**控件自身(控件级抓图)的像素完全相同**")
    lines.append("> ⇒ 用户看不出焦点在哪。多次重测都为 `no` 才算数;`unknown` 不算缺陷。")
    lines.append("> 抓图用 `widget.grab()` 而不是 `window.grab(rect)`:后者在本环境下拿不到子控件刚重绘的像素")
    lines.append("> (实测给复选框加一条无条件 2px 红边框后它仍报 0 字节,控件级抓图报 4767 字节)⇒ 曾误报 17 个。")
    lines.append("")
    if invisible:
        lines.append("| 页面 | 控件 | objectName | 可读名称 | 矩形(窗口坐标) |")
        lines.append("|---|---|---|---|---|")
        for page_key, kind, name, label, rect in invisible:
            lines.append(f"| {page_key} | `{kind}` | `{name}` | {label or '—'} | {rect} |")
    else:
        lines.append("(无)")
    lines.append("")
    lines.append(f"## 无法判定(测不准)的落点({len(not_measured)} 个,不是缺陷)")
    lines.append("")
    lines.append("> 这两类**不是**「焦点不可见」✗,而是本工具在离屏环境下**测不出来**。它们必须由真机复核")
    lines.append("> (见 `MinePick_Docs/tasks/T-0004.md` 的 E5),**不得**被当成通过 ✗。")
    lines.append("")
    lines.append("> - `not_painted_by_setfocus`:该落点未被本轮 Tab 走查覆盖到,程序化放焦点不绘制焦点环 ⇒ 无从比较。")
    lines.append("> - `out_of_view`:控件被窗口边界裁掉一部分(滚动区),只抓到半截 ⇒ 无从比较。")
    lines.append("")
    if not_measured:
        lines.append("| 页面 | 控件 | objectName | 可读名称 | 原因 |")
        lines.append("|---|---|---|---|---|")
        for page_key, kind, name, label, cause in not_measured:
            lines.append(f"| {page_key} | `{kind}` | `{name}` | {label or '—'} | `{cause}` |")
    else:
        lines.append("(无)")
    lines.append("")
    lines.append(f"## 样式表中的 `:focus` 选择器({len(selectors)} 条)")
    lines.append("")
    for selector in selectors:
        lines.append(f"- `{selector}`")
    lines.append("")
    lines.append("## 各页面焦点路径")
    lines.append("")
    lines.extend(detail)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {out_path}")
    print(f"focus stops: {total}; pages: {len(NAV_KEYS)}; hard failures: {len(failures)}")
    print(
        "focus visual: "
        + ", ".join(f"{name}={count}" for name, count in sorted(visual_tally.items()) if count)
    )
    print(f"no visible focus effect: {len(invisible)}")
    for page_key, kind, name, label, rect in invisible:
        print(f"  INVISIBLE {page_key}: {kind} {name or '-'} {label or '-'} @ {rect}")
    print(f"not measurable (NOT a pass): {len(not_measured)}")
    for page_key, kind, name, label, cause in not_measured:
        print(f"  UNMEASURED {page_key}: {kind} {name or '-'} {label or '-'} ({cause})")
    for failure in failures:
        print(f"  FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())


