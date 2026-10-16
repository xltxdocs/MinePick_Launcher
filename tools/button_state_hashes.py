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

"""Digest every button's *unfocused* rendering, per theme, so a stylesheet change can be proved inert.

The claim this exists for: the focus ring added in this round costs the unfocused button nothing.
That cannot be asserted inside one build - both versions of the sheet have to exist at once - so the
check is a two-run digest report, stashing only the sheets:

    python tools/button_state_hashes.py > after.txt
    git stash push -- gui/resources/style.qss gui/resources/style_light.qss
    python tools/button_state_hashes.py > before.txt
    git stash pop
    diff before.txt after.txt

Every line carries the widget's size, its size hint and a SHA-256 prefix of the grabbed pixels, so an
empty diff means identical geometry *and* identical pixels - not merely a similar-looking screenshot.
Two lines are expected to differ, and only these two: `dialog-cancel-default`, which is the default
button this round gives a visible ring (that is the point of the change), and any file another
uncommitted change touched. Everything with `keyboardFocus` unset and no `defaultChoice` property is
the state the change promises not to touch, and it must hash the same.

Runs offscreen; it never opens a window on the user's desktop.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

THEMES = ("dark", "light")


def digest(image: QImage) -> str:
    return hashlib.sha256(bytes(image.constBits())).hexdigest()[:16]


def build_widgets(host: QWidget) -> list[tuple[str, QWidget]]:
    """One entry per button variant the stylesheets style, plus a few non-buttons to catch a leak."""
    widgets: list[tuple[str, QWidget]] = []

    def add(name: str, widget: QWidget, y: int) -> None:
        widget.setParent(host)
        widget.move(20, y)
        widgets.append((name, widget))

    add("primary", QPushButton("Primary", host), 10)
    secondary = QPushButton("Secondary", host)
    secondary.setObjectName("secondaryButton")
    add("secondary", secondary, 44)
    danger = QPushButton("Danger", host)
    danger.setObjectName("dangerButton")
    add("danger", danger, 78)
    icon = QPushButton("I", host)
    icon.setObjectName("iconButton")
    add("icon", icon, 112)
    chip = QPushButton("Chip", host)
    chip.setObjectName("categoryTab")
    add("categoryTab", chip, 146)
    wizard = QPushButton("Wizard", host)
    wizard.setObjectName("wizardOption")
    add("wizardOption", wizard, 180)
    disabled = QPushButton("Disabled", host)
    disabled.setEnabled(False)
    add("disabled", disabled, 220)
    secondary_off = QPushButton("Secondary off", host)
    secondary_off.setObjectName("secondaryButton")
    secondary_off.setEnabled(False)
    add("secondary-disabled", secondary_off, 254)

    box = QMessageBox(host)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("仍有 1 个下载任务正在进行，确定要退出吗？")
    cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    confirm = box.addButton("退出", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(cancel)
    box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    # Marked exactly as gui/main_window.py marks it: the marker is part of the state under test, so a
    # change to its rendering shows up in the digest.
    cancel.setProperty("defaultChoice", True)
    widgets.append(("dialog-cancel-default", cancel))
    widgets.append(("dialog-confirm", confirm))

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, host
    )
    buttons.move(20, 295)
    widgets.append(("buttonbox-ok", buttons.button(QDialogButtonBox.StandardButton.Ok)))
    widgets.append(("buttonbox-cancel", buttons.button(QDialogButtonBox.StandardButton.Cancel)))

    line = QLineEdit(host)
    add("lineedit", line, 330)
    check = QCheckBox("Check", host)
    add("checkbox", check, 364)
    combo = QComboBox(host)
    combo.addItem("one")
    add("combobox", combo, 392)
    return widgets


def main() -> int:
    app = QApplication([])
    app.setStyle("Fusion")
    from gui import theme

    # The shared rule that keeps a focus ring out of a grab: the digest below is the *unfocused*
    # rendering, and this is how that claim is checked instead of assumed.
    from tools.shot_pages import assert_no_focus_mark

    host = QWidget()
    host.resize(420, 440)
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widgets = build_widgets(host)
    host.show()
    # The message box owns its buttons, so it has to be shown for them to lay out and paint.
    for _name, widget in widgets:
        parent = widget.parentWidget()
        if isinstance(parent, QMessageBox):
            parent.show()
    app.processEvents()

    for mode in THEMES:
        theme.apply_theme(mode, None, None, "default")
        app.processEvents()
        print(f"--- {mode} ---")
        for name, widget in widgets:
            # Exactly the state the change promises not to touch.
            widget.setProperty("keyboardFocus", False)
            widget.clearFocus()
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
            app.processEvents()
            # The digest is about the *unfocused* rendering: prove nothing in the tree still carries the
            # mark the focus ring is gated on, rather than trusting the clear above (tools/shot_pages.py
            # has the same rule the README renderer uses).
            assert_no_focus_mark(host)
            image = widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
            print(
                f"  {name:22} {image.width():>4}x{image.height():<4} "
                f"hint={widget.sizeHint().width()}x{widget.sizeHint().height()} {digest(image)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
