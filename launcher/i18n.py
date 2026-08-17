"""核心库 i18n（#27）：launcher/ 包内面向用户的错误/状态消息中英双语。

GUI 通过 gui.i18n.set_language 同步核心语言；CLI 在 main() 按配置 ui_language 设置。
默认 zh_cn（与历史行为一致）。
"""

from __future__ import annotations

import httpx

ZH = "zh_cn"
EN = "en_us"

CORE_TRANSLATIONS: dict[str, dict[str, str]] = {
    ZH: {
        "error.verify_failed": "校验失败: {}",
        "net.timeout": "网络请求超时，请检查网络连接",
        "net.connect": "网络连接失败，请检查网络/代理设置",
        "net.http_error": "服务器返回错误（HTTP {}）",
        "net.server_error": "服务器错误（HTTP {}），请稍后重试",
        "net.rate_limited": "请求过于频繁（429），请稍后再试",
        "net.ssl": "SSL 证书校验失败: {}",
        "net.other": "网络请求失败: {}",
        "meta.manifest_fetch_failed": "无法获取版本清单: {}",
        "meta.version_fetch_failed": "获取版本信息失败: {}",
        "meta.version_missing": "版本不存在: {}",
        "meta.version_not_installed": "版本未安装: {}",
        "meta.inherit_cycle": "版本继承链存在循环: {}",
        "mods.request_failed": "请求失败 {}: {}",
        "mods.project_failed": "查询项目 {} 失败: {}",
        "mods.versions_failed": "查询版本失败: {}",
        "mods.search_failed": "搜索失败: {}",
        "mods.cf_key_invalid": "CurseForge API Key 无效（403）",
        "mods.cf_http_error": "（HTTP {}）",
        "mods.deps_failed": "解析依赖信息失败: {}",
        "mods.file_missing": "文件不存在: {}",
        "mods.no_versions": "没有找到该项目的版本",
        "mods.no_file": "该版本没有可下载的文件",
        "mods.no_match": "没有找到匹配的版本（loader={}，MC={}）",
        "mods.version_not_in_list": "指定的版本 id 不在列表中: {}",
        "mods.version_not_in_matches": "指定的版本 id 不在匹配列表中: {}",
        "mods.download_failed": "下载失败: {}",
        "mods.unknown_loader": "未知加载器: {}",
        "mods.loader_unavailable": "加载器 {} {} 对 MC {} 不可用",
        "mods.need_java": "未找到 Java，请先运行 java install",
        "mods.need_suitable_java": "未找到适配的 Java",
        "mods.no_installer_url": "该加载器版本没有安装器下载地址",
        "mods.installer_download_failed": "安装器下载失败: {}",
        "mods.installer_not_written": "安装器下载失败: 文件未落盘",
        "mods.installer_exit": "{} 安装器退出码 {}（详见控制台输出）",
        "mods.installer_no_version": "安装完成但未检测到新版本目录",
        "mods.pack_no_versions": "没有找到该整合包的版本",
        "mods.pack_parse_failed": "无法解析整合包内容",
        "mods.pack_mc_missing": "整合包未声明 Minecraft 版本",
        "mods.pack_need_base_mc": "请先安装 Minecraft {}（Forge/NeoForge 安装器需要基础版本）",
        "mods.pack_files_failed": "整合包文件下载失败（{} 个）",
        "mods.instance_exists": "同名实例已存在: {}",
        "mods.isolation_profile_missing": "版本隔离开启：请先安装对应的加载器版本，或通过 --version-id 指定档案 id",
        "java.assets_failed": "查询 Adoptium 资产列表失败: {}",
        "java.no_asset": "Adoptium 上没有适用于当前平台的 Java {} 资产",
        "java.download_failed": "下载失败: {}",
        "java.extract_failed": "解压后未找到可执行文件: {}",
        "java.runtime_missing": "托管 Java {} 未安装",
        "instances.name_invalid": "实例名需为 1~32 字符（字母/数字/中文/空格/._-），不含路径分隔符",
        "instances.exists": "实例已存在: {}",
        "instances.missing": "实例不存在: {}",
        "instances.dir_exists": "目标目录已存在: {}",
        "instances.dir_missing": "实例目录不存在: {}",
        "instances.import_invalid": "不是有效的实例压缩包（缺少 instance.json）",
        "launch.missing_natives": "缺少 natives 库: {}",
        "vault.dependency_missing": "缺少 cryptography 依赖，无法使用令牌加密",
        "vault.no_vault": "令牌保险库不存在，请先在设置中开启令牌加密",
        "vault.corrupt": "令牌保险库文件损坏",
        "vault.bad_format": "令牌密文格式不识别",
        "vault.decrypt_failed": "令牌解密失败（密码可能已更改）",
        "vault.wrong_password": "令牌加密密码不正确",
        "vault.env_wrong_password": "MCLAUNCHER_TOKEN_PASSWORD 提供的令牌密码不正确",
        "vault.password_required": "令牌加密已开启但未提供密码（请先输入密码解锁，或设置 MCLAUNCHER_TOKEN_PASSWORD 环境变量）",
        "vault.password_prompt": "令牌加密密码: ",
        "vault.account_decrypt_failed": "账号 {} 解密失败: {}",
        "auth.device_flow_failed": "发起设备码流程失败: {}",
        "auth.device_flow_started": "正在发起微软登录（设备码流程）...",
        "auth.device_code": "请在浏览器打开 {} 并输入代码 {}",
        "auth.page_opened": "已在默认浏览器打开授权页面",
        "auth.code_copied": "授权码 {} 已复制到剪贴板",
        "auth.waiting": "等待授权完成（最长约 15 分钟，按 Ctrl+C 取消）...",
        "auth.declined": "您在浏览器中拒绝了授权。",
        "auth.expired": "设备码已过期，请重新运行登录。",
        "auth.flow_failed": "设备码流程失败: {}（{}）",
        "auth.refresh_failed": "令牌刷新请求失败: {}",
        "auth.chain_failed": "认证请求失败: {}",
        "auth.no_ownership": "该微软账号未拥有 Minecraft Java 版（正版资格校验未通过）。",
        "auth.no_profile": "该账号还没有 Minecraft 档案（从未创建过角色）。",
        "auth.needs_login": "登录已失效，请重新登录。",
        "auth.xbox_failed": "Xbox 认证失败（错误码 {}）：{}",
        "auth.xbox_unknown": "未知原因",
        "auth.xsts.no_profile": "该账号没有 Xbox 档案，或该账号受家庭设置限制；请先登录 xbox.com 处理。",
        "auth.xsts.region": "Xbox Live 在您所在的国家/地区不可用。",
        "auth.xsts.adult": "该账号需要成人验证（仅韩国地区要求）。",
        "auth.xsts.child": "该账号是未成年人账号，需要家长在家庭设置中同意后才能登录。",
        "offline.locked": "离线模式需先使用微软正版账号登录一次（启动器和系统语言均为中文时可直接使用）",
    },
    EN: {
        "error.verify_failed": "Verification failed: {}",
        "net.timeout": "Network request timed out; check your connection",
        "net.connect": "Network connection failed; check your network/proxy settings",
        "net.http_error": "Server returned an error (HTTP {})",
        "net.server_error": "Server error (HTTP {}); please retry later",
        "net.rate_limited": "Too many requests (429); please retry later",
        "net.ssl": "SSL verification failed: {}",
        "net.other": "Network request failed: {}",
        "meta.manifest_fetch_failed": "Failed to fetch version manifest: {}",
        "meta.version_fetch_failed": "Failed to fetch version info: {}",
        "meta.version_missing": "Version not found: {}",
        "meta.version_not_installed": "Version not installed: {}",
        "meta.inherit_cycle": "Inheritance cycle for version: {}",
        "mods.request_failed": "Request failed {}: {}",
        "mods.project_failed": "Failed to query project {}: {}",
        "mods.versions_failed": "Failed to query versions: {}",
        "mods.search_failed": "Search failed: {}",
        "mods.cf_key_invalid": "Invalid CurseForge API key (403)",
        "mods.cf_http_error": " (HTTP {})",
        "mods.deps_failed": "Failed to resolve dependencies: {}",
        "mods.file_missing": "File not found: {}",
        "mods.no_versions": "No versions found for this project",
        "mods.no_file": "No downloadable file for this version",
        "mods.no_match": "No matching version (loader={}, MC={})",
        "mods.version_not_in_list": "Specified version id not in list: {}",
        "mods.version_not_in_matches": "Specified version id not in matching list: {}",
        "mods.download_failed": "Download failed: {}",
        "mods.unknown_loader": "Unknown loader: {}",
        "mods.loader_unavailable": "Loader {} {} unavailable for MC {}",
        "mods.need_java": "No Java found; run 'java install' first",
        "mods.need_suitable_java": "No compatible Java found",
        "mods.no_installer_url": "Loader version has no installer URL",
        "mods.installer_download_failed": "Installer download failed: {}",
        "mods.installer_not_written": "Installer download failed: file not written",
        "mods.installer_exit": "{} installer exited with code {} (see console)",
        "mods.installer_no_version": "Installer finished but no new version dir detected",
        "mods.pack_no_versions": "No versions found for this modpack",
        "mods.pack_parse_failed": "Failed to parse modpack contents",
        "mods.pack_mc_missing": "Modpack declares no Minecraft version",
        "mods.pack_need_base_mc": "Install Minecraft {} first (Forge/NeoForge installers need the base game)",
        "mods.pack_files_failed": "Modpack file download failed ({} files)",
        "mods.instance_exists": "Instance already exists: {}",
        "mods.isolation_profile_missing": "Version isolation on: install the matching loader profile first, or pass --version-id",
        "java.assets_failed": "Failed to query Adoptium assets: {}",
        "java.no_asset": "No Adoptium Java {} asset for this platform",
        "java.download_failed": "Download failed: {}",
        "java.extract_failed": "No executable found after extraction: {}",
        "java.runtime_missing": "Managed Java {} is not installed",
        "instances.name_invalid": "Instance name must be 1-32 chars (letters/digits/Chinese/space/._-), no path separators",
        "instances.exists": "Instance already exists: {}",
        "instances.missing": "Instance not found: {}",
        "instances.dir_exists": "Target directory already exists: {}",
        "instances.dir_missing": "Instance directory does not exist: {}",
        "instances.import_invalid": "Not a valid instance archive (missing instance.json)",
        "launch.missing_natives": "Missing natives library: {}",
        "vault.dependency_missing": "cryptography is missing; token encryption unavailable",
        "vault.no_vault": "Token vault missing; enable token encryption in settings first",
        "vault.corrupt": "Token vault file is corrupt",
        "vault.bad_format": "Unrecognized token ciphertext format",
        "vault.decrypt_failed": "Token decryption failed (password may have changed)",
        "vault.wrong_password": "Wrong token encryption password",
        "vault.env_wrong_password": "MCLAUNCHER_TOKEN_PASSWORD has the wrong password",
        "vault.password_required": "Token encryption enabled but no password provided (unlock first or set MCLAUNCHER_TOKEN_PASSWORD)",
        "vault.password_prompt": "Token encryption password: ",
        "vault.account_decrypt_failed": "Failed to decrypt account {}: {}",
        "auth.device_flow_failed": "Failed to start device flow: {}",
        "auth.device_flow_started": "Starting Microsoft login (device code flow)...",
        "auth.device_code": "Open {} in your browser and enter code {}",
        "auth.page_opened": "Opened the authorization page in your browser",
        "auth.code_copied": "Authorization code {} copied to clipboard",
        "auth.waiting": "Waiting for authorization (up to ~15 minutes, Ctrl+C to cancel)...",
        "auth.declined": "You declined the authorization in your browser.",
        "auth.expired": "Device code expired; start login again.",
        "auth.flow_failed": "Device flow failed: {} ({})",
        "auth.refresh_failed": "Token refresh request failed: {}",
        "auth.chain_failed": "Authentication request failed: {}",
        "auth.no_ownership": "This Microsoft account does not own Minecraft Java Edition.",
        "auth.no_profile": "This account has no Minecraft profile yet.",
        "auth.needs_login": "Session expired; please log in again.",
        "auth.xbox_failed": "Xbox authentication failed (code {}): {}",
        "auth.xbox_unknown": "unknown reason",
        "auth.xsts.no_profile": "This account has no Xbox profile, or it is restricted by family settings; fix it at xbox.com first.",
        "auth.xsts.region": "Xbox Live is not available in your country/region.",
        "auth.xsts.adult": "This account needs adult verification (required in Korea).",
        "auth.xsts.child": "This is a minor account; a parent must approve it in family settings.",
        "offline.locked": "Offline mode requires signing in with a Microsoft account first (available directly when both the UI and system language are Chinese)",
    },
}

_current: dict[str, str] = CORE_TRANSLATIONS[ZH]


def _merge_extra_core() -> None:
    """额外语言表由 scripts 生成（launcher/i18n_langs.py），首次导入后合并。"""
    try:
        from launcher.i18n_langs import EXTRA_CORE as _extra_core
    except ImportError:
        return
    for lang, table in _extra_core.items():
        CORE_TRANSLATIONS.setdefault(lang, table)


_merge_extra_core()


def set_core_language(lang: str) -> None:
    global _current
    _current = CORE_TRANSLATIONS.get(lang, CORE_TRANSLATIONS[ZH])


def get_core_language() -> str:
    for lang, table in CORE_TRANSLATIONS.items():
        if table is _current:
            return lang
    return ZH


def tr_core(key: str, *args) -> str:
    template = _current.get(key)
    if template is None:
        template = CORE_TRANSLATIONS[ZH].get(key, key)
    if args:
        return template.format(*args)
    return template


def describe_network_error(exc: httpx.HTTPError) -> str:
    """把 httpx 异常映射为面向用户的双语消息（#5：网络错误/5xx 中文化）。"""
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return tr_core("net.timeout")
    if isinstance(exc, httpx.ConnectError):
        return tr_core("net.connect")
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if 500 <= code < 600:
            return tr_core("net.server_error", code)
        if code == 429:
            return tr_core("net.rate_limited")
        return tr_core("net.http_error", code)
    return tr_core("net.other", str(exc))
