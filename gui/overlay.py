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

"""In-window overlay with a blurred, dimmed backdrop and a centred card.

The launcher shows overlays inside its own window instead of separate OS windows
(the crash diagnosis dialog is the first user of this). The backdrop is a snapshot
of the window scaled down and drawn back up: a cheap, stable approximation of a
large-radius Gaussian blur, costing one grab per open instead of compositing the
whole subtree on every frame.

The snapshot is taken once, before the overlay becomes visible, and is simply
rescaled while the window is resized. Re-grabbing a visible overlay would capture
the overlay itself, and hiding it around the grab flickers — freezing the backdrop
is both cheaper and predictable. If grabbing fails, or the caller disables the
blur (the "blur dialogs" setting), the overlay degrades to a plain scrim and never
fails to open.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QVBoxLayout, QWidget

BLUR_DOWNSCALE = 8  # 1/8 scale + smooth upscale reads as a wide Gaussian blur
FADE_MS = 120
SLIDE_MS = 300
SLIDE_PX = 40
CARD_RADIUS = 12
CARD_MARGIN = 25  # keep the card clear of the window edges
CARD_WIDTH = 460

SCRIM = {
    "normal": QColor(0, 0, 0, 90),  # ~35% black, matching the launcher's dialog tint
    "warning": QColor(80, 0, 0, 140),
    "error": QColor(80, 0, 0, 140),
}


class BlurOverlay(QWidget):
    """Full-window overlay: blurred backdrop + dim scrim + one centred card.

    Usage: build the overlay with the window as parent, fill the card through
    `content_layout`, then `show_overlay()`. Closing is button driven (the crash
    dialog's own buttons) or Esc; clicking the backdrop deliberately does nothing,
    so a stray click cannot dismiss a diagnosis the user has not read yet.
    """

    def __init__(
        self,
        parent: QWidget,
        *,
        blur: bool = True,
        severity: str = "normal",
        card_width: int = CARD_WIDTH,
    ) -> None:
        super().__init__(parent)
        self._blur = blur
        self._severity = severity if severity in SCRIM else "normal"
        self._snapshot: QPixmap | None = None
        self._card_width = card_width
        self._card = QWidget(self)
        self._card.setObjectName("overlayCard")
        # The card's look comes from the theme's QSS (`QWidget#overlayCard`, the same way
        # #latestCard is styled): reading the widget palette instead painted a white card in
        # the dark theme, because QSS colours never reach QPalette.
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._content = QVBoxLayout(self._card)
        self._content.setContentsMargins(28, 24, 28, 24)
        self._content.setSpacing(14)
        self._animations: list[QPropertyAnimation] = []
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

    # ---------- public API ----------

    @property
    def content_layout(self) -> QVBoxLayout:
        """Layout the caller fills with the card's widgets."""
        return self._content

    @property
    def snapshot(self) -> QPixmap | None:
        """The downscaled backdrop (None when the blur is off or grabbing failed)."""
        return self._snapshot

    def show_overlay(self) -> None:
        """Show the overlay over the whole window and animate the card in."""
        parent = self.parentWidget()
        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())
        self.rebuild_snapshot()
        self._place_card()
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._animate_in()

    def hide_overlay(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        self.hide()

    def rebuild_snapshot(self) -> None:
        """Grab and downscale the window; silently degrade to a plain scrim on failure."""
        parent = self.parentWidget()
        self._snapshot = None
        if not self._blur or parent is None:
            return
        pixmap = parent.grab()
        if pixmap.isNull() or pixmap.width() < BLUR_DOWNSCALE or pixmap.height() < BLUR_DOWNSCALE:
            return
        self._snapshot = pixmap.scaled(
            max(1, pixmap.width() // BLUR_DOWNSCALE),
            max(1, pixmap.height() // BLUR_DOWNSCALE),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # ---------- geometry ----------

    def _card_rect(self):
        from PySide6.QtCore import QRect

        available_h = max(120, self.height() - 2 * CARD_MARGIN)
        # Long translations (German buttons, French hints) need more room than the default width:
        # grow with the content, but never past the window minus the margins.
        wanted = max(self._card_width, self._card.sizeHint().width())
        width = min(wanted, max(200, self.width() - 2 * CARD_MARGIN))
        height = min(self._card.sizeHint().height(), available_h)
        x = (self.width() - width) // 2
        y = max(CARD_MARGIN, (self.height() - height) // 2)
        return QRect(x, y, width, height)

    def _place_card(self) -> None:
        rect = self._card_rect()
        self._card.setGeometry(rect)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_card()

    def eventFilter(self, obj, event) -> bool:
        """Keep the overlay glued to the window it covers."""
        parent = self.parentWidget()
        if obj is parent and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Show,
        ):
            self.setGeometry(parent.rect())
            self._place_card()
        return False

    # ---------- painting ----------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._snapshot is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(self.rect(), self._snapshot)
        painter.fillRect(self.rect(), SCRIM[self._severity])

    # ---------- interaction ----------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_overlay()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        # Swallow clicks so they neither dismiss the overlay nor reach the page below
        event.accept()

    def _animate_in(self) -> None:
        """Fade and slide the card in; the backdrop stays static (fading it is laggy)."""
        effect = QGraphicsOpacityEffect(self._card)
        self._card.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self._card)
        fade.setDuration(FADE_MS)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade.finished.connect(lambda: self._card.setGraphicsEffect(None))

        target = self._card_rect()
        self._card.move(target.x(), target.y() - SLIDE_PX)
        slide = QPropertyAnimation(self._card, b"pos", self._card)
        slide.setDuration(SLIDE_MS)
        slide.setStartValue(self._card.pos())
        slide.setEndValue(target.topLeft())
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        for animation in (fade, slide):
            animation.start(QPropertyAnimation.DeletionPolicy.KeepWhenStopped)
        self._animations = [fade, slide]  # keep references: a GC'd animation never finishes
