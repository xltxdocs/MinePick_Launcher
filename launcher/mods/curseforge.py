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

"""CurseForge content source: search / popular / file listing / download.

API key priority: user-entered in the settings page > the bundled key injected at
build time (build/cf_key.txt, kept out of the repo and source tree to avoid leaking
the key; neither the GUI nor the docs display the key value).
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
# classId: mod 6 / resourcepack 12 / shaderpack 6552 / modpack 4471
CLASS_IDS = {"mod": 6, "resourcepack": 12, "shaderpack": 6552, "modpack": 4471}
# modLoaderType: Forge 1 / Fabric 4 / NeoForge 6 (mods only)
LOADER_IDS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}


@dataclass
class CfFile:
    """A CurseForge version file."""

    id: int
    name: str
    url: str
    size: int


def _bundled_key() -> str:
    """The bundled key injected at build time (read from build/ in dev mode; neither location is committed)."""
    for p in (
        paths.resource_path("launcher/mods/data/cf_key.txt"),
        paths.resource_path("build/cf_key.txt"),  # dev mode
    ):
        try:
            key = p.read_text(encoding="ascii", errors="ignore").strip()
            if key:
                return key
        except OSError:
            continue
    return ""


def effective_api_key() -> str:
    """The effective API key: user-entered first, then the bundled default."""
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
    """Search CurseForge projects by keyword (sorted by total downloads)."""
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
                slug=str(m.get("id") or ""),  # the slug slot stores the CF project id
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
    """List project files (release versions with a download URL only), newest first."""
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
    """Download the file into the target directory; return the on-disk path."""
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

