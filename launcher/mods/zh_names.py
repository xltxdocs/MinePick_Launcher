"""资源中文名对照表：内置精选数据（中文展示与中文搜索）。

数据文件：launcher/mods/data/zh_mod_names.json（slug -> 中文名）。
"""

from __future__ import annotations

import json
from functools import lru_cache

from launcher import paths


@lru_cache(maxsize=1)
def zh_names() -> dict[str, str]:
    """加载 slug -> 中文名 对照表（内置数据）。"""
    data_path = paths.resource_path("launcher/mods/data/zh_mod_names.json")
    try:
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in raw.items() if v}
    except Exception:  # noqa: BLE001 - 数据缺失时按空表处理
        return {}


def zh_name(slug: str) -> str:
    """slug 对应的中文名；无则返回空串。"""
    return zh_names().get(slug, "")


def has_cjk(text: str) -> bool:
    """是否包含中日韩统一表意文字（用于判断是否启用中文本地搜索）。"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def search_local(query: str) -> list[str]:
    """在本地中文名表中搜索：返回匹配的 slug 列表（精确匹配优先）。"""
    q = query.strip().lower()
    if not q:
        return []
    exact, partial = [], []
    for slug, name in zh_names().items():
        if q == name.lower() or q == slug.lower():
            exact.append(slug)
        elif q in name.lower() or q in slug:
            partial.append(slug)
    return exact + partial

