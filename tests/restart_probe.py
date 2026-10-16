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

"""Stand-in for the packaged launcher: the build fixture of the slow restart tests.

``tests/test_updates.py`` freezes this file with PyInstaller (``--onefile`` and ``--onedir``) and
never imports it. It has to be a real frozen build, because the defect it guards against lives in the
bootloader and not in the generated script: only a real restart can show whether the process that
comes back is an independent instance or a worker that reused the extraction directory of the
process that was exiting.

Without arguments it is what the helper's ``start`` launches: it records the environment it was
started in, plus whether it can read the data file bundled next to it. With ``--parent`` it does what
the frozen launcher does during a self-update - ask the production code for the swap helper and start
it - and then stays alive, so that a restarted build which reuses its extraction directory has a
silent failure mode instead of the crash. The test's docstring explains that trade.
"""

import json
import os
import sys
import time
from pathlib import Path

ALIVE_DEFAULT = "45"


def record() -> dict:
    """Everything a restarted process can observe about how it was started."""
    home = getattr(sys, "_MEIPASS", None)
    bundled = Path(home) / "probe-payload.txt" if home else None
    text = ""
    if bundled is not None and bundled.is_file():
        text = bundled.read_text(encoding="utf-8").strip()
    return {
        "pid": os.getpid(),
        "argv": sys.argv[1:],
        "exe": sys.executable,
        "frozen": bool(getattr(sys, "frozen", False)),
        "meipass": home,
        "env_home": os.environ.get("_PYI_APPLICATION_HOME_DIR"),
        "env_archive": os.environ.get("_PYI_ARCHIVE_FILE"),
        "env_level": os.environ.get("_PYI_PARENT_PROCESS_LEVEL"),
        "reset": os.environ.get("PYINSTALLER_RESET_ENVIRONMENT"),
        "payload": text,
    }


def write(name: str, payload: dict, raw: bytes | None = None) -> None:
    out = Path(os.environ.get("PROBE_RECORD_DIR", "."))
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_bytes(raw if raw is not None else json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))


def parent() -> int:
    """Ask production code for the swap helper, start it, then stay alive for the restarted build."""
    from launcher import updates

    staged, target = Path(os.environ["PROBE_STAGED"]), Path(sys.executable)
    # wait_pid points at a PID that is not running: this probe deliberately outlives the restart, so
    # the helper must not wait for it to exit (see the test's docstring).
    script = updates.write_install_script(staged, target, True, wait_pid=999999)
    if os.environ.get("PROBE_DROP_RESET") == "1":
        # The pre-fix script: the same bytes, with the one line this fix added removed. Done at byte
        # level because the helper is written in the console code page, so nothing is re-encoded.
        kept = [
            line
            for line in script.read_bytes().split(b"\r\n")
            if b"PYINSTALLER_RESET_ENVIRONMENT" not in line
        ]
        script.write_bytes(b"\r\n".join(kept))
    # What the frozen build actually generated, for the test to read once the helper has deleted it.
    write("generated-apply-update.cmd", {}, raw=script.read_bytes())
    write(
        "parent-launched.json",
        {"script": str(script), "started": updates.launch_install_script(script)},
    )
    child = Path(os.environ["PROBE_RECORD_DIR"]) / "child.json"
    deadline = time.time() + float(os.environ.get("PROBE_ALIVE_SECONDS", ALIVE_DEFAULT))
    while time.time() < deadline and not child.is_file():
        time.sleep(0.2)
    time.sleep(1.0)  # the restarted process may still be reading its own extraction directory
    return 0


def main() -> int:
    mode = "parent" if "--parent" in sys.argv else "child"
    try:
        write(f"{mode}.json", record())
        if mode == "parent":
            return parent()
    except Exception as exc:  # noqa: BLE001 - a windowed build has no console: report to the file
        write("error.json", {"mode": mode, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
