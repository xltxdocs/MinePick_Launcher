"""微软账号登录：OAuth 设备码流程 + Xbox 认证链 + Minecraft 会话。

认证链（参考 wiki.vg / Microsoft Authentication Scheme）：
  MS 设备码流程 -> MS access token
  -> XBL (user.auth.xboxlive.com) -> XSTS (xsts.auth.xboxlive.com)
  -> Minecraft access token (api.minecraftservices.com)
  -> 正版资格校验 -> 游戏档案（UUID/用户名）
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid as uuidlib
import webbrowser
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from msal import PublicClientApplication

from launcher.auth.models import Account, GameProfile, MicrosoftTokens
from launcher.i18n import describe_network_error, tr_core

# 微软已停用旧版公开 client id（如 00000000402b5328，返回 AADSTS700016）。
# 当前默认值来自 PrismLauncher 开源项目（GPL）源码中的构建配置，支持设备码流程；
# 可用配置项 msa_client_id 或环境变量 MSA_CLIENT_ID 覆盖（例如注册自有 Azure 应用）。
DEFAULT_CLIENT_ID = "c36a9fb6-4f2a-41ff-90bd-ae7cc92031eb"
ENV_CLIENT_ID = "MSA_CLIENT_ID"


def resolve_client_id(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get(ENV_CLIENT_ID)
    if env:
        return env
    return DEFAULT_CLIENT_ID


# 注意：msal 会自动附加 offline_access 等保留 scope，显式传入会被拒绝
SCOPES = ["XboxLive.signin"]
AUTHORITY = "https://login.microsoftonline.com/consumers"

XBL_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_ENTITLEMENTS_URL = "https://api.minecraftservices.com/entitlements/mcstore"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"

XBL_RELYING_PARTY = "http://auth.xboxlive.com"
XSTS_RELYING_PARTY = "rp://api.minecraftservices.com/"

USER_AGENT = "mclauncher/0.1.0"
TOKEN_MARGIN = 60.0  # 提前 60 秒视为过期

XSTS_ERROR_KEYS: dict[int, str] = {
    2148916233: "auth.xsts.no_profile",
    2148916235: "auth.xsts.region",
    2148916236: "auth.xsts.adult",
    2148916237: "auth.xsts.adult",
    2148916238: "auth.xsts.child",
}


class AuthError(Exception):
    """认证失败基类（消息面向用户，中文）。"""


class XboxAuthError(AuthError):
    def __init__(self, code: int, message: str = ""):
        self.code = code
        self.xbox_message = message
        key = XSTS_ERROR_KEYS.get(code)
        if key is not None:
            text = tr_core(key)
        else:
            text = tr_core("auth.xbox_failed", code, message or tr_core("auth.xbox_unknown"))
        super().__init__(text)


class NoOwnershipError(AuthError):
    def __init__(self) -> None:
        super().__init__(tr_core("auth.no_ownership"))


class NoProfileError(AuthError):
    def __init__(self) -> None:
        super().__init__(tr_core("auth.no_profile"))


class NeedsLoginError(AuthError):
    def __init__(self) -> None:
        super().__init__(tr_core("auth.needs_login"))


def open_verification_page(flow: dict[str, Any]) -> bool:
    """在默认浏览器打开设备码授权页面（尽力而为，失败不影响登录）。"""
    uri = flow.get("verification_uri")
    if not uri:
        return False
    try:
        return bool(webbrowser.open(str(uri)))
    except Exception:  # noqa: BLE001 - 打开失败不影响登录流程
        return False


def copy_user_code(flow: dict[str, Any]) -> bool:
    """把设备码复制到系统剪贴板（尽力而为，失败不影响登录）。

    Windows 用 PowerShell Set-Clipboard（无需管道，无控制台闪现）；
    macOS 用 pbcopy；Linux 尝试 xclip/xsel（均需管道，受限环境自动跳过）。
    """
    code = str(flow.get("user_code") or "")
    if not code or re.fullmatch(r"[A-Za-z0-9-]+", code) is None:
        return False  # 异常字符不注入命令行
    try:
        if os.name == "nt":
            extra: dict = {}
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                extra["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Set-Clipboard -Value '" + code + "'",
                ],
                timeout=10,
                check=False,
                **extra,
            )
            return proc.returncode == 0
        for cmd in (
            ["pbcopy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            if shutil.which(cmd[0]) is None:
                continue
            try:
                proc = subprocess.run(
                    cmd, input=code.encode("utf-8"), timeout=5, check=False
                )
                return proc.returncode == 0
            except OSError:
                continue
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def _is_expired(expires_at: float | None) -> bool:
    return expires_at is None or time.time() + TOKEN_MARGIN >= expires_at


class XboxAuthChain:
    """XBL -> XSTS -> Minecraft 会话 的 HTTP 认证链。"""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30.0
        )

    def close(self) -> None:
        self._client.close()

    def xbl_token(self, ms_access_token: str) -> tuple[str, str]:
        resp = self._client.post(
            XBL_AUTH_URL,
            headers={"x-xbl-contract-version": "1", "Accept": "application/json"},
            json={
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": f"d={ms_access_token}",
                },
                "RelyingParty": XBL_RELYING_PARTY,
                "TokenType": "JWT",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["Token"], data["DisplayClaims"]["xui"][0]["uhs"]

    def xsts_token(self, xbl_token: str) -> tuple[str, str]:
        resp = self._client.post(
            XSTS_AUTH_URL,
            headers={"x-xbl-contract-version": "1", "Accept": "application/json"},
            json={
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
                "RelyingParty": XSTS_RELYING_PARTY,
                "TokenType": "JWT",
            },
        )
        data = resp.json()
        if resp.status_code >= 400 or "XErr" in data:
            raise XboxAuthError(int(data.get("XErr", resp.status_code)), data.get("Message", ""))
        return data["Token"], data["DisplayClaims"]["xui"][0]["uhs"]

    def minecraft_token(self, uhs: str, xsts_token: str) -> tuple[str, int]:
        """返回 (minecraft access token, 有效期秒数)。"""
        resp = self._client.post(
            MC_LOGIN_URL,
            json={"identityToken": f"XBL3.0 x={uhs};{xsts_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], int(data["expires_in"])

    def check_ownership(self, mc_token: str) -> bool:
        resp = self._client.get(
            MC_ENTITLEMENTS_URL, headers={"Authorization": f"Bearer {mc_token}"}
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return any(i.get("name") in ("game_minecraft", "product_minecraft") for i in items)

    def profile(self, mc_token: str) -> GameProfile:
        resp = self._client.get(
            MC_PROFILE_URL, headers={"Authorization": f"Bearer {mc_token}"}
        )
        if resp.status_code == 404:
            raise NoProfileError()
        resp.raise_for_status()
        data = resp.json()
        skin_url = ""
        skin_model = ""
        for skin in data.get("skins") or []:
            if skin.get("state") == "ACTIVE" and skin.get("url"):
                skin_url = skin["url"]
                skin_model = skin.get("variant") or "classic"
                break
        return GameProfile(
            uuid=str(uuidlib.UUID(hex=data["id"])),
            username=data["name"],
            skin_url=skin_url,
            skin_model=skin_model,
        )


class DeviceFlowProtocol(Protocol):
    """msal 设备码流程接口（便于测试注入）。"""

    def start(self) -> dict[str, Any]: ...
    def poll(self, flow: dict[str, Any]) -> dict[str, Any]: ...
    def refresh(self, refresh_token: str) -> dict[str, Any]: ...


class DeviceFlow:
    def __init__(
        self, app: PublicClientApplication | None = None, client_id: str | None = None
    ) -> None:
        self.app = app or PublicClientApplication(
            resolve_client_id(client_id), authority=AUTHORITY
        )

    def start(self) -> dict[str, Any]:
        flow = self.app.initiate_device_flow(scopes=SCOPES)
        if not flow or "device_code" not in flow:
            raise AuthError(tr_core("auth.device_flow_failed", flow))
        return flow

    def poll(self, flow: dict[str, Any]) -> dict[str, Any]:
        return self.app.acquire_token_by_device_flow(flow)

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self.app.acquire_token_by_refresh_token(refresh_token, scopes=SCOPES)


class MicrosoftSession:
    """组合设备码流程与 Xbox 认证链，产出/刷新 Minecraft 会话。"""

    def __init__(
        self,
        chain: XboxAuthChain | None = None,
        flow: DeviceFlowProtocol | None = None,
        client_id: str | None = None,
    ) -> None:
        self.chain = chain or XboxAuthChain()
        self.flow: DeviceFlowProtocol = flow or DeviceFlow(client_id=client_id)

    def login_interactive(
        self,
        progress: Callable[[str], None] | None = None,
        on_flow: Callable[[dict[str, Any]], None] | None = None,
    ) -> Account:
        """交互式登录：展示设备码并阻塞等待用户授权。

        progress 回调用于 UI/日志；on_flow 在拿到设备码后调用一次
        （携带 expires_in / interval 等字段，供 GUI 显示倒计时 #3）。
        """

        def report(msg: str) -> None:
            if progress is not None:
                progress(msg)

        report(tr_core("auth.device_flow_started"))
        flow = self.flow.start()
        if on_flow is not None:
            on_flow(flow)
        report(
            tr_core(
                "auth.device_code",
                flow.get("verification_uri"),
                flow.get("user_code"),
            )
        )
        report(tr_core("auth.waiting"))
        result = self.flow.poll(flow)
        if "access_token" not in result:
            error = result.get("error", "unknown_error")
            desc = result.get("error_description", "")
            if error == "authorization_declined":
                raise AuthError(tr_core("auth.declined"))
            if error in ("expired_token", "authorization_expired"):
                raise AuthError(tr_core("auth.expired"))
            raise AuthError(tr_core("auth.flow_failed", error, desc))
        return self._complete(
            result["access_token"],
            result.get("refresh_token"),
            int(result.get("expires_in", 3600)),
        )

    def ensure_session(self, account: Account) -> Account:
        """确保 Minecraft 会话可用：必要时刷新令牌并重走认证链，返回可能更新的账号。"""
        if account.tokens is None:
            raise NeedsLoginError()
        tokens = account.tokens
        if not _is_expired(tokens.mc_expires_at):
            return account

        ms_access = tokens.ms_access_token
        refresh = tokens.ms_refresh_token
        if ms_access is None or _is_expired(tokens.ms_expires_at):
            if refresh is None:
                raise NeedsLoginError()
            result = self.flow.refresh(refresh)
            if "access_token" not in result:
                raise NeedsLoginError()
            ms_access = result["access_token"]
            refresh = result.get("refresh_token", refresh)
            expires_in = int(result.get("expires_in", 3600))
        else:
            expires_in = max(0, int(tokens.ms_expires_at - time.time()))

        try:
            updated = self._complete(ms_access, refresh, expires_in)
        except httpx.HTTPError as exc:
            raise AuthError(
                tr_core("auth.refresh_failed", describe_network_error(exc))
            ) from exc
        updated.created_at = account.created_at
        return updated

    def _complete(self, ms_access: str, refresh: str | None, expires_in: int) -> Account:
        try:
            xbl, _ = self.chain.xbl_token(ms_access)
            xsts, uhs = self.chain.xsts_token(xbl)
            mc_token, mc_expires = self.chain.minecraft_token(uhs, xsts)
            if not self.chain.check_ownership(mc_token):
                raise NoOwnershipError()
            profile = self.chain.profile(mc_token)
        except httpx.HTTPError as exc:
            raise AuthError(
                tr_core("auth.chain_failed", describe_network_error(exc))
            ) from exc

        now = time.time()
        return Account(
            id=profile.uuid,
            type="microsoft",
            username=profile.username,
            uuid=profile.uuid,
            created_at=now,
            skin_url=profile.skin_url,
            tokens=MicrosoftTokens(
                ms_access_token=ms_access,
                ms_refresh_token=refresh,
                ms_expires_at=now + expires_in,
                mc_access_token=mc_token,
                mc_expires_at=now + mc_expires,
            ),
        )
