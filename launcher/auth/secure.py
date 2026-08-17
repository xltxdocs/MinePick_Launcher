"""令牌加密存储：cryptography Fernet + 用户密码（PBKDF2 派生密钥）。

密码来源优先级：进程内缓存（GUI 启动时交互输入）> 环境变量
MCLAUNCHER_TOKEN_PASSWORD > 交互式终端提示（CLI getpass，仅 tty）。

保险库文件 accounts.key（与 accounts.json 同目录）：
    {"version": 1, "salt": "<b64>", "verifier": "<b64>", "kdf": {...}}
salt 用于 PBKDF2 派生 Fernet 密钥；verifier 用于校验密码。
令牌密文格式：enc:v1:<base64(Fernet(token))>。
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import logging
import os
import sys
from pathlib import Path

from launcher import paths
from launcher.i18n import tr_core

VAULT_FILENAME = "accounts.key"
ENV_PASSWORD = "MCLAUNCHER_TOKEN_PASSWORD"
PBKDF2_ITERATIONS = 600_000
CIPHER_PREFIX = "enc:v1:"

_logger = logging.getLogger(__name__)
_password: str | None = None


class VaultError(Exception):
    """令牌保险库错误（消息面向用户）。"""


def _vault_path() -> Path:
    return paths.launcher_dir() / VAULT_FILENAME


def vault_exists() -> bool:
    return _vault_path().exists()


def _derive(password: str, salt: bytes) -> tuple[bytes, bytes]:
    """由密码 + 盐派生 (fernet_key, verifier)。"""
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给出清晰提示
        raise VaultError(tr_core("vault.dependency_missing")) from exc
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS
    )
    key = kdf.derive(password.encode("utf-8"))
    verifier = hashlib.sha256(b"mclauncher-vault-verifier" + key).digest()
    return base64.urlsafe_b64encode(key), verifier


def create_vault(password: str) -> Path:
    """新建保险库（覆盖旧的）并把密码缓存到内存。"""
    salt = os.urandom(16)
    _key, verifier = _derive(password, salt)
    vault_path = _vault_path()
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "kdf": {"algorithm": "PBKDF2HMAC-SHA256", "iterations": PBKDF2_ITERATIONS},
        "salt": base64.b64encode(salt).decode("ascii"),
        "verifier": base64.b64encode(verifier).decode("ascii"),
    }
    tmp = vault_path.with_name(vault_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(vault_path)
    set_password(password)
    return vault_path


def verify_password(password: str) -> bool:
    """校验密码是否与保险库一致（保险库不存在时 False）。"""
    vault_path = _vault_path()
    if not vault_path.exists():
        return False
    try:
        payload = json.loads(vault_path.read_text(encoding="utf-8"))
        salt = base64.b64decode(payload["salt"])
        verifier = base64.b64decode(payload["verifier"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        _logger.warning("保险库文件损坏: %s", vault_path)
        return False
    try:
        _key, expected = _derive(password, salt)
    except VaultError:
        return False
    return hmac.compare_digest(expected, verifier)


def set_password(password: str) -> None:
    """把密码缓存到进程内（GUI 启动时交互输入后调用）。"""
    global _password
    _password = password


def forget_password() -> None:
    global _password
    _password = None


def has_password() -> bool:
    return _password is not None


def unlock_vault(password: str | None = None, *, interactive: bool = False) -> bool:
    """解锁保险库：校验密码并缓存到内存。成功返回 True。

    interactive=True 时尝试 getpass 交互输入（仅 tty 生效）。
    环境变量密码错误时抛 VaultError。
    """
    candidate = password
    if candidate is None:
        candidate = os.environ.get(ENV_PASSWORD)
        if candidate is not None and not verify_password(candidate):
            raise VaultError(tr_core("vault.env_wrong_password"))
    if candidate is None and interactive:
        candidate = getpass.getpass("令牌加密密码: ")
    if candidate is None:
        return False
    if not verify_password(candidate):
        return False
    set_password(candidate)
    return True


def require_password(*, interactive: bool = True) -> str:
    """取可用密码：内存 > 环境变量 > 交互提示；不可用时抛 VaultError。"""
    global _password
    if _password is not None:
        return _password
    env = os.environ.get(ENV_PASSWORD)
    if env:
        if verify_password(env):
            _password = env
            return env
        raise VaultError(tr_core("vault.env_wrong_password"))
    if interactive and sys.stdin is not None and sys.stdin.isatty():
        candidate = getpass.getpass(tr_core("vault.password_prompt"))
        if verify_password(candidate):
            _password = candidate
            return candidate
        raise VaultError(tr_core("vault.wrong_password"))
    raise VaultError(tr_core("vault.password_required"))


def _fernet_key() -> bytes:
    vault_path = _vault_path()
    if not vault_path.exists():
        raise VaultError(tr_core("vault.no_vault"))
    try:
        payload = json.loads(vault_path.read_text(encoding="utf-8"))
        salt = base64.b64decode(payload["salt"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise VaultError(tr_core("vault.corrupt")) from exc
    key, _verifier = _derive(require_password(), salt)
    return key


def encrypt_token_blob(plaintext: str) -> str:
    """加密令牌 JSON 字符串 -> enc:v1:<b64>。"""
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover
        raise VaultError(tr_core("vault.dependency_missing")) from exc
    token = Fernet(_fernet_key()).encrypt(plaintext.encode("utf-8"))
    return CIPHER_PREFIX + base64.b64encode(token).decode("ascii")


def decrypt_token_blob(ciphertext: str) -> str:
    """解密 enc:v1:<b64> -> 明文。"""
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:  # pragma: no cover
        raise VaultError(tr_core("vault.dependency_missing")) from exc
    if not ciphertext or not ciphertext.startswith(CIPHER_PREFIX):
        raise VaultError(tr_core("vault.bad_format"))
    try:
        raw = Fernet(_fernet_key()).decrypt(
            base64.b64decode(ciphertext[len(CIPHER_PREFIX) :])
        )
    except InvalidToken as exc:
        raise VaultError(tr_core("vault.decrypt_failed")) from exc
    return raw.decode("utf-8")
