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

"""One command for the whole UI check: tests, lint, screenshots and the corner audit.

Usage:  python tools/ui_regression.py          (from the trial folder)
        python tools/ui_regression.py --quick  (skip the screenshots)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".." / "minecraft-launcher" / ".venv" / "Scripts" / "python.exe"


def run(label: str, args: list[str]) -> bool:
    print(f"\n=== {label} ===")
    result = subprocess.run(args, cwd=str(ROOT), check=False)  # stdio inherited on purpose
    ok = result.returncode == 0
    print(f"--- {label}: {'OK' if ok else 'FAILED'} (exit {result.returncode})")
    return ok


def main() -> int:
    quick = "--quick" in sys.argv
    python = str(PYTHON if PYTHON.exists() else sys.executable)
    checks = [
        ("unit tests", [python, "-m", "pytest", "-q"]),
        ("lint", [python, "-m", "ruff", "check", "launcher", "gui", "tools", "tests"]),
        ("GPL headers", [python, "scripts/check_headers.py"]),
        ("UI quality (contrast / overflow / high DPI)", [python, "tools/audit_ui_quality.py"]),
        ("corner audit (dark)", [python, "tools/audit_corners.py", "--theme", "dark"]),
        ("corner audit (light)", [python, "tools/audit_corners.py", "--theme", "light"]),
    ]
    if not quick:
        checks.append(
            (
                "screenshots (dark + light)",
                [python, "tools/shot_pages.py", "--root", ".", "--preview", ".", "--out", "preview/after",
                 "--theme", "dark", "--label", "after"],
            )
        )
    results = [(label, run(label, args)) for label, args in checks]
    print("\n=== summary ===")
    for label, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {label}")
    return 0 if all(ok for _label, ok in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
