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

"""Automatic header enforcement: every .py file must start with the GPL-3.0 header.

This test runs with the normal suite, so any new file added without the
license header fails CI/pytest and gets caught right after coding.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_headers.py"
_spec = importlib.util.spec_from_file_location("check_headers", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_check)


def test_all_python_files_have_gpl_header():
    expected = _check.header_lines()
    problems = []
    for path in _check.iter_project_files():
        issue = _check.check_file(path, expected)
        if issue:
            problems.append(f"{issue}: {path.relative_to(_check.PROJECT_ROOT)}")
    assert not problems, (
        "files without the GPL header (fix with: python scripts/check_headers.py --fix):\n"
        + "\n".join(problems)
    )
