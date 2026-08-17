"""Launch orchestration: the launch-preparation flow shared by the CLI and GUI.

Gathers "account resolution -> version loading -> Java matching -> natives extraction -> argv assembly" in one place;
the CLI runs it with runner.run_process, and the GUI runs the same argv in a worker thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from launcher import paths
from launcher.auth import Account, AccountStore, MicrosoftSession, create_offline_account
from launcher.java import JavaRuntime, has_suitable_java, list_java, match_java
from launcher.launch.command import LaunchCommand, LaunchProfile, build_argv
from launcher.launch.natives import LaunchError, prepare_natives
from launcher.meta import detect_platform, load_version_json, resolve_libraries
from launcher.meta.version import VersionJson


class OfflineLockedError(LaunchError):
    """Offline mode is not unlocked (requires one Microsoft premium login first, or an English UI/system)."""

    def __init__(self) -> None:
        from launcher.i18n import tr_core

        super().__init__(tr_core("offline.locked"))


class JavaMissingError(LaunchError):
    """No suitable Java runtime (the caller should prompt "need Java X, download now?")."""

    def __init__(self, required_major: int) -> None:
        self.required_major = required_major
        super().__init__("需要 Java " + str(required_major))


@dataclass(frozen=True)
class PreparedLaunch:
    command: LaunchCommand
    account: Account
    version: VersionJson
    java: JavaRuntime
    isolated: bool


def resolve_launch_account(
    store: AccountStore,
    selected_id: str | None,
    offline_name: str | None,
) -> Account:
    """Resolve the launch account; Microsoft accounts auto-refresh their session and persist it.

    Offline-mode gate: when premium verification hasn't passed (and the UI/system isn't English),
    an explicit offline launch or the no-account fallback both raise OfflineLockedError.
    """
    from launcher.config import offline_mode_allowed

    accounts = store.load()
    if offline_name is not None:
        if not offline_mode_allowed():
            raise OfflineLockedError()
        return create_offline_account(offline_name)
    account = accounts.get(selected_id) if selected_id else None
    if account is None:
        if not offline_mode_allowed():
            raise OfflineLockedError()
        return create_offline_account("Player")
    if account.type == "microsoft":
        session = MicrosoftSession()
        account = session.ensure_session(account)
        accounts[account.id] = account
        store.save(accounts)
    return account


def prepare_launch(
    version_id: str,
    *,
    game_dir: Path,
    cache_dir: Path,
    account: Account,
    memory_gb: float = 4.0,
    demo: bool = False,
    window_width: int | None = None,
    window_height: int | None = None,
    isolated: bool = False,
    language: str | None = None,
    force: bool = False,
    instance_name: str | None = None,
    jvm_args: str | None = None,
    server: str | None = None,
    server_port: int | None = None,
) -> PreparedLaunch:
    """Prepare a launch (without running the process). May raise MetaError / LaunchError.

    When instance_name is given: game directory = <game_dir>/instances/<name> (
    saves/mods/config/logs are isolated), version files load from the instance directory,
    and libraries & assets still share the global directories.
    """
    global_gp = paths.GamePaths(game_dir)
    if instance_name is not None:
        from launcher.instances import instance_dir as instance_dir_fn

        launch_game_dir = instance_dir_fn(game_dir, instance_name)
        gp = paths.GamePaths(launch_game_dir)
        shared_libraries = global_gp.libraries_dir
        shared_assets = global_gp.assets_dir
        isolated_effective = False
    else:
        launch_game_dir = game_dir
        gp = global_gp
        shared_libraries = gp.libraries_dir
        shared_assets = gp.assets_dir
        isolated_effective = isolated

    version = load_version_json(
        version_id,
        versions_dir=gp.versions_dir,
        cache_dir=cache_dir,
        force=force,
    )
    platform = detect_platform()
    resolved = resolve_libraries(version.libraries, platform)

    required_major = version.java_version.major_version if version.java_version else 8
    runtimes = list_java(probe_dir=cache_dir)
    if not has_suitable_java(runtimes, required_major):
        raise JavaMissingError(required_major)
    java = match_java(runtimes, required_major)
    if java is None:
        raise JavaMissingError(required_major)

    natives_dir = gp.version_dir(version.id) / "natives"
    prepare_natives(resolved, shared_libraries, natives_dir)

    if account.type == "microsoft":
        tokens = account.tokens
        profile = LaunchProfile(
            username=account.username,
            uuid=account.uuid,
            access_token=tokens.mc_access_token if tokens is not None else "0",
            user_type="msa",
        )
    else:
        profile = LaunchProfile(
            username=account.username, uuid=account.uuid, access_token="0", user_type="legacy"
        )

    command = build_argv(
        version,
        game_dir=launch_game_dir,
        libraries_dir=shared_libraries,
        natives_dir=natives_dir,
        java_path=java.path,
        java_major=java.major,
        profile=profile,
        platform=platform,
        resolved_libraries=resolved,
        memory_gb=memory_gb,
        demo=demo,
        window_width=window_width,
        window_height=window_height,
        isolated=isolated_effective,
        language=language,
        assets_dir=shared_assets,
        extra_jvm_args=jvm_args,
        server=server,
        server_port=server_port,
    )
    return PreparedLaunch(
        command=command, account=account, version=version, java=java, isolated=isolated
    )
