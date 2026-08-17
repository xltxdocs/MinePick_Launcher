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

"""System memory helpers for the launcher (Windows focused)."""

from __future__ import annotations

import ctypes
import logging
import os


def trim_working_set() -> None:
    """Release the launcher process idle physical pages back to the OS.

    Best-effort only: on failure the launcher simply keeps its pages.
    Call this after the game process has started so the game gets the
    maximum amount of free RAM.
    """
    if os.name != "nt":
        return
    try:
        ctypes.windll.psapi.SetProcessWorkingSetSize(-1, -1, -1)  # type: ignore[attr-defined]
    except Exception:  # best effort
        logging.getLogger(__name__).debug("TrimWorkingSet failed", exc_info=True)

