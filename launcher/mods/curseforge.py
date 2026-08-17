"""CurseForge 内容源：搜索/热门/文件列表/下载。

API Key 优先级：设置页用户自填 > 打包时注入的内置 Key（build/cf_key.txt，
不进仓库与源码树，避免 Key 泄露；GUI 与文档均不展示 Key 值）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from launcher import config, paths
from launcher.i18n import describe_network_error, tr_core
from launcher.meta.manifest import _new_client
from launcher.mods.loaders import ModsError
from launcher.mods.models import ModSearchHit

CURSEFORGE_API = "https://api.curseforge.com"
GAME_ID = 432  # Minecraft
# classId：模组 6 / 资源包 12 / 光影 6552 / 整合包 4471
CLASS_IDS = {"mod": 6, "resourcepack": 12, "shaderpack": 6552, "modpack": 4471}
# modLoaderType：Forge 1 / Fabric 4 / NeoForge 6（仅模组使用）
LOADER_IDS = {"forge": 1, "fabric": 4, "neoforge": 6}


@dataclass
class CfFile:
    """CurseForge 版本文件。"""

    id: int
    name: str
    url: str
    size: int


def _bundled_key() -> str:
    """打包时注入的内置 Key（开发模式从 build/ 读取；两处均不进仓库）。"""
    for p in (
        paths.resource_path("launcher/mods/data/cf_key.txt"),
        paths.resource_path("build/cf_key.txt"),  # 开发模式
    ):
        try:
            key = p.read_text(encoding="ascii", errors="ignore").strip()
            if key:
                return key
        except OSError:
            continue
    return ""


def effective_api_key() -> str:
    """生效的 API Key：用户自填优先，其次内置默认。"""
    cfg, _ = config.load()
    return (cfg.curseforge_api_key or _bundled_key()).strip()


def has_key() -> bool:
    return bool(effective_api_key())


def _client() -> httpx.Client:
    client = _new_client()
    client.headers["x-api-key"] = effective_api_key()
    return client


def _check(resp: httpx.Response, message: str) -> dict:
    if resp.status_code == 403:
        raise ModsError(tr_core("mods.cf_key_invalid"))
    if resp.status_code >= 400:
        raise ModsError(message + tr_core("mods.cf_http_error", resp.status_code))
    return resp.json()


def search_projects(
    query: str,
    *,
    limit: int = 30,
    kind: str = "mod",
    game_version: str = "",
    loader: str = "",
    client: httpx.Client | None = None,
) -> list[ModSearchHit]:
    """按关键词搜索 CurseForge 项目（按总下载量排序）。"""
    own = client is None
    if own:
        client = _client()
    params = {
        "gameId": str(GAME_ID),
        "classId": str(CLASS_IDS.get(kind, 6)),
        "searchFilter": query,
        "sortField": "TotalDownloads",
        "sortOrder": "desc",
        "pageSize": str(min(limit, 50)),
    }
    if game_version:
        params["gameVersion"] = game_version
    if loader and kind == "mod":
        params["modLoaderType"] = str(LOADER_IDS.get(loader, 0))
    try:
        resp = client.get(CURSEFORGE_API + "/v1/mods/search", params=params)
        payload = _check(resp, tr_core("mods.search_failed"))
    except httpx.HTTPError as exc:
        raise ModsError(tr_core("mods.search_failed", describe_network_error(exc))) from exc
    finally:
        if own:
            client.close()
    hits: list[ModSearchHit] = []
    for m in payload.get("data", []):
        if not isinstance(m, dict):
            continue
        logo = m.get("logo") or {}
        hits.append(
            ModSearchHit(
                slug=str(m.get("id") or ""),  # slug 位置存 CF 项目 id
                title=m.get("name") or "",
                description=m.get("summary") or "",
                downloads=int(m.get("downloadCount") or 0),
                icon_url=logo.get("thumbnailUrl") or "",
            )
        )
    return hits


def list_files(
    mod_id: int,
    *,
    game_version: str = "",
    loader: str = "",
    client: httpx.Client | None = None,
) -> list[CfFile]:
    """列出项目文件（仅正式版、带下载地址），新文件在前。"""
    own = client is None
    if own:
        client = _client()
    params: dict[str, str] = {}
    if game_version:
        params["gameVersion"] = game_version
    if loader:
        params["modLoaderType"] = str(LOADER_IDS.get(loader, 0))
    try:
        resp = client.get(CURSEFORGE_API + "/v1/mods/" + str(mod_id) + "/files", params=params)
        payload = _check(resp, tr_core("mods.versions_failed"))
    except httpx.HTTPError as exc:
        raise ModsError(tr_core("mods.versions_failed", describe_network_error(exc))) from exc
    finally:
        if own:
            client.close()
    files: list[CfFile] = []
    for f in payload.get("data", []):
        if not isinstance(f, dict) or f.get("releaseType") != 1:
            continue
        url = f.get("downloadUrl")
        if not url:
            continue
        files.append(
            CfFile(
                id=int(f.get("id") or 0),
                name=f.get("displayName") or f.get("fileName") or "",
                url=url,
                size=int(f.get("fileLength") or 0),
            )
        )
    files.sort(key=lambda f: f.id, reverse=True)
    return files


def download_file(
    cf_file: CfFile,
    target_dir: Path,
    *,
    client: httpx.Client | None = None,
) -> Path:
    """下载文件到目标目录；返回落盘路径。"""
    own = client is None
    if own:
        client = _client()
    target_dir.mkdir(parents=True, exist_ok=True)
    name = cf_file.name or str(cf_file.id) + ".jar"
    target = target_dir / name
    try:
        with client.stream("GET", cf_file.url, follow_redirects=True) as resp:
            resp.raise_for_status()
            tmp = target.with_name(target.name + ".part")
            with tmp.open("wb") as f:
                for chunk in resp.iter_bytes(1 << 18):
                    f.write(chunk)
            tmp.replace(target)
    except httpx.HTTPError as exc:
        raise ModsError(tr_core("mods.download_failed", describe_network_error(exc))) from exc
    finally:
        if own:
            client.close()
    return target

