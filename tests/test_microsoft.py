import time

import httpx
import pytest
import respx

from launcher.auth import microsoft as ms
from launcher.auth.models import Account, MicrosoftTokens

FAKE_MS = {"access_token": "ms-at", "refresh_token": "ms-rt", "expires_in": 3600}
PROFILE_ID_HEX = "069a79f444e94726a5befca90e38aaf5"
PROFILE_UUID = "069a79f4-44e9-4726-a5be-fca90e38aaf5"


class FakeDeviceFlow:
    def __init__(self, poll_result=None):
        self.poll_result = dict(poll_result if poll_result is not None else FAKE_MS)
        self.refresh_calls = 0

    def start(self):
        return {
            "device_code": "dc",
            "user_code": "ABCD1234",
            "verification_uri": "https://microsoft.com/link",
            "interval": 1,
            "expires_in": 900,
        }

    def poll(self, flow):
        return dict(self.poll_result)

    def refresh(self, refresh_token):
        self.refresh_calls += 1
        return dict(FAKE_MS)


def _mock_chain_ok():
    respx.post("https://user.auth.xboxlive.com/user/authenticate").mock(
        return_value=httpx.Response(
            200, json={"Token": "xbl", "DisplayClaims": {"xui": [{"uhs": "uhs1"}]}}
        )
    )
    respx.post("https://xsts.auth.xboxlive.com/xsts/authorize").mock(
        return_value=httpx.Response(
            200, json={"Token": "xsts", "DisplayClaims": {"xui": [{"uhs": "uhs1"}]}}
        )
    )
    respx.post("https://api.minecraftservices.com/authentication/login_with_xbox").mock(
        return_value=httpx.Response(
            200, json={"access_token": "mc-token", "expires_in": 86400}
        )
    )
    respx.get("https://api.minecraftservices.com/entitlements/mcstore").mock(
        return_value=httpx.Response(200, json={"items": [{"name": "game_minecraft"}]})
    )
    respx.get("https://api.minecraftservices.com/minecraft/profile").mock(
        return_value=httpx.Response(200, json={"id": PROFILE_ID_HEX, "name": "Steve"})
    )


def _account(ms_exp=None, mc_exp=None, refresh="ms-rt"):
    now = time.time()
    return Account(
        id=PROFILE_UUID,
        type="microsoft",
        username="Steve",
        uuid=PROFILE_UUID,
        created_at=now,
        tokens=MicrosoftTokens(
            ms_access_token="ms-at",
            ms_refresh_token=refresh,
            ms_expires_at=now + 3600 if ms_exp is None else ms_exp,
            mc_access_token="mc-token",
            mc_expires_at=now + 3600 if mc_exp is None else mc_exp,
        ),
    )


@respx.mock
def test_login_interactive_success():
    _mock_chain_ok()
    session = ms.MicrosoftSession(flow=FakeDeviceFlow())
    progress = []
    account = session.login_interactive(progress=progress.append)
    assert account.username == "Steve"
    assert account.uuid == PROFILE_UUID
    assert account.type == "microsoft"
    assert account.tokens is not None
    assert account.tokens.mc_access_token == "mc-token"
    assert account.tokens.ms_access_token == "ms-at"
    assert account.tokens.ms_refresh_token == "ms-rt"
    assert any("ABCD1234" in m for m in progress)
    assert any("microsoft.com/link" in m for m in progress)


@respx.mock
def test_xsts_error_mapped():
    respx.post("https://user.auth.xboxlive.com/user/authenticate").mock(
        return_value=httpx.Response(
            200, json={"Token": "xbl", "DisplayClaims": {"xui": [{"uhs": "uhs1"}]}}
        )
    )
    respx.post("https://xsts.auth.xboxlive.com/xsts/authorize").mock(
        return_value=httpx.Response(
            401,
            json={
                "Identity": "0",
                "XErr": 2148916233,
                "Message": "The account does not have an Xbox account",
                "Redirect": "https://www.xbox.com/link",
            },
        )
    )
    session = ms.MicrosoftSession(flow=FakeDeviceFlow())
    with pytest.raises(ms.XboxAuthError) as ei:
        session.login_interactive()
    assert ei.value.code == 2148916233
    assert "Xbox" in str(ei.value)


@respx.mock
def test_no_ownership():
    respx.post("https://user.auth.xboxlive.com/user/authenticate").mock(
        return_value=httpx.Response(
            200, json={"Token": "xbl", "DisplayClaims": {"xui": [{"uhs": "uhs1"}]}}
        )
    )
    respx.post("https://xsts.auth.xboxlive.com/xsts/authorize").mock(
        return_value=httpx.Response(
            200, json={"Token": "xsts", "DisplayClaims": {"xui": [{"uhs": "uhs1"}]}}
        )
    )
    respx.post("https://api.minecraftservices.com/authentication/login_with_xbox").mock(
        return_value=httpx.Response(
            200, json={"access_token": "mc-token", "expires_in": 86400}
        )
    )
    respx.get("https://api.minecraftservices.com/entitlements/mcstore").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    session = ms.MicrosoftSession(flow=FakeDeviceFlow())
    with pytest.raises(ms.NoOwnershipError):
        session.login_interactive()


@respx.mock
def test_profile_404():
    respx.post("https://user.auth.xboxlive.com/user/authenticate").mock(
        return_value=httpx.Response(
            200, json={"Token": "xbl", "DisplayClaims": {"xui": [{"uhs": "uhs1"}]}}
        )
    )
    respx.post("https://xsts.auth.xboxlive.com/xsts/authorize").mock(
        return_value=httpx.Response(
            200, json={"Token": "xsts", "DisplayClaims": {"xui": [{"uhs": "uhs1"}]}}
        )
    )
    respx.post("https://api.minecraftservices.com/authentication/login_with_xbox").mock(
        return_value=httpx.Response(
            200, json={"access_token": "mc-token", "expires_in": 86400}
        )
    )
    respx.get("https://api.minecraftservices.com/entitlements/mcstore").mock(
        return_value=httpx.Response(200, json={"items": [{"name": "game_minecraft"}]})
    )
    respx.get("https://api.minecraftservices.com/minecraft/profile").mock(
        return_value=httpx.Response(404)
    )
    session = ms.MicrosoftSession(flow=FakeDeviceFlow())
    with pytest.raises(ms.NoProfileError):
        session.login_interactive()


def test_device_flow_declined():
    session = ms.MicrosoftSession(
        flow=FakeDeviceFlow(
            poll_result={"error": "authorization_declined", "error_description": "nope"}
        )
    )
    with pytest.raises(ms.AuthError, match="拒绝"):
        session.login_interactive()


def test_open_verification_page():
    opened = []
    monkey = ms.webbrowser
    original = monkey.open
    monkey.open = lambda uri: (opened.append(uri) or True)
    try:
        assert ms.open_verification_page({"verification_uri": "https://microsoft.com/link"}) is True
        assert opened == ["https://microsoft.com/link"]
        assert ms.open_verification_page({}) is False
    finally:
        monkey.open = original


def test_copy_user_code_windows(monkeypatch):
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(
        ms.subprocess,
        "run",
        lambda cmd, **kw: (calls.append((cmd, kw)) or SimpleNamespace(returncode=0)),
    )
    monkeypatch.setattr(ms.os, "name", "nt")
    assert ms.copy_user_code({"user_code": "ABCD1234"}) is True
    assert len(calls) == 1
    assert "ABCD1234" in calls[0][0][-1]
    assert calls[0][1].get("creationflags") is not None


def test_copy_user_code_sanitize_rejects_shell_chars(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("不应执行剪贴板命令")

    monkeypatch.setattr(ms.subprocess, "run", boom)
    assert ms.copy_user_code({"user_code": "bad;rm -rf"}) is False
    assert ms.copy_user_code({"user_code": ""}) is False


def test_login_interactive_reports_flow_callback():
    """#3：拿到设备码后回调 on_flow（GUI 用它显示倒计时）。"""
    session = ms.MicrosoftSession(
        flow=FakeDeviceFlow(poll_result={"error": "authorization_declined"})
    )
    seen = []

    with pytest.raises(ms.AuthError):
        session.login_interactive(progress=seen.append, on_flow=seen.append)
    flow = next(item for item in seen if isinstance(item, dict))
    assert flow["user_code"] == "ABCD1234"
    assert flow["expires_in"] == 900


@respx.mock
def test_ensure_session_valid_returns_same():
    account = _account()
    session = ms.MicrosoftSession(flow=FakeDeviceFlow())
    assert session.ensure_session(account) is account


@respx.mock
def test_ensure_session_refreshes_mc_with_valid_ms():
    _mock_chain_ok()
    account = _account(mc_exp=time.time() - 10)  # mc token 已过期，ms 仍有效
    session = ms.MicrosoftSession(flow=FakeDeviceFlow())
    updated = session.ensure_session(account)
    assert updated is not account
    assert updated.tokens is not None
    assert updated.tokens.mc_access_token == "mc-token"
    assert updated.tokens.mc_expires_at is not None
    assert updated.tokens.mc_expires_at > time.time()
    assert updated.tokens.ms_access_token == "ms-at"  # 未触发 ms 刷新
    assert updated.tokens.ms_refresh_token == "ms-rt"


@respx.mock
def test_ensure_session_refreshes_ms_then_chain():
    _mock_chain_ok()
    flow = FakeDeviceFlow()
    now = time.time()
    account = _account(ms_exp=now - 10, mc_exp=now - 10, refresh="old-rt")
    session = ms.MicrosoftSession(flow=flow)
    updated = session.ensure_session(account)
    assert flow.refresh_calls == 1
    assert updated.tokens is not None
    assert updated.tokens.ms_access_token == "ms-at"
    assert updated.tokens.mc_access_token == "mc-token"


def test_ensure_session_needs_login():
    session = ms.MicrosoftSession(flow=FakeDeviceFlow())
    no_tokens = _account()
    no_tokens.tokens = None
    with pytest.raises(ms.NeedsLoginError):
        session.ensure_session(no_tokens)
    no_refresh = _account(ms_exp=time.time() - 10, mc_exp=time.time() - 10, refresh=None)
    with pytest.raises(ms.NeedsLoginError):
        session.ensure_session(no_refresh)
