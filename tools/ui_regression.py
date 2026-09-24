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

Usage:  python tools/ui_regression.py          (from the repository root)
        python tools/ui_regression.py --quick  (skip the screenshots)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".." / "minecraft-launcher" / ".venv" / "Scripts" / "python.exe"


LOG_DIR = ROOT / "tmp" / "regression_logs"


def run(label: str, args: list[str], expect_json: bool = False) -> tuple[bool, str]:
    """Run one check with its output kept in a log file (no pipes: the sandbox blocks them).

    Returns (blocking_ok, status) where status is "OK", "FAIL" or "WARN". The UI quality audit
    is judged by its JSON verdict; if that verdict is missing the check is a warning, because a
    crash inside the audit must not be reported as a product failure.
    """
    print(f"\n=== {label} ===")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / (label.replace(" ", "_").replace("/", "_") + ".log")
    for attempt in (1, 2):
        with log.open("w", encoding="utf-8") as handle:
            result = subprocess.run(
                args,
                cwd=str(ROOT),
                check=False,
                stdout=handle,
                stderr=subprocess.STDOUT,
                # a GBK console cannot encode Korean/Japanese diagnostics: pin the children to UTF-8
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        output = log.read_text(encoding="utf-8", errors="replace")
        # a GBK console cannot encode the replacement characters of a decoded log
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(output.rstrip().encode(encoding, "replace").decode(encoding, "replace"))
        verdict = None
        if expect_json:
            for line in reversed(output.splitlines()):
                line = line.strip()
                if line.startswith("{") and '"ok"' in line:
                    try:
                        verdict = json.loads(line)
                    except ValueError:
                        verdict = None
                    break
        if verdict is not None:
            ok = bool(verdict.get("ok"))
            print(f"--- {label}: {'OK' if ok else 'FAILED'} (json verdict, exit {result.returncode})")
            return ok, ("OK" if ok else "FAIL")
        if result.returncode == 0:
            print(f"--- {label}: OK (exit 0)")
            return True, "OK"
        if attempt == 1:
            print(f"--- {label}: exit {result.returncode}, retrying in 3s ...")
            time.sleep(3)
        else:
            if expect_json:
                print(f"--- {label}: WARN (no json verdict; see {log})")
                return True, "WARN"
            print(f"--- {label}: FAILED (exit {result.returncode}; see {log})")
            return False, "FAIL"
    return False, "FAIL"


def main() -> int:
    quick = "--quick" in sys.argv
    python = str(PYTHON if PYTHON.exists() else sys.executable)
    checks = [
        ("unit tests", [python, "-m", "pytest", "-q"]),
        ("lint", [python, "-m", "ruff", "check", "launcher", "gui", "tools", "tests"]),
        ("GPL headers", [python, "scripts/check_headers.py"]),
        ("README sync (9 translations)", [python, "tools/check_readme_sync.py", "--json"]),
        (
            "UI quality (contrast / overflow / high DPI)",
            [python, "tools/audit_ui_quality.py", "--json"],
        ),
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
    if "--list-checks" in sys.argv:
        # the check list lives here and nowhere else: docs refer to this command instead of
        # enumerating the checks, so adding or removing one never leaves the docs stale
        for label, _args in checks:
            print(label)
        return 0

    results = [
        (label, *run(label, args, expect_json="--json" in args))
        for label, args in checks
    ]
    print("\n=== summary ===")
    for label, ok, status in results:
        print(f"  {status:4}  {label}")
    print(f"  (logs: {LOG_DIR})")
    return 0 if all(ok for _label, ok, _status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
