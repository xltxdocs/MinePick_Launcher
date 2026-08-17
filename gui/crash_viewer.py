"""Crash report viewer: scans multiple locations, list + built-in text viewer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from gui import i18n

tr = i18n.tr


def collect_crash_reports(game_dir: Path) -> list[tuple[Path, Path]]:
    """Collect a list of (report file, owning crash-reports dir), newest first by mtime."""
    roots: list[Path] = [game_dir / "crash-reports"]
    for base_name, base in (("instances", game_dir / "instances"), ("versions", game_dir / "versions")):
        if base.exists():
            roots += [p / "crash-reports" for p in base.iterdir() if p.is_dir()]
    found: list[tuple[Path, Path]] = []
    for root in roots:
        if not root.exists():
            continue
        for entry in root.iterdir():
            if entry.is_file() and entry.suffix == ".txt":
                found.append((entry, root))

    def _mtime(pair: tuple[Path, Path]) -> float:
        try:
            return pair[0].stat().st_mtime
        except OSError:  # file was deleted during the scan
            return 0.0

    found.sort(key=_mtime, reverse=True)
    return found


class CrashViewerDialog(QDialog):
    def __init__(self, game_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.game_dir = game_dir
        self.setWindowTitle(tr("crash.title"))
        self.resize(760, 520)
        self.list = QListWidget()
        self.list.setFixedWidth(240)
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        self.open_button = QPushButton(tr("crash.open_folder"))
        self.refresh_button = QPushButton(tr("java.refresh"))

        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        right = QVBoxLayout()
        right.addWidget(self.viewer, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        right.addLayout(buttons)
        body = QHBoxLayout()
        body.addLayout(left)
        body.addLayout(right, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body)

        self.list.currentRowChanged.connect(self._on_select)
        self.refresh_button.clicked.connect(self.refresh)
        self.open_button.clicked.connect(self._open_folder)
        self.refresh()

    def refresh(self) -> None:
        self.reports = collect_crash_reports(self.game_dir)
        self.list.clear()
        if not self.reports:
            self.list.addItem(QListWidgetItem(tr("crash.empty")))
            self.viewer.setPlainText("")
            return
        for report, _root in self.reports:
            self.list.addItem(QListWidgetItem(report.name))
        self.list.setCurrentRow(0)

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self.reports):
            return
        report, _root = self.reports[row]
        try:
            text = report.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = "(read failed)"
        self.viewer.setPlainText(text)

    def _open_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        row = self.list.currentRow()
        if 0 <= row < len(self.reports):
            target = self.reports[row][1]
        else:
            target = self.game_dir / "crash-reports"
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

