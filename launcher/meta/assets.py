"""资源索引（asset index）：下载、缓存与缺失对比。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from launcher.meta.manifest import _new_client
from launcher.meta.version import AssetIndexInfo


class AssetObject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hash: str
    size: int = 0


class AssetIndex(BaseModel):
    model_config = ConfigDict(extra="ignore")

    objects: dict[str, AssetObject] = {}


def asset_relative_path(hash_: str) -> Path:
    """资源在 assets/objects 下的相对路径（hash 前两位做目录）。"""
    return Path(hash_[:2]) / hash_


def fetch_asset_index(
    info: AssetIndexInfo,
    *,
    cache_path: Path | None = None,
    force: bool = False,
    client: httpx.Client | None = None,
) -> AssetIndex:
    if cache_path is not None and not force and cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return AssetIndex.model_validate(raw)
        except (OSError, ValueError):
            pass
    own = client is None
    if own:
        client = _new_client()
    try:
        resp = client.get(info.url)
        resp.raise_for_status()
        raw = resp.json()
    finally:
        if own:
            client.close()
    index = AssetIndex.model_validate(raw)
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(cache_path.name + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        tmp.replace(cache_path)
    return index


def missing_assets(index: AssetIndex, objects_dir: Path) -> list[tuple[str, AssetObject]]:
    """返回 (资源名, 对象) 中本地缺失或大小不符的资源。"""
    missing: list[tuple[str, AssetObject]] = []
    for name, obj in index.objects.items():
        path = objects_dir / asset_relative_path(obj.hash)
        try:
            if path.stat().st_size == obj.size:
                continue
        except OSError:
            pass
        missing.append((name, obj))
    return missing
