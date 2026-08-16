"""主题应用（#30）：深色 / 浅色 QSS 切换，立即生效。"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from launcher import paths


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    filename = "style_light.qss" if theme == "light" else "style.qss"
    path = paths.resource_path("gui/resources/" + filename)
    if path.exists():
        app.setStyleSheet(path.read_text(encoding="utf-8"))
