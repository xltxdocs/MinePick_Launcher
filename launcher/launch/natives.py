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

"""Natives extraction: version-isolated directory, rebuilt before every launch."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from launcher.i18n import tr_core
from launcher.install import library_path
from launcher.meta.rules import ResolvedLibrary


class LaunchError(Exception):
    """Launch-related error (user-facing message)."""


def prepare_natives(
    resolved: list[ResolvedLibrary], libraries_dir: Path, natives_dir: Path
) -> Path:
    """Clear and extract all natives libraries for the current platform into the version-specific directory."""
    if natives_dir.exists():
        shutil.rmtree(natives_dir, ignore_errors=True)
    natives_dir.mkdir(parents=True, exist_ok=True)
    for item in resolved:
        if item.classifier is None:
            continue
        lib = item.library
        downloads = lib.downloads
        classifiers = downloads.classifiers if downloads else None
        art = classifiers.get(item.classifier) if classifiers else None
        if art is None and downloads is not None:
            # modern natives entries: the artifact is the natives jar
            art = downloads.artifact
        rel = (
            art.path
            if art is not None and art.path
            else library_path(lib.name, item.classifier)
        )
        jar = libraries_dir / rel
        if not jar.exists():
            raise LaunchError(tr_core("launch.missing_natives", rel))
        excludes = ["META-INF/"]
        if lib.extract and isinstance(lib.extract.get("exclude"), list):
            excludes += [str(entry) for entry in lib.extract["exclude"]]
        _extract_jar(jar, natives_dir, excludes)
    return natives_dir


def _extract_jar(jar: Path, dest: Path, excludes: list[str]) -> None:
    with zipfile.ZipFile(jar) as zf:
        for member in zf.infolist():
            name = member.filename
            if member.is_dir() or any(name.startswith(prefix) for prefix in excludes):
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
