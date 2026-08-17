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

"""Download and install the Adoptium Temurin JRE (api.adoptium.net v3).

Managed runtime directory layout: <launcher data dir>/runtime/java-<major>/bin/java(.exe).
Download links ultimately point at github.com (Adoptium release assets), so the system certificate store is needed (see meta.manifest._enable_system_ca).
"""

from __future__ import annotations

import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from launcher.i18n import describe_network_error, tr_core
from launcher.java.locate import JavaError, JavaRuntime, probe_java_major
from launcher.meta.manifest import _new_client
from launcher.meta.rules import Platform, detect_platform
from launcher.net.downloader import Downloader, DownloadProgress, DownloadTask

ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"

_OS_MAP = {"windows": "windows", "osx": "mac", "linux": "linux"}
_ARCH_MAP = {"x64": "x64", "x86": "x86", "arm64": "aarch64"}


@dataclass(frozen=True)
class JavaAsset:
    release_name: str
    os: str
    arch: str
    image_type: str
    link: str
    name: str
    size: int
    checksum: str = ""  # official sha256 (package.checksum, integrity verification)


def fetch_assets(
    major: int,
    *,
    platform: Platform | None = None,
    image_type: str = "jre",
    client: httpx.Client | None = None,
) -> list[JavaAsset]:
    """Query Adoptium's latest asset list (filtered by platform / image type)."""
    platform = platform or detect_platform()
    os_name = _OS_MAP.get(platform.os, platform.os)
    arch = _ARCH_MAP.get(platform.arch, platform.arch)
    url = (
        ADOPTIUM_API.format(major=major)
        + "?os="
        + os_name
        + "&architecture="
        + arch
        + "&image_type="
        + image_type
    )
    own = client is None
    if own:
        client = _new_client()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise JavaError(
            tr_core("java.assets_failed", describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()

    assets: list[JavaAsset] = []
    for release in payload:
        binary = release.get("binary") or {}
        package = binary.get("package") or {}
        name = package.get("name") or ""
        if not name.endswith((".zip", ".tar.gz")):
            continue
        assets.append(
            JavaAsset(
                release_name=release.get("release_name") or "",
                os=binary.get("os") or "",
                arch=binary.get("architecture") or "",
                image_type=binary.get("image_type") or "",
                link=package.get("link") or "",
                name=name,
                size=int(package.get("size") or 0),
                checksum=package.get("checksum") or "",
            )
        )
    return assets


def _extract_zip(zip_path: Path, target_dir: Path) -> None:
    """Extract the zip to the target directory, stripping the zip's top-level directory (Adoptium package layout)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            parts = member.filename.split("/")
            rel = "/".join(parts[1:]) if len(parts) > 1 and parts[0] else member.filename
            if not rel:
                continue
            dest = target_dir / rel
            if member.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, dest.open("wb") as dst:
                while True:
                    chunk = src.read(64 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)


def list_managed_runtimes(
    runtime_dir: Path | None = None,
) -> list[tuple[int, Path]]:
    """List managed Java runtimes (major, directory), sorted by major ascending."""
    from launcher import paths as launcher_paths

    runtime_dir = runtime_dir or (launcher_paths.launcher_dir() / "runtime")
    if not runtime_dir.exists():
        return []
    out: list[tuple[int, Path]] = []
    for entry in sorted(runtime_dir.iterdir()):
        if not entry.is_dir():
            continue
        try:
            major = int(entry.name.removeprefix("java-"))
        except ValueError:
            continue
        out.append((major, entry))
    return out


def delete_managed_runtime(major: int, runtime_dir: Path | None = None) -> Path:
    """Delete a managed Java runtime directory."""
    match = next(
        (d for m, d in list_managed_runtimes(runtime_dir) if m == major), None
    )
    if match is None:
        raise JavaError(tr_core("java.runtime_missing", major))
    shutil.rmtree(match, ignore_errors=True)
    return match


def install_java(
    major: int,
    *,
    runtime_dir: Path | None = None,
    platform: Platform | None = None,
    probe_dir: Path | None = None,
    progress: Callable[[DownloadProgress], None] | None = None,
    client: httpx.Client | None = None,
) -> JavaRuntime:
    """Download and install an Adoptium JRE into the managed directory; return directly if already installed."""
    from launcher import paths as launcher_paths

    runtime_dir = runtime_dir or (launcher_paths.launcher_dir() / "runtime")
    target_dir = runtime_dir / ("java-" + str(major))
    exe_name = "java.exe" if (platform or detect_platform()).os == "windows" else "java"
    existing = target_dir / "bin" / exe_name
    if existing.exists():
        probed = probe_java_major(existing, probe_dir=probe_dir)
        if probed is not None:
            return JavaRuntime(path=existing, major=probed.major, provider="managed", version=probed.version)
        return JavaRuntime(path=existing, major=major, provider="managed")

    assets = fetch_assets(major, platform=platform, client=client)
    if not assets:
        raise JavaError(tr_core("java.no_asset", major))
    asset = assets[0]

    downloads_dir = runtime_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    zip_path = downloads_dir / asset.name
    result = Downloader(client=client).download(
        [
            DownloadTask(
                url=asset.link,
                dest=zip_path,
                size=asset.size,
                sha256=asset.checksum or None,
            )
        ],
        progress=progress,
    )
    if result.failed:
        raise JavaError(tr_core("java.download_failed", result.failed[0][1]))

    _extract_zip(zip_path, target_dir)
    java_path = target_dir / "bin" / exe_name
    if not java_path.exists():
        raise JavaError(tr_core("java.extract_failed", str(java_path)))
    probed = probe_java_major(java_path, probe_dir=probe_dir)
    if probed is None:
        return JavaRuntime(path=java_path, major=major, provider="managed")
    return JavaRuntime(path=java_path, major=probed.major, provider="managed", version=probed.version)
