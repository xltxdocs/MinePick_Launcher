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

"""Every tracked Python file must carry the project's SPDX header.

The header is a licence statement, not decoration: a file shipped without it is a file whose licence
a recipient cannot determine from the file itself. The audit that added this test found all 150
tracked Python files already compliant; the test exists so the 151st cannot quietly break that.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COPYRIGHT_LINE = "SPDX-FileCopyrightText:"
LICENCE_LINE = "SPDX-License-Identifier: GPL-3.0-only"
HEAD_LINES = 8  # the header goes at the very top, before the module docstring


def _tracked_python_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"git ls-files unavailable: {result.stderr.strip()}")
    return [ROOT / line for line in result.stdout.splitlines() if line.strip()]


def test_every_tracked_python_file_declares_copyright_and_licence():
    offenders: list[str] = []
    for path in _tracked_python_files():
        if not path.is_file():
            continue
        head = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:HEAD_LINES])
        missing = [line for line in (COPYRIGHT_LINE, LICENCE_LINE) if line not in head]
        if missing:
            offenders.append(f"{path.relative_to(ROOT)}  missing: {', '.join(missing)}")

    assert not offenders, (
        "These tracked Python files lack the SPDX header (add both lines at the very top):\n  "
        + "\n  ".join(offenders)
    )
