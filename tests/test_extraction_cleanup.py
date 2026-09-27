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

"""Onefile extraction folders: stale ones get swept, recent or unrelated ones survive."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from launcher import paths


def _fake_extraction(root: Path, name: str, age_seconds: float) -> Path:
    folder = root / name
    folder.mkdir()
    (folder / "marker.txt").write_text("x", encoding="utf-8")
    stamp = time.time() - age_seconds
    os.utime(folder, (stamp, stamp))
    return folder


def test_stale_extraction_folders_are_removed_and_recent_ones_kept(ws_tmp, monkeypatch):
    root = ws_tmp / "mei_root"
    root.mkdir()
    stale = _fake_extraction(root, "_MEI111111", 3 * 86400)
    fresh = _fake_extraction(root, "_MEI222222", 60)  # e.g. a second instance running right now
    unrelated = root / "some_other_dir"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(sys, "_MEIPASS", str(root / "_MEI999999"), raising=False)

    assert paths.cleanup_stale_extraction_dirs() == 1
    assert not stale.exists()
    assert fresh.exists()
    assert (unrelated / "keep.txt").is_file()


def test_no_extraction_root_outside_a_frozen_build(monkeypatch):
    """In development there is no _MEIPASS, so the sweep must be a no-op rather than an error."""
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert paths.extraction_root() is None
    assert paths.cleanup_stale_extraction_dirs() == 0


def test_a_missing_root_is_not_fatal(ws_tmp, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(ws_tmp / "gone" / "_MEI1"), raising=False)
    assert paths.cleanup_stale_extraction_dirs() == 0
