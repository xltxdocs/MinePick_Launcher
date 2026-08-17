"""Java 运行时探测与匹配。

探测顺序（provider 标记来源）：
  1. managed  —— 启动器自管目录（launcher 数据目录/runtime/java-<major>/bin）；
  2. java_home —— JAVA_HOME 环境变量；
  3. path —— PATH 上的 java；
  4. system —— 常见安装目录（Windows: Program Files 各发行版目录；Linux: /usr/lib/jvm）。

沙箱/打包兼容：探测用管道捕获失败时自动退回文件重定向（不依赖管道 stdio）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from launcher import paths

VERSION_RE = re.compile(r'version "([^"]+)"')
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # GUI 启动探测不弹命令行窗口


class JavaError(Exception):
    """Java 运行时相关错误（消息面向用户）。"""


@dataclass(frozen=True)
class JavaRuntime:
    path: Path
    major: int
    provider: str  # managed / config / java_home / path / system
    version: str = ""


def parse_java_major(version_output: str) -> int | None:
    """从 java -version 输出解析主版本：1.8.0_401 -> 8，17.0.10 -> 17。"""
    match = VERSION_RE.search(version_output)
    if match is None:
        return None
    ver = match.group(1)
    try:
        if ver.startswith("1."):
            return int(ver.split(".")[1])
        return int(ver.split(".")[0].split("-")[0])  # 剥离 21-ea 等后缀
    except (ValueError, IndexError):
        return None


def probe_java_major(
    java_path: Path, probe_dir: Path | None = None
) -> JavaRuntime | None:
    """运行 java -version 并解析。probe_dir 供受限环境存放重定向输出文件。"""
    cmd = [str(java_path), "-version"]
    try:
        extra = {"creationflags": NO_WINDOW} if os.name == "nt" else {}
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            **extra,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
    except OSError:
        # 管道 stdio 被禁（本开发沙箱）：退回文件重定向
        if probe_dir is not None:
            probe_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = probe_dir / ("java-probe-" + str(os.getpid()) + ".txt")
        else:
            try:
                fd, name = tempfile.mkstemp(suffix=".txt")
                os.close(fd)
                tmp_path = Path(name)
            except OSError:
                return None
        try:
            with tmp_path.open("w", encoding="utf-8", errors="replace") as f:
                extra = {"creationflags": NO_WINDOW} if os.name == "nt" else {}
                proc = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                    check=False,
                    **extra,
                )
            output = tmp_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            return None
        finally:
            tmp_path.unlink(missing_ok=True)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    major = parse_java_major(output)
    if major is None:
        return None
    first_line = output.strip().splitlines()[0] if output.strip() else ""
    return JavaRuntime(path=java_path, major=major, provider="unknown", version=first_line)


def _managed_runtime_dirs() -> list[Path]:
    base = paths.launcher_dir() / "runtime"
    if not base.exists():
        return []
    return [p for p in sorted(base.iterdir()) if p.is_dir()]


def _java_candidates() -> list[tuple[Path, str]]:
    """收集 (java 可执行文件, provider) 候选。"""
    exe_name = "java.exe" if os.name == "nt" else "java"
    out: list[tuple[Path, str]] = []

    for d in _managed_runtime_dirs():
        exe = d / "bin" / exe_name
        if exe.exists():
            out.append((exe, "managed"))

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        exe = Path(java_home) / "bin" / exe_name
        if exe.exists():
            out.append((exe, "java_home"))

    which = shutil.which("java")
    if which:
        out.append((Path(which), "path"))

    if os.name == "nt":
        roots: list[Path] = []
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(env_name)
            if value:
                roots.append(Path(value))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(Path(local))
        for root in roots:
            for vendor in (
                "Java",
                "Eclipse Adoptium",
                "Microsoft",
                "Zulu",
                "Amazon Corretto",
                "BellSoft",
            ):
                base = root / vendor
                if not base.exists():
                    continue
                for exe in base.glob("*/bin/java.exe"):
                    out.append((exe, "system"))
    else:
        for base in (Path("/usr/lib/jvm"), Path("/opt")):
            if base.exists():
                for exe in base.glob("*/bin/java"):
                    out.append((exe, "system"))
    return out


def list_java(probe_dir: Path | None = None) -> list[JavaRuntime]:
    """探测所有候选 Java；按 (major 降序, managed 优先) 排序。"""
    seen: set[Path] = set()
    runtimes: list[JavaRuntime] = []
    for exe, provider in _java_candidates():
        try:
            resolved = exe.resolve()
        except OSError:
            resolved = exe
        if resolved in seen:
            continue
        seen.add(resolved)
        runtime = probe_java_major(exe, probe_dir=probe_dir)
        if runtime is None:
            continue
        runtimes.append(
            JavaRuntime(
                path=resolved,
                major=runtime.major,
                provider=provider,
                version=runtime.version,
            )
        )
    runtimes.sort(key=lambda r: (-r.major, r.provider != "managed", str(r.path)))
    return runtimes


def has_suitable_java(runtimes: list[JavaRuntime], required_major: int) -> bool:
    """是否存在适配的 Java。

    - 需要 8（旧版本）：必须精确 8（9+ 无法运行 1.16.5 及更早）；
    - 需要 16/17/21：任意 major >= 需求即可。
    """
    if not runtimes:
        return False
    if required_major <= 8:
        return any(r.major == 8 for r in runtimes)
    return any(r.major >= required_major for r in runtimes)


def match_java(
    runtimes: list[JavaRuntime], required_major: int | None
) -> JavaRuntime | None:
    """选择最合适的 Java：
    1. 托管运行时且 major 精确匹配；
    2. 任意来源且 major 精确匹配；
    3. major >= 需求的最小版本（同分时托管优先）；
    4. 任意（取最大 major）。
    """
    if not runtimes:
        return None
    if required_major is None:
        return max(runtimes, key=lambda r: r.major)
    managed_exact = [r for r in runtimes if r.provider == "managed" and r.major == required_major]
    if managed_exact:
        return managed_exact[0]
    exact = [r for r in runtimes if r.major == required_major]
    if exact:
        return exact[0]
    ge = [r for r in runtimes if r.major >= required_major]
    if ge:
        return min(ge, key=lambda r: (r.major, r.provider != "managed"))
    return max(runtimes, key=lambda r: r.major)
