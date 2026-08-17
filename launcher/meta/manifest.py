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


# 愚人节版本（Mojang 官方清单中 type 为 snapshot/release，需按 id 单独归类）
APRIL_FOOLS_IDS = frozenset(
    {
        "2.0",  # 2013（老启动器渠道，不在现行官方清单中）
        "15w14a",  # 2015 Love and Hugs
        "1.RV-Pre1",  # 2016 Trendy
        "3D Shareware v1.34",  # 2019
        "20w14infinite",  # 2020（官方清单 id 为 20w14infinite）
        "22w13oneblockatatime",  # 2022（官方清单 id 全小写）
        "23w13a_or_b",  # 2023
        "24w14potato",  # 2024
        "25w14craftmine",  # 2025
        "26w14a",  # 2026 Herdcraft
    }
)


def version_category(version_id: str, version_type: str) -> str:
    """版本分类：april_fools / release / snapshot / old_beta / old_alpha。"""
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


def _normalize_proxy(value: str) -> str:
    """补全代理地址的协议头（httpx 要求带 scheme，否则报错）。"""
    value = value.strip()
    if value and "://" not in value:
        value = "http://" + value
    return value


def _proxy_url() -> str | None:
    """解析代理地址：配置 http_proxy 优先，其次环境变量（HTTPS/HTTP/ALL_PROXY）。

    国内网络直连 api.modrinth.com 等可能被墙（返回 404/超时）；
    浏览器能访问是因为走了系统代理，httpx 默认不读系统代理，需手动注入。
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


def _new_client() -> httpx.Client:
    _enable_system_ca()
    kwargs: dict = {
        "headers": {"User-Agent": USER_AGENT},
        "timeout": 30.0,
        "follow_redirects": True,
    }
    proxy = _proxy_url()
    if proxy:
        kwargs["proxies"] = {"http://": proxy, "https://": proxy}
    return httpx.Client(**kwargs)


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
