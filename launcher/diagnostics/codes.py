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

"""Stable diagnosis error codes.

Two prefixes, one numbering space each (never reuse a retired number):

* ``MPL-Launch-####`` — the launcher could not start the game at all
  (Java missing, offline gate, broken version JSON, download/write failures,
  an unusable heap size argument). Always emitted by ``phase == "launcher"``.
* ``MPL-Crash-####`` — the game process ran and died (or was killed) and the
  knowledge base found a cause in the game's logs, crash report or ``hs_err``
  file. Emitted by the ``fatal`` / ``primary`` / ``secondary`` phases.

``0001`` and ``0000`` are reserved inside the crash space: they are synthesised
by the engine, never written in ``data/rules.json``.
"""

from __future__ import annotations

import re

LAUNCH_PREFIX = "MPL-Launch-"
CRASH_PREFIX = "MPL-Crash-"

# Reserved codes (synthesised by the engine, must not appear in the rule file)
UNKNOWN_CODE = "MPL-Crash-0000"  # something was analysable, nothing matched
NOTHING_TO_ANALYSE_CODE = "MPL-Crash-0001"  # no analysable log at all

RESERVED_CODES = frozenset({UNKNOWN_CODE, NOTHING_TO_ANALYSE_CODE})

_CODE_RE = re.compile(r"^(MPL-Launch|MPL-Crash)-(\d{4})$")


def parse_code(code: str) -> tuple[str, int] | None:
    """Split a code into (prefix, number); None when it is not a diagnosis code."""
    match = _CODE_RE.match(code or "")
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def expected_prefix(phase: str) -> str:
    """The prefix a rule in `phase` must use (launcher-side vs game-side)."""
    return LAUNCH_PREFIX if phase == "launcher" else CRASH_PREFIX


def validate_code(code: str, phase: str) -> str | None:
    """Return an error message when `code` is unusable for `phase`, else None."""
    parsed = parse_code(code)
    if parsed is None:
        return f"invalid code {code!r}: expected MPL-Launch-#### or MPL-Crash-####"
    prefix, number = parsed
    if code in RESERVED_CODES:
        return f"code {code} is reserved for the engine and must not be used by a rule"
    if prefix != expected_prefix(phase).rstrip("-"):
        return (
            f"code {code} has the wrong prefix for phase {phase!r}: "
            f"expected {expected_prefix(phase)}####"
        )
    if not 0 <= number <= 9999:
        return f"code {code} is out of range"
    return None
