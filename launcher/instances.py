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
"""Instance management: instances are recognized by their folder structure.

Every subdirectory of <game dir>/instances/ is an instance. Optional metadata
(name, version id, creation time, note) lives in <instance>/instance.json;
folders without it are synthesized (version id read from versions/<id>/,
creation time from the folder mtime). The legacy registry file instances.json
is only used for a one-time metadata backfill.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
import zipfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from launcher import paths
from launcher.i18n import tr_core
from launcher.meta.version import load_version_json

INSTANCE_META_FILENAME = "instance.json"  # per-instance metadata inside the folder
INSTANCES_FILENAME = "instances.json"  # legacy registry (migration source only)
_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff ._-]{0,31}$")


class Instance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    version_id: str
    created_at: float
    note: str = ""  # user note
    base: bool = False  # True = a base version detected in the global versions/ folder


class InstancesError(Exception):
    """Instance operation error (message is user-facing)."""


def _game_dir() -> Path:
    """The configured game directory (falling back to the official folder)."""
    from launcher import config

    cfg, _ = config.load()
    return cfg.game_dir or paths.default_game_dir()


def default_instance_name(version_id: str) -> str:
    """Generate a default instance name from a version/profile id.

    Vanilla -> the version number itself (e.g. 1.20.1);
    mod profile -> version_loader_name_loader_version (e.g. 1.21.11_fabric_0.19.3).
    """
    if version_id.startswith("fabric-loader-"):
        parts = version_id.split("-")
        return parts[-1] + "_fabric_" + parts[2]
    if version_id.startswith("neoforge-"):
        base = version_id[len("neoforge-"):]
        parts = base.split(".")
        mc = ".".join(parts[:3]) if len(parts) >= 4 else "1." + ".".join(parts[:2])
        return mc + "_neoforge_" + base
    if "-forge-" in version_id:
        mc, lv = version_id.split("-forge-")
        return mc + "_forge_" + lv
    return version_id


def display_version_name(version_id: str) -> str:
    """Human-readable profile name (loader names capitalized).

    fabric-loader-0.15.11-1.20.1 -> "Fabric 0.15.11-1.20.1"
    neoforge-21.1.5            -> "NeoForge 21.1.5"
    1.20.1-forge-47.4.22       -> "Forge 47.4.22 (1.20.1)"
    quilt-loader-0.24.0-1.20.1 -> "Quilt 0.24.0-1.20.1"
    """
    if version_id.startswith("fabric-loader-"):
        parts = version_id.split("-")
        if len(parts) >= 4:
            return "Fabric " + parts[2] + "-" + parts[3]
        return "Fabric " + version_id[len("fabric-loader-"):]
    if version_id.startswith("quilt-loader-"):
        parts = version_id.split("-")
        if len(parts) >= 4:
            return "Quilt " + parts[2] + "-" + parts[3]
        return "Quilt " + version_id[len("quilt-loader-"):]
    if version_id.startswith("neoforge-"):
        return "NeoForge " + version_id[len("neoforge-"):]
    if "-forge-" in version_id:
        mc, lv = version_id.split("-forge-", 1)
        return "Forge " + lv + " (" + mc + ")"
    return version_id


def validate_name(name: str) -> str:
    name = name.strip()
    if not name or not _NAME_RE.match(name):
        raise InstancesError(tr_core("instances.name_invalid"))
    return name


def instance_dir(game_dir: Path, name: str) -> Path:
    return game_dir / "instances" / name


def _load_folder_meta(folder: Path) -> Instance:
    """Read instance.json from the folder; synthesize metadata when missing."""
    # Same detection logic as the launch page dropdown: an entry under
    # versions/ only counts as a version when <id>/<id>.json exists.
    version_id = ""
    try:
        from launcher.install import list_installed_versions

        detected = list_installed_versions(folder)
        if detected:
            version_id = detected[0]
    except ImportError:  # launcher.install is always present in practice
        pass
    created_at = time.time()
    note = ""
    try:
        created_at = folder.stat().st_mtime
    except OSError:
        pass
    meta_file = folder / INSTANCE_META_FILENAME
    if meta_file.exists():
        try:
            inst = Instance.model_validate(json.loads(meta_file.read_text(encoding="utf-8-sig")))
            note = inst.note
            # The folder structure is the source of truth: only keep the stored
            # version id when the versions/ folder is absent.
            if not version_id:
                version_id = inst.version_id
        except (ValueError, TypeError, OSError):  # fall back to synthesized metadata
            logging.getLogger(__name__).warning("Ignoring corrupt instance metadata: %s", meta_file)
    return Instance(name=folder.name, version_id=version_id, created_at=created_at, note=note)


def _write_folder_meta(folder: Path, inst: Instance) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (INSTANCE_META_FILENAME + ".tmp")
    tmp.write_text(json.dumps(inst.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(folder / INSTANCE_META_FILENAME)


def _backfill_from_registry(game_dir: Path) -> None:
    """One-time best-effort backfill of per-folder metadata from the legacy registry."""
    for reg_path in (game_dir / INSTANCES_FILENAME, paths.launcher_dir() / INSTANCES_FILENAME):
        if not reg_path.exists():
            continue
        try:
            raw = json.loads(reg_path.read_text(encoding="utf-8-sig"))
            entries = raw.get("instances", raw) if isinstance(raw, dict) else {}
            if not isinstance(entries, dict):
                continue
            for key, value in entries.items():
                folder = instance_dir(game_dir, str(key))
                if not folder.is_dir() or (folder / INSTANCE_META_FILENAME).exists():
                    continue
                try:
                    inst = Instance.model_validate(value)
                    inst.name = str(key)
                    _write_folder_meta(folder, inst)
                except (ValueError, TypeError, OSError):  # skip corrupt entries
                    logging.getLogger(__name__).warning("Skipping corrupt legacy instance entry: %s", key)
        except Exception:  # migration is best-effort
            logging.getLogger(__name__).debug("Instance registry backfill failed for %s", reg_path, exc_info=True)


def list_instances() -> dict[str, Instance]:
    """List launchable entries.

    - Custom instances: every folder under <game dir>/instances/.
    - Base versions/profiles: every installed version in <game dir>/versions/,
      detected with the same rule as the launch page (needs <id>/<id>.json).
    """
    game_dir = _game_dir()
    _backfill_from_registry(game_dir)
    out: dict[str, Instance] = {}
    base = game_dir / "instances"
    if base.is_dir():
        for entry in sorted(base.iterdir()):
            if entry.is_dir():
                out[entry.name] = _load_folder_meta(entry)
    # Base versions from the global versions folder (launch-page detection logic)
    try:
        from launcher.install import list_installed_versions

        detected = sorted(list_installed_versions(game_dir))
    except ImportError:
        detected = []
    for version_id in detected:
        if version_id in out:
            continue  # a custom instance with the same name wins
        folder = game_dir / "versions" / version_id
        try:
            created_at = folder.stat().st_mtime
        except OSError:
            created_at = time.time()
        out[version_id] = Instance(
            name=version_id, version_id=version_id, created_at=created_at, base=True
        )
    return out


def create_instance(
    name: str | None,
    version_id: str,
    game_dir: Path,
    *,
    cache_dir: Path | None = None,
) -> Instance:
    """Create an instance: copy the version JSON and client jar into the instance folder."""
    name = validate_name(name or default_instance_name(version_id))
    target = instance_dir(game_dir, name)
    if target.exists():
        raise InstancesError(tr_core("instances.exists", name))

    gp = paths.GamePaths(game_dir)
    version = load_version_json(
        version_id,
        versions_dir=gp.versions_dir,
        cache_dir=cache_dir,
    )
    target_versions = target / "versions"
    version_dir = target_versions / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        version.model_dump(by_alias=True, exclude_none=True),
        ensure_ascii=False,
        indent=2,
    )
    (version_dir / (version_id + ".json")).write_text(payload, encoding="utf-8")
    source_jar = gp.version_dir(version_id) / version.client_jar_name
    dest_jar = version_dir / version.client_jar_name
    if source_jar.exists():
        shutil.copyfile(source_jar, dest_jar)
    # Deferred import to avoid a circular dependency with the launcher.mods package
    from launcher.mods.installer import _copy_game_jar

    _copy_game_jar(version_id, target)  # copy of the loader profile's parent jar

    instance = Instance(name=name, version_id=version_id, created_at=time.time())
    _write_folder_meta(target, instance)
    return instance


def rename_instance(name: str, new_name: str, game_dir: Path) -> Instance:
    """Rename an instance: rename its folder and update the folder metadata."""
    name = validate_name(name)
    new_name = validate_name(new_name)
    old_dir = instance_dir(game_dir, name)
    new_dir = instance_dir(game_dir, new_name)
    if not old_dir.is_dir():
        raise InstancesError(tr_core("instances.missing", name))
    if new_dir.exists():
        raise InstancesError(tr_core("instances.dir_exists", str(new_dir)))
    inst = _load_folder_meta(old_dir)
    old_dir.rename(new_dir)
    inst.name = new_name
    _write_folder_meta(new_dir, inst)
    return inst


def update_instance_note(name: str, note: str) -> Instance:
    """Update the instance note (stored in the folder metadata)."""
    name = validate_name(name)
    folder = instance_dir(_game_dir(), name)
    if not folder.is_dir():
        raise InstancesError(tr_core("instances.missing", name))
    inst = _load_folder_meta(folder)
    inst.note = note.strip()
    _write_folder_meta(folder, inst)
    return inst


def export_instance(name: str, dest_zip: Path, game_dir: Path) -> Path:
    """Export the instance to a zip archive (version files/saves/mods/config and metadata)."""
    name = validate_name(name)
    source = instance_dir(game_dir, name)
    if not source.is_dir():
        raise InstancesError(tr_core("instances.missing", name))
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_zip.with_name(dest_zip.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "instance.json",
            json.dumps(
                _load_folder_meta(source).model_dump(mode="json"), ensure_ascii=False, indent=2
            ),
        )
        for path in source.rglob("*"):
            # The folder's own instance.json is replaced by the freshly written root one
            if path.is_file() and path.name != INSTANCE_META_FILENAME:
                zf.write(path, path.relative_to(source).as_posix())
    tmp.replace(dest_zip)
    return dest_zip


def import_instance(
    zip_path: Path, game_dir: Path, *, new_name: str | None = None
) -> Instance:
    """Import an instance from a zip: extract into the instance folder and write metadata."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "instance.json" not in names:
            raise InstancesError(tr_core("instances.import_invalid"))
        try:
            meta = Instance.model_validate(json.loads(zf.read("instance.json")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise InstancesError(tr_core("instances.import_invalid")) from exc
        name = validate_name(new_name or meta.name)
        target = instance_dir(game_dir, name)
        if target.exists():
            raise InstancesError(tr_core("instances.dir_exists", str(target)))
        target.mkdir(parents=True)
        for entry in names:
            if entry == "instance.json" or entry.endswith(("/", "\\")):
                continue
            rel = Path(entry)
            if ".." in rel.parts:  # zip-slip protection
                raise InstancesError(tr_core("instances.import_invalid"))
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(entry) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    inst = Instance(
        name=name,
        version_id=meta.version_id,
        created_at=meta.created_at or time.time(),
        note=meta.note or "",
    )
    _write_folder_meta(target, inst)
    return inst


def delete_instance(name: str, game_dir: Path) -> None:
    name = validate_name(name)
    folder = instance_dir(game_dir, name)
    if not folder.is_dir():
        raise InstancesError(tr_core("instances.missing", name))
    shutil.rmtree(folder, ignore_errors=True)
