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

"""One diagnosis request: everything the collector, the facts and the report need.

The context is a plain frozen dataclass (no Qt, no IO); the caller — the GUI
phase, the CLI or a test — fills in what it knows and the core library derives
the rest. Field precedence is always "explicit argument wins over the resolved
instance", so a caller can diagnose a launch it prepared itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps pydantic out of the core import graph
    from launcher.instances import ResolvedInstance


@dataclass(frozen=True)
class DiagnosisContext:
    """Input of :func:`launcher.diagnostics.diagnose`.

    version_id          profile / instance id of the launch (also the folder name)
    game_dir            shared game directory (versions / libraries / assets)
    launch_dir          effective working directory of the game process; None = game_dir
    instance            the resolved instance, when the caller has one
    exit_code           process exit code; None when the launch never started
    launch_started_at   epoch seconds of the launch start — the freshness gate:
                        only files with ``mtime >= launch_started_at`` are used.
                        0 disables the gate (manual log analysis).
    captured_output     line tail of the game's stdout/stderr (see run_process)
    error_text          launcher-side failure text (exception type + message) when
                        the launcher failed before/while starting the game
    launcher_logs_dir   override for the launcher's own log directory
    rules_path          override for data/rules.json (tests / custom knowledge bases)
    memory_gb           heap size the launcher passed to the JVM
    java_path/java_major  the Java runtime used for this launch
    isolated            whether the instance was launched isolated
    mods_dir            effective mods directory
    now                 override "now" (unused by the pipeline, kept for callers)
    """

    version_id: str = ""
    game_dir: Path | None = None
    launch_dir: Path | None = None
    instance: ResolvedInstance | None = None
    exit_code: int | None = None
    launch_started_at: float = 0.0
    captured_output: Sequence[str] = field(default_factory=tuple)
    error_text: str = ""
    launcher_logs_dir: Path | None = None
    rules_path: Path | None = None
    memory_gb: float | None = None
    java_path: Path | None = None
    java_major: int | None = None
    isolated: bool | None = None
    mods_dir: Path | None = None
    now: float | None = None

    # ---- resolution helpers (explicit argument first, resolved instance second) ----
    def _from_instance(self, name: str):
        return getattr(self.instance, name, None) if self.instance is not None else None

    def resolved_game_dir(self) -> Path:
        for value in (self.game_dir, self._from_instance("game_dir")):
            if value is not None:
                return Path(value)
        return Path(".")

    def resolved_launch_dir(self) -> Path:
        for value in (self.launch_dir, self._from_instance("launch_dir")):
            if value is not None:
                return Path(value)
        return self.resolved_game_dir()

    def resolved_mods_dir(self) -> Path | None:
        for value in (self.mods_dir, self._from_instance("mods_dir")):
            if value is not None:
                return Path(value)
        return None

    def resolved_memory_gb(self) -> float | None:
        for value in (self.memory_gb, self._from_instance("memory_gb")):
            if value is not None:
                return float(value)
        return None

    def resolved_java_path(self) -> Path | None:
        for value in (self.java_path, self._from_instance("java_path")):
            if value is not None:
                return Path(value)
        return None

    def resolved_isolated(self) -> bool | None:
        if self.isolated is not None:
            return bool(self.isolated)
        return self._from_instance("isolated")

    def search_roots(self) -> list[Path]:
        """Directories searched for game logs, most specific first (de-duplicated).

        An isolated instance writes its ``logs/`` and ``crash-reports/`` into the
        instance folder, but a few failures still land in the shared game
        directory, so both are searched.
        """
        roots: list[Path] = []
        seen: set[str] = set()
        for value in (self.resolved_launch_dir(), self.resolved_game_dir()):
            key = str(value).lower()
            if key not in seen:
                seen.add(key)
                roots.append(value)
        return roots
