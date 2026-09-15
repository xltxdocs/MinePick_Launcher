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

"""pytest shared fixtures.

Note: this development sandbox locks writes inside mkdtemp-style (random-suffix) directories,
so it provides an ordinary mkdir directory via ws_tmp instead of pytest's built-in tmp_path.
"""

import shutil
from pathlib import Path

import pytest

WORK_DIR = Path(__file__).resolve().parent / ".work"
_counter = 0


@pytest.fixture()
def ws_tmp():
    """A writable ordinary temporary directory inside the workspace (function-scoped, auto-cleaned)."""
    global _counter
    WORK_DIR.mkdir(exist_ok=True)
    d = WORK_DIR / f"case{_counter:03d}"
    _counter += 1
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _settle_background_work():
    """Let the worker pool finish before the next test tears widgets down.

    Windows recorded 0xC0000005 inside Qt6Widgets.dll at a fixed offset: a test ended while a
    QThreadPool job started by an earlier test was still running, so Qt later touched widget
    objects that had already been destroyed. Draining the pool and flushing the event queue
    between tests removes that overlap without changing what any test asserts.
    """
    yield
    try:
        from PySide6.QtCore import QThreadPool
        from PySide6.QtWidgets import QApplication
    except ImportError:  # no Qt in this environment: nothing to drain
        return
    QThreadPool.globalInstance().waitForDone(5000)
    application = QApplication.instance()
    if application is not None:
        application.processEvents()
