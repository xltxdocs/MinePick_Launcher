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

"""Version metadata (version manifest / version JSON / library rules / asset index)."""

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
