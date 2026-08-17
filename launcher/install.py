"""Version install: download version JSON, client jar, libraries, natives, assets,
and logging config into the official directory layout.

Packaging-compatible: all paths are based on the runtime-resolved game directory
(GamePaths), not __file__; downloads are all done by net.Downloader (thread pool +
verification + retry).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import httpx

from launcher import paths
from launcher.i18n import tr_core
from launcher.meta.assets import AssetIndex, fetch_asset_index, missing_assets
from launcher.meta.rules import (
    Platform,
    ResolvedLibrary,
    detect_platform,
    resolve_libraries,
)
from launcher.meta.version import (
    Artifact,
    VersionJson,
    load_version_json,
    required_java_major,
)
from launcher.net.downloader import (
    Downloader,
    DownloadProgress,
    DownloadResult,
    DownloadTask,
)

DEFAULT_LIBRARY_BASE = "https://libraries.minecraft.net/"
ASSET_BASE = "https://resources.download.minecraft.net/"
CLIENT_JAR_FALLBACK = "https://launcher.mojang.com/v1/objects/{sha1}/client.jar"


def library_path(name: str, classifier: str | None = None) -> str:
    """Build the default relative path from the coordinate name (maven-style)."""
    parts = name.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    eff_classifier = classifier or (parts[3] if len(parts) > 3 else None)
    filename = artifact + "-" + version
    if eff_classifier:
        filename += "-" + eff_classifier
    return group.replace(".", "/") + "/" + artifact + "/" + version + "/" + filename + ".jar"


def _library_task(resolved: ResolvedLibrary, libraries_dir: Path) -> DownloadTask:
    lib = resolved.library
    downloads = lib.downloads
    if resolved.classifier is not None:
        classifiers = downloads.classifiers if downloads else None
        art: Artifact | None = classifiers.get(resolved.classifier) if classifiers else None
        if art is None:
            # Modern natives entries (4th segment of library name is the classifier): the artifact is the natives jar
            art = downloads.artifact if downloads else None
    else:
        art = downloads.artifact if downloads else None

    if art is not None and art.path:
        rel = art.path
    else:
        rel = library_path(lib.name, resolved.classifier)

    if art is not None and art.url:
        url = art.url
    elif lib.url and art is not None and art.path:
        url = lib.url.rstrip("/") + "/" + art.path
    elif art is not None and art.path:
        url = DEFAULT_LIBRARY_BASE + art.path
    else:
        url = DEFAULT_LIBRARY_BASE + rel

    return DownloadTask(
        url=url,
        dest=libraries_dir / rel,
        sha1=art.sha1 if art is not None else None,
        size=art.size if art is not None else None,
    )


def list_installed_versions(game_dir: Path) -> list[str]:
    """List installed version/profile ids (versions/<id>/ exists and contains <id>.json)."""
    versions_dir = paths.GamePaths(game_dir).versions_dir
    if not versions_dir.exists():
        return []
    out: list[str] = []
    for entry in versions_dir.iterdir():
        if entry.is_dir() and (entry / (entry.name + ".json")).exists():
            out.append(entry.name)
    return sorted(out)


def find_version_dependents(game_dir: Path, version_id: str) -> list[str]:
    """Find other profile ids under versions/ that inherit from version_id (inheritsFrom)."""
    versions_dir = paths.GamePaths(game_dir).versions_dir
    dependents: list[str] = []
    if not versions_dir.exists():
        return dependents
    for entry in versions_dir.iterdir():
        if not entry.is_dir() or entry.name == version_id:
            continue
        json_file = entry / (entry.name + ".json")
        if not json_file.exists():
            continue
        try:
            raw = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict) and raw.get("inheritsFrom") == version_id:
            dependents.append(entry.name)
    return sorted(dependents)


def uninstall_version(version_id: str, game_dir: Path) -> list[str]:
    """Uninstall a version: remove the versions/<id>/ directory (keeping the shared
global libraries/assets).

    Returns the list of profile ids that depend on this version (for the caller to
surface). In version-isolation mode, versions/<id>/ contains that version's
saves/mods/config, which are removed along with it.
    """
    from launcher.meta import MetaError

    version_dir = paths.GamePaths(game_dir).versions_dir / version_id
    if not version_dir.exists():
        raise MetaError(tr_core("meta.version_not_installed", version_id))
    dependents = find_version_dependents(game_dir, version_id)
    shutil.rmtree(version_dir, ignore_errors=True)
    return dependents


def plan_tasks(
    version: VersionJson,
    game_dir: Path,
    platform: Platform,
    asset_index: AssetIndex,
) -> list[DownloadTask]:
    """Generate all pending download tasks for this version (the downloader skips valid files that already exist)."""
    gp = paths.GamePaths(game_dir)
    tasks: list[DownloadTask] = []
    version_dir = gp.versions_dir / version.id

    # Client jar
    client = version.downloads.get("client")
    client_url = client.url if client is not None and client.url else None
    if client_url is None and client is not None and client.sha1:
        client_url = CLIENT_JAR_FALLBACK.format(sha1=client.sha1)
    if client_url is not None:
        tasks.append(
            DownloadTask(
                url=client_url,
                dest=version_dir / version.client_jar_name,
                sha1=client.sha1 if client is not None else None,
                size=client.size if client is not None else None,
            )
        )

    # Libraries (including natives classifiers)
    for resolved in resolve_libraries(version.libraries, platform):
        tasks.append(_library_task(resolved, gp.libraries_dir))

    # Assets
    for _name, obj in missing_assets(asset_index, gp.assets_dir / "objects"):
        tasks.append(
            DownloadTask(
                url=ASSET_BASE + obj.hash[:2] + "/" + obj.hash,
                dest=gp.assets_dir / "objects" / obj.hash[:2] / obj.hash,
                sha1=obj.hash,
                size=obj.size,
            )
        )

    # Logging config (launch args need it)
    if version.logging and isinstance(version.logging.get("client"), dict):
        log_file = version.logging["client"].get("file") or {}
        log_url = log_file.get("url")
        if log_url:
            tasks.append(
                DownloadTask(
                    url=log_url,
                    dest=gp.assets_dir / "log_configs" / version.asset_index.id,
                    sha1=log_file.get("sha1"),
                    size=log_file.get("size"),
                )
            )

    return tasks


def write_version_files(version: VersionJson, game_dir: Path) -> Path:
    """Write the (merged) version JSON to versions/<id>/<id>.json (official layout)."""
    gp = paths.GamePaths(game_dir)
    version_dir = gp.versions_dir / version.id
    version_dir.mkdir(parents=True, exist_ok=True)
    version_file = version_dir / (version.id + ".json")
    payload = json.dumps(
        version.model_dump(by_alias=True, exclude_none=True),
        ensure_ascii=False,
        indent=2,
    )
    tmp = version_file.with_name(version_file.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(version_file)
    return version_file


def write_asset_index(asset_index: AssetIndex, index_id: str, game_dir: Path) -> Path:
    """Write the asset index to assets/indexes/<id>.json (official layout)."""
    gp = paths.GamePaths(game_dir)
    index_dir = gp.assets_dir / "indexes"
    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / (index_id + ".json")
    if not index_file.exists():
        payload = json.dumps(
            asset_index.model_dump(by_alias=True, exclude_none=True),
            ensure_ascii=False,
        )
        tmp = index_file.with_name(index_file.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(index_file)
    return index_file


def ensure_java_for_version(
    version: VersionJson,
    *,
    cache_dir: Path | None = None,
    runtime_dir: Path | None = None,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> int | None:
    """Auto-download Java from Adoptium when no suitable Java exists; return the downloaded major (None when no download is needed)."""
    declared = version.java_version.major_version if version.java_version else None
    required = required_java_major(version.id, declared)
    if required is None:
        return None
    from launcher.java import has_suitable_java, install_java, list_java

    runtimes = list_java(probe_dir=cache_dir)
    if has_suitable_java(runtimes, required):
        return None
    install_java(
        required,
        runtime_dir=runtime_dir,
        probe_dir=cache_dir,
        progress=progress,
    )
    return required


def install_version(
    version_id: str,
    *,
    game_dir: Path,
    cache_dir: Path | None = None,
    concurrency: int = 4,
    force: bool = False,
    platform: Platform | None = None,
    client: httpx.Client | None = None,
    progress: Callable[[DownloadProgress], None] | None = None,
    auto_install_java: bool = False,
    runtime_dir: Path | None = None,
) -> DownloadResult:
    """Install a version: write version JSON + asset index + download all files.
Return a download summary.

    When auto_install_java=True, a missing suitable Java triggers an automatic JRE
download first.
    """
    platform = platform or detect_platform()
    version = load_version_json(
        version_id, cache_dir=cache_dir, force=force, client=client
    )
    if auto_install_java:
        ensure_java_for_version(
            version,
            cache_dir=cache_dir,
            runtime_dir=runtime_dir,
            progress=progress,
        )
    gp = paths.GamePaths(game_dir)
    gp.ensure_all()
    write_version_files(version, game_dir)

    asset_index_cache = (
        cache_dir / "assets" / (version.asset_index.id + ".json")
        if cache_dir is not None
        else None
    )
    asset_index = fetch_asset_index(
        version.asset_index, cache_path=asset_index_cache, client=client
    )
    write_asset_index(asset_index, version.asset_index.id, game_dir)

    tasks = plan_tasks(version, game_dir, platform, asset_index)
    return Downloader(concurrency=concurrency, client=client).download(tasks, progress)
