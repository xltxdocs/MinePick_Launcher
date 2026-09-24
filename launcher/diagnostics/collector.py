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

"""Collect the candidate logs of one launch.

Sources (per the knowledge-base design):

* ``<game dir>/crash-reports/*`` — any extension, newest first;
* ``<game dir>/logs/latest.log`` and ``<game dir>/logs/debug.log``;
* ``hs_err_pid*.log`` in the game directory and in its ``logs/`` folder;
* the launcher's own log under ``paths.launcher_dir()/logs``;
* the captured stdout/stderr tail of the game process (see ``run_process``);
* the launcher-side failure text, when the caller has one.

**Freshness gate**: a file only counts when its mtime is at or after the launch
start time the caller supplies. There is deliberately no "modified in the last
N minutes" heuristic — the launcher knows the exact moment the process started,
so a stale log from an earlier session can never be mistaken for this crash.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from launcher import paths
from launcher.diagnostics.context import DiagnosisContext

_LOGGER = logging.getLogger(__name__)

ORIGIN_GAME = "game"  # written by the game itself
ORIGIN_LAUNCHER = "launcher"  # the launcher's own log
ORIGIN_CAPTURED = "captured"  # stdout/stderr tail captured while running the game
ORIGIN_ERROR = "error"  # launcher-side failure text supplied by the caller

CAPTURED_NAME = "game-stdout.log"
ERROR_NAME = "launcher-error.txt"
LAUNCHER_LOG_NAME = "launcher.log"


@dataclass(frozen=True)
class LogCandidate:
    """A file (or an in-memory pseudo file) that may hold evidence for one launch."""

    path: Path
    name: str  # file name used for classification and in the report
    mtime: float
    origin: str
    text: str | None = None  # pre-read content for the captured/error pseudo files


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:  # pragma: no cover - unreadable path
        return False


def _fresh(mtime: float, since: float | None) -> bool:
    """The freshness gate: no `since` (0 / None) means "no gate"."""
    return since is None or mtime >= since


def _dedup_key(path: Path) -> str:
    """Case-insensitive, absolute de-duplication key (Windows paths are case-blind)."""
    try:
        return os.path.normcase(os.path.abspath(str(path)))
    except (OSError, ValueError):  # pragma: no cover - pathological path
        return os.path.normcase(str(path))


def _collect_from_root(root: Path, since: float | None) -> list[LogCandidate]:
    """Crash reports, the two standard logs and every ``hs_err`` of one game directory."""
    out: list[LogCandidate] = []

    reports_dir = root / "crash-reports"
    reports: list[LogCandidate] = []
    if reports_dir.is_dir():
        for entry in sorted(reports_dir.iterdir()):
            if not _is_file(entry):
                continue
            stamp = _mtime(entry)
            if stamp is None or not _fresh(stamp, since):
                continue
            reports.append(
                LogCandidate(path=entry, name=entry.name, mtime=stamp, origin=ORIGIN_GAME)
            )
    # Newest first: the report of this launch is the most likely explanation.
    out.extend(sorted(reports, key=lambda item: item.mtime, reverse=True))

    logs_dir = root / "logs"
    for name in ("latest.log", "debug.log"):
        candidate = logs_dir / name
        stamp = _mtime(candidate) if _is_file(candidate) else None
        if stamp is not None and _fresh(stamp, since):
            out.append(
                LogCandidate(path=candidate, name=name, mtime=stamp, origin=ORIGIN_GAME)
            )

    for directory in (root, logs_dir):
        if not directory.is_dir():
            continue
        for entry in sorted(directory.glob("hs_err_pid*.log")):
            if not _is_file(entry):
                continue
            stamp = _mtime(entry)
            if stamp is not None and _fresh(stamp, since):
                out.append(
                    LogCandidate(path=entry, name=entry.name, mtime=stamp, origin=ORIGIN_GAME)
                )
    return out


def _collect_launcher_logs(logs_dir: Path, since: float | None) -> list[LogCandidate]:
    """The launcher's own log files (the app writes ``launcher.log`` there)."""
    if not logs_dir.is_dir():
        return []
    out: list[LogCandidate] = []
    for entry in sorted(logs_dir.glob("*.log")):
        if not _is_file(entry):
            continue
        stamp = _mtime(entry)
        if stamp is not None and _fresh(stamp, since):
            out.append(
                LogCandidate(path=entry, name=entry.name, mtime=stamp, origin=ORIGIN_LAUNCHER)
            )
    out.sort(key=lambda item: item.mtime, reverse=True)
    return out


def collect_candidates(
    context: DiagnosisContext, *, since: float | None = None
) -> list[LogCandidate]:
    """Every log candidate for one launch, de-duplicated case-insensitively.

    `since` defaults to ``context.launch_started_at`` (0 = no freshness gate).
    """
    if since is None:
        since = context.launch_started_at if context.launch_started_at > 0 else None

    collected: list[LogCandidate] = []
    seen: set[str] = set()

    def add(candidate: LogCandidate) -> None:
        key = _dedup_key(candidate.path)
        if key in seen:
            return
        seen.add(key)
        collected.append(candidate)

    for root in context.search_roots():
        for candidate in _collect_from_root(root, since):
            add(candidate)

    logs_dir = context.launcher_logs_dir or (paths.launcher_dir() / "logs")
    for candidate in _collect_launcher_logs(logs_dir, since):
        add(candidate)

    captured = [line for line in context.captured_output if line is not None]
    if captured:
        add(
            LogCandidate(
                path=Path(CAPTURED_NAME),
                name=CAPTURED_NAME,
                mtime=context.launch_started_at,
                origin=ORIGIN_CAPTURED,
                text="\n".join(captured),
            )
        )

    if context.error_text.strip():
        add(
            LogCandidate(
                path=Path(ERROR_NAME),
                name=ERROR_NAME,
                mtime=context.launch_started_at,
                origin=ORIGIN_ERROR,
                text=context.error_text,
            )
        )

    _LOGGER.debug(
        "diagnostics: %d candidate log(s) for instance %s (since=%s)",
        len(collected),
        context.version_id or "?",
        since,
    )
    return collected
