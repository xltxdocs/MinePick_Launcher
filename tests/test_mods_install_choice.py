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

"""WCAG 2.5.1 / 2.5.7: installing mods must not require dragging.

Dropping jars onto the mods table is a pointer gesture. The mods tab therefore offers a file-picker
button that feeds the same ``install_dropped`` path, so the two routes cannot drift apart. These
tests check that route and the button that reaches it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.pages import instance_detail as detail_module
from gui.pages.instance_detail import InstanceDetail


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


_ANY_INSTANCE = object()


def _stub(resolved=_ANY_INSTANCE):
    """Bare object good enough for the two attributes the method touches."""
    calls: list[list[Path]] = []
    stub = SimpleNamespace(
        resolved=resolved,
        install_dropped=lambda jars: calls.append(jars),
    )
    return stub, calls


def test_chosen_files_go_through_the_same_path_as_a_drop(monkeypatch, ws_tmp):
    stub, calls = _stub()
    chosen = [str(ws_tmp / "a.jar"), str(ws_tmp / "b.jar")]
    monkeypatch.setattr(
        detail_module.QFileDialog, "getOpenFileNames", lambda *a, **k: (chosen, "")
    )
    InstanceDetail.choose_mod_files(stub)
    assert len(calls) == 1
    assert calls[0] == [Path(chosen[0]), Path(chosen[1])]


def test_cancelling_the_dialog_installs_nothing(monkeypatch):
    stub, calls = _stub()
    monkeypatch.setattr(detail_module.QFileDialog, "getOpenFileNames", lambda *a, **k: ([], ""))
    InstanceDetail.choose_mod_files(stub)
    assert calls == []


def test_without_an_instance_it_explains_instead_of_opening_a_dialog(monkeypatch):
    stub, calls = _stub(resolved=None)
    statuses: list[tuple[str, object]] = []
    monkeypatch.setattr(
        detail_module, "set_app_status", lambda widget, text, level=None: statuses.append((text, level))
    )
    opened: list[bool] = []
    monkeypatch.setattr(
        detail_module.QFileDialog,
        "getOpenFileNames",
        lambda *a, **k: (opened.append(True), ([], ""))[1],
    )
    InstanceDetail.choose_mod_files(stub)
    assert opened == []
    assert statuses and statuses[0][0]  # a real, translated hint - not an empty string
    assert calls == []


def test_mods_tab_has_a_keyboard_reachable_install_button(app):
    """The equivalent of the drag gesture must be reachable without a pointer."""
    detail = InstanceDetail()
    try:
        button = detail.mods_install_button
        assert button.isEnabled()
        assert button.text().strip(), "an unnamed button is unusable with a screen reader"
        assert button.focusPolicy() != Qt.FocusPolicy.NoFocus, "keyboard users must be able to reach it"
        seen: list[bool] = []
        button.clicked.disconnect()
        button.clicked.connect(lambda: seen.append(True))
        button.click()
        assert seen == [True]
    finally:
        detail.deleteLater()
        app.processEvents()
