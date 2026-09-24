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

"""Small glyph icons drawn at runtime with QPainter.

Icon-only buttons need artwork the launcher does not ship, and the theme's colours live in the QSS
(which, as [P24] records, never reaches QPalette). Painting the glyphs from the theme's accent
colour therefore has three advantages: they follow the user's accent choice, they need no asset per
theme, and they cannot fail to load in a packaged build (no SVG plugin, no missing file).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_CACHE: dict[tuple[str, int, str], QIcon] = {}
KINDS = ("account", "instances", "settings")


def accent_color() -> str:
    """The accent colour of the active theme (the default one when the config cannot be read)."""
    try:
        from gui import theme
        from launcher import config

        cfg, _ = config.load()
        return theme.accent_palette(theme.resolve_theme(cfg.theme), cfg.accent_color)["ACCENT"]
    except Exception:  # noqa: BLE001 - an icon colour must never break a page
        return "#35a06a"


def icon(kind: str, size: int = 20, color: str | None = None) -> QIcon:
    """A cached QIcon for `kind`; unknown kinds return an empty icon instead of raising."""
    accent = color or accent_color()
    key = (kind, size, accent)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    drawer = _DRAWERS.get(kind)
    if drawer is not None:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(accent))
        pen.setWidthF(max(1.4, size / 11.0))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        drawer(painter, float(size))
        painter.end()

    result = QIcon(pixmap)
    _CACHE[key] = result
    return result


def clear_cache() -> None:
    """Drop the cache (the theme or accent changed, so the colours are stale)."""
    _CACHE.clear()


# ---------- glyphs (drawn in a size x size box) ----------


def _account(painter: QPainter, size: float) -> None:
    """A head plus shoulders."""
    head = QRectF(size * 0.32, size * 0.18, size * 0.36, size * 0.36)
    painter.drawEllipse(head)
    body = QPainterPath()
    body.moveTo(size * 0.20, size * 0.84)
    body.cubicTo(
        QPointF(size * 0.22, size * 0.56),
        QPointF(size * 0.78, size * 0.56),
        QPointF(size * 0.80, size * 0.84),
    )
    painter.drawPath(body)


def _instances(painter: QPainter, size: float) -> None:
    """Three stacked rows: a list of instances."""
    for index, y in enumerate((0.28, 0.50, 0.72)):
        painter.drawLine(
            QPointF(size * 0.22, size * y), QPointF(size * 0.78, size * y)
        )
        painter.drawPoint(QPointF(size * 0.22, size * y))
        if index == 0:
            continue


def _settings(painter: QPainter, size: float) -> None:
    """A gear: outer ring, eight teeth, inner hole."""
    center = QPointF(size / 2.0, size / 2.0)
    radius = size * 0.24
    painter.drawEllipse(center, radius, radius)
    painter.drawEllipse(center, size * 0.09, size * 0.09)
    for step in range(8):
        angle = step * 45.0
        painter.save()
        painter.translate(center)
        painter.rotate(angle)
        painter.drawLine(QPointF(0.0, -radius), QPointF(0.0, -size * 0.40))
        painter.restore()


_DRAWERS = {"account": _account, "instances": _instances, "settings": _settings}
