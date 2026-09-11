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

"""Fetching, caching, and parsing of the version manifest (version_manifest_v2.json)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from launcher.i18n import describe_network_error, tr_core

MANIFEST_URLS = (
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
    "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
)
USER_AGENT = "mclauncher/0.1.0"
DEFAULT_MAX_AGE = 3600.0


class MetaError(Exception):
    """Version metadata error (user-facing message)."""


class ManifestVersion(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    type: Literal["release", "snapshot", "old_beta", "old_alpha"]
    url: str
    time: str = ""
    release_time: str = Field(default="", alias="releaseTime")


# April Fools versions (type is snapshot/release in Mojang's official manifest, so they must be classified separately by id)
APRIL_FOOLS_IDS = frozenset(
    {
        "2.0",  # 2013 (old launcher channel, not in the current official manifest)
        "15w14a",  # 2015 Love and Hugs
        "1.RV-Pre1",  # 2016 Trendy
        "3D Shareware v1.34",  # 2019
        "20w14infinite",  # 2020 (official manifest id is 20w14infinite)
        "22w13oneblockatatime",  # 2022 (official manifest id is all lowercase)
        "23w13a_or_b",  # 2023
        "24w14potato",  # 2024
        "25w14craftmine",  # 2025
        "26w14a",  # 2026 Herdcraft
    }
)


def version_category(version_id: str, version_type: str) -> str:
    """Version category: april_fools / release / snapshot / old_beta / old_alpha."""
    if version_id in APRIL_FOOLS_IDS:
        return "april_fools"
    if version_type == "release":
        return "release"
    if version_type == "snapshot":
        return "snapshot"
    if version_type in ("old_beta", "old_alpha"):
        return version_type
    return version_type or "release"


class VersionManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    latest: dict[str, str] = {}
    versions: list[ManifestVersion] = []

    def find(self, version_id: str) -> ManifestVersion | None:
        for v in self.versions:
            if v.id == version_id:
                return v
        return None


_system_ca_injected = False


def _enable_system_ca() -> None:
    """On Windows, make httpx use the system certificate store (so enterprise proxy / intranet CAs pass verification)."""
    global _system_ca_injected
    if _system_ca_injected or os.name != "nt":
        return
    _system_ca_injected = True
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass  # fall back to certifi's default behavior when not installed


def _normalize_proxy(value: str) -> str:
    """Add the scheme to a proxy address (httpx requires a scheme, otherwise it errors)."""
    value = value.strip()
    if value and "://" not in value:
        value = "http://" + value
    return value


def _proxy_url() -> str | None:
    """Resolve the proxy address: config http_proxy takes priority, then env vars (HTTPS/HTTP/ALL_PROXY).

    On some networks a direct connection to api.modrinth.com and similar may be blocked
    (returning 404/timeout); the browser works because it goes through the system proxy,
    while httpx doesn't read the system proxy by default, so it must be injected manually.
    """
    try:
        from launcher import config

        cfg, _ = config.load()
        configured = (cfg.http_proxy or "").strip()
        if configured:
            return _normalize_proxy(configured)
    except Exception:
        import logging

        logging.getLogger(__name__).debug("读取代理配置失败，回退环境变量", exc_info=True)
    for name in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.environ.get(name)
        if value:
            return _normalize_proxy(value)
    return None


class _SharedHttpClient(httpx.Client):
    """Shared client whose close() is a no-op so per-call cleanup keeps the pool alive."""

    def close(self) -> None:
        pass

    def force_close(self) -> None:
        super().close()


_shared_client: httpx.Client | None = None
_shared_client_lock = threading.Lock()


def _new_client() -> httpx.Client:
    """Return a shared reusable client (system CA + proxy injected).

    Callers may call close() safely - the shared pool survives. Call
    reset_http_client() to actually rebuild it after proxy / API key changes.
    """
    global _shared_client
    if _shared_client is not None:
        return _shared_client
    with _shared_client_lock:
        if _shared_client is None:
            _enable_system_ca()
            kwargs: dict = {
                "headers": {"User-Agent": USER_AGENT},
                "timeout": 30.0,
                "follow_redirects": True,
            }
            proxy = _proxy_url()
            if proxy:
                kwargs["proxies"] = {"http://": proxy, "https://": proxy}
            _shared_client = _SharedHttpClient(**kwargs)
        return _shared_client


def reset_http_client() -> None:
    """Close and rebuild the shared HTTP client (proxy / API key changes)."""
    global _shared_client
    with _shared_client_lock:
        if _shared_client is not None:
            _shared_client.force_close()
            _shared_client = None


def _fetch_first(client: httpx.Client, urls: tuple[str, ...]) -> dict:
    last_error: Exception | None = None
    for url in urls:
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            last_error = exc
    raise MetaError(
        tr_core("meta.manifest_fetch_failed", describe_network_error(last_error))
    ) from last_error


def _read_cache(cache_path: Path, max_age: float) -> VersionManifest | None:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        fetched_at = float(data.get("fetched_at", 0))
        if time.time() - fetched_at < max_age:
            return VersionManifest.model_validate(data["manifest"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _write_cache(cache_path: Path, raw: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": time.time(), "manifest": raw}
    tmp = cache_path.with_name(cache_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache_path)


def fetch_manifest(
    cache_path: Path | None = None,
    max_age: float = DEFAULT_MAX_AGE,
    force: bool = False,
    client: httpx.Client | None = None,
) -> VersionManifest:
    """Fetch the version manifest; when cache_path is provided, cache it by age (default 1 hour)."""
    if cache_path is not None and not force:
        cached = _read_cache(cache_path, max_age)
        if cached is not None:
            return cached
    own = client is None
    if own:
        client = _new_client()
    try:
        raw = _fetch_first(client, MANIFEST_URLS)
    finally:
        if own:
            client.close()
    manifest = VersionManifest.model_validate(raw)
    if cache_path is not None:
        _write_cache(cache_path, raw)
    return manifest
