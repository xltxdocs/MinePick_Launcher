"""Modrinth 下载：项目/版本查询、依赖 slug 解析、文件下载到 mods 目录。"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from launcher import paths as launcher_paths
from launcher.i18n import describe_network_error, tr_core
from launcher.meta.manifest import _new_client
from launcher.mods.loaders import ModsError
from launcher.mods.models import (
    InstalledContent,
    ModDependency,
    ModFile,
    ModInfo,
    ModSearchHit,
    ModVersion,
)
from launcher.net.downloader import Downloader, DownloadProgress, DownloadTask

MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "mclauncher/0.1.0 (modrinth downloader)"


def _client() -> httpx.Client:
    return _new_client()


def fetch_project(slug: str, *, client: httpx.Client | None = None) -> dict:
    """项目元数据（title/description）。"""
    own = client is None
    if own:
        client = _client()
    try:
        resp = client.get(MODRINTH_API + "/project/" + slug)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise ModsError(
            tr_core("mods.project_failed", slug, describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()


def search_projects(
    query: str,
    *,
    limit: int = 20,
    project_type: str = "mod",
    client: httpx.Client | None = None,
) -> list[ModSearchHit]:
    """按关键词搜索 Modrinth 项目（project_type: mod/resourcepack/shader，下载量排序）。"""
    own = client is None
    if own:
        client = _client()
    params = {
        "query": query,
        "limit": str(limit),
        "index": "downloads",
        "facets": json.dumps([["project_type:" + project_type]]),
    }
    try:
        resp = client.get(MODRINTH_API + "/search", params=params)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise ModsError(
            tr_core("mods.search_failed", describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()
    hits: list[ModSearchHit] = []
    for entry in payload.get("hits", []):
        if not isinstance(entry, dict):
            continue
        hits.append(
            ModSearchHit(
                slug=entry.get("slug") or entry.get("project_id") or "",
                title=entry.get("title") or "",
                description=entry.get("description") or "",
                downloads=int(entry.get("downloads") or 0),
                icon_url=entry.get("icon_url") or "",
            )
        )
    return hits


def list_installed_content(
    game_dir: Path,
    subdir: str,
    *,
    version_id: str | None = None,
    isolated: bool = False,
    loader: str | None = None,
    game_version: str | None = None,
) -> list[InstalledContent]:
    """列出内容目录（mods/resourcepacks/shaderpacks）下已安装的文件。

    目录不存在或隔离模式下无法定位档案时返回空列表（不抛错，便于 UI 展示）。
    """
    try:
        target = resolve_content_dir(
            game_dir,
            subdir,
            version_id=version_id,
            isolated=isolated,
            loader=loader,
            game_version=game_version,
        )
    except ModsError:
        return []
    items: list[InstalledContent] = []
    for entry in sorted(target.iterdir()):
        if entry.is_file():
            items.append(
                InstalledContent(
                    name=entry.name, path=str(entry), size=entry.stat().st_size
                )
            )
    return items


def delete_installed_content(
    game_dir: Path,
    subdir: str,
    filename: str,
    *,
    version_id: str | None = None,
    isolated: bool = False,
    loader: str | None = None,
    game_version: str | None = None,
) -> None:
    """删除内容目录中的单个文件（按文件名匹配）。"""
    target = resolve_content_dir(
        game_dir,
        subdir,
        version_id=version_id,
        isolated=isolated,
        loader=loader,
        game_version=game_version,
    )
    file_path = target / filename
    if not file_path.exists() or not file_path.is_file():
        raise ModsError(tr_core("mods.file_missing", filename))
    file_path.unlink()


def resolve_slugs(
    project_ids: list[str], *, client: httpx.Client | None = None
) -> dict[str, str]:
    """批量解析 project_id -> slug（依赖展示用）。"""
    if not project_ids:
        return {}
    own = client is None
    if own:
        client = _client()
    try:
        resp = client.get(
            MODRINTH_API + "/projects",
            params={"ids": json.dumps(project_ids)},
        )
        resp.raise_for_status()
        return {p["id"]: p.get("slug", "") for p in resp.json()}
    except httpx.HTTPError as exc:
        raise ModsError(
            tr_core("mods.deps_failed", describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()


def fetch_versions(
    slug: str,
    *,
    loader: str | None = None,
    game_version: str | None = None,
    client: httpx.Client | None = None,
) -> list[ModVersion]:
    """项目版本列表（可按 loader / MC 版本过滤，最新在前）。"""
    own = client is None
    if own:
        client = _client()
    params: dict[str, str] = {}
    if loader:
        params["loaders"] = json.dumps([loader])
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    try:
        resp = client.get(MODRINTH_API + "/project/" + slug + "/version", params=params)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise ModsError(
            tr_core("mods.versions_failed", describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()

    versions: list[ModVersion] = []
    for entry in payload:
        files = [
            ModFile(
                filename=f.get("filename", ""),
                url=f.get("url", ""),
                size=int(f.get("size") or 0),
                sha1=(f.get("hashes") or {}).get("sha1"),
                sha512=(f.get("hashes") or {}).get("sha512"),
                primary=bool(f.get("primary")),
            )
            for f in entry.get("files", [])
        ]
        deps = [
            ModDependency(
                project_id=d.get("project_id") or "",
                dependency_type=d.get("dependency_type", ""),
            )
            for d in entry.get("dependencies", [])
        ]
        versions.append(
            ModVersion(
                version_id=entry["id"],
                version_number=entry.get("version_number", ""),
                loaders=entry.get("loaders", []),
                game_versions=entry.get("game_versions", []),
                files=files,
                dependencies=deps,
            )
        )
    return versions


def pick_file(version: ModVersion) -> ModFile | None:
    """选择主文件（primary 优先）。"""
    for f in version.files:
        if f.primary:
            return f
    return version.files[0] if version.files else None


def to_mod_info(
    slug: str, project: dict, version: ModVersion, slugs: dict[str, str]
) -> ModInfo:
    required: list[str] = []
    optional: list[str] = []
    for dep in version.dependencies:
        dep_slug = slugs.get(dep.project_id) or dep.project_id
        if dep.dependency_type == "required":
            required.append(dep_slug)
        elif dep.dependency_type == "optional":
            optional.append(dep_slug)
    return ModInfo(
        slug=slug,
        title=project.get("title") or slug,
        description=project.get("description") or "",
        depends=required,
        optional_depends=optional,
    )


def find_profile_id(
    game_dir: Path, loader: str | None, game_version: str
) -> str | None:
    """在 versions 目录中查找已安装的加载器档案 id（版本隔离用）。"""
    gp = launcher_paths.GamePaths(game_dir)
    if not gp.versions_dir.exists():
        return None
    if loader == "fabric":
        for d in sorted(gp.versions_dir.iterdir(), reverse=True):
            if d.name.startswith("fabric-loader-") and d.name.endswith("-" + game_version):
                return d.name
    elif loader == "forge":
        prefix = game_version + "-forge-"
        for d in sorted(gp.versions_dir.iterdir(), reverse=True):
            if d.name.startswith(prefix):
                return d.name
    elif loader == "neoforge":
        base = game_version.removeprefix("1.")
        for d in sorted(gp.versions_dir.iterdir(), reverse=True):
            if d.name.startswith("neoforge-" + base):
                return d.name
    else:
        for d in sorted(gp.versions_dir.iterdir(), reverse=True):
            if d.name == game_version:
                return d.name
    return None


def resolve_mods_dir(
    game_dir: Path,
    *,
    version_id: str | None = None,
    isolated: bool = False,
    loader: str | None = None,
    game_version: str | None = None,
) -> Path:
    """确定模组安装目录（版本隔离时指向已安装档案的 mods 目录）。"""
    gp = launcher_paths.GamePaths(game_dir)
    if not isolated:
        gp.mods_dir.mkdir(parents=True, exist_ok=True)
        return gp.mods_dir
    profile_id = version_id or find_profile_id(game_dir, loader, game_version or "")
    if profile_id is None:
        raise ModsError(tr_core("mods.isolation_profile_missing"))
    mods_dir = gp.version_dir(profile_id) / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    return mods_dir


def resolve_content_dir(
    game_dir: Path,
    subdir: str,
    *,
    version_id: str | None = None,
    isolated: bool = False,
    loader: str | None = None,
    game_version: str | None = None,
) -> Path:
    """通用内容目录（mods/resourcepacks/shaderpacks）：隔离模式按档案定位。"""
    if subdir == "mods":
        return resolve_mods_dir(
            game_dir,
            version_id=version_id,
            isolated=isolated,
            loader=loader,
            game_version=game_version,
        )
    gp = launcher_paths.GamePaths(game_dir)
    if not isolated:
        target = gp.game_dir / subdir
    else:
        profile_id = version_id or find_profile_id(game_dir, loader, game_version or "")
        if profile_id is None:
            raise ModsError(tr_core("mods.isolation_profile_missing"))
        target = gp.version_dir(profile_id) / subdir
    target.mkdir(parents=True, exist_ok=True)
    return target


def _install_file_to_dir(
    slug: str,
    subdir: str,
    *,
    game_dir: Path,
    loader: str | None = None,
    game_version: str | None = None,
    version_id: str | None = None,
    mod_version_id: str | None = None,
    isolated: bool = False,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> ModInfo:
    """通用下载：把项目主文件下载到指定内容目录（mods/resourcepacks/shaderpacks）。"""
    versions = fetch_versions(slug, loader=loader, game_version=game_version)
    if not versions:
        raise ModsError(tr_core("mods.no_match", loader, game_version))
    if mod_version_id:
        picked = next((v for v in versions if v.version_id == mod_version_id), None)
        if picked is None:
            raise ModsError(tr_core("mods.version_not_in_matches", mod_version_id))
    else:
        picked = versions[0]
    file = pick_file(picked)
    if file is None or not file.url:
        raise ModsError(tr_core("mods.no_file"))

    project = fetch_project(slug)
    dep_ids = [d.project_id for d in picked.dependencies if d.project_id]
    slugs = resolve_slugs(dep_ids)

    target = resolve_content_dir(
        game_dir,
        subdir,
        version_id=version_id,
        isolated=isolated,
        loader=loader,
        game_version=game_version,
    )
    result = Downloader().download(
        [
            DownloadTask(
                url=file.url,
                dest=target / file.filename,
                sha1=file.sha1,
                size=file.size,
            )
        ],
        progress=progress,
    )
    if result.failed:
        raise ModsError(tr_core("mods.download_failed", result.failed[0][1]))
    return to_mod_info(slug, project, picked, slugs)


def install_mod(
    slug: str,
    *,
    game_dir: Path,
    loader: str | None = None,
    game_version: str | None = None,
    version_id: str | None = None,
    mod_version_id: str | None = None,
    isolated: bool = False,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> ModInfo:
    """下载模组到 mods 目录；返回 ModInfo（含依赖提示）。"""
    return _install_file_to_dir(
        slug,
        "mods",
        game_dir=game_dir,
        loader=loader,
        game_version=game_version,
        version_id=version_id,
        mod_version_id=mod_version_id,
        isolated=isolated,
        progress=progress,
    )


def install_resourcepack(
    slug: str,
    *,
    game_dir: Path,
    game_version: str | None = None,
    version_id: str | None = None,
    mod_version_id: str | None = None,
    isolated: bool = False,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> ModInfo:
    """下载资源包到 resourcepacks 目录。"""
    return _install_file_to_dir(
        slug,
        "resourcepacks",
        game_dir=game_dir,
        game_version=game_version,
        version_id=version_id,
        mod_version_id=mod_version_id,
        isolated=isolated,
        progress=progress,
    )


def install_shaderpack(
    slug: str,
    *,
    game_dir: Path,
    game_version: str | None = None,
    version_id: str | None = None,
    mod_version_id: str | None = None,
    isolated: bool = False,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> ModInfo:
    """下载光影到 shaderpacks 目录。"""
    return _install_file_to_dir(
        slug,
        "shaderpacks",
        game_dir=game_dir,
        game_version=game_version,
        version_id=version_id,
        mod_version_id=mod_version_id,
        isolated=isolated,
        progress=progress,
    )
