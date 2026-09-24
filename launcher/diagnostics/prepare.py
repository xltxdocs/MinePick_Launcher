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

"""Turn candidates into bounded, classified, decoded log windows.

Three rules keep matching cheap and predictable:

1. **Classification** uses the file name *plus a content marker*, never the
   extension: ``hs_err*`` -> hs_err, ``crash-*`` (and anything carrying the
   crash-report header) -> crash report, ``debug.log`` -> debug, ``latest.log``
   and the captured stdout -> game, the launcher's own log -> launcher, and
   everything else -> ``extra`` (kept for the export, never matched).
2. **Windows**: every kind is cut to a fixed head/tail window, then the window is
   de-duplicated line by line with blank lines dropped. A whole file is never
   handed to a matcher.
3. **Encoding**: BOM detection (UTF-8/16/32) -> UTF-8 -> **GB18030** -> lossy
   UTF-8. Old Chinese logs are commonly GBK/GB18030, not UTF-8.
"""

from __future__ import annotations

import codecs
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from launcher.diagnostics.collector import (
    ORIGIN_CAPTURED,
    ORIGIN_ERROR,
    ORIGIN_LAUNCHER,
    LogCandidate,
    collect_candidates,
)
from launcher.diagnostics.context import DiagnosisContext

_LOGGER = logging.getLogger(__name__)

KIND_GAME = "game"
KIND_DEBUG = "debug"
KIND_CRASH_REPORT = "crash_report"
KIND_HS_ERR = "hs_err"
KIND_LAUNCHER = "launcher"
KIND_EXTRA = "extra"

KINDS = (KIND_GAME, KIND_DEBUG, KIND_CRASH_REPORT, KIND_HS_ERR, KIND_LAUNCHER, KIND_EXTRA)
# Only these kinds take part in matching; `extra` is export-only.
MATCHABLE_KINDS = (KIND_GAME, KIND_DEBUG, KIND_CRASH_REPORT, KIND_HS_ERR, KIND_LAUNCHER)

# (head lines, tail lines) per kind. The first four are fixed by the design;
# launcher / extra are our own values (they only ever carry launcher-side text).
WINDOWS: dict[str, tuple[int, int]] = {
    KIND_GAME: (1500, 500),
    KIND_DEBUG: (1000, 0),
    KIND_CRASH_REPORT: (300, 700),
    KIND_HS_ERR: (200, 100),
    KIND_LAUNCHER: (600, 400),
    KIND_EXTRA: (400, 200),
}

# A single monster line must not blow up the matcher; the same for the joined text.
MAX_LINE_CHARS = 2000
MAX_MATCH_CHARS = 400_000
MAX_READ_BYTES = 4 * 1024 * 1024
_TRUNCATED_MARK = "... [truncated] ..."

_BOMS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    # UTF-32 first: its LE BOM starts with the UTF-16 LE BOM
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

HS_ERR_MARKERS = (
    "# A fatal error has been detected by the Java Runtime Environment",
    "#  EXCEPTION_ACCESS_VIOLATION",
    "# There is insufficient memory for the Java Runtime Environment",
    "# Java VM: ",
)
CRASH_REPORT_MARKERS = (
    "---- Minecraft Crash Report ----",
    "-- System Details --",
    "// Description:",
)


@dataclass(frozen=True)
class PreparedLog:
    """One classified log reduced to its matching window."""

    path: Path
    name: str
    kind: str
    lines: tuple[str, ...]
    origin: str
    encoding: str
    total_lines: int
    truncated: bool  # the window dropped lines from the middle of the file

    @property
    def match_text(self) -> str:
        """The bounded text handed to matchers (head + tail preserved)."""
        return bound_text("\n".join(self.lines))

    @property
    def is_matchable(self) -> bool:
        return self.kind in MATCHABLE_KINDS and bool(self.lines)


def bound_text(text: str, limit: int = MAX_MATCH_CHARS) -> str:
    """Limit a text for matching while keeping both ends (no unbounded regex input)."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n" + _TRUNCATED_MARK + "\n" + text[-half:]


def decode_bytes(data: bytes) -> tuple[str, str]:
    """Decode log bytes; return (text, encoding label actually used)."""
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data.decode(encoding), encoding
            except (UnicodeDecodeError, LookupError):  # pragma: no cover - broken BOM
                break
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        # Chinese players' older logs are GBK/GB18030, not UTF-8
        return data.decode("gb18030"), "gb18030"
    except UnicodeDecodeError:
        return data.decode("utf-8", "replace"), "utf-8/replace"


def read_log_bytes(path: Path) -> bytes:
    """Read a log with a plain shared read handle (a file still being written is fine).

    Files larger than ``MAX_READ_BYTES`` are read as head + tail so that both the
    crash-report header and the end of a running log survive.
    """
    with path.open("rb") as handle:
        head = handle.read(MAX_READ_BYTES)
        if len(head) < MAX_READ_BYTES:
            return head
        try:
            handle.seek(-MAX_READ_BYTES // 2, os.SEEK_END)
            tail = handle.read(MAX_READ_BYTES // 2)
        except OSError:  # pragma: no cover - unusual filesystem
            return head
    return head[: MAX_READ_BYTES // 2] + b"\n" + tail


def classify(name: str, text: str, origin: str) -> str:
    """Classify by file name plus a content marker (never by extension alone)."""
    if origin == ORIGIN_LAUNCHER:
        return KIND_LAUNCHER
    if origin == ORIGIN_ERROR:
        return KIND_LAUNCHER  # launcher-side failure text is launcher evidence
    if origin == ORIGIN_CAPTURED:
        return KIND_GAME  # the game's own stdout/stderr
    lower = name.lower()
    if lower.startswith(("hs_err", "_hs_err")) or "hs_err_pid" in lower:
        return KIND_HS_ERR
    if lower.startswith(("crash-", "crash_")):
        return KIND_HS_ERR if _has_any(text, HS_ERR_MARKERS) else KIND_CRASH_REPORT
    if lower == "debug.log":
        return KIND_DEBUG
    if lower == "latest.log":
        return KIND_GAME
    if lower.startswith("launcher") and lower.endswith(".log"):
        return KIND_LAUNCHER
    if _has_any(text, HS_ERR_MARKERS):
        return KIND_HS_ERR
    if _has_any(text, CRASH_REPORT_MARKERS):
        return KIND_CRASH_REPORT
    return KIND_EXTRA


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _clip(line: str) -> str:
    return line if len(line) <= MAX_LINE_CHARS else line[:MAX_LINE_CHARS]


def window_lines(
    lines: list[str], kind: str, *, windows: dict[str, tuple[int, int]] | None = None
) -> tuple[tuple[str, ...], bool]:
    """Cut to the kind's head/tail window, then de-duplicate and drop blank lines."""
    head, tail = (windows or WINDOWS).get(kind, WINDOWS[KIND_EXTRA])
    drop_blank = [line for line in lines if line.strip()]
    if tail <= 0:
        selected = drop_blank[:head]
    elif len(drop_blank) <= head + tail:
        selected = drop_blank
    else:
        selected = drop_blank[:head] + drop_blank[len(drop_blank) - tail :]
    unique: dict[str, None] = {}
    for line in selected:
        unique.setdefault(_clip(line.strip()), None)
    return tuple(unique), len(unique) < len(drop_blank)


def prepare_candidate(candidate: LogCandidate) -> PreparedLog | None:
    """Decode + classify + window one candidate; None when it cannot be read."""
    if candidate.text is not None:
        text = candidate.text
        encoding = "text"
    else:
        try:
            data = read_log_bytes(candidate.path)
        except OSError as exc:
            _LOGGER.debug("diagnostics: cannot read %s: %s", candidate.path, exc)
            return None
        text, encoding = decode_bytes(data)
    kind = classify(candidate.name, text, candidate.origin)
    raw_lines = text.splitlines()
    lines, truncated = window_lines(raw_lines, kind)
    return PreparedLog(
        path=candidate.path,
        name=candidate.name,
        kind=kind,
        lines=lines,
        origin=candidate.origin,
        encoding=encoding,
        total_lines=len(raw_lines),
        truncated=truncated,
    )


def prepare_candidates(candidates: list[LogCandidate]) -> list[PreparedLog]:
    prepared: list[PreparedLog] = []
    for candidate in candidates:
        log = prepare_candidate(candidate)
        if log is not None:
            prepared.append(log)
    return prepared


def prepare_logs(context: DiagnosisContext) -> list[PreparedLog]:
    """Collect + prepare every log of one launch."""
    return prepare_candidates(collect_candidates(context))
