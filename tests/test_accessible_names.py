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

"""Hard gate: every focusable control on every page (and sub-page) has an accessible name.

Why this is a test of its own rather than part of the keyboard walkthrough's Markdown check:

* the walkthrough checks the stops it *records*, and a recording bug silently shrinks that set. The
  "58 focus stops, weak names 0" result this gate was written after is exactly that failure mode - the
  traversal stopped at the first repeated widget description, so most controls were never examined and
  fourteen unnamed ones sat on pages the report showed as clean;
* this test therefore enumerates controls independently of any walk: it asks the widget tree of each
  page, switches to **every** sub-page (four resource tabs, six per-instance tabs), and answers the
  accessibility question the way a screen reader does - ask Qt for the name.

The criteria match the audit that found the fourteen: a control whose accessible name is empty *and*
whose accessible interface reports no name is a defect. Qt's own sub-widgets are not controls
(`qt_spinbox_lineedit`, `qt_tableview_cornerbutton`, the tab bar's internal buttons), and neither is a
container that merely holds others, so they are excluded here for the same reason they were excluded
there.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Widgets that Qt builds inside a compound control and that a user never addresses directly.
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

# The control families a keyboard user can reach. Kept in step with tools/keyboard_walkthrough.INTERACTIVE
# on purpose: the walkthrough records these, and a control it records must pass this gate.
INTERACTIVE = (
    "QAbstractButton",
    "QLineEdit",
    "QComboBox",
    "QAbstractSpinBox",
    "QAbstractItemView",
    "QTextEdit",
    "QPlainTextEdit",
    "QSlider",
    "QTabBar",
    "QScrollArea",
    "QTabWidget",
)


@pytest.fixture()
def window(monkeypatch):
    """One offscreen window with preview data, built for each case in this module.

    Function-scoped on purpose: the shared teardown fixture in ``conftest.py`` closes and deletes every
    top-level widget after each test (that is what keeps Qt destructors on the main thread), so a
    module-scoped window is a deleted C++ object by the time the second case runs. The data directories
    are the preview ones the other UI tooling uses, never the real launcher profile.

    The four variables below go through ``monkeypatch`` rather than ``os.environ`` so this module leaves
    the process as it found it. Writing them directly leaked a launcher data directory into every later
    test file: ``launcher.paths.launcher_dir()`` reads ``MCLAUNCHER_DATA_DIR`` before portable/frozen
    detection, so ``tests/test_paths.py`` then resolved the preview folder instead of the path it had
    monkeypatched, and the mods search in ``tests/test_e2e.py`` ran against the preview profile.
    """
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")

    import shot_pages
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication

    data_dir, game_dir = shot_pages.ensure_preview(ROOT, Path("%APPDATA%\\.minecraft"))
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MINECRAFT_GAME_DIR", str(game_dir))

    from gui.pages import java_page, mods_page, versions_page
    from gui.theme import apply_theme
    from launcher import config
    from launcher.auth import AccountStore, create_offline_account
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit

    # The rest of the suite may already own the process-wide QApplication; create_app() would reuse it
    # but re-run its startup work (theme, trackers), so only build one when there is none.
    if QApplication.instance() is None:
        from gui.main import create_app

        app = create_app([])
    else:
        app = QApplication.instance()

    monkeypatch.setattr(
        versions_page,
        "fetch_manifest",
        lambda cache_path=None: VersionManifest(
            latest={"release": "1.21.11", "snapshot": "26w02a"},
            versions=[
                ManifestVersion(
                    id=version_id,
                    type=version_type,  # type: ignore[arg-type]
                    url="https://example.invalid/version.json",
                    time=f"{date}T12:00:00+00:00",
                    release_time=f"{date}T12:00:00+00:00",
                )
                for version_id, version_type, date in shot_pages.FAKE_VERSIONS
            ],
        ),
    )
    monkeypatch.setattr(
        mods_page,
        "search_projects",
        lambda *a, **k: [
            ModSearchHit(slug=slug, title=title, description=desc, downloads=downloads)
            for slug, title, desc, downloads in shot_pages.FAKE_MODS
        ],
    )
    monkeypatch.setattr(java_page, "list_java", lambda *a, **k: [])

    apply_theme("dark", None, None, "default")
    cfg, cfg_path = config.load()
    cfg.game_dir = str(game_dir)
    cfg.theme = "dark"
    config.save(cfg, cfg_path)
    store = AccountStore()
    if not store.load():
        account = create_offline_account("Steve")
        store.save({account.uuid: account})

    from gui.main_window import MainWindow

    built = MainWindow()
    built.resize(1000, 600)
    built.show()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 5.0)
    for key in ("versions", "java"):
        page = built.pages.get(key)
        if page is not None and hasattr(page, "refresh"):
            page.refresh()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 15.0)

    # Select an instance so the detail panel is rendered. Without a selection every per-instance control
    # stays hidden, and a hidden control is not one the gate can judge - the six detail tabs would be
    # visited as empty containers and the gate would look green while measuring nothing.
    instances_page = built.pages["instances"]
    instances_page.refresh()
    if instances_page.list.count():
        instances_page.list.setCurrentRow(0)
    app.processEvents()
    yield app, built
    built.close()


def _sub_scopes(page) -> list[tuple[str, object]]:
    """Every sub-page of ``page`` that has to be visited, as (name, container) pairs.

    The container is the widget the sub-page shows, not the page: searching the page for children would
    return controls from *every* tab at once, and ``isVisibleTo`` cannot tell them apart (the tabs are
    stacked but not hidden), so the gate would judge controls that are not rendered. Searching the
    visible sub-page's own container asks exactly the controls the user can see there.
    """
    scopes: list[tuple[str, object]] = []
    tabs = getattr(page, "tabs", None)
    if tabs is not None and hasattr(tabs, "count") and hasattr(tabs, "setCurrentIndex"):
        scopes.extend((f"tab{index}", tabs.widget(index)) for index in range(tabs.count()))
    detail = getattr(page, "detail", None)
    stack = getattr(detail, "stack", None)
    if detail is not None and stack is not None and hasattr(detail, "set_tab"):
        scopes.extend((f"detail{index}", stack.widget(index)) for index in range(stack.count()))
    return scopes


def _is_internal(widget) -> bool:
    """Qt's own sub-widgets of a compound control: not addressable by a user, so not judged."""
    if widget.objectName() in INTERNAL_OBJECT_NAMES:
        return True
    if type(widget).__name__ == "ElidedLabel":  # a QLabel subclass: text, not a control
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


def _accessible_name(widget) -> str:
    """The name a screen reader announces: the explicit one, else what Qt's interface reports.

    Delegates to the walkthrough's own helper, so the report and this gate cannot disagree about what
    counts as a name: the second half matters because Qt derives a name for some controls without
    anything being set - a QCheckBox from its own label, a QSpinBox or QComboBox from the QFormLayout row
    it sits in. Both routes reach the accessibility layer, so both count as named, and a tooltip or a
    placeholder does not (Qt does not pass either on).
    """
    import keyboard_walkthrough

    return keyboard_walkthrough.accessible_name_of(widget)


def _unnamed_controls(scope_root, page, seen: set[int]) -> list[str]:
    """Focusable, user-facing controls inside ``scope_root`` that expose no name at all.

    ``seen`` carries the controls already judged in an earlier scope of the same page: the main page
    contains its sub-pages' containers, so without it every control inside a tab would be judged twice.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    offenders: list[str] = []
    for widget in scope_root.findChildren(QWidget):
        if _is_internal(widget):
            continue
        if widget.focusPolicy() == Qt.FocusPolicy.NoFocus:
            continue
        if not any(widget.inherits(name) for name in INTERACTIVE):
            continue
        if not widget.isVisibleTo(page):
            continue  # not rendered on this sub-page
        if id(widget) in seen:
            continue
        seen.add(id(widget))
        if _accessible_name(widget):
            continue
        offenders.append(
            f"{type(widget).__name__} objectName={widget.objectName() or '-'}"
            f" policy={str(widget.focusPolicy()).split('.')[-1]}"
        )
    return offenders


def _scopes(window_page) -> list[tuple[str, str]]:
    """(page key, sub-page name) for the whole main page and each of its sub-pages."""
    from gui.main_window import NAV_KEYS

    _, built = window_page
    scopes: list[tuple[str, str]] = []
    for key in NAV_KEYS:
        scopes.append((key, "main"))
        scopes.extend((key, name) for name, _container in _sub_scopes(built.pages[key]))
    return scopes


def _select(window_page, key: str, scope: str):
    """Make the requested page and sub-page the rendered one, and return the container to judge."""
    from gui.main_window import NAV_KEYS

    app, built = window_page
    page = built.pages[key]
    built.stack.setCurrentIndex(NAV_KEYS.index(key))
    if scope == "main":
        app.processEvents()
        return page
    if scope.startswith("tab"):
        page.tabs.setCurrentIndex(int(scope[3:]))
        app.processEvents()
        return page.tabs.currentWidget()
    page.detail.set_tab(int(scope[6:]))
    app.processEvents()
    return page.detail.stack.currentWidget()


def test_the_gate_covers_every_page_and_sub_page(window) -> None:
    """Guard the guard: a scope list that silently shrinks would make the gate vacuous."""
    scopes = _scopes(window)
    pages = {key for key, _scope in scopes}
    assert len(pages) == 8, f"expected 8 pages, got {sorted(pages)}"
    # four resource tabs + six per-instance tabs, plus the eight main pages
    assert len(scopes) >= 18, f"only {len(scopes)} scopes: {scopes}"
    from gui.main_window import NAV_KEYS

    assert pages == set(NAV_KEYS), f"pages do not match the navigation: {sorted(pages)}"


def test_no_focusable_control_lacks_an_accessible_name(window) -> None:
    """The hard gate: WCAG 4.1.2 on every page and every sub-page.

    Scope covers the controls the E1 review found unnamed by wrapping them in a layout (the game
    directory and accent fields, the eight accent presets, the instance sort and resource loader combos)
    and the two it found later (the versions table itself, the resource source dropdowns).
    """
    offenders: dict[str, list[str]] = {}
    seen_by_page: dict[str, set[int]] = {}
    for key, scope in _scopes(window):
        container = _select(window, key, scope)
        if container is None:
            continue
        seen = seen_by_page.setdefault(key, set())
        found = _unnamed_controls(container, window[1].pages[key], seen)
        if found:
            offenders[f"{key}/{scope}"] = found
    assert not offenders, "focusable controls with no accessible name:\n" + "\n".join(
        f"  {where}: {', '.join(items)}" for where, items in offenders.items()
    )
