"""Launch-command assembly: placeholder substitution, rule filtering, -Xmx injection, log4j args, @argfile.

Decoupled from process execution: the CLI uses runner.run_process, and the GUI can reuse the same argv and hand it to QProcess.
Packaging-compatible: all paths are resolved at runtime; the argfile is written to the version directory.
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

ARGFILE_THRESHOLD = 7000  # Windows command-line length threshold; beyond it, use an @argfile (Java 9+)


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
    """Flatten argument items and filter by rules (ArgumentItem.value may be a list)."""
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
    """Write/update the lang line in options.txt (keeping other settings; UTF-8 without BOM).

    All versions (including 1.8.9) read the language from options.txt; the --lang arg is only supported by some newer versions.
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
    """Split user-supplied JVM args: split on whitespace and strip quotes (mimicking shell behavior).

    Supports two forms: a fully quoted token ("a b") and the key="value" form.
    """
    try:
        args = shlex.split(text, posix=False)
    except ValueError:
        # input errors like unmatched quotes: fall back to whitespace splitting to avoid failing at launch
        args = text.split()
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
        # build the placeholder by concatenation (dollar-brace form) to avoid template-interpolation ambiguity in the source
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
    """Assemble the complete launch command (java + jvm args + main class + game args).

    When isolated=True the game directory switches to versions/<id>/ (version-isolated saves/mods/config),
    and natives live under versions/<id>/natives. language is passed to the game via --lang
    (silently ignored by unsupported versions on the game side).
    """
    gp = paths.GamePaths(game_dir)
    version_dir = gp.versions_dir / version.id
    effective_game_dir = version_dir if isolated else game_dir
    effective_assets_dir = assets_dir or gp.assets_dir
    if isolated:
        # version isolation: pre-create the mods directory (used by loaders), saves/config are created by the game
        (version_dir / "mods").mkdir(parents=True, exist_ok=True)
    else:
        # instance/normal mode: ensure the game directory exists (saves/config are created by the game)
        effective_game_dir.mkdir(parents=True, exist_ok=True)

    # Classpath: client jar + all main libraries (deduped by path — inheritance merging can produce duplicates,
    # and NeoForge's union filesystem is zero-tolerance toward duplicate entries)
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

    # Game language: the --lang arg (supported by some newer versions, silently ignored otherwise)
    # + the options.txt lang line (a reliable mechanism across all versions, keeping the user's other settings)
    if language:
        game_args += ["--lang", language]
        _ensure_options_lang(effective_game_dir / "options.txt", language)

    # direct server connect: --server / --port (supported by vanilla clients across versions)
    if server:
        game_args += ["--server", server]
    if server_port is not None:
        game_args += ["--port", str(server_port)]

    if log_arg_template and not any(
        arg.startswith("-Dlog4j.configurationFile") for arg in jvm_args
    ):
        jvm_args.append(_substitute(log_arg_template, mapping))

    # inject -Xmx (replacing any existing one, so it appears only once)
    jvm_args = [arg for arg in jvm_args if not arg.startswith("-Xmx")]
    jvm_args.append("-Xmx" + f"{memory_gb:g}" + "G")

    # custom JVM args (user input); strip -Xmx/-Xms to avoid conflicting with the memory setting
    if extra_jvm_args and extra_jvm_args.strip():
        for arg in _split_extra_jvm_args(extra_jvm_args):
            if not arg.startswith("-Xmx") and not arg.startswith("-Xms"):
                jvm_args.append(arg)

    # use an @argfile for overly long classpaths on Windows (Java 9+)
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
