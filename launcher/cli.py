"""Launcher CLI (full-featured command-line entry point for the core library).

Subcommands: paths / config / login / logout / whoami / list-versions / show /
install / uninstall / java (list|install|remove) / launch / loader / mods /
instance (list|create|delete|rename|note|export|import|launch).

GUI counterpart: python -m gui or MinePick_Launcher.exe (launch with no args).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from launcher import __version__, config, logging_setup, paths
from launcher.auth import (
    AccountStore,
    AuthError,
    MicrosoftSession,
    create_offline_account,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="MinePick Launcher", description="MinePick Launcher 核心库 CLI"
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="调试日志")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("paths", help="显示目录解析结果")

    cfg = sub.add_parser("config", help="查看/修改启动器配置")
    cfg_sub = cfg.add_subparsers(dest="config_action", required=True)
    cfg_sub.add_parser("show", help="显示当前配置（JSON）")
    cfg_set = cfg_sub.add_parser("set", help="修改单个配置项")
    cfg_set.add_argument("key", help="配置项名（如 memory_gb / game_dir / java_path）")
    cfg_set.add_argument("value", help="新值")

    login_p = sub.add_parser("login", help="登录账号（默认微软正版登录）")
    login_p.add_argument("--offline", metavar="用户名", help="离线模式登录（不联网）")

    logout_p = sub.add_parser("logout", help="登出账号")
    logout_p.add_argument("--account", metavar="ID", help="登出指定账号（UUID）")
    logout_p.add_argument("--all", action="store_true", help="登出全部账号")

    sub.add_parser("whoami", help="显示当前登录的账号")

    lv = sub.add_parser("list-versions", help="列出可用的 Minecraft 版本")
    lv.add_argument(
        "--type",
        choices=["release", "snapshot", "old_beta", "old_alpha"],
        help="按版本类型过滤",
    )
    lv.add_argument("--limit", type=int, default=20, help="最多显示条数（默认 20）")
    lv.add_argument("--refresh", action="store_true", help="忽略缓存重新获取清单")

    show_p = sub.add_parser("show", help="查看指定版本的元数据")
    show_p.add_argument("id", help="版本 id（如 1.8.9 / 1.20.1）")
    show_p.add_argument("--refresh", action="store_true", help="忽略缓存重新获取")

    install_p = sub.add_parser("install", help="下载并安装指定版本")
    install_p.add_argument("id", help="版本 id（如 1.8.9 / 1.20.1）")
    install_p.add_argument("--refresh", action="store_true", help="忽略缓存重新获取元数据")
    install_p.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="下载并发数（默认取配置 max_concurrent_downloads）",
    )
    install_p.add_argument(
        "--auto-java",
        action="store_true",
        help="缺少适配 Java 时自动下载 JRE（默认取配置 auto_install_java）",
    )

    java_p = sub.add_parser("java", help="管理 Java 运行时")
    java_sub = java_p.add_subparsers(dest="java_action", required=True)
    java_sub.add_parser("list", help="列出检测到的 Java")
    java_install_p = java_sub.add_parser("install", help="从 Adoptium 下载 JRE")
    java_install_p.add_argument("major", type=int, help="主版本（如 17 / 21）")
    java_remove_p = java_sub.add_parser("remove", help="删除托管的 JRE")
    java_remove_p.add_argument("major", type=int, help="主版本（如 17 / 21）")

    launch_p = sub.add_parser("launch", help="启动游戏")
    launch_p.add_argument("id", help="版本 id")
    launch_p.add_argument(
        "--offline", metavar="用户名", help="以离线模式启动（覆盖所选账号）"
    )
    launch_p.add_argument("--memory", type=float, help="分配内存（GB）")
    launch_p.add_argument("--demo", action="store_true", help="演示模式")
    launch_p.add_argument("--width", type=int, help="窗口宽度")
    launch_p.add_argument("--height", type=int, help="窗口高度")
    launch_p.add_argument(
        "--lang",
        choices=[code for code, _name in config.GAME_LANGUAGES],
        default=None,
        help="游戏语言代码（默认取配置；空代码 = 跟随游戏内设置）",
    )
    launch_p.add_argument("--refresh", action="store_true", help="忽略缓存重新获取元数据")
    launch_p.add_argument("--jvm-args", default=None, help="自定义 JVM 参数（追加到版本默认参数之后）")
    launch_p.add_argument("--server", default=None, help="服务器直连地址（透传 --server）")
    launch_p.add_argument("--port", type=int, default=None, help="服务器端口（透传 --port）")

    uninstall_p = sub.add_parser("uninstall", help="卸载已安装的版本（删除 versions/<id>/，保留共享 libraries/assets）")
    uninstall_p.add_argument("id", help="版本 id")
    uninstall_p.add_argument("--yes", action="store_true", help="跳过确认提示")

    loader_p = sub.add_parser("loader", help="管理模组加载器（Fabric/Forge/NeoForge）")
    loader_sub = loader_p.add_subparsers(dest="loader_action", required=True)
    loader_list_p = loader_sub.add_parser("list", help="列出加载器可用版本")
    loader_list_p.add_argument("--game-version", help="MC 版本（如 1.20.1），缺省列出各加载器支持的 MC 版本")
    loader_install_p = loader_sub.add_parser("install", help="安装加载器（官方安装器静默运行）")
    loader_install_p.add_argument("loader", choices=["fabric", "forge", "neoforge"])
    loader_install_p.add_argument("--game-version", required=True, help="MC 版本（如 1.20.1）")
    loader_install_p.add_argument("--version", help="加载器版本号（缺省最新）")

    mods_p = sub.add_parser("mods", help="Modrinth 模组下载")
    mods_sub = mods_p.add_subparsers(dest="mods_action", required=True)
    mods_sub.add_parser("list", help="列出已安装的模组文件")
    mods_install_p = mods_sub.add_parser("install", help="从 Modrinth 下载模组")
    mods_install_p.add_argument("--project", required=True, help="项目 slug（如 sodium）")
    mods_install_p.add_argument(
        "--loader", choices=["fabric", "forge", "neoforge"], help="按加载器过滤"
    )
    mods_install_p.add_argument("--game-version", help="按 MC 版本过滤（如 1.20.1）")
    mods_install_p.add_argument("--version", help="指定 Modrinth 版本 id")
    mods_install_p.add_argument("--version-id", help="版本隔离时指定档案 id（versions/<id>）")

    mods_rp_p = mods_sub.add_parser("install-resourcepack", help="从 Modrinth 下载资源包")
    mods_rp_p.add_argument("--project", required=True, help="项目 slug（如 default-dark-mode）")
    mods_rp_p.add_argument("--game-version", help="按 MC 版本过滤")
    mods_rp_p.add_argument("--version", help="指定 Modrinth 版本 id")
    mods_rp_p.add_argument("--version-id", help="版本隔离时指定档案 id")

    mods_sp_p = mods_sub.add_parser("install-shaderpack", help="从 Modrinth 下载光影")
    mods_sp_p.add_argument("--project", required=True, help="项目 slug（如 complementary-reimagined）")
    mods_sp_p.add_argument("--game-version", help="按 MC 版本过滤")
    mods_sp_p.add_argument("--version", help="指定 Modrinth 版本 id")
    mods_sp_p.add_argument("--version-id", help="版本隔离时指定档案 id")

    mods_mp_p = mods_sub.add_parser("install-modpack", help="从 Modrinth 下载并安装整合包")
    mods_mp_p.add_argument("--project", required=True, help="项目 slug（如 better-mc）")
    mods_mp_p.add_argument("--version", help="指定 Modrinth 版本 id")

    inst_p = sub.add_parser("instance", help="实例管理（独立存档/模组/配置的游戏目录）")
    inst_sub = inst_p.add_subparsers(dest="instance_action", required=True)
    inst_sub.add_parser("list", help="列出实例")
    inst_create_p = inst_sub.add_parser("create", help="创建实例")
    inst_create_p.add_argument("name", nargs="?", help="实例名（缺省按版本/档案自动命名，如 1.21.11-Fabric_0.19.3）")
    inst_create_p.add_argument("--version", required=True, help="版本 id（如 1.20.1）")
    inst_delete_p = inst_sub.add_parser("delete", help="删除实例")
    inst_delete_p.add_argument("name", help="实例名")
    inst_rename_p = inst_sub.add_parser("rename", help="重命名实例")
    inst_rename_p.add_argument("name", help="当前实例名")
    inst_rename_p.add_argument("new_name", help="新实例名")
    inst_launch_p = inst_sub.add_parser("launch", help="启动实例")
    inst_launch_p.add_argument("name", help="实例名")
    inst_launch_p.add_argument(
        "--offline", metavar="用户名", help="以离线模式启动（覆盖所选账号）"
    )
    inst_launch_p.add_argument("--memory", type=float, help="分配内存（GB）")
    inst_launch_p.add_argument("--demo", action="store_true", help="演示模式")
    inst_launch_p.add_argument("--width", type=int, help="窗口宽度")
    inst_launch_p.add_argument("--height", type=int, help="窗口高度")
    inst_launch_p.add_argument(
        "--lang",
        choices=[code for code, _name in config.GAME_LANGUAGES],
        default=None,
        help="游戏语言代码（默认取配置；空代码 = 跟随游戏内设置）",
    )
    inst_launch_p.add_argument("--jvm-args", default=None, help="自定义 JVM 参数")
    inst_launch_p.add_argument("--server", default=None, help="服务器直连地址")
    inst_launch_p.add_argument("--port", type=int, default=None, help="服务器端口")
    inst_note_p = inst_sub.add_parser("note", help="编辑实例备注")
    inst_note_p.add_argument("name", help="实例名")
    inst_note_p.add_argument("text", help="备注内容（空字符串清空）")
    inst_export_p = inst_sub.add_parser("export", help="导出实例为 zip")
    inst_export_p.add_argument("name", help="实例名")
    inst_export_p.add_argument("dest", help="目标 zip 路径")
    inst_import_p = inst_sub.add_parser("import", help="从 zip 导入实例")
    inst_import_p.add_argument("zip_path", help="zip 文件路径")
    inst_import_p.add_argument("--name", default=None, help="导入后的新实例名（缺省用包内名称）")

    return parser


def cmd_paths(args: argparse.Namespace) -> int:
    cfg, _ = config.load()
    env_game = paths.ENV_GAME_DIR
    env_value = os.environ.get(env_game)
    effective = (
        cfg.game_dir
        or (Path(env_value).expanduser() if env_value else None)
        or paths.default_game_dir()
    )
    gp = paths.GamePaths(effective)

    print("启动器数据目录:", paths.launcher_dir())
    print("游戏目录解析:")
    print("  - 配置文件 game_dir:", cfg.game_dir or "(未设置)")
    print("  - 环境变量", env_game, ":", env_value or "(未设置)")
    print("  - 平台默认值:", paths.default_game_dir())
    print("生效的游戏目录:", gp.game_dir)
    print("  versions :", gp.versions_dir)
    print("  libraries:", gp.libraries_dir)
    print("  assets   :", gp.assets_dir)
    print("  mods     :", gp.mods_dir)
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    cfg, cfg_path = config.load()
    print("配置文件:", cfg_path)
    print(json.dumps(cfg.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    cfg, cfg_path = config.load()
    if args.key not in config.LauncherConfig.model_fields:
        print("错误: 未知配置项 '" + args.key + "'", file=sys.stderr)
        return 2
    try:
        setattr(cfg, args.key, args.value)
    except ValidationError as exc:
        print("错误: 值 '" + args.value + "' 无效: " + exc.errors()[0]["msg"], file=sys.stderr)
        return 2
    config.save(cfg, cfg_path)
    print("已写入", cfg_path)
    print(json.dumps(cfg.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def _select_account(account_id: str | None) -> None:
    cfg, cfg_path = config.load()
    cfg.selected_account = account_id
    config.save(cfg, cfg_path)


def cmd_login(args: argparse.Namespace) -> int:
    store = AccountStore()
    accounts = store.load()

    if args.offline is not None:
        if not config.offline_mode_allowed():
            from launcher.i18n import tr_core

            print("错误:", tr_core("offline.locked"), file=sys.stderr)
            return 1
        try:
            account = create_offline_account(args.offline)
        except ValueError as exc:
            print("错误:", exc, file=sys.stderr)
            return 2
        accounts[account.id] = account
        store.save(accounts)
        _select_account(account.id)
        print("离线登录成功:", account.username)
        print("  UUID:", account.uuid)
        return 0

    cfg, _ = config.load()
    session = MicrosoftSession(client_id=cfg.msa_client_id)

    def on_flow(flow) -> None:
        """After the device code is obtained: auto-open the verification page and copy the code."""
        from launcher.auth.microsoft import copy_user_code, open_verification_page
        from launcher.i18n import tr_core

        if open_verification_page(flow):
            print(tr_core("auth.page_opened"), flush=True)
        if copy_user_code(flow):
            print(tr_core("auth.code_copied", flow.get("user_code")), flush=True)

    try:
        account = session.login_interactive(
            progress=lambda msg: print(msg, flush=True), on_flow=on_flow
        )
    except AuthError as exc:
        print("登录失败:", exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        print("已取消登录。", file=sys.stderr)
        return 130
    accounts[account.id] = account
    store.save(accounts)
    _select_account(account.id)
    config.unlock_offline_mode()  # unlock offline mode after a premium login
    print("登录成功:", account.username)
    print("  UUID:", account.uuid)
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    store = AccountStore()
    accounts = store.load()
    cfg, cfg_path = config.load()

    if args.all:
        accounts.clear()
        cfg.selected_account = None
    elif args.account is not None:
        if args.account not in accounts:
            print("错误: 账号 '" + args.account + "' 不存在", file=sys.stderr)
            return 1
        accounts.pop(args.account, None)
        if cfg.selected_account == args.account:
            cfg.selected_account = None
    else:
        if not cfg.selected_account or cfg.selected_account not in accounts:
            print("当前没有登录的账号。", file=sys.stderr)
            return 1
        accounts.pop(cfg.selected_account, None)
        cfg.selected_account = None

    store.save(accounts)
    config.save(cfg, cfg_path)
    print("已登出。")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    accounts = AccountStore().load()
    cfg, _ = config.load()
    selected = cfg.selected_account
    if not selected or selected not in accounts:
        print("当前没有登录的账号。")
        return 1

    account = accounts[selected]
    kind = "微软正版" if account.type == "microsoft" else "离线模式"
    print("账号:", account.username, "（" + kind + "）")
    print("UUID:", account.uuid)
    if account.type == "microsoft" and account.tokens is not None:
        tokens = account.tokens
        for label, exp in (
            ("微软 access token", tokens.ms_expires_at),
            ("Minecraft token", tokens.mc_expires_at),
        ):
            state = time.ctime(exp) if exp else "未知"
            print(label + ": 有效至 " + state)
        if tokens.ms_refresh_token:
            print("刷新令牌: 已保存（可自动续期）")
    return 0


def cmd_list_versions(args: argparse.Namespace) -> int:
    from launcher.meta import MetaError, fetch_manifest

    cache = paths.launcher_dir() / "cache" / "version_manifest.json"
    try:
        manifest = fetch_manifest(cache_path=cache, force=args.refresh)
    except MetaError as exc:
        print("错误:", exc, file=sys.stderr)
        return 1
    versions = manifest.versions
    if args.type:
        versions = [v for v in versions if v.type == args.type]
    shown = versions[: args.limit]
    for v in shown:
        print(v.id.ljust(18), v.type.ljust(11), v.release_time)
    print("共", len(versions), "个版本（显示", len(shown), "个）")
    if not args.type:
        print("latest release :", manifest.latest.get("release"))
        print("latest snapshot:", manifest.latest.get("snapshot"))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    from launcher.meta import (
        MetaError,
        detect_platform,
        load_version_json,
        resolve_libraries,
    )

    cache_dir = paths.launcher_dir() / "cache"
    try:
        version = load_version_json(args.id, cache_dir=cache_dir, force=args.refresh)
    except MetaError as exc:
        print("错误:", exc, file=sys.stderr)
        return 1

    platform = detect_platform()
    resolved = resolve_libraries(version.libraries, platform)
    natives = [r for r in resolved if r.classifier is not None]

    print("版本:", version.id, "（" + version.type + "）")
    print("发布时间:", version.release_time or "未知")
    print("mainClass:", version.main_class)
    if version.java_version is not None:
        print(
            "Java:",
            version.java_version.major_version,
            "（" + version.java_version.component + "）",
        )
    else:
        print("Java: 未声明（旧版本默认 8）")
    print("assetIndex:", version.asset_index.id, "| assets:", version.assets)
    print("客户端 jar:", version.client_jar_name)
    client_art = version.downloads.get("client")
    if client_art is not None:
        print("  下载:", client_art.url or "(无 url 字段)")
        print("  sha1:", client_art.sha1, "| size:", client_art.size)
    print(
        "libraries:",
        len(version.libraries),
        "个（平台过滤后",
        len(resolved),
        "，其中 natives",
        len(natives),
        "）",
    )
    fmt = "旧格式 minecraftArguments" if version.is_legacy else "新格式 arguments"
    print(
        "参数:",
        fmt,
        "| game",
        len(version.effective_game_arguments()),
        "条 | jvm",
        len(version.effective_jvm_arguments()),
        "条",
    )
    return 0


def _install_progress_printer():
    """Throttled progress printing (every 0.5s, carriage-return overwrite)."""
    last = [0.0]

    def cb(p) -> None:
        now = time.time()
        if now - last[0] < 0.5 and p.done_files < p.total_files:
            return
        last[0] = now
        line = "  " + str(p.done_files) + "/" + str(p.total_files) + " 文件"
        if p.total_bytes:
            line += " | " + f"{p.done_bytes / 1048576:.1f}/{p.total_bytes / 1048576:.1f} MB"
        if p.current:
            line += " | " + p.current
        print(line + "   ", end="\r", flush=True)

    return cb


def cmd_install(args: argparse.Namespace) -> int:
    from launcher.install import install_version
    from launcher.meta import MetaError

    cfg, _ = config.load()
    env_value = os.environ.get(paths.ENV_GAME_DIR)
    game_dir = (
        cfg.game_dir
        or (Path(env_value).expanduser() if env_value else None)
        or paths.default_game_dir()
    )
    concurrency = args.concurrency or cfg.max_concurrent_downloads
    auto_java = args.auto_java or cfg.auto_install_java
    print("游戏目录:", game_dir)
    print("安装版本:", args.id, "（并发", concurrency, "，自动 JRE", "开" if auto_java else "关", "）")
    try:
        result = install_version(
            args.id,
            game_dir=game_dir,
            cache_dir=paths.launcher_dir() / "cache",
            concurrency=concurrency,
            force=args.refresh,
            progress=_install_progress_printer(),
            auto_install_java=auto_java,
            runtime_dir=paths.launcher_dir() / "runtime",
        )
    except MetaError as exc:
        print()
        print("错误:", exc, file=sys.stderr)
        return 1

    print()
    print(
        "完成: 下载",
        result.downloaded,
        "个文件（" + f"{result.bytes / 1048576:.1f}" + " MB），跳过",
        result.skipped,
        "个，失败",
        len(result.failed),
        "个",
    )
    for url, err in result.failed:
        print("失败:", url, "->", err, file=sys.stderr)
    return 1 if result.failed else 0


def cmd_java(args: argparse.Namespace) -> int:
    from launcher.java import JavaError, install_java, list_java

    probe_dir = paths.launcher_dir() / "cache"
    if args.java_action == "remove":
        from launcher.java.install import delete_managed_runtime

        try:
            removed = delete_managed_runtime(
                args.major, runtime_dir=paths.launcher_dir() / "runtime"
            )
        except JavaError as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        print("已删除:", removed)
        return 0

    if args.java_action == "list":
        runtimes = list_java(probe_dir=probe_dir)
        if not runtimes:
            print("未检测到 Java。可用 java install 17 / java install 21 自动下载。")
            return 1
        for r in runtimes:
            print(
                str(r.major).ljust(4),
                r.provider.ljust(10),
                (r.version + "  ").ljust(30),
                "->",
                r.path,
            )
        return 0
    try:
        runtime = install_java(
            args.major,
            runtime_dir=paths.launcher_dir() / "runtime",
            probe_dir=probe_dir,
            progress=_install_progress_printer(),
        )
    except JavaError as exc:
        print()
        print("错误:", exc, file=sys.stderr)
        return 1
    print()
    print("Java", runtime.major, "已就绪:", runtime.path)
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    from launcher.auth import AccountStore, NeedsLoginError
    from launcher.java import JavaError, install_java
    from launcher.launch import (
        JavaMissingError,
        LaunchError,
        OfflineLockedError,
        find_new_crash_reports,
        prepare_launch,
        resolve_launch_account,
        run_process,
    )
    from launcher.meta import MetaError

    cfg, _ = config.load()
    env_value = os.environ.get(paths.ENV_GAME_DIR)
    game_dir = (
        cfg.game_dir
        or (Path(env_value).expanduser() if env_value else None)
        or paths.default_game_dir()
    )

    # Account (Microsoft accounts auto-refresh their session; offline mode is gated by premium verification)
    store = AccountStore()
    try:
        account = resolve_launch_account(store, cfg.selected_account, args.offline)
    except (NeedsLoginError, ValueError, OfflineLockedError) as exc:
        print("错误:", exc, file=sys.stderr)
        return 1

    memory = args.memory if args.memory is not None else cfg.memory_gb
    language = args.lang if args.lang is not None else cfg.game_language
    jvm_args = args.jvm_args if args.jvm_args is not None else (cfg.jvm_args or None)
    probe_dir = paths.launcher_dir() / "cache"
    runtime_dir = paths.launcher_dir() / "runtime"

    def do_prepare():
        return prepare_launch(
            args.id,
            game_dir=game_dir,
            cache_dir=probe_dir,
            account=account,
            memory_gb=memory,
            demo=args.demo,
            window_width=args.width,
            window_height=args.height,
            isolated=cfg.version_isolation,
            language=language,
            force=args.refresh,
            jvm_args=jvm_args,
            server=args.server,
            server_port=args.port,
        )

    try:
        prepared = do_prepare()
    except JavaMissingError as exc:
        answer = input(
            "需要 Java " + str(exc.required_major) + "，是否立即下载？[y/N] "
        ).strip().lower()
        if answer not in ("y", "yes", "是"):
            print("已取消。可先运行 java install " + str(exc.required_major), file=sys.stderr)
            return 1
        print("正在下载 Java " + str(exc.required_major) + " ...")
        try:
            install_java(
                exc.required_major,
                runtime_dir=runtime_dir,
                probe_dir=probe_dir,
                progress=_install_progress_printer(),
            )
        except JavaError as exc2:
            print()
            print("下载失败:", exc2, file=sys.stderr)
            return 1
        try:
            prepared = do_prepare()
        except (MetaError, LaunchError) as exc3:
            print("错误:", exc3, file=sys.stderr)
            return 1
    except (MetaError, LaunchError) as exc:
        print("错误:", exc, file=sys.stderr)
        return 1

    command = prepared.command
    print(
        "启动",
        prepared.version.id,
        "| Java",
        prepared.java.major,
        "|",
        account.username,
        "| 内存 " + str(memory) + "G",
        "| 语言 " + (language or "跟随游戏"),
        "| 版本隔离 " + ("开" if prepared.isolated else "关"),
    )
    print("cwd:", command.cwd)
    if command.argfile is not None:
        print("使用 @argfile:", command.argfile)
    started = time.time()
    code = run_process(command.argv, command.cwd)
    for report in find_new_crash_reports(game_dir, started):
        print("发现崩溃报告:", report, file=sys.stderr)
    print("游戏进程退出码:", code)
    return 0 if code == 0 else code


def _game_dir_from_config() -> Path:
    cfg, _ = config.load()
    env_value = os.environ.get(paths.ENV_GAME_DIR)
    return (
        cfg.game_dir
        or (Path(env_value).expanduser() if env_value else None)
        or paths.default_game_dir()
    )


def cmd_uninstall(args: argparse.Namespace) -> int:
    from launcher.install import find_version_dependents, uninstall_version
    from launcher.meta import MetaError

    game_dir = _game_dir_from_config()
    dependents = find_version_dependents(game_dir, args.id)
    if dependents:
        print("注意: 以下档案依赖", args.id, ":", ", ".join(dependents))
    if not args.yes:
        answer = input(
            "确定卸载 " + args.id + "？该版本目录将被删除（版本隔离模式下含其存档/模组/配置）[y/N] "
        ).strip().lower()
        if answer not in ("y", "yes", "是"):
            print("已取消。")
            return 1
    try:
        uninstall_version(args.id, game_dir)
    except MetaError as exc:
        print("错误:", exc, file=sys.stderr)
        return 1
    print("已卸载:", args.id)
    return 0


def cmd_loader(args: argparse.Namespace) -> int:
    from launcher.mods import (
        ModsError,
        install_loader,
        list_game_versions,
        list_loader_versions,
    )

    if args.loader_action == "list":
        if args.game_version is None:
            for loader in ("fabric", "forge", "neoforge"):
                try:
                    versions = list_game_versions(loader)
                except ModsError as exc:
                    print(loader, "获取失败:", exc, file=sys.stderr)
                    continue
                print(loader, "支持版本（最新 8 个）:", ", ".join(versions[:8]))
            return 0
        try:
            versions = list_loader_versions("fabric", args.game_version)
        except ModsError as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        for loader in ("fabric", "forge", "neoforge"):
            try:
                items = list_loader_versions(loader, args.game_version)
            except ModsError as exc:
                print(loader + ":", "不可用（" + str(exc) + "）")
                continue
            for item in items[:5]:
                mark = "（推荐）" if item.recommended else ""
                print(loader, item.version, mark)
            if not items:
                print(loader + ": 不支持 " + args.game_version)
        return 0

    # install
    try:
        items = list_loader_versions(args.loader, args.game_version)
    except ModsError as exc:
        print("错误:", exc, file=sys.stderr)
        return 1
    if not items:
        print("错误:", args.loader, "不支持", args.game_version, file=sys.stderr)
        return 1
    if args.version:
        chosen = next((i for i in items if i.version == args.version), None)
        if chosen is None:
            print("错误: 找不到版本", args.version, file=sys.stderr)
            return 1
    else:
        chosen = items[0]
    print(
        "安装",
        args.loader,
        chosen.version,
        "（MC",
        args.game_version + "）...",
    )
    try:
        version_id = install_loader(
            chosen,
            _game_dir_from_config(),
            cache_dir=paths.launcher_dir() / "cache",
            progress=_install_progress_printer(),
        )
    except ModsError as exc:
        print()
        print("错误:", exc, file=sys.stderr)
        return 1
    print()
    print("安装完成，新版本 id:", version_id)
    print("启动方式: launch", version_id)
    return 0


def cmd_mods(args: argparse.Namespace) -> int:
    from launcher.mods import (
        ModsError,
        install_mod,
        install_modpack,
        install_resourcepack,
        install_shaderpack,
    )

    cfg, _ = config.load()
    game_dir = _game_dir_from_config()
    if args.mods_action == "list":
        gp = paths.GamePaths(game_dir)
        target = gp.mods_dir
        if not target.exists():
            print("（空）模组目录:", target)
            return 0
        files = sorted(target.glob("*.jar"))
        if not files:
            print("（空）模组目录:", target)
            return 0
        print("模组目录:", target)
        for file in files:
            print(" ", file.name, "（" + str(file.stat().st_size) + " 字节）")
        return 0

    try:
        if args.mods_action == "install":
            info = install_mod(
                args.project,
                game_dir=game_dir,
                loader=args.loader,
                game_version=args.game_version,
                version_id=args.version_id,
                mod_version_id=args.version,
                isolated=cfg.version_isolation,
                progress=_install_progress_printer(),
            )
            print()
            print("已安装:", info.title, "（" + info.slug + "）")
            if info.depends:
                print("必要前置:", ", ".join(info.depends), "— 缺少这些模组可能无法运行")
            if info.optional_depends:
                print("可选前置:", ", ".join(info.optional_depends), "— 建议安装以启用完整功能")
            return 0
        if args.mods_action == "install-resourcepack":
            info = install_resourcepack(
                args.project,
                game_dir=game_dir,
                game_version=args.game_version,
                version_id=args.version_id,
                mod_version_id=args.version,
                isolated=cfg.version_isolation,
                progress=_install_progress_printer(),
            )
            print()
            print("资源包已安装:", info.title, "（" + info.slug + "）")
            return 0
        if args.mods_action == "install-shaderpack":
            info = install_shaderpack(
                args.project,
                game_dir=game_dir,
                game_version=args.game_version,
                version_id=args.version_id,
                mod_version_id=args.version,
                isolated=cfg.version_isolation,
                progress=_install_progress_printer(),
            )
            print()
            print("光影已安装:", info.title, "（" + info.slug + "）")
            return 0
        # install-modpack
        pack = install_modpack(
            args.project,
            game_dir=game_dir,
            cache_dir=paths.launcher_dir() / "cache",
            mod_version_id=args.version,
            progress=_install_progress_printer(),
        )
        print()
        print("整合包已安装:", pack.name, "（" + pack.version + "）")
        if pack.loader:
            print("加载器:", pack.loader, pack.loader_version)
        print("Minecraft:", pack.minecraft, "| 文件数:", pack.files_count)
        print("实例:", pack.instance_name, "（启动: instance launch", pack.instance_name + "）")
        return 0
    except ModsError as exc:
        print()
        print("错误:", exc, file=sys.stderr)
        return 1


def cmd_instance(args: argparse.Namespace) -> int:
    from launcher.auth import AccountStore, NeedsLoginError
    from launcher.instances import (
        InstancesError,
        create_instance,
        delete_instance,
        instance_dir,
        list_instances,
    )
    from launcher.java import JavaError, install_java
    from launcher.launch import (
        JavaMissingError,
        LaunchError,
        OfflineLockedError,
        find_new_crash_reports,
        prepare_launch,
        resolve_launch_account,
        run_process,
    )
    from launcher.meta import MetaError

    cfg, _ = config.load()
    game_dir = _game_dir_from_config()
    probe_dir = paths.launcher_dir() / "cache"

    if args.instance_action == "list":
        instances = list_instances()
        if not instances:
            print("（空）实例目录:", instance_dir(game_dir, "").parent)
            return 0
        for name, inst in sorted(instances.items()):
            print(name, "->", inst.version_id)
        return 0

    if args.instance_action == "create":
        try:
            inst = create_instance(
                args.name, args.version, game_dir, cache_dir=probe_dir
            )
        except (InstancesError, MetaError) as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        print("实例已创建:", inst.name, "->", inst.version_id)
        print("目录:", instance_dir(game_dir, inst.name))
        return 0

    if args.instance_action == "delete":
        try:
            delete_instance(args.name, game_dir)
        except InstancesError as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        print("已删除实例:", args.name)
        return 0

    if args.instance_action == "rename":
        from launcher.instances import rename_instance

        try:
            inst = rename_instance(args.name, args.new_name, game_dir)
        except InstancesError as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        print("已重命名:", args.name, "->", inst.name)
        print("目录:", instance_dir(game_dir, inst.name))
        return 0

    if args.instance_action == "note":
        from launcher.instances import update_instance_note

        try:
            inst = update_instance_note(args.name, args.text)
        except InstancesError as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        print("已更新备注:", inst.name, "->", repr(inst.note))
        return 0

    if args.instance_action == "export":
        from launcher.instances import export_instance

        try:
            dest = export_instance(args.name, Path(args.dest), game_dir)
        except InstancesError as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        print("已导出:", dest)
        return 0

    if args.instance_action == "import":
        from launcher.instances import import_instance

        try:
            inst = import_instance(Path(args.zip_path), game_dir, new_name=args.name)
        except (InstancesError, OSError) as exc:
            print("错误:", exc, file=sys.stderr)
            return 1
        print("已导入:", inst.name, "->", inst.version_id)
        print("目录:", instance_dir(game_dir, inst.name))
        return 0

    # launch
    instances = list_instances()
    inst = instances.get(args.name)
    if inst is None:
        print("错误: 实例不存在: " + args.name, file=sys.stderr)
        return 1

    store = AccountStore()
    try:
        account = resolve_launch_account(store, cfg.selected_account, args.offline)
    except (NeedsLoginError, ValueError, OfflineLockedError) as exc:
        print("错误:", exc, file=sys.stderr)
        return 1

    memory = args.memory if args.memory is not None else cfg.memory_gb
    language = args.lang if args.lang is not None else cfg.game_language
    jvm_args = args.jvm_args if args.jvm_args is not None else (cfg.jvm_args or None)

    def do_prepare():
        return prepare_launch(
            inst.version_id,
            game_dir=game_dir,
            cache_dir=probe_dir,
            account=account,
            memory_gb=memory,
            demo=args.demo,
            window_width=args.width,
            window_height=args.height,
            language=language or None,
            instance_name=inst.name,
            jvm_args=jvm_args,
            server=args.server,
            server_port=args.port,
        )

    try:
        prepared = do_prepare()
    except JavaMissingError as exc:
        answer = input(
            "需要 Java " + str(exc.required_major) + "，是否立即下载？[y/N] "
        ).strip().lower()
        if answer not in ("y", "yes", "是"):
            print("已取消。", file=sys.stderr)
            return 1
        try:
            install_java(
                exc.required_major,
                runtime_dir=paths.launcher_dir() / "runtime",
                probe_dir=probe_dir,
                progress=_install_progress_printer(),
            )
        except JavaError as exc2:
            print("下载失败:", exc2, file=sys.stderr)
            return 1
        try:
            prepared = do_prepare()
        except (MetaError, LaunchError) as exc3:
            print("错误:", exc3, file=sys.stderr)
            return 1
    except (MetaError, LaunchError) as exc:
        print("错误:", exc, file=sys.stderr)
        return 1

    command = prepared.command
    print(
        "启动实例",
        inst.name,
        "|",
        prepared.version.id,
        "| Java",
        prepared.java.major,
        "|",
        account.username,
    )
    print("cwd:", command.cwd)
    started = time.time()
    code = run_process(command.argv, command.cwd)
    for report in find_new_crash_reports(game_dir, started):
        print("发现崩溃报告:", report, file=sys.stderr)
    print("游戏进程退出码:", code)
    return 0 if code == 0 else code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    from launcher.auth.secure import VaultError

    logging_setup.configure_logging(
        verbose=args.verbose, log_file=paths.launcher_dir() / "logs" / "launcher.log"
    )
    # First launch: auto-initialize the game language (sync launcher/system language, once only)
    _cfg, _cfg_path = config.load()
    config.initialize_language(_cfg, _cfg_path)
    # Core-library error message language follows config ui_language
    from launcher.i18n import set_core_language

    set_core_language(_cfg.ui_language)
    try:
        return _dispatch(args)
    except VaultError as exc:
        # Token encryption enabled but no password, etc.: show a friendly hint instead of a stack trace
        print("错误:", exc, file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "paths":
        return cmd_paths(args)
    if args.command == "config":
        if args.config_action == "show":
            return cmd_config_show(args)
        return cmd_config_set(args)
    if args.command == "login":
        return cmd_login(args)
    if args.command == "logout":
        return cmd_logout(args)
    if args.command == "whoami":
        return cmd_whoami(args)
    if args.command == "list-versions":
        return cmd_list_versions(args)
    if args.command == "show":
        return cmd_show(args)
    if args.command == "install":
        return cmd_install(args)
    if args.command == "java":
        return cmd_java(args)
    if args.command == "launch":
        return cmd_launch(args)
    if args.command == "uninstall":
        return cmd_uninstall(args)
    if args.command == "loader":
        return cmd_loader(args)
    if args.command == "mods":
        return cmd_mods(args)
    if args.command == "instance":
        return cmd_instance(args)
    return 2
