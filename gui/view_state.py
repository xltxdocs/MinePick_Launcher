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

"""Per-view UI state: table column widths survive a restart."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from launcher import paths

STATE_FILENAME = "ui_state.ini"


def _settings() -> QSettings:
    return QSettings(str(paths.launcher_dir() / STATE_FILENAME), QSettings.Format.IniFormat)


def remember_column_widths(view, key: str) -> None:
    """Restore this table's saved column widths and store them again when they change."""
    header = view.horizontalHeader()
    settings = _settings()
    saved = settings.value(f"columns/{key}")
    if saved is not None:
        try:
            header.restoreState(saved)
        except (TypeError, ValueError):
            pass  # stale state from an older column layout: keep the defaults
    header.sectionResized.connect(
        lambda *_: settings.setValue(f"columns/{key}", header.saveState())
    )


def apply_current_sort(view, model) -> None:
    """Re-apply the header's sort indicator after the rows were rebuilt."""
    header = view.horizontalHeader()
    section = header.sortIndicatorSection()
    if section >= 0 and header.isSortIndicatorShown():
        model.sort(section, header.sortIndicatorOrder())
