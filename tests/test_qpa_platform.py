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

"""The test suite must never put a window on someone's screen.

Six test files used to create real windows because only a few modules set the platform themselves,
so running the suite flickered windows in front of whoever was using the machine. conftest now sets
it for everything; this test keeps that from silently regressing.
"""

from __future__ import annotations

import os

import pytest


def test_suite_runs_on_the_offscreen_platform():
    assert os.environ.get("QT_QPA_PLATFORM") == "offscreen", (
        "the suite is not offscreen - GUI tests would open real windows. "
        "conftest.py must set QT_QPA_PLATFORM=offscreen before Qt is imported."
    )


def test_qt_reports_the_offscreen_platform():
    QGuiApplication = pytest.importorskip("PySide6.QtGui").QGuiApplication
    if QGuiApplication.instance() is None:
        pytest.skip("no QApplication in this process yet")
    assert QGuiApplication.platformName() == "offscreen", QGuiApplication.platformName()
