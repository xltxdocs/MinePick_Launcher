"""版本 JSON 的解析模型、继承合并与获取。

兼容新旧两种格式：
- 旧版（如 1.8.9）：minecraftArguments 字符串 + 隐式 JVM 参数；
- 新版：arguments.game / arguments.jvm 列表（含带规则的参数项）。
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field

from launcher.i18n import describe_network_error, tr_core
from launcher.meta.manifest import (
    MetaError,
    VersionManifest,
    _new_client,
    fetch_manifest,
)

# Minecraft 版本 -> 所需 Java 主版本（版本 JSON 未声明 javaVersion 时的兜底规则）
# 显式区间（含端点）：
#   26.1 及以上 -> 25；1.20.5~1.21.11 -> 21；1.17~1.20.4 -> 17；1.16.5 及更早 -> 8。
JAVA_REQUIREMENT_RULES: list[tuple[str, str | None, int]] = [
    ("26.1", None, 25),
    ("1.20.5", "1.21.11", 21),
    ("1.17", "1.20.4", 17),
    ("0", "1.16.5", 8),
]


def required_java_major(version_id: str, declared: int | None = None) -> int | None:
    """所需 Java 主版本：优先版本 JSON 声明，缺失时按版本区间规则推断。

    快照等无法按 semver 解析的 id（如 25w01a）或区间外版本返回 None（调用方回退声明值）。
    """
    if declared is not None:
        return declared
    base = re.sub(r"[-+].*$", "", version_id)
    try:
        ver = Version(base)
    except InvalidVersion:
        return None
    for min_version, max_version, major in JAVA_REQUIREMENT_RULES:
        if ver >= Version(min_version) and (max_version is None or ver <= Version(max_version)):
            return major
    return None


class OsRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    arch: str | None = None
    version: str | None = None


class Rule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = "allow"  # allow / disallow
    os: OsRule | None = None
    features: dict[str, bool] | None = None


class ArgumentItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rules: list[Rule] = []
    value: str | list[str]


GameArgument = str | ArgumentItem


class GameArguments(BaseModel):
    model_config = ConfigDict(extra="ignore")

    game: list[GameArgument] = []
    jvm: list[GameArgument] = []


class Artifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str | None = None
    sha1: str | None = None
    size: int | None = None
    url: str | None = None


class LibraryDownload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    artifact: Artifact | None = None
    classifiers: dict[str, Artifact] | None = None


class Library(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    downloads: LibraryDownload | None = None
    rules: list[Rule] | None = None
    natives: dict[str, str] | None = None
    url: str | None = None
    extract: dict[str, Any] | None = None


class AssetIndexInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    sha1: str | None = None
    size: int | None = None
    total_size: int | None = None
    url: str


class JavaVersionInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    component: str = ""
    major_version: int = Field(default=8, alias="majorVersion")


class VersionJson(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    type: str = "release"
    main_class: str = Field(alias="mainClass")
    minecraft_arguments: str | None = Field(default=None, alias="minecraftArguments")
    arguments: GameArguments | None = None
    asset_index: AssetIndexInfo = Field(alias="assetIndex")
    assets: str = "legacy"
    java_version: JavaVersionInfo | None = Field(default=None, alias="javaVersion")
    libraries: list[Library] = []
    inherits_from: str | None = Field(default=None, alias="inheritsFrom")
    jar: str | None = None
    downloads: dict[str, Artifact] = {}
    logging: dict[str, Any] | None = None
    release_time: str = Field(default="", alias="releaseTime")

    @property
    def is_legacy(self) -> bool:
        """旧格式（minecraftArguments 字符串）。"""
        return self.arguments is None and bool(self.minecraft_arguments)

    @property
    def client_jar_name(self) -> str:
        if self.jar:
            return self.jar
        info = self.downloads.get("client")
        if info and info.path:
            return Path(info.path).name
        return self.id + ".jar"

    def effective_game_arguments(self) -> list[GameArgument]:
        if self.arguments is not None:
            return list(self.arguments.game)
        if self.minecraft_arguments:
            return shlex.split(self.minecraft_arguments)
        return []

    def effective_jvm_arguments(self) -> list[GameArgument]:
        if self.arguments is not None:
            return list(self.arguments.jvm)
        return LEGACY_JVM_ARGUMENTS


# 旧版版本的隐式 JVM 参数（与官方启动器一致）
LEGACY_JVM_ARGUMENTS: list[GameArgument] = [
    "-Djava.library.path=${natives_directory}",
    "-cp",
    "${classpath}",
]


def merge_raw(child: dict, parent: dict) -> dict:
    """把子版本 JSON 合并到父版本上（处理 inheritsFrom 继承）。"""
    merged = dict(parent)
    merged.update(child)
    merged["libraries"] = list(child.get("libraries", [])) + list(
        parent.get("libraries", [])
    )
    child_args = child.get("arguments")
    parent_args = parent.get("arguments")
    if isinstance(child_args, dict) and isinstance(parent_args, dict):
        merged["arguments"] = {
            "game": list(child_args.get("game", [])) + list(parent_args.get("game", [])),
            "jvm": list(child_args.get("jvm", [])) + list(parent_args.get("jvm", [])),
        }
    elif parent_args is not None:
        merged["arguments"] = parent_args
    merged.pop("inheritsFrom", None)
    return merged


def load_version_json(
    version_id: str,
    *,
    versions_dir: Path | None = None,
    manifest: VersionManifest | None = None,
    cache_dir: Path | None = None,
    force: bool = False,
    client: httpx.Client | None = None,
) -> VersionJson:
    """加载版本 JSON（含继承解析）。

    查找顺序：versions_dir/<id>/<id>.json -> cache_dir 缓存 -> 在线获取（需清单）。
    """
    raw = _load_raw_chain(version_id, versions_dir, manifest, cache_dir, force, client, set())
    return VersionJson.model_validate(raw)


def _load_raw_chain(
    version_id: str,
    versions_dir: Path | None,
    manifest: VersionManifest | None,
    cache_dir: Path | None,
    force: bool,
    client: httpx.Client | None,
    seen: set[str],
) -> dict:
    if version_id in seen:
        raise MetaError(tr_core("meta.inherit_cycle", version_id))
    seen.add(version_id)
    raw = _load_raw(version_id, versions_dir, manifest, cache_dir, force, client)
    parent = raw.get("inheritsFrom")
    if parent:
        parent_raw = _load_raw_chain(
            parent, versions_dir, manifest, cache_dir, force, client, seen
        )
        return merge_raw(raw, parent_raw)
    return raw


def _load_raw(
    version_id: str,
    versions_dir: Path | None,
    manifest: VersionManifest | None,
    cache_dir: Path | None,
    force: bool,
    client: httpx.Client | None,
) -> dict:
    if versions_dir is not None:
        local = versions_dir / version_id / (version_id + ".json")
        if local.exists():
            return json.loads(local.read_text(encoding="utf-8"))
    if cache_dir is not None and not force:
        cached = cache_dir / "versions" / (version_id + ".json")
        if cached.exists():
            try:
                return json.loads(cached.read_text(encoding="utf-8"))
            except ValueError:
                pass
    if manifest is None:
        manifest = fetch_manifest(
            cache_path=(cache_dir / "version_manifest.json") if cache_dir else None,
            client=client,
        )
    entry = manifest.find(version_id)
    if entry is None:
        raise MetaError(tr_core("meta.version_missing", version_id))
    own = client is None
    if own:
        client = _new_client()
    try:
        resp = client.get(entry.url)
        resp.raise_for_status()
        raw = resp.json()
    except httpx.HTTPError as exc:
        raise MetaError(
            tr_core("meta.version_fetch_failed", describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()
    if cache_dir is not None:
        target = cache_dir / "versions" / (version_id + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
    return raw
