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

"""Java runtime detection and matching.

Detection order (the source of the provider marker):
  1. managed  -- launcher-managed directory (launcher data dir/runtime/java-<major>/bin);
  2. java_home -- the JAVA_HOME env var;
  3. path -- java on PATH;
  4. system -- common install directories (Windows: per-vendor dirs under Program Files; Linux: /usr/lib/jvm).

Sandbox/packaging compatible: when pipe-captured probing fails, it automatically falls back to file redirection (not relying on piped stdio).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from launcher import paths

VERSION_RE = re.compile(r'version "([^"]+)"')
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # don't pop a console window when probing from the GUI


class JavaError(Exception):
    """Java-runtime-related error (user-facing message)."""


@dataclass(frozen=True)
class JavaRuntime:
    path: Path
    major: int
    provider: str  # managed / config / java_home / path / system
    version: str = ""


def parse_java_major(version_output: str) -> int | None:
    """Parse the major version from java -version output: 1.8.0_401 -> 8, 17.0.10 -> 17."""
    match = VERSION_RE.search(version_output)
    if match is None:
        return None
    ver = match.group(1)
    try:
        if ver.startswith("1."):
            return int(ver.split(".")[1])
        return int(ver.split(".")[0].split("-")[0])  # strip suffixes like 21-ea
    except (ValueError, IndexError):
        return None


def probe_java_major(
    java_path: Path, probe_dir: Path | None = None
) -> JavaRuntime | None:
    """Run java -version and parse it. probe_dir holds the redirected output file in restricted environments."""
    cmd = [str(java_path), "-version"]
    try:
        extra = {"creationflags": NO_WINDOW} if os.name == "nt" else {}
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            **extra,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
    except OSError:
        # piped stdio is forbidden (this dev sandbox): fall back to file redirection
        if probe_dir is not None:
            probe_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = probe_dir / ("java-probe-" + str(os.getpid()) + ".txt")
        else:
            try:
                fd, name = tempfile.mkstemp(suffix=".txt")
                os.close(fd)
                tmp_path = Path(name)
            except OSError:
                return None
        try:
            with tmp_path.open("w", encoding="utf-8", errors="replace") as f:
                extra = {"creationflags": NO_WINDOW} if os.name == "nt" else {}
                proc = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                    check=False,
                    **extra,
                )
            output = tmp_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            return None
        finally:
            tmp_path.unlink(missing_ok=True)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    major = parse_java_major(output)
    if major is None:
        return None
    first_line = output.strip().splitlines()[0] if output.strip() else ""
    return JavaRuntime(path=java_path, major=major, provider="unknown", version=first_line)


def _managed_runtime_dirs() -> list[Path]:
    base = paths.launcher_dir() / "runtime"
    if not base.exists():
        return []
    return [p for p in sorted(base.iterdir()) if p.is_dir()]


def _java_candidates() -> list[tuple[Path, str]]:
    """Collect (java executable, provider) candidates."""
    exe_name = "java.exe" if os.name == "nt" else "java"
    out: list[tuple[Path, str]] = []

    for d in _managed_runtime_dirs():
        exe = d / "bin" / exe_name
        if exe.exists():
            out.append((exe, "managed"))

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        exe = Path(java_home) / "bin" / exe_name
        if exe.exists():
            out.append((exe, "java_home"))

    which = shutil.which("java")
    if which:
        out.append((Path(which), "path"))

    if os.name == "nt":
        roots: list[Path] = []
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(env_name)
            if value:
                roots.append(Path(value))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local))
        for root in roots:
            for vendor in (
                "Java",
                "Eclipse Adoptium",
                "Microsoft",
                "Zulu",
                "Amazon Corretto",
                "BellSoft",
            ):
                base = root / vendor
                if not base.exists():
                    continue
                for exe in base.glob("*/bin/java.exe"):
                    out.append((exe, "system"))
    else:
        for base in (Path("/usr/lib/jvm"), Path("/opt")):
            if base.exists():
                for exe in base.glob("*/bin/java"):
                    out.append((exe, "system"))
    return out


def list_java(probe_dir: Path | None = None) -> list[JavaRuntime]:
    """Probe all candidate Javas; sort by (major descending, managed first)."""
    seen: set[Path] = set()
    runtimes: list[JavaRuntime] = []
    for exe, provider in _java_candidates():
        try:
            resolved = exe.resolve()
        except OSError:
            resolved = exe
        if resolved in seen:
            continue
        seen.add(resolved)
        runtime = probe_java_major(exe, probe_dir=probe_dir)
        if runtime is None:
            continue
        runtimes.append(
            JavaRuntime(
                path=resolved,
                major=runtime.major,
                provider=provider,
                version=runtime.version,
            )
        )
    runtimes.sort(key=lambda r: (-r.major, r.provider != "managed", str(r.path)))
    return runtimes


def has_suitable_java(runtimes: list[JavaRuntime], required_major: int) -> bool:
    """Whether a suitable Java exists.

    - needing 8 (old versions): must be exactly 8 (9+ can't run 1.16.5 and earlier);
    - needing 16/17/21: any major >= the requirement works.
    """
    if not runtimes:
        return False
    if required_major <= 8:
        return any(r.major == 8 for r in runtimes)
    return any(r.major >= required_major for r in runtimes)


def match_java(
    runtimes: list[JavaRuntime], required_major: int | None
) -> JavaRuntime | None:
    """Pick the most suitable Java:
    1. a managed runtime with an exact major match;
    2. any source with an exact major match;
    3. the smallest major >= the requirement (managed preferred on ties);
    4. any (take the largest major).
    """
    if not runtimes:
        return None
    if required_major is None:
        return max(runtimes, key=lambda r: r.major)
    managed_exact = [r for r in runtimes if r.provider == "managed" and r.major == required_major]
    if managed_exact:
        return managed_exact[0]
    exact = [r for r in runtimes if r.major == required_major]
    if exact:
        return exact[0]
    ge = [r for r in runtimes if r.major >= required_major]
    if ge:
        return min(ge, key=lambda r: (r.major, r.provider != "managed"))
    return max(runtimes, key=lambda r: r.major)
