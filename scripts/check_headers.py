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

"""Verify the GPL-3.0 license header on every .py file in the repository.

Usage:
    python scripts/check_headers.py          # check only (exit 1 when files are missing it)
    python scripts/check_headers.py --fix    # prepend the header to files missing it

The header text is embedded below; a local "statement.txt" next to the
repository root takes precedence when present.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STATEMENT_FILENAME = "statement.txt"

EMBEDDED_HEADER = [
    "# SPDX-FileCopyrightText: 2026 WDNDXLTX",
    "# SPDX-License-Identifier: GPL-3.0-only",
    "#",
    "# This file is part of MinePick Launcher.",
    "#",
    "# MinePick Launcher is free software: you can redistribute it and/or modify",
    "# it under the terms of the GNU General Public License as published by",
    "# the Free Software Foundation, version 3 of the License.",
    "#",
    "# MinePick Launcher is distributed in the hope that it will be useful,",
    "# but WITHOUT ANY WARRANTY; without even the implied warranty of",
    "# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the",
    "# GNU General Public License for more details.",
    "#",
    "# You should have received a copy of the GNU General Public License",
    "# along with MinePick Launcher. If not, see <https://www.gnu.org/licenses/>.",
]

EXCLUDE_PARTS = {
    ".venv",
    "build",
    "dist",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def header_lines() -> list[str]:
    """The expected header lines (local statement.txt wins over the embedded copy)."""
    statement = PROJECT_ROOT.parent / STATEMENT_FILENAME
    if statement.exists():
        return statement.read_text(encoding="utf-8").rstrip("\n").splitlines()
    return list(EMBEDDED_HEADER)


def iter_project_files() -> list[Path]:
    """Every tracked .py file under the repository root, excluding build artifacts."""
    files = []
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        parts = path.relative_to(PROJECT_ROOT).parts
        if any(part in EXCLUDE_PARTS for part in parts):
            continue
        files.append(path)
    return files


def check_file(path: Path, expected: list[str]) -> str | None:
    """Return 'missing' / 'partial' for files without the exact header, else None."""
    text = path.read_text(encoding="utf-8-sig")
    head = text.splitlines()[: len(expected)]
    if head == expected:
        return None
    if not head or not head[0].startswith("# SPDX-FileCopyrightText:"):
        return "missing"
    return "partial"


def fix_file(path: Path, expected: list[str]) -> bool:
    """Prepend the header to a file that lacks it (BOM-safe, keeps line endings)."""
    text = path.read_text(encoding="utf-8-sig")
    if text.startswith("# SPDX-FileCopyrightText:"):
        return False  # partial headers are reported, never rewritten blindly
    newline = "\r\n" if "\r\n" in text else "\n"
    block = newline.join(expected) + newline + newline
    path.write_text(block + text, encoding="utf-8", newline="")
    return True


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    expected = header_lines()
    problems: list[tuple[Path, str]] = []
    for path in iter_project_files():
        issue = check_file(path, expected)
        if issue:
            problems.append((path, issue))
    if fix:
        fixed = 0
        for path, issue in problems:
            if issue == "missing" and fix_file(path, expected):
                print("fixed:", path.relative_to(PROJECT_ROOT))
                fixed += 1
        remaining = [p for p, _issue in problems if check_file(p, expected)]
        print(
            f"header check: {len(iter_project_files())} files, "
            f"{fixed} fixed, {len(remaining)} still missing the header"
        )
        return 1 if remaining else 0
    for path, issue in problems:
        print(f"{issue.upper()}: {path.relative_to(PROJECT_ROOT)}")
    print(
        f"header check: {len(iter_project_files())} files checked, "
        f"{len(problems)} without the header"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
