"""Chinese display-name lookup for resources: bundled curated data (Chinese display and Chinese search).

Data file: launcher/mods/data/zh_mod_names.json (slug -> Chinese name).
"""

from __future__ import annotations

import json
from functools import lru_cache

from launcher import paths


@lru_cache(maxsize=1)
def zh_names() -> dict[str, str]:
    """Load the slug -> Chinese name lookup table (bundled data)."""
    data_path = paths.resource_path("launcher/mods/data/zh_mod_names.json")
    try:
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in raw.items() if v}
    except Exception:  # noqa: BLE001 - treat missing data as an empty table
        return {}


def zh_name(slug: str) -> str:
    """The Chinese name for a slug; return an empty string when absent."""
    return zh_names().get(slug, "")


def has_cjk(text: str) -> bool:
    """Whether the text contains CJK unified ideographs (used to decide whether to enable Chinese local search)."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def search_local(query: str) -> list[str]:
    """Search the local Chinese-name table: return matching slugs (exact matches first)."""
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

