"""natives 解压：版本隔离目录，每次启动前重建。"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from launcher.i18n import tr_core
from launcher.install import library_path
from launcher.meta.rules import ResolvedLibrary


class LaunchError(Exception):
    """启动相关错误（消息面向用户）。"""


def prepare_natives(
    resolved: list[ResolvedLibrary], libraries_dir: Path, natives_dir: Path
) -> Path:
    """清空并按当前平台解压全部 natives 库到版本专属目录。"""
    if natives_dir.exists():
        shutil.rmtree(natives_dir, ignore_errors=True)
    natives_dir.mkdir(parents=True, exist_ok=True)
    for item in resolved:
        if item.classifier is None:
            continue
        lib = item.library
        downloads = lib.downloads
        classifiers = downloads.classifiers if downloads else None
        art = classifiers.get(item.classifier) if classifiers else None
        if art is None and downloads is not None:
            # 现代 natives 条目：artifact 即 natives jar
            art = downloads.artifact
        rel = (
            art.path
            if art is not None and art.path
            else library_path(lib.name, item.classifier)
        )
        jar = libraries_dir / rel
        if not jar.exists():
            raise LaunchError(tr_core("launch.missing_natives", rel))
        excludes = ["META-INF/"]
        if lib.extract and isinstance(lib.extract.get("exclude"), list):
            excludes += [str(entry) for entry in lib.extract["exclude"]]
        _extract_jar(jar, natives_dir, excludes)
    return natives_dir


def _extract_jar(jar: Path, dest: Path, excludes: list[str]) -> None:
    with zipfile.ZipFile(jar) as zf:
        for member in zf.infolist():
            name = member.filename
            if member.is_dir() or any(name.startswith(prefix) for prefix in excludes):
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
