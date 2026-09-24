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

"""Environment facts of one launch.

Facts are what the rules and the report talk about — exit code, Java major and
path, the configured heap size, loader kind, Minecraft version, isolation state,
OS architecture and the installed mod list (read straight from ``mods/*.jar``
metadata via :func:`launcher.mods.local.scan_mods`, never guessed from a crash
report).

Nothing here touches the network, and the Java major version is taken from the
caller (the launcher already knows it from the prepared launch) — the core never
spawns ``java -version`` behind the user's back.
"""

from __future__ import annotations

import logging
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from launcher.diagnostics.context import DiagnosisContext
from launcher.mods.local import scan_mods

_LOGGER = logging.getLogger(__name__)

LOADER_NAMES = {
    "vanilla": "Vanilla",
    "fabric": "Fabric",
    "forge": "Forge",
    "neoforge": "NeoForge",
    "quilt": "Quilt",
    "unknown": "",
}
UNKNOWN_VALUE = "-"


@dataclass(frozen=True)
class ModFact:
    """One file in the effective mods directory."""

    file: str
    name: str
    mod_id: str
    version: str
    loader: str
    enabled: bool


@dataclass(frozen=True)
class EnvironmentFacts:
    """Everything the report says about the environment of this launch."""

    instance_id: str
    exit_code: int | None
    java_major: int | None
    java_path: str
    memory_gb: float | None
    memory_from_instance: bool
    loader: str
    mc_version: str
    isolated: bool | None
    os_name: str
    os_arch: str
    game_dir: str
    launch_dir: str
    mods: tuple[ModFact, ...]

    # ---- display helpers (units / product names only, never prose) ----
    @property
    def loader_name(self) -> str:
        return LOADER_NAMES.get(self.loader, "") or LOADER_NAMES["unknown"]

    @property
    def java_text(self) -> str:
        if self.java_major is None and not self.java_path:
            return UNKNOWN_VALUE
        major = str(self.java_major) if self.java_major is not None else UNKNOWN_VALUE
        return f"{major} · {self.java_path}" if self.java_path else major

    @property
    def memory_text(self) -> str:
        if self.memory_gb is None:
            return UNKNOWN_VALUE
        return f"{self.memory_gb:g} GB"

    @property
    def mods_text(self) -> str:
        return str(len(self.mods))

    def placeholder(self, name: str) -> str:
        """Value of a ``{name}`` placeholder used in rule advice/keys."""
        values = {
            "memory": self.memory_text,
            "java": str(self.java_major) if self.java_major is not None else UNKNOWN_VALUE,
            "java_path": self.java_path or UNKNOWN_VALUE,
            "mc": self.mc_version or UNKNOWN_VALUE,
            "loader": self.loader_name or UNKNOWN_VALUE,
            "instance": self.instance_id or UNKNOWN_VALUE,
            "exit_code": str(self.exit_code) if self.exit_code is not None else UNKNOWN_VALUE,
            "mods": self.mods_text,
            "os": self.os_name,
            "os_arch": self.os_arch,
            "game_dir": self.game_dir or UNKNOWN_VALUE,
            "launch_dir": self.launch_dir or UNKNOWN_VALUE,
        }
        return values.get(name, UNKNOWN_VALUE)


def os_arch_text() -> str:
    """Human-readable OS architecture of this machine ("64-bit" / "32-bit")."""
    return "64-bit" if sys.maxsize > 2**32 else "32-bit"


def os_name_text() -> str:
    """OS name + machine type, e.g. ``Windows 11 (AMD64)``."""
    system = platform.system() or "Unknown"
    release = platform.release()
    machine = platform.machine()
    name = f"{system} {release}".strip()
    return f"{name} ({machine})" if machine else name


def derive_version_facts(version_id: str) -> tuple[str, str]:
    """Return ``(loader, minecraft version)`` derived from a profile id.

    ``fabric-loader-0.19.3-1.21.11`` -> ``("fabric", "1.21.11")``;
    ``neoforge-21.1.5`` -> ``("neoforge", "1.21.1")``;
    ``1.20.1-forge-47.4.22`` -> ``("forge", "1.20.1")``;
    anything else is treated as a vanilla version id.
    """
    vid = (version_id or "").strip()
    if vid.startswith("fabric-loader-"):
        parts = vid.split("-")
        return "fabric", parts[-1] if parts else ""
    if vid.startswith("quilt-loader-"):
        parts = vid.split("-")
        return "quilt", parts[-1] if parts else ""
    if vid.startswith("neoforge-"):
        return "neoforge", _mc_from_neoforge(vid[len("neoforge-") :])
    if "-forge-" in vid:
        mc, _, _loader_version = vid.partition("-forge-")
        return "forge", mc
    if vid.endswith("-forge"):
        return "forge", vid[: -len("-forge")]
    return "vanilla", vid


def _mc_from_neoforge(version: str) -> str:
    """NeoForge 21.1.5 -> Minecraft 1.21.1 (1.20.1-47.x keeps its explicit prefix)."""
    if version.startswith("1.") and version.count(".") >= 2 and "-" in version:
        return version.split("-", 1)[0]  # "1.20.1-47.1.79" style
    parts = version.split(".")
    if len(parts) >= 2 and parts[0].isdigit():
        return f"1.{parts[0]}.{parts[1]}"
    return ""


def collect_facts(context: DiagnosisContext) -> EnvironmentFacts:
    """Read the environment facts for one diagnosis request."""
    loader, mc_version = derive_version_facts(context.version_id)

    mods: tuple[ModFact, ...] = ()
    mods_dir = context.resolved_mods_dir()
    if mods_dir is not None:
        try:
            mods = tuple(
                ModFact(
                    file=item.file,
                    name=item.name,
                    mod_id=item.mod_id,
                    version=item.version,
                    loader=item.loader,
                    enabled=item.enabled,
                )
                for item in scan_mods(Path(mods_dir))
            )
        except OSError as exc:  # pragma: no cover - unreadable mods directory
            _LOGGER.warning("diagnostics: cannot scan the mods directory %s: %s", mods_dir, exc)

    return EnvironmentFacts(
        instance_id=context.version_id,
        exit_code=context.exit_code,
        java_major=context.java_major,
        java_path=str(context.resolved_java_path() or ""),
        memory_gb=context.resolved_memory_gb(),
        memory_from_instance=bool(getattr(context.instance, "memory_from_instance", False)),
        loader=loader,
        mc_version=mc_version,
        isolated=context.resolved_isolated(),
        os_name=os_name_text(),
        os_arch=os_arch_text(),
        game_dir=str(context.resolved_game_dir()),
        launch_dir=str(context.resolved_launch_dir()),
        mods=mods,
    )
