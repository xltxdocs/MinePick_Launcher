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

Layout: a step rail on the left (done = tick, current = accent, later = muted), the current
step on the right, and a fixed action bar at the bottom. Texts are injected by the caller, so
this module holds no translations and no launcher logic — it only lays out the steps, the
tiled option pickers and the restrained transitions (fade in/out, step fade + small lift).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

FADE_MS = 90  # step content only: cheap, one small subtree
LIFT_PX = 8


@dataclass
class WizardStep:
    """One page of the wizard: rail label, heading, explanation and the caller's widget."""

    title: str
    description: str
    widget: QWidget
    rail: str = ""


def _styled(widget: QWidget) -> QWidget:
    """Let a plain QWidget actually paint its QSS background (Qt needs the attribute)."""
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    return widget


class StepRail(QWidget):
    """Vertical list of the steps: tick when done, accent while current, muted afterwards."""

    def __init__(self, labels: list[str]) -> None:
        super().__init__()
        self.setObjectName("wizardRail")
        _styled(self)
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 14, 18)
        layout.setSpacing(4)
        self._items: list[QLabel] = []
        for index, text in enumerate(labels):
            item = QLabel(f"{index + 1}.  {text}")
            item.setObjectName("wizardRailItem")
            self._items.append(item)
            layout.addWidget(item)
        layout.addStretch(1)

    def set_current(self, index: int) -> None:
        for position, item in enumerate(self._items):
            state = "current" if position == index else ("done" if position < index else "todo")
            if position < index and not item.text().startswith("✓"):
                item.setText("✓  " + item.text().split("  ", 1)[-1])
            item.setProperty("state", state)
            style = item.style()
            style.unpolish(item)
            style.polish(item)


class OptionGrid(QWidget):
    """Tiled radio-like picker: every option is one cell, the chosen one is highlighted."""

    selected = Signal(str)

    def __init__(self, options: list[tuple[str, str]], columns: int = 3) -> None:
        super().__init__()
        self.setObjectName("wizardOptions")
        self._buttons: dict[str, QPushButton] = {}
        self._value = options[0][0] if options else ""

        inner = QWidget()
        inner.setObjectName("wizardOptionsInner")
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        for position, (value, label) in enumerate(options):
            button = QPushButton(label)
            button.setObjectName("wizardOption")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, v=value: self.set_value(v, emit=True))
            grid.addWidget(button, position // columns, position % columns)
            self._buttons[value] = button

        scroll = QScrollArea()
        scroll.setObjectName("wizardOptionsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.set_value(self._value)

    def set_value(self, value: str, emit: bool = False) -> None:
        self._value = value
        for key, button in self._buttons.items():
            button.setChecked(key == value)
            button.setProperty("selected", key == value)
            style = button.style()
            style.unpolish(button)
            style.polish(button)
        if emit:
            self.selected.emit(value)

    def value(self) -> str:
        return self._value


class BulletList(QWidget):
    """Short list of bullet points, used to fill the welcome step."""

    def __init__(self, points: list[str]) -> None:
        super().__init__()
        self.setObjectName("wizardBullets")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for point in points:
            label = QLabel("•   " + point)
            label.setObjectName("wizardBullet")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch(1)


class WizardOverlay(QWidget):
    """Overlay with a step rail, one card per step and a fixed action bar."""

    finished = Signal()

    def __init__(self, parent: QWidget, steps: list[WizardStep], labels: dict[str, str]) -> None:
        super().__init__(parent)
        self.setObjectName("wizardOverlay")
        _styled(self)
        self._steps = steps
        self._labels = labels
        self._index = 0
        self._animation: QPropertyAnimation | None = None

        self.rail = StepRail([step.rail or step.title for step in steps])
        self.heading = QLabel()
        self.heading.setObjectName("wizardHeading")
        self.description = QLabel()
        self.description.setObjectName("wizardDescription")
        self.description.setWordWrap(True)

        self.pages = QStackedWidget()
        for step in steps:
            self.pages.addWidget(step.widget)

        right = QWidget()
        right.setObjectName("wizardContent")
        _styled(right)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(30, 24, 30, 12)
        right_layout.setSpacing(10)
        right_layout.addWidget(self.heading)
        right_layout.addWidget(self.description)
        right_layout.addWidget(self.pages, 1)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.rail)
        body.addWidget(right, 1)

        self.back_button = QPushButton(labels["back"])
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.go_back)
        self.next_button = QPushButton(labels["next"])
        self.next_button.clicked.connect(self.go_next)
        self.skip_button = QPushButton(labels["skip"])
        self.skip_button.setObjectName("secondaryButton")
        self.skip_button.clicked.connect(self.finish)

        actions = QWidget()
        actions.setObjectName("wizardActionBar")
        _styled(actions)
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(30, 12, 30, 14)
        action_layout.setSpacing(10)
        action_layout.addWidget(self.skip_button)
        action_layout.addStretch(1)
        action_layout.addWidget(self.back_button)
        action_layout.addWidget(self.next_button)

        card = QWidget()
        card.setObjectName("wizardCard")
        _styled(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addLayout(body, 1)
        card_layout.addWidget(actions)

        # the card fills the whole overlay: any margin here would be a strip where the
        # window behind shows the same colour and reads as "not covered"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card, 1)  # stretch: the card must fill the overlay, top to bottom

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
        self.rail.set_current(self._index)
        self.pages.setCurrentIndex(self._index)
        self.back_button.setEnabled(self._index > 0)
        last = self._index == len(self._steps) - 1
        self.next_button.setText(self._labels["done"] if last else self._labels["next"])
        if fade:
            self._fade_page(step.widget)

    # ---------- restrained animation ----------

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
        """Show the overlay over the content area below the title bar.

        No opacity effect here on purpose: fading a subtree this large had to be composited
        offscreen every frame (visibly laggy) and left the overlay see-through while it ran.
        """
        parent = self.parentWidget()
        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())  # correct size even before the first resize event
        self._fit_parent()
        self.setGraphicsEffect(None)
        self.show()
        self.raise_()

    def fade_out(self, then) -> None:
        """Hide at once, then let the caller rebuild: no fade to sit through while it works."""
        self.setGraphicsEffect(None)
        self.hide()
        then()

    # ---------- geometry ----------

    def eventFilter(self, obj, event) -> bool:
        """An unmanaged child is never resized by Qt, so follow the parent's own resize events."""
        if event.type() == QEvent.Type.Resize and obj is self.parentWidget() or event.type() == QEvent.Type.Show and obj is self.parentWidget():
            self._fit_parent()
        return False

    def _fit_parent(self) -> None:
        """Cover everything below the custom title bar (status bar included)."""
        parent = self.parentWidget()
        if parent is None:
            return
        bar = getattr(parent, "title_bar", None)
        offset = bar.height() if bar is not None else 0
        rect = parent.rect()
        self.setGeometry(rect.x(), rect.y() + offset, rect.width(), rect.height() - offset)
        self.raise_()  # QMainWindow re-stacks its own children when the layout activates

    def resizeEvent(self, event) -> None:
        self._fit_parent()
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:
        event.accept()  # swallow clicks so the covered UI cannot be used
