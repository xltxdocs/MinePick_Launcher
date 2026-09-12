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

"""First-run wizard drawn inside the main window instead of a separate dialog.

The wizard is an overlay: the window frame, sidebar and page stack stay where they are, the
overlay simply covers the content area until the user finishes (or skips). All texts are passed
in by the caller, so this module holds no translations and no launcher logic — it only lays out
the cards, the step indicator and the (restrained) transitions.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

FADE_MS = 180
LIFT_PX = 8


@dataclass
class WizardStep:
    """One page of the wizard: heading, explanation and the widget the caller provides."""

    title: str
    description: str
    widget: QWidget


class StepDots(QWidget):
    """Small step indicator: one dot per step, the current one filled with the accent colour."""

    def __init__(self, count: int) -> None:
        super().__init__()
        self.setObjectName("wizardDots")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._dots = []
        for _ in range(count):
            dot = QLabel()
            dot.setObjectName("wizardDot")
            dot.setFixedSize(8, 8)
            self._dots.append(dot)
            layout.addWidget(dot)
        layout.addStretch(1)

    def set_current(self, index: int) -> None:
        for position, dot in enumerate(self._dots):
            dot.setProperty("current", position == index)
            style = dot.style()
            style.unpolish(dot)
            style.polish(dot)


class WizardOverlay(QWidget):
    """Full-area overlay with a card per step, Back / Next / Skip and a short fade per step."""

    finished = Signal()

    def __init__(self, parent: QWidget, steps: list[WizardStep], labels: dict[str, str]) -> None:
        super().__init__(parent)
        self.setObjectName("wizardOverlay")
        self._steps = steps
        self._labels = labels
        self._index = 0
        self._animation: QPropertyAnimation | None = None

        self.dots = StepDots(len(steps))
        self.heading = QLabel()
        self.heading.setObjectName("wizardHeading")
        self.description = QLabel()
        self.description.setObjectName("wizardDescription")
        self.description.setWordWrap(True)

        self.pages = QStackedWidget()
        for step in steps:
            self.pages.addWidget(step.widget)

        self.back_button = QPushButton(labels["back"])
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.go_back)
        self.next_button = QPushButton(labels["next"])
        self.next_button.clicked.connect(self.go_next)
        self.skip_button = QPushButton(labels["skip"])
        self.skip_button.setObjectName("secondaryButton")
        self.skip_button.clicked.connect(self.finish)

        card = QWidget()
        card.setObjectName("wizardCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 24)
        card_layout.setSpacing(12)
        card_layout.addWidget(self.dots)
        card_layout.addWidget(self.heading)
        card_layout.addWidget(self.description)
        card_layout.addWidget(self.pages, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        card_layout.addLayout(buttons)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(34, 26, 34, 26)
        outer.addWidget(card, 1)

        self._sync()

    # ---------- navigation ----------

    def go_back(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._sync(fade=True)

    def go_next(self) -> None:
        if self._index < len(self._steps) - 1:
            self._index += 1
            self._sync(fade=True)
        else:
            self.finish()

    def finish(self) -> None:
        self.fade_out(lambda: self.finished.emit())

    def _sync(self, fade: bool = False) -> None:
        step = self._steps[self._index]
        self.heading.setText(step.title)
        self.description.setText(step.description)
        self.dots.set_current(self._index)
        self.pages.setCurrentIndex(self._index)
        self.back_button.setEnabled(self._index > 0)
        last = self._index == len(self._steps) - 1
        self.next_button.setText(self._labels["done"] if last else self._labels["next"])
        if fade:
            self._fade_page(step.widget)

    # ---------- restrained animation: fade + a small lift ----------

    def _fade_page(self, page: QWidget) -> None:
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(FADE_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation

    def show_overlay(self) -> None:
        """Fade the whole overlay in over the content area."""
        self.show()
        self.raise_()
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(FADE_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: self.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation

    def fade_out(self, then) -> None:
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(FADE_MS)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InCubic)
        animation.finished.connect(lambda: (self.setGraphicsEffect(None), self.hide(), then()))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation

    def resizeEvent(self, event) -> None:  # keep covering the whole content area
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:
        event.accept()  # swallow clicks so the covered UI cannot be used
        if event.button() == Qt.MouseButton.LeftButton:
            return
