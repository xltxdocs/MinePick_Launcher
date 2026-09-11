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

"""Error severity display: fatal errors use a dialog, ordinary warnings only the status bar."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from gui import i18n


def show_fatal(parent: QWidget | None, message: str) -> None:
    """Fatal error: dialog + status bar text. Returns None (the caller sets the status bar itself)."""
    QMessageBox.critical(parent, i18n.tr("error.title"), message)


def show_warning(parent: QWidget | None, message: str) -> None:
    """Ordinary warning: non-blocking prompt box."""
    QMessageBox.warning(parent, i18n.tr("error.warning.title"), message)
