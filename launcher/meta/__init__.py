"""M2：版本元数据（版本清单 / 版本 JSON / 库规则 / 资源索引）。"""

from launcher.meta.assets import (
    AssetIndex,
    AssetObject,
    asset_relative_path,
    fetch_asset_index,
    missing_assets,
)
from launcher.meta.manifest import (
    APRIL_FOOLS_IDS,
    ManifestVersion,
    MetaError,
    VersionManifest,
    fetch_manifest,
    version_category,
)
from launcher.meta.rules import (
    Platform,
    ResolvedLibrary,
    allowed,
    detect_platform,
    native_classifier,
    resolve_libraries,
)
from launcher.meta.version import (
    Artifact,
    AssetIndexInfo,
    Library,
    OsRule,
    Rule,
    VersionJson,
    load_version_json,
    merge_raw,
    required_java_major,
)

__all__ = [
    "APRIL_FOOLS_IDS",
    "Artifact",
    "AssetIndex",
    "AssetIndexInfo",
    "AssetObject",
    "Library",
    "ManifestVersion",
    "MetaError",
    "OsRule",
    "Platform",
    "ResolvedLibrary",
    "Rule",
    "VersionJson",
    "VersionManifest",
    "allowed",
    "asset_relative_path",
    "detect_platform",
    "fetch_asset_index",
    "fetch_manifest",
    "load_version_json",
    "merge_raw",
    "missing_assets",
    "native_classifier",
    "required_java_major",
    "resolve_libraries",
    "version_category",
]
