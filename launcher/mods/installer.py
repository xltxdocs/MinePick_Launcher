"""加载器安装：下载官方安装器 jar 并静默运行，检测新生成的版本 id。

打包/沙箱兼容：
- 安装器子进程用 stdio 继承运行（受限环境禁用管道捕获）；
- TMP/TEMP 重定向到启动器缓存目录（安装器内部临时文件不写系统 TEMP）；
- 版本 id 通过"安装前后 versions 目录对比"识别，不依赖解析安装器输出。
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
    """各加载器安装器的静默安装参数。"""
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
    # 优先托管运行时（信任库/文件都在启动器数据目录内，受限环境可读）
    managed = [r for r in runtimes if r.provider == "managed"]
    pool = managed or runtimes
    if loader_version.loader == "fabric":
        java = match_java(pool, None)  # 安装器本身任意现代 Java 均可
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
    """直写流式下载安装器 jar（小文件；无 .part/rename 环节，受限环境更稳）。"""
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
    """把父版本的游戏 jar 复制到档案目录（官方布局：versions/<档案id>/<档案id>.jar）。

    加载器安装器只写档案 JSON（inheritsFrom 父版本），不复制游戏 jar；
    而我们的启动 classpath 按 versions/<id>/<id>.jar 查找，需自行补齐。
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
    """Forge/NeoForge 安装器要求游戏目录存在官方启动器的档案文件。"""
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
    """运行安装器（stdio 继承）；返回退出码。"""
    env = os.environ.copy()
    env["TMP"] = env["TEMP"] = str(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    # GUI（无控制台父进程）下不弹出命令行窗口；CLI 保持继承输出。
    # creationflags 仅 Windows 支持，其它平台不能传入（否则 ValueError）。
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
    """下载并运行安装器；返回新生成的版本 id。"""
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
