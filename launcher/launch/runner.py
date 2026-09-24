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

"""Game-process running (stdio inherit mode, optional bounded output capture).

Sandbox/packaging compatible: by default output is not captured via pipes (restricted environments
forbid piped stdio); output inherits the console directly, and log redirection is up to the caller.
The GUI runs the same argv with QProcess.

``capture_tail=True`` opts in to a bounded capture: stdout and stderr are merged into one pipe and
a reader thread keeps only the last :data:`TAIL_LINES` lines in a ring buffer. That tail is the only
evidence left when the game dies before writing any log, and it is what the crash diagnosis feeds to
the knowledge base. The default path is unchanged (no pipe, no thread, ``int`` return value).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from launcher.diagnostics.prepare import decode_bytes

#: Ring-buffer size of the captured output tail (501 = 500 lines of context + the last line).
TAIL_LINES = 501


@dataclass(frozen=True)
class RunResult:
    """Result of a captured run: the exit code plus the bounded output tail."""

    exit_code: int
    tail: list[str]


def _capture_stream(stream, buffer: deque[bytes]) -> None:
    """Reader-thread body: keep only the newest lines (never blocks the child)."""
    try:
        for raw in stream:
            buffer.append(raw)
    except (OSError, ValueError):  # pragma: no cover - pipe closed while reading
        return


def _decode_tail(buffer: deque[bytes]) -> list[str]:
    """Decode captured lines with the same policy as log files (UTF-8 -> GB18030)."""
    lines: list[str] = []
    for raw in buffer:
        text, _encoding = decode_bytes(raw)
        lines.append(text.rstrip("\r\n"))
    return lines


def run_process(
    argv: list[str],
    cwd: Path,
    on_started: Callable[[], None] | None = None,
    *,
    capture_tail: bool = False,
    tail_lines: int = TAIL_LINES,
) -> int | RunResult:
    """Run with inherited stdio and wait for exit; Ctrl+C forwards a termination signal.

    on_started is called once after the process starts successfully (used by the GUI to auto-hide).

    With ``capture_tail=True`` stdout/stderr are merged and the last ``tail_lines`` lines are
    returned as ``RunResult.tail`` (the return value is then a :class:`RunResult`, not an ``int``).
    """
    # Under a GUI (no console parent process), don't pop a console window (console-flash fix); the CLI keeps inheritance.
    # creationflags is Windows-only; passing it on other platforms raises ValueError.
    extra: dict = {}
    if os.name == "nt" and sys.stdout is None and sys.stdin is None:
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    buffer: deque[bytes] = deque(maxlen=max(1, tail_lines))
    reader: threading.Thread | None = None
    if capture_tail:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **extra,
        )
        reader = threading.Thread(
            target=_capture_stream, args=(proc.stdout, buffer), daemon=True
        )
        reader.start()
    else:
        proc = subprocess.Popen(argv, cwd=str(cwd), **extra)

    if on_started is not None:
        on_started()

    def finish(code: int) -> int | RunResult:
        if reader is not None:
            reader.join(timeout=5)
            return RunResult(exit_code=code, tail=_decode_tail(buffer))
        return code

    try:
        return finish(proc.wait())
    except KeyboardInterrupt:
        print()
        print("正在关闭游戏进程...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return finish(130)


def find_new_crash_reports(game_dir: Path, since: float) -> list[Path]:
    """Return crash reports generated after `since`."""
    reports_dir = game_dir / "crash-reports"
    if not reports_dir.exists():
        return []
    out: list[Path] = []
    for report in reports_dir.glob("crash-*.txt"):
        try:
            if report.stat().st_mtime >= since:
                out.append(report)
        except OSError:
            continue
    return out
