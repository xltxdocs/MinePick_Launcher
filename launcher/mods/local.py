"""本地模组管理：扫描 mods 目录、解析 jar 内元数据、启用/禁用、复制安装。"""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

DISABLED_SUFFIX = ".disabled"


@dataclass
class LocalMod:
    """mods 目录中的一个模组文件。"""

    file: str  # 显示文件名（不含 .disabled）
    enabled: bool
    name: str  # 元数据显示名（缺失时用文件名）
    mod_id: str
    version: str
    loader: str  # fabric/quilt/neoforge/forge/unknown
    path: Path  # 磁盘实际路径


def _parse_toml_mods_table(text: str) -> dict | None:
    """极简 TOML：提取第一个 [[mods]] 表（Forge/NeoForge 的 mods.toml）。"""
    current: dict | None = None
    in_mods = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[[mods]]"):
            in_mods = True
            if current is not None:
                return current
            current = {}
            continue
        if line.startswith("[") and in_mods:
            break  # 下一个表，[[mods]] 结束
        if current is not None and "=" in raw:
            key, _, value = raw.partition("=")
            current[key.strip()] = value.strip().strip('"')
    return current


def read_mod_metadata(path: Path) -> tuple[str, str, str, str]:
    """读取 jar 内元数据，返回 (显示名, mod id, 版本, 加载器)。解析失败按未知处理。"""
    mod_id = path.stem
    name = mod_id
    version = ""
    loader = "unknown"
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "fabric.mod.json" in names:
                loader = "fabric"
                data = json.loads(zf.read("fabric.mod.json").decode("utf-8"))
                mod_id = str(data.get("id") or mod_id)
                name = str(data.get("name") or mod_id)
                version = str(data.get("version") or "")
            elif "quilt.mod.json" in names:
                loader = "quilt"
                data = json.loads(zf.read("quilt.mod.json").decode("utf-8"))
                qm = data.get("quilt_loader") or {}
                qmeta = qm.get("metadata") or {}
                mod_id = str(qm.get("id") or data.get("id") or mod_id)
                name = str(qmeta.get("name") or qm.get("name") or mod_id)
                version = str(qm.get("version") or "")
            elif "META-INF/neoforge.mods.toml" in names:
                loader = "neoforge"
                table = _parse_toml_mods_table(zf.read("META-INF/neoforge.mods.toml").decode("utf-8", "replace"))
                if table:
                    mod_id = str(table.get("modId") or mod_id)
                    name = str(table.get("displayName") or mod_id)
                    version = str(table.get("version") or "")
            elif "META-INF/mods.toml" in names:
                loader = "forge"
                table = _parse_toml_mods_table(zf.read("META-INF/mods.toml").decode("utf-8", "replace"))
                if table:
                    mod_id = str(table.get("modId") or mod_id)
                    name = str(table.get("displayName") or mod_id)
                    version = str(table.get("version") or "")
            elif "mcmod.info" in names:
                loader = "forge"
                data = json.loads(zf.read("mcmod.info").decode("utf-8", "replace"))
                if isinstance(data, list) and data:
                    data = data[0]
                entries = data.get("modList") or data.get("mods") or [data]
                if isinstance(entries, list) and entries:
                    entries = entries[0]
                mod_id = str(entries.get("modid") or mod_id)
                name = str(entries.get("name") or mod_id)
                version = str(entries.get("version") or "")
    except Exception:  # noqa: BLE001 - 损坏/无元数据 jar 按未知处理
        logging.getLogger(__name__).debug("读取模组元数据失败: %s", path)
    return name, mod_id, version, loader


def scan_mods(mods_dir: Path) -> list[LocalMod]:
    """扫描目录：*.jar 为启用，*.jar.disabled 为禁用；按显示名排序。"""
    if not mods_dir.exists():
        return []
    result: list[LocalMod] = []
    for p in sorted(mods_dir.iterdir()):
        lower = p.name.lower()
        if not lower.endswith((".jar", ".jar.disabled")):
            continue
        if lower.endswith(".jar.disabled"):
            enabled = False
            stem = p.name[: -len(DISABLED_SUFFIX)]
        else:
            enabled = True
            stem = p.name
        name, mod_id, version, loader = read_mod_metadata(p)
        result.append(
            LocalMod(file=stem, enabled=enabled, name=name, mod_id=mod_id,
                     version=version, loader=loader, path=p)
        )
    result.sort(key=lambda m: m.name.lower())
    return result


def set_mod_enabled(mod: LocalMod, enabled: bool) -> Path:
    """切换启用状态：重命名 jar <-> jar.disabled；返回新路径。"""
    if mod.enabled == enabled:
        return mod.path
    if enabled:
        new = mod.path.with_name(mod.path.name[: -len(DISABLED_SUFFIX)])
    else:
        new = mod.path.with_name(mod.path.name + DISABLED_SUFFIX)
    mod.path.replace(new)
    mod.enabled = enabled
    mod.path = new
    return new


def install_mod_file(src: Path, mods_dir: Path) -> Path:
    """把 .jar 复制进 mods 目录（同名覆盖；清理同名禁用副本）；返回目标路径。"""
    mods_dir.mkdir(parents=True, exist_ok=True)
    target = mods_dir / src.name
    disabled = mods_dir / (src.name + DISABLED_SUFFIX)
    if disabled.exists():
        disabled.unlink()
    shutil.copy2(src, target)
    return target

