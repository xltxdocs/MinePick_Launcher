"""Loader install: download the official installer jar, run it silently, and detect the newly generated version id.

Packaging/sandbox compatible:
- the installer subprocess runs with inherited stdio (restricted environments forbid pipe capture);
- TMP/TEMP is redirected to the launcher cache directory (the installer's internal temp files don't go to the system TEMP);
- the version id is detected by "comparing the versions directory before and after install", not by parsing installer output.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import httpx

from launcher import paths as launcher_paths
from launcher.i18n import describe_network_error, tr_core
from launcher.java import JavaRuntime, list_java, match_java
from launcher.meta.manifest import _new_client
from launcher.meta.version import required_java_major
from launcher.mods.loaders import ModsError
from launcher.mods.models import LoaderVersion
from launcher.net.downloader import DownloadProgress


def installer_args(loader_version: LoaderVersion, game_dir: Path) -> list[str]:
    """Silent-install arguments for each loader's installer."""
    if loader_version.loader == "fabric":
        return [
            "client",
            "-dir",
            str(game_dir),
            "-mcversion",
            loader_version.game_version,
            "-loader",
            loader_version.version,
            "-noprofile",
        ]
    if loader_version.loader in ("forge", "neoforge"):
        return ["--installClient", str(game_dir)]
    raise ModsError(tr_core("mods.unknown_loader", loader_version.loader))


def _pick_java(loader_version: LoaderVersion, probe_dir: Path) -> JavaRuntime:
    runtimes = list_java(probe_dir=probe_dir)
    if not runtimes:
        raise ModsError(tr_core("mods.need_java"))
    # prefer managed runtimes (the trust store/files live inside the launcher data directory, readable in restricted environments)
    managed = [r for r in runtimes if r.provider == "managed"]
    pool = managed or runtimes
    if loader_version.loader == "fabric":
        java = match_java(pool, None)  # the installer itself works with any modern Java
    else:
        required = required_java_major(loader_version.game_version) or 8
        java = match_java(pool, required)
    if java is None:
        raise ModsError(tr_core("mods.need_suitable_java"))
    return java


def download_installer(
    loader_version: LoaderVersion,
    cache_dir: Path,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> Path:
    """Stream-download the installer jar directly to disk (small file; no .part/rename step, more robust in restricted environments)."""
    if not loader_version.installer_url:
        raise ModsError(tr_core("mods.no_installer_url"))
    dest_dir = cache_dir / "loaders"
    filename = (
        loader_version.loader + "-" + loader_version.version + "-"
        + loader_version.game_version + "-installer.jar"
    )
    dest = dest_dir / filename
    client = _new_client()
    try:
        with client.stream("GET", loader_version.installer_url) as resp:
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            total = int(resp.headers.get("content-length") or 0)
            done = 0
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(64 * 1024):
                    f.write(chunk)
                    done += len(chunk)
            if progress is not None:
                progress(
                    DownloadProgress(
                        done_bytes=done,
                        total_bytes=total,
                        done_files=1,
                        total_files=1,
                        current=dest.name,
                    )
                )
    except httpx.HTTPError as exc:
        raise ModsError(
            tr_core("mods.installer_download_failed", describe_network_error(exc))
        ) from exc
    finally:
        client.close()
    if not dest.exists() or dest.stat().st_size == 0:
        raise ModsError(tr_core("mods.installer_not_written"))
    return dest


def _copy_game_jar(created_id: str, game_dir: Path) -> None:
    """Copy the parent version's game jar into the profile directory (official layout: versions/<profile id>/<profile id>.jar).

    Loader installers only write the profile JSON (inheritsFrom the parent version), not the game jar;
    but our launch classpath looks under versions/<id>/<id>.jar, so we have to fill it in ourselves.
    """
    gp = launcher_paths.GamePaths(game_dir)
    profile_file = gp.version_dir(created_id) / (created_id + ".json")
    try:
        raw = json.loads(profile_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    parent_id = raw.get("inheritsFrom")
    if not parent_id:
        return
    try:
        parent_raw = json.loads(
            (gp.version_dir(parent_id) / (parent_id + ".json")).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return
    parent_jar_name = parent_raw.get("jar")
    if not parent_jar_name:
        client = parent_raw.get("downloads", {}).get("client") or {}
        parent_jar_name = (
            Path(client["path"]).name if client.get("path") else parent_id + ".jar"
        )
    parent_jar = gp.version_dir(parent_id) / parent_jar_name
    dest = gp.version_dir(created_id) / (created_id + ".jar")
    if parent_jar.exists() and not dest.exists():
        shutil.copyfile(parent_jar, dest)


def _ensure_launcher_profiles(game_dir: Path) -> Path:
    """The Forge/NeoForge installers require the official launcher's profile file in the game directory."""
    profiles_file = game_dir / "launcher_profiles.json"
    if not profiles_file.exists():
        profiles_file.write_text(
            '{"profiles": {}, "selectedProfile": "(Default)", "version": 3}',
            encoding="utf-8",
        )
    return profiles_file


def _list_version_ids(versions_dir: Path) -> set[str]:
    if not versions_dir.exists():
        return set()
    return {p.name for p in versions_dir.iterdir() if p.is_dir()}


def run_installer_jar(
    jar: Path,
    args: list[str],
    *,
    java_path: Path,
    work_dir: Path,
    temp_dir: Path,
    timeout_s: int = 3600,
) -> int:
    """Run the installer (inherited stdio); return the exit code."""
    env = os.environ.copy()
    env["TMP"] = env["TEMP"] = str(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    # Under a GUI (no console parent process), don't pop a console window; the CLI keeps inherited output.
    # creationflags is Windows-only; passing it on other platforms raises ValueError.
    extra: dict = {}
    if os.name == "nt" and sys.stdout is None and sys.stdin is None:
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        [str(java_path), "-jar", str(jar), *args],
        cwd=str(work_dir),
        env=env,
        timeout=timeout_s,
        check=False,
        **extra,
    )
    return proc.returncode


def install_loader(
    loader_version: LoaderVersion,
    game_dir: Path,
    *,
    cache_dir: Path | None = None,
    progress: Callable[[DownloadProgress], None] | None = None,
    timeout_s: int = 3600,
) -> str:
    """Download and run the installer; return the newly generated version id."""
    cache_dir = cache_dir or (launcher_paths.launcher_dir() / "cache")
    gp = launcher_paths.GamePaths(game_dir)
    gp.ensure_all()

    jar = download_installer(loader_version, cache_dir, progress=progress)
    java = _pick_java(loader_version, cache_dir)

    if loader_version.loader in ("forge", "neoforge"):
        _ensure_launcher_profiles(game_dir)

    before = _list_version_ids(gp.versions_dir)
    code = run_installer_jar(
        jar,
        installer_args(loader_version, game_dir),
        java_path=java.path,
        work_dir=game_dir,
        temp_dir=cache_dir / "tmp",
        timeout_s=timeout_s,
    )
    if code != 0:
        raise ModsError(
            tr_core("mods.installer_exit", loader_version.loader, code)
        )
    after = _list_version_ids(gp.versions_dir)
    created = sorted(after - before)
    if not created:
        raise ModsError(tr_core("mods.installer_no_version"))
    created_id = created[-1]
    _copy_game_jar(created_id, game_dir)
    return created_id
