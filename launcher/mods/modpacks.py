"""Modpack (Modrinth .mrpack) download and install.

Flow: download the .mrpack -> parse modrinth.index.json -> auto-install the needed loader
-> create a same-named instance -> download all files + merge overrides.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from launcher import paths as launcher_paths
from launcher.i18n import describe_network_error, tr_core
from launcher.instances import create_instance, default_instance_name, validate_name
from launcher.meta.manifest import _new_client
from launcher.mods.installer import install_loader
from launcher.mods.loaders import ModsError, list_loader_versions
from launcher.mods.models import LoaderVersion
from launcher.mods.modrinth import fetch_versions, pick_file
from launcher.net.downloader import Downloader, DownloadProgress, DownloadTask


@dataclass
class ModpackInfo:
    name: str
    version: str
    loader: str | None
    loader_version: str | None
    minecraft: str | None
    files_count: int
    instance_name: str


def _download_direct(url: str, dest: Path) -> None:
    client = _new_client()
    try:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(64 * 1024):
                    f.write(chunk)
    except httpx.HTTPError as exc:
        raise ModsError(tr_core("mods.download_failed", describe_network_error(exc))) from exc
    finally:
        client.close()


def _loader_from_deps(deps: dict) -> tuple[str | None, str | None, str | None]:
    minecraft = deps.get("minecraft")
    if "fabric-loader" in deps:
        return "fabric", deps["fabric-loader"], minecraft
    if "forge" in deps:
        return "forge", deps["forge"], minecraft
    if "neoforge" in deps:
        return "neoforge", deps["neoforge"], minecraft
    return None, None, minecraft


def _profile_id(loader: str, loader_version: str, minecraft: str) -> str:
    if loader == "fabric":
        return "fabric-loader-" + loader_version + "-" + minecraft
    if loader == "forge":
        return minecraft + "-forge-" + loader_version
    return "neoforge-" + loader_version


def _ensure_loader_profile(
    loader: str, loader_version: str, minecraft: str, game_dir: Path, cache_dir: Path
) -> str:
    """Ensure the loader profile is installed; if missing, install it automatically with the official installer. Return the profile id."""
    profile_id = _profile_id(loader, loader_version, minecraft)
    gp = launcher_paths.GamePaths(game_dir)
    if (gp.version_dir(profile_id) / (profile_id + ".json")).exists():
        return profile_id
    versions = list_loader_versions(loader, minecraft)
    chosen: LoaderVersion | None = next(
        (v for v in versions if v.version == loader_version), None
    )
    if chosen is None:
        if loader == "fabric" and versions:
            # the Fabric loader is highly compatible: fall back to the latest stable when the old version isn't listed
            chosen = versions[0]
        else:
            raise ModsError(tr_core("mods.loader_unavailable", loader, loader_version, minecraft))
    return install_loader(chosen, game_dir, cache_dir=cache_dir)


def install_modpack(
    slug: str,
    *,
    game_dir: Path,
    cache_dir: Path | None = None,
    mod_version_id: str | None = None,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> ModpackInfo:
    """Download and install a modpack: auto-install the loader, create an instance, install files."""
    cache_dir = cache_dir or (launcher_paths.launcher_dir() / "cache")
    versions = fetch_versions(slug)
    if not versions:
        raise ModsError(tr_core("mods.pack_no_versions"))
    gp = launcher_paths.GamePaths(game_dir)
    installed = {p.name for p in gp.versions_dir.iterdir()} if gp.versions_dir.exists() else set()

    def download_and_parse(candidate) -> tuple[dict, dict[str, bytes]]:
        file = pick_file(candidate)
        if file is None or not file.url:
            raise ModsError(tr_core("mods.no_file"))
        mrpack_path = (
            cache_dir / "modpacks" / (slug + "-" + candidate.version_id + ".mrpack")
        )
        _download_direct(file.url, mrpack_path)
        with zipfile.ZipFile(mrpack_path) as zf:
            index = json.loads(zf.read("modrinth.index.json"))
            overrides_data = {
                n: zf.read(n) for n in zf.namelist() if n.startswith("overrides/")
            }
        return index, overrides_data

    if mod_version_id:
        candidate = next((v for v in versions if v.version_id == mod_version_id), None)
        if candidate is None:
            raise ModsError(tr_core("mods.version_not_in_list", mod_version_id))
        index, overrides_data = download_and_parse(candidate)
        picked = candidate
    else:
        # prefer the build matching a locally installed MC version (verify the MC in the index after download)
        ordered = [v for v in versions if any(gv in installed for gv in v.game_versions)]
        ordered += [v for v in versions if v not in ordered]
        index, overrides_data, picked = None, {}, versions[0]
        for candidate in ordered[:5]:
            try:
                idx, ov = download_and_parse(candidate)
            except ModsError:
                continue
            mc = (idx.get("dependencies") or {}).get("minecraft")
            if mc in installed:
                index, overrides_data, picked = idx, ov, candidate
                break
            index, overrides_data = idx, ov  # keep the last one as a fallback
        if index is None:
            raise ModsError(tr_core("mods.pack_parse_failed"))

    deps = index.get("dependencies") or {}
    loader, loader_version, minecraft = _loader_from_deps(deps)
    if not minecraft:
        raise ModsError(tr_core("mods.pack_mc_missing"))
    gp = launcher_paths.GamePaths(game_dir)
    installed = {p.name for p in gp.versions_dir.iterdir()} if gp.versions_dir.exists() else set()
    if minecraft not in installed and loader in ("forge", "neoforge"):
        raise ModsError(tr_core("mods.pack_need_base_mc", minecraft))
    base_id = (
        _ensure_loader_profile(loader, loader_version, minecraft, game_dir, cache_dir)
        if loader
        else minecraft
    )

    pack_name = (index.get("name") or slug).strip()
    try:
        instance_name = validate_name(pack_name)
    except Exception:  # noqa: BLE001 - fall back to the default name when the name is invalid
        instance_name = default_instance_name(base_id)
    from launcher.instances import InstanceStore

    if instance_name in InstanceStore().load():
        raise ModsError(tr_core("mods.instance_exists", instance_name))
    create_instance(instance_name, base_id, game_dir, cache_dir=cache_dir)

    from launcher.instances import instance_dir

    target = instance_dir(game_dir, instance_name)
    tasks: list[DownloadTask] = []
    for entry in index.get("files", []):
        env = entry.get("env") or {}
        if env.get("server") is True and env.get("client") is not True:
            continue  # skip server-only files
        rel = entry.get("path") or ""
        urls = entry.get("downloads") or []
        if not urls or not rel:
            continue
        hashes = entry.get("hashes") or {}
        tasks.append(
            DownloadTask(
                url=urls[0],
                dest=target / rel,
                sha1=hashes.get("sha1"),
                size=int(entry.get("fileSize") or 0) or None,
            )
        )
    result = Downloader(concurrency=8).download(tasks, progress=progress)
    if result.failed:
        raise ModsError(tr_core("mods.pack_files_failed", len(result.failed)))

    # merge overrides (strip the prefix)
    for name, data in overrides_data.items():
        rel = name[len("overrides/") :]
        if not rel:
            continue
        dest = target / rel
        if name.endswith("/"):
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    return ModpackInfo(
        name=pack_name,
        version=picked.version_number,
        loader=loader,
        loader_version=loader_version,
        minecraft=minecraft,
        files_count=len(tasks),
        instance_name=instance_name,
    )
