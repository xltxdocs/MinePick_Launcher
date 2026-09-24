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

"""Crash / launch-failure diagnosis dialog, drawn on the blurred in-window overlay.

The content comes from the Qt-free knowledge base (`launcher.diagnostics`): the
engine decides the error code and the findings, `render_lines()` turns them into
localized text, and this module only lays that out and wires the actions. Nothing
here talks to the network, and the exported report is sanitized by the core
before it is written.

Buttons: dismiss, open the log file, export a diagnosis report, copy the code
and summary. Clicking the backdrop never dismisses the dialog; Esc does.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.overlay import BlurOverlay
from gui.widgets import set_app_status
from launcher.diagnostics import (
    Diagnosis,
    export_report,
    render_lines,
)

# Phases that mean "the launcher itself failed" rather than "the game crashed"
LAUNCHER_PHASES = ("launcher",)


class CrashDiagnosisDialog:
    """Owns one overlay + card for a single diagnosis. Create, then `show()`."""

    def __init__(
        self,
        window: QWidget,
        diagnosis: Diagnosis,
        *,
        log_path: Path | None = None,
        blur: bool = True,
    ) -> None:
        self._window = window
        self._diagnosis = diagnosis
        self._log_path = log_path
        self._overlay = BlurOverlay(window, blur=blur, severity=self._severity())
        self._body_lines = render_lines(diagnosis, i18n.tr)
        self._build()

    # ---------- public ----------

    @property
    def overlay(self) -> BlurOverlay:
        return self._overlay

    @property
    def code_label(self) -> QLabel:
        return self._code_label

    @property
    def body_label(self) -> QLabel:
        return self._body_label

    def show(self) -> None:
        self._overlay.show_overlay()

    def close(self) -> None:
        self._overlay.hide_overlay()

    # ---------- construction ----------

    def _severity(self) -> str:
        """Red scrim for launcher-side failures; plain dim for everything else."""
        if self._diagnosis.phase in LAUNCHER_PHASES:
            return "error"
        low = self._diagnosis.confidence == "low" or not self._diagnosis.analysable
        return "warning" if low else "error"

    def _build(self) -> None:
        layout: QVBoxLayout = self._overlay.content_layout

        self._title_label = QLabel(i18n.tr("diagnosis.dialog.title"))
        self._title_label.setObjectName("title")
        layout.addWidget(self._title_label)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._code_label = QLabel(self._diagnosis.code)
        self._code_label.setObjectName("overlayCode")
        self._code_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        head.addWidget(self._code_label)
        head.addStretch(1)
        layout.addLayout(head)

        self._body_label = QLabel("\n".join(self._body_lines))
        self._body_label.setObjectName("overlayBody")
        self._body_label.setWordWrap(True)
        self._body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._body_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        area = QScrollArea()
        area.setObjectName("overlayScroll")
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(self._body_label)
        area.setMinimumHeight(160)
        area.setMaximumHeight(320)
        layout.addWidget(area, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self._log_button = QPushButton(i18n.tr("diagnosis.dialog.open_log"))
        self._log_button.setObjectName("secondaryButton")
        self._log_button.setEnabled(self._log_path is not None and Path(self._log_path).exists())
        self._log_button.clicked.connect(self._open_log)
        self._export_button = QPushButton(i18n.tr("diagnosis.dialog.export"))
        self._export_button.setObjectName("secondaryButton")
        self._export_button.clicked.connect(self._export)
        self._copy_button = QPushButton(i18n.tr("diagnosis.dialog.copy"))
        self._copy_button.setObjectName("secondaryButton")
        self._copy_button.clicked.connect(self._copy)
        dismiss = QPushButton(i18n.tr("diagnosis.dialog.dismiss"))
        dismiss.setObjectName("primaryButton")
        dismiss.clicked.connect(self.close)
        for button in (self._log_button, self._export_button, self._copy_button, dismiss):
            buttons.addWidget(button)
        layout.addLayout(buttons)

    # ---------- actions ----------

    def _open_log(self) -> None:
        if self._log_path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_path)))

    def _copy(self) -> None:
        summary = self._diagnosis.code + "\n" + "\n".join(self._body_lines)
        QGuiApplication.clipboard().setText(summary)
        set_app_status(self._window, i18n.tr("diagnosis.dialog.copied", self._diagnosis.code))

    def _export(self) -> None:
        import time

        suggested = f"MinePick-{self._diagnosis.code}-{time.strftime('%Y%m%d-%H%M%S')}.zip"
        target, _selected = QFileDialog.getSaveFileName(
            self._window, i18n.tr("diagnosis.dialog.export"), suggested, "*.zip"
        )
        if not target:
            return
        try:
            export_report(Path(target), self._diagnosis, translate=i18n.tr)
        except OSError as exc:  # the report is best-effort: never block the dialog on it
            from gui.errors import show_fatal

            show_fatal(self._window, i18n.tr("diagnosis.dialog.export_failed", str(exc)))
            return
        set_app_status(self._window, i18n.tr("diagnosis.dialog.exported", target))


def diagnose_after_exit(
    window: QWidget,
    context,
    *,
    log_path: Path | None = None,
    blur: bool = True,
    auto_analyse: bool = True,
) -> CrashDiagnosisDialog | None:
    """Run the knowledge base for a finished launch and show the dialog.

    Returns None when automatic analysis is switched off in the settings, and also
    when nothing was analysable *and* the process exited cleanly (or never ran):
    a normal game exit must never pop a dialog. A non-zero exit with no logs at all
    still gets the "nothing to analyse" message, because that failure is worth
    showing even when there is nothing to read.
    """
    if not auto_analyse:
        return None
    from launcher.diagnostics import diagnose

    diagnosis = diagnose(context)
    if not diagnosis.analysable and diagnosis.exit_code in (0, None):
        return None
    dialog = CrashDiagnosisDialog(window, diagnosis, log_path=log_path, blur=blur)
    dialog.show()
    return dialog


def context_for_launch(
    *,
    version_id: str = "",
    game_dir: Path | None = None,
    launch_dir: Path | None = None,
    exit_code: int | None = None,
    started: float | None = None,
    tail=(),
    instance=None,
    error_text: str = "",
    memory_gb: float | None = None,
    java_major: int | None = None,
    java_path: Path | None = None,
):
    """Build the knowledge-base context from what a page happens to know."""
    from launcher.diagnostics import DiagnosisContext

    return DiagnosisContext(
        version_id=version_id,
        game_dir=Path(game_dir) if game_dir else None,
        launch_dir=Path(launch_dir) if launch_dir else None,
        instance=instance,
        exit_code=exit_code,
        launch_started_at=started or 0.0,
        captured_output=tuple(tail or ()),
        error_text=error_text,
        memory_gb=memory_gb,
        java_major=java_major,
        java_path=Path(java_path) if java_path else None,
    )


__all__ = ["CrashDiagnosisDialog", "context_for_launch", "diagnose_after_exit"]
