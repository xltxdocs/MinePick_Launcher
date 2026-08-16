"""版本清单（version_manifest_v2.json）的获取、缓存与解析。"""

from __future__ import annotations

import json
import os
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
    """版本元数据错误（消息面向用户，中文）。"""


class ManifestVersion(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    type: Literal["release", "snapshot", "old_beta", "old_alpha"]
    url: str
    time: str = ""
    release_time: str = Field(default="", alias="releaseTime")


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
    """Windows 上让 httpx 使用系统证书库（企业代理/内网 CA 也能通过校验）。"""
    global _system_ca_injected
    if _system_ca_injected or os.name != "nt":
        return
    _system_ca_injected = True
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass  # 未安装则退回 certifi 默认行为


def _new_client() -> httpx.Client:
    _enable_system_ca()
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True
    )


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
    """获取版本清单；提供 cache_path 时做时间缓存（默认 1 小时）。"""
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
