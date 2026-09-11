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

"""Build Source_code.zip for this branch (GPL-3.0 source package shipped with the EXE)."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dist" / "Source_code.zip"

INCLUDE_DIRS = ("launcher", "gui", "tests", "scripts", "tools", "docs")
INCLUDE_FILES = (
    "run.py",
    "build_exe.spec",
    "pyproject.toml",
    "README.md",
    "README_zh.md",
    "LICENSE",
    ".gitignore",
    "requirements.txt",
    "requirements-dev.txt",
    "run_cli.py",
    "_bootstrap_pip.py",
    "_fetch_gpl2.py",
)
FORBIDDEN_PARTS = {".git", ".venv", "build", "dist", "__pycache__", ".pytest_cache", "_preview", "preview"}
FORBIDDEN_FILES = {"cf_key.txt", "codesign.pfx", "Source_code.zip"}


def collect() -> list[Path]:
    files: list[Path] = []
    for name in INCLUDE_FILES:
        path = ROOT / name
        if path.exists():
            files.append(path)
    for directory in INCLUDE_DIRS:
        base = ROOT / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if any(part in FORBIDDEN_PARTS for part in path.relative_to(ROOT).parts):
                continue
            if path.name in FORBIDDEN_FILES:
                continue
            files.append(path)
    return files


def main() -> int:
    files = collect()
    forbidden = [
        path
        for path in files
        if any(part in FORBIDDEN_PARTS for part in path.relative_to(ROOT).parts)
        or path.name in FORBIDDEN_FILES
    ]
    assert not forbidden, f"forbidden entries: {forbidden}"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path("Source_code") / path.relative_to(ROOT))
    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"{OUTPUT}: {len(files)} files, {size_mb:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
