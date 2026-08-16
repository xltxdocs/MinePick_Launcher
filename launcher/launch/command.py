"""启动命令组装：占位符替换、规则过滤、-Xmx 注入、log4j 参数、@argfile。

与进程执行解耦：CLI 用 runner.run_process，GUI（M6）可复用同一 argv 交给 QProcess。
打包兼容：所有路径运行时解析；argfile 写到版本目录。
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from launcher import __version__, paths
from launcher.install import library_path
from launcher.meta.rules import (
    Platform,
    ResolvedLibrary,
    allowed,
)
from launcher.meta.version import ArgumentItem, GameArgument, VersionJson

ARGFILE_THRESHOLD = 7000  # Windows 命令行长度阈值，超过则改用 @argfile（Java 9+）


@dataclass(frozen=True)
class LaunchProfile:
    username: str
    uuid: str
    access_token: str
    user_type: str  # msa / legacy


@dataclass(frozen=True)
class LaunchCommand:
    argv: list[str]
    cwd: Path
    argfile: Path | None = None


def _flatten_filtered(
    items: list[GameArgument], platform: Platform, features: frozenset[str]
) -> list[str]:
    """展开参数项并按规则过滤（ArgumentItem.value 可能是列表）。"""
    out: list[str] = []
    for item in items:
        if isinstance(item, ArgumentItem):
            if not allowed(item.rules or None, platform, features):
                continue
            value = item.value
            if isinstance(value, list):
                out.extend(str(v) for v in value)
            else:
                out.append(str(value))
        else:
            out.append(str(item))
    return out


def _ensure_options_lang(path: Path, lang_code: str) -> None:
    """在 options.txt 中写入/更新 lang 行（保留其它设置；UTF-8 无 BOM）。

    所有版本（含 1.8.9）都通过 options.txt 读取语言；--lang 参数仅部分新版支持。
    """
    lines: list[str] = []
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            lines = []
    new_line = "lang:" + lang_code
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("lang:"):
            out.append(new_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _split_extra_jvm_args(text: str) -> list[str]:
    """拆分用户自定义 JVM 参数：按空白切分，去掉引号（模拟 shell 行为）。

    支持两种形式：整体引号包裹的 token（"a b"）与 key="value" 形式。
    """
    args = shlex.split(text, posix=False)
    out: list[str] = []
    for arg in args:
        if len(arg) >= 2 and arg[0] == arg[-1] == '"':
            arg = arg[1:-1]
        else:
            eq = arg.find("=")
            if eq > 0 and eq + 2 < len(arg) and arg[eq + 1] == arg[-1] == '"':
                arg = arg[: eq + 1] + arg[eq + 2 : -1]
        out.append(arg)
    return out


def _substitute(arg: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        # 拼接构造占位符（美元花括号形式），避免源文件出现模板插值歧义
        arg = arg.replace("$" + "{" + key + "}", value)
    return arg


def build_argv(
    version: VersionJson,
    *,
    game_dir: Path,
    libraries_dir: Path,
    natives_dir: Path,
    java_path: Path,
    java_major: int,
    profile: LaunchProfile,
    platform: Platform,
    resolved_libraries: list[ResolvedLibrary],
    memory_gb: float = 4.0,
    demo: bool = False,
    window_width: int | None = None,
    window_height: int | None = None,
    isolated: bool = False,
    language: str | None = None,
    assets_dir: Path | None = None,
    extra_jvm_args: str | None = None,
    server: str | None = None,
    server_port: int | None = None,
) -> LaunchCommand:
    """组装完整启动命令（java + jvm 参数 + 主类 + game 参数）。

    isolated=True 时游戏目录切换为 versions/<id>/（存档/模组/配置版本隔离），
    natives 位于 versions/<id>/natives。language 通过 --lang 传给游戏
    （不支持的版本由游戏侧静默忽略）。
    """
    gp = paths.GamePaths(game_dir)
    version_dir = gp.versions_dir / version.id
    effective_game_dir = version_dir if isolated else game_dir
    effective_assets_dir = assets_dir or gp.assets_dir
    if isolated:
        # 版本隔离：预创建模组目录（M7 加载器使用），存档/配置由游戏自建
        (version_dir / "mods").mkdir(parents=True, exist_ok=True)
    else:
        # 实例/普通模式：保证游戏目录存在（存档/配置由游戏自建）
        effective_game_dir.mkdir(parents=True, exist_ok=True)

    # 类路径：客户端 jar + 全部主库（按路径去重——继承合并可能带来重复条目，
    # NeoForge 的 union 文件系统对重复项零容忍）
    raw_entries = [str(version_dir / version.client_jar_name)]
    for item in resolved_libraries:
        if item.classifier is not None:
            continue
        lib = item.library
        downloads = lib.downloads
        art = downloads.artifact if downloads else None
        rel = art.path if art is not None and art.path else library_path(lib.name)
        raw_entries.append(str(libraries_dir / rel))
    classpath_entries: list[str] = []
    seen_entries: set[str] = set()
    for entry in raw_entries:
        if entry in seen_entries:
            continue
        seen_entries.add(entry)
        classpath_entries.append(entry)
    classpath = os.pathsep.join(classpath_entries)

    features = frozenset()
    if demo:
        features |= {"is_demo_user"}
    if window_width is not None or window_height is not None:
        features |= {"has_custom_resolution"}

    mapping: dict[str, str] = {
        "auth_player_name": profile.username,
        "auth_uuid": profile.uuid,
        "auth_access_token": profile.access_token,
        "auth_session": "token:" + profile.access_token + ":" + profile.uuid,
        "auth_xuid": "0",
        "clientid": "",
        "user_properties": "{}",
        "user_type": profile.user_type,
        "version_name": version.id,
        "version_type": version.type or "release",
        "game_directory": str(effective_game_dir),
        "assets_root": str(effective_assets_dir),
        "game_assets": str(effective_assets_dir),
        "assets_index_name": version.asset_index.id,
        "natives_directory": str(natives_dir),
        "library_directory": str(libraries_dir),
        "classpath": classpath,
        "classpath_separator": os.pathsep,
        "launcher_name": "MinePick Launcher",
        "launcher_version": __version__,
    }
    if window_width is not None:
        mapping["resolution_width"] = str(window_width)
    if window_height is not None:
        mapping["resolution_height"] = str(window_height)

    log_arg_template: str | None = None
    if version.logging and isinstance(version.logging.get("client"), dict):
        log_arg_template = version.logging["client"].get("argument")
        if log_arg_template:
            mapping["path"] = str(effective_assets_dir / "log_configs" / version.asset_index.id)

    jvm_args = _flatten_filtered(version.effective_jvm_arguments(), platform, features)
    game_args = _flatten_filtered(version.effective_game_arguments(), platform, features)

    jvm_args = [_substitute(arg, mapping) for arg in jvm_args]
    game_args = [_substitute(arg, mapping) for arg in game_args]

    # 游戏语言：--lang 参数（部分新版支持，其余静默忽略）
    # + options.txt lang 行（全版本通用的可靠机制，保留用户其它设置）
    if language:
        game_args += ["--lang", language]
        _ensure_options_lang(effective_game_dir / "options.txt", language)

    # 服务器直连（#15）：--server / --port（原版客户端各版本均支持）
    if server:
        game_args += ["--server", server]
    if server_port is not None:
        game_args += ["--port", str(server_port)]

    if log_arg_template and not any(
        arg.startswith("-Dlog4j.configurationFile") for arg in jvm_args
    ):
        jvm_args.append(_substitute(log_arg_template, mapping))

    # 注入 -Xmx（替换已有的，保证只出现一次）
    jvm_args = [arg for arg in jvm_args if not arg.startswith("-Xmx")]
    jvm_args.append("-Xmx" + f"{memory_gb:g}" + "G")

    # 自定义 JVM 参数（用户输入）；剔除 -Xmx/-Xms 避免与内存设置冲突
    if extra_jvm_args and extra_jvm_args.strip():
        for arg in _split_extra_jvm_args(extra_jvm_args):
            if not arg.startswith("-Xmx") and not arg.startswith("-Xms"):
                jvm_args.append(arg)

    # Windows 超长类路径改用 @argfile（Java 9+）
    argfile: Path | None = None
    if java_major >= 9 and len(classpath) > ARGFILE_THRESHOLD:
        argfile = version_dir / (version.id + "-classpath.txt")
        argfile.parent.mkdir(parents=True, exist_ok=True)
        argfile.write_text(classpath, encoding="utf-8")
        replaced = False
        for index, arg in enumerate(jvm_args):
            if arg == "-cp" and index + 1 < len(jvm_args):
                jvm_args[index + 1] = "@" + str(argfile)
                replaced = True
                break
        if not replaced:
            jvm_args += ["-cp", "@" + str(argfile)]

    argv = [str(java_path)] + jvm_args + [version.main_class] + game_args
    return LaunchCommand(argv=argv, cwd=effective_game_dir, argfile=argfile)
