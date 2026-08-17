"""Theme application: dark / light QSS switch, takes effect immediately."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from launcher import paths


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    filename = "style_light.qss" if theme == "light" else "style.qss"
    path = paths.resource_path("gui/resources/" + filename)
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # url() in QSS cannot reliably resolve relative paths: replace with the image's absolute path when loading
    arrow = "down_arrow_light.png" if theme == "light" else "down_arrow.png"
    arrow_path = paths.resource_path("gui/resources/" + arrow)
    text = text.replace("__DOWN_ARROW__", arrow_path.as_posix())
    check_path = paths.resource_path("gui/resources/check.png")
    text = text.replace("__CHECK__", check_path.as_posix())
    app.setStyleSheet(text)
