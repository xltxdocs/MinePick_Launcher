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

"""Crash diagnosis dialog: opens on the overlay, never for a clean exit, Esc closes it."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from gui.dialogs.crash_dialog import (
    CrashDiagnosisDialog,
    context_for_launch,
    diagnose_after_exit,
)

SAMPLES = Path(__file__).parent / "data" / "crash_samples"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _game_with_log(ws_tmp: Path, sample: str) -> Path:
    """A game directory whose logs/latest.log is one of the sample logs."""
    game = ws_tmp / "mc"
    logs = game / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SAMPLES / sample, logs / "latest.log")
    return game


def test_clean_exit_never_pops_a_dialog(app, ws_tmp):
    game = ws_tmp / "mc"
    game.mkdir(parents=True, exist_ok=True)
    window = QWidget()
    try:
        context = context_for_launch(game_dir=game, exit_code=0, started=0.0)
        assert diagnose_after_exit(window, context) is None
    finally:
        window.close()


def test_auto_analysis_off_never_pops_a_dialog(app, ws_tmp):
    game = _game_with_log(ws_tmp, "oom.latest.log")
    window = QWidget()
    try:
        context = context_for_launch(
            version_id="1.20.1", game_dir=game, exit_code=1, started=0.0
        )
        assert diagnose_after_exit(window, context, auto_analyse=False) is None
    finally:
        window.close()


def test_failing_exit_shows_the_diagnosis(app, ws_tmp):
    game = _game_with_log(ws_tmp, "oom.latest.log")
    window = QWidget()
    window.resize(800, 600)
    window.show()
    app.processEvents()
    dialog = None
    try:
        context = context_for_launch(
            version_id="1.20.1", game_dir=game, exit_code=1, started=0.0
        )
        dialog = diagnose_after_exit(window, context, blur=False)
        assert dialog is not None
        app.processEvents()
        assert dialog.overlay.isVisible()
        assert dialog.code_label.text().startswith("MPL-")
        assert dialog.body_label.text()  # the localized explanation is not empty
        labels = {b.text() for b in dialog.overlay.findChildren(QPushButton)}
        assert len(labels) == 4  # dismiss / open log / export / copy
        QTest.keyClick(dialog.overlay, Qt.Key.Key_Escape)
        assert not dialog.overlay.isVisible()
    finally:
        if dialog is not None:
            dialog.close()
        window.close()


def test_record_and_load_diagnosis_roundtrip(app, ws_tmp):
    """The recorded summary survives a restart and tolerates a missing or corrupt file."""
    from gui.dialogs.crash_dialog import load_recorded_diagnosis, record_diagnosis
    from launcher.diagnostics import diagnose

    game = _game_with_log(ws_tmp, "oom.latest.log")
    diagnosis = diagnose(context_for_launch(game_dir=game, exit_code=1, started=0.0))
    folder = ws_tmp / "instance"
    written = record_diagnosis(folder, diagnosis)
    assert written is not None and written.is_file()

    record = load_recorded_diagnosis(folder)
    assert record is not None
    assert record["code"] == diagnosis.code
    assert record["lines"] and record["recorded_at"]

    assert load_recorded_diagnosis(ws_tmp / "nothing-here") is None
    (folder / "diagnosis.json").write_text("{ not json", encoding="utf-8")
    assert load_recorded_diagnosis(folder) is None


def test_diagnostics_tab_shows_the_recorded_code(app, ws_tmp, monkeypatch):
    """The instance's diagnosis tab reads diagnosis.json and shows code plus summary."""
    import json

    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_diag"))
    from launcher import config as config_mod

    game = ws_tmp / "mc"
    version_id = "1.20.1"
    folder = game / "versions" / version_id
    folder.mkdir(parents=True)
    (folder / (version_id + ".json")).write_text(
        json.dumps({"id": version_id}), encoding="utf-8"
    )
    (folder / "diagnosis.json").write_text(
        json.dumps(
            {
                "code": "MPL-Crash-0107",
                "phase": "fatal",
                "confidence": "high",
                "recorded_at": 1.0,
                "lines": ["可能原因：内存不足", "建议：调高内存上限"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cfg, cfg_path = config_mod.load()
    cfg.game_dir = game
    config_mod.save(cfg, cfg_path)

    from gui.main_window import MainWindow
    from gui.pages.instance_detail import TAB_DIAGNOSIS

    window = None
    try:
        window = MainWindow()
        page = window.pages["instances"]
        page.list.setCurrentRow(0)
        app.processEvents()
        detail = page.detail
        detail.set_tab(TAB_DIAGNOSIS)
        app.processEvents()
        assert detail.diagnosis_code.text() == "MPL-Crash-0107"
        assert "内存不足" in detail.diagnosis_body.text()
        assert detail.diagnosis_empty.isVisible() is False
        assert detail.diagnosis_copy_button.isEnabled() is True
        detail.copy_diagnosis()
        assert "MPL-Crash-0107" in QApplication.clipboard().text()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_dialog_renders_from_a_prepared_diagnosis(app, ws_tmp):
    """The dialog itself takes any diagnosis: build one directly from the knowledge base."""
    from launcher.diagnostics import diagnose

    game = _game_with_log(ws_tmp, "mixin_failure.latest.log")
    window = QWidget()
    window.resize(700, 500)
    window.show()
    app.processEvents()
    dialog = None
    try:
        diagnosis = diagnose(
            context_for_launch(version_id="1.20.1", game_dir=game, exit_code=1, started=0.0)
        )
        dialog = CrashDiagnosisDialog(window, diagnosis, blur=False)
        dialog.show()
        app.processEvents()
        assert dialog.code_label.text() == diagnosis.code
        assert dialog.body_label.text().splitlines() == dialog._body_lines
    finally:
        if dialog is not None:
            dialog.close()
        window.close()
