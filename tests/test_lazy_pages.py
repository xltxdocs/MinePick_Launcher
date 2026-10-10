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

"""Pages are built on first visit, and iterating still means "give me all of them".

Startup used to construct all eight pages (1457 widgets in the real window) before the window appeared,
and the application stylesheet polished every one of them. These tests pin both halves of the contract:
the first page is built at startup, and the audits/tests that walk every page keep getting all eight.
"""

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gui.main_window import NAV_KEYS, MainWindow


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Same three stubs tests/test_gui.py installs: no network, no Java probing subprocess."""
    def _fail(**kw):
        raise RuntimeError("offline test")

    monkeypatch.setattr("gui.pages.versions_page.fetch_manifest", _fail)
    monkeypatch.setattr("launcher.mods.modrinth._client", _fail)
    monkeypatch.setattr("gui.pages.java_page.list_java", lambda *a, **kw: [])


@pytest.fixture
def window(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "lazy"))
    built = MainWindow()
    yield built
    # Destroy the window here, under our own control, instead of leaving it to the garbage collector: a
    # wrapper whose C++ object is already gone must not be collected later, during another test's
    # allocation. A download test several files away used to abort exactly that way.
    built.close()
    built.deleteLater()
    app.processEvents()
    gc.collect()


def test_startup_builds_only_the_first_page(window):
    assert window.pages.built_keys() == ("launch",)
    assert window.stack.count() == 1
    assert window.stack.currentWidget() is window.pages["launch"]


def test_visiting_a_page_builds_exactly_that_page(window, app):
    window.sidebar.setCurrentRow(NAV_KEYS.index("settings"))
    app.processEvents()
    assert set(window.pages.built_keys()) == {"launch", "settings"}
    assert window.stack.currentWidget() is window.pages["settings"]


def test_repeat_visits_do_not_rebuild(window, app):
    first = window.pages["java"]
    window.sidebar.setCurrentRow(NAV_KEYS.index("java"))
    app.processEvents()
    window.sidebar.setCurrentRow(0)
    app.processEvents()
    window.sidebar.setCurrentRow(NAV_KEYS.index("java"))
    app.processEvents()
    assert window.pages["java"] is first


def test_iteration_materialises_every_page(window):
    # the quality audits and several tests walk the registry on purpose: that must yield all eight
    keys = [key for key in window.pages]
    assert keys == list(NAV_KEYS)
    assert len(window.pages) == len(NAV_KEYS)
    assert [key for key, _ in window.pages.items()] == list(NAV_KEYS)
    assert window.pages.built_keys() == tuple(NAV_KEYS)
    assert window.stack.count() == len(NAV_KEYS)


def test_peek_does_not_build(window):
    assert window.pages.peek("about") is None
    assert window.pages.built_keys() == ("launch",)
    assert window.pages.peek("launch") is window.pages["launch"]


def test_get_with_an_unknown_key_returns_the_default(window):
    assert window.pages.get("nope") is None
    assert window.pages.get("nope", "fallback") == "fallback"
    assert window.pages.built_keys() == ("launch",)  # a miss must not build anything


def test_rebuild_after_a_language_switch_drops_pages(window, app):
    window.sidebar.setCurrentRow(NAV_KEYS.index("versions"))
    app.processEvents()
    assert "versions" in window.pages.built_keys()

    window.build_pages()
    app.processEvents()
    # only the page that is shown again exists; the rest will be rebuilt in the new language on demand
    assert window.pages.built_keys() == ("launch",)
    assert window.stack.count() == 1
    # The pages removed above were deleted for real when the event loop ran, so their wrappers have to be
    # collected here as well. Left to a later test's garbage collection, one of them aborted the process.
    gc.collect()


def test_account_change_still_reaches_the_launch_page(window, monkeypatch):
    launch = window.pages["launch"]
    account = window.pages["account"]
    calls = []
    monkeypatch.setattr(launch, "refresh_account", lambda: calls.append("refresh_account"))

    account.account_changed.emit()

    assert calls == ["refresh_account"]


def test_launch_account_change_still_reaches_the_account_page(window, monkeypatch):
    launch = window.pages["launch"]
    account = window.pages["account"]
    calls = []
    monkeypatch.setattr(account, "refresh", lambda: calls.append("refresh"))

    launch.account_changed.emit()

    assert calls == ["refresh"]


def test_versions_change_still_reaches_the_launch_page(window, monkeypatch):
    launch = window.pages["launch"]
    versions = window.pages["versions"]
    calls = []
    monkeypatch.setattr(launch, "refresh_versions", lambda: calls.append("refresh_versions"))

    versions.versions_changed.emit()

    assert calls == ["refresh_versions"]


def test_settings_change_still_reaches_the_window(window, monkeypatch):
    settings = window.pages["settings"]
    calls = []
    monkeypatch.setattr(window, "_on_settings_changed", lambda: calls.append("settings_changed"))

    settings.settings_changed.emit()

    assert calls == ["settings_changed"]


def test_wiring_does_not_build_the_peer_page(window):
    # connecting account's signal must not drag the launch page in: the slot resolves it at signal time
    window.build_pages()
    window.pages["account"]  # building the account page wires its outgoing signal
    assert set(window.pages.built_keys()) == {"launch", "account"}


def test_the_window_minimum_does_not_grow_when_pages_are_built(window, app):
    before = (window.minimumWidth(), window.minimumHeight(), window.minimumSizeHint().height())
    for index in range(len(NAV_KEYS)):
        window.sidebar.setCurrentRow(index)
        app.processEvents()
    after = (window.minimumWidth(), window.minimumHeight(), window.minimumSizeHint().height())
    assert before == after, "the window floor must not depend on which pages have been visited"
    assert (window.minimumWidth(), window.minimumHeight()) == (1000, 610)
