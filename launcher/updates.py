# SPDX-FileCopyrightText: 2026 WDNDXLTX
# SPDX-License-Identifier: GPL-3.0-only
#
# This file is part of MinePick Launcher.
#
# MinePick Launcher is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# MinePick Launcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MinePick Launcher. If not, see <https://www.gnu.org/licenses/>.

"""Update check and self-update: query the GitHub release, compare versions, stage and swap the EXE.

GitHub Releases is the only source. Everything here is synchronous and Qt-free, so the GUI can run it
on a worker thread and the tests can call it directly.

Failure policy (see the standard process document, [P19]): whenever the download or the swap cannot be
verified, nothing is installed and the caller is expected to offer the release page instead. A failed
update must never leave the user without a working launcher.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = "xltxdocs/MinePick_Launcher"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"

# The asset name changed with the 0.2.0 rename; releases before that still ship the old name.
EXE_ASSETS = ("MinePick_Launcher.exe", "MinePick_UI_Trial.exe")
GITHUB_ACCEPT = "application/vnd.github+json"

# Signature policy: the launcher's own certificate (see scripts/sign_exe.ps1). A self-signed
# certificate never chains to a trusted root on a user machine, so Windows reports UnknownError or
# NotTrusted there; those are accepted, while a missing signature, a hash mismatch or a foreign
# signer still blocks the update. (Spellings follow PowerShell's SignatureStatus values.)
EXPECTED_SIGNER = "CN=WDNDXLTX"
ACCEPTED_SIGNATURE_STATUSES = {"valid", "unknownerror", "nottrusted"}


class UpdateError(RuntimeError):
    """Update failure carrying an i18n key suffix: network / http / parse / no_asset / size / signature."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


@dataclass(frozen=True)
class ReleaseInfo:
    """The bits of a GitHub release this launcher cares about."""

    version: str  # tag without the leading "v", e.g. "0.2.0"
    tag: str
    page_url: str
    notes: str
    exe_url: str
    exe_name: str
    exe_size: int


@dataclass(frozen=True)
class UpdateCheck:
    """Result of a check: status is "up_to_date", "update_available" or "failed"."""

    status: str
    current: str
    latest: str = ""
    release: ReleaseInfo | None = None
    error: str = ""


def parse_version(text: str):
    """A comparable version for a tag like ``v0.2.0``; None when it cannot be parsed."""
    from packaging.version import InvalidVersion, Version

    cleaned = (text or "").strip().lstrip("vV")
    if not cleaned:
        return None
    try:
        return Version(cleaned)
    except InvalidVersion:
        return None


def is_newer(latest: str, current: str) -> bool:
    """Whether ``latest`` is strictly newer than ``current`` (unparsable versions never are)."""
    left, right = parse_version(latest), parse_version(current)
    if left is None or right is None:
        return False
    return left > right


def select_exe_asset(assets: list[dict]) -> dict | None:
    """Pick the asset holding the launcher EXE: current name, then legacy name, then a lone .exe."""
    by_name = {str(asset.get("name") or ""): asset for asset in assets}
    for candidate in EXE_ASSETS:
        if candidate in by_name:
            return by_name[candidate]
    exes = [a for a in assets if str(a.get("name") or "").lower().endswith(".exe")]
    return exes[0] if len(exes) == 1 else None


def fetch_latest_release(client=None) -> ReleaseInfo:
    """Latest published release; raises :class:`UpdateError` with an i18n key suffix on failure."""
    import httpx

    from launcher.meta.manifest import _new_client

    owns_client = client is None
    client = client or _new_client()
    try:
        response = client.get(RELEASES_API, headers={"Accept": GITHUB_ACCEPT})
    except httpx.HTTPError as exc:
        raise UpdateError("network", str(exc)) from exc
    finally:
        if owns_client:
            client.close()
    if response.status_code != 200:
        raise UpdateError("http", f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpdateError("parse", str(exc)) from exc
    if not isinstance(payload, dict):
        raise UpdateError("parse", "unexpected payload")

    tag = str(payload.get("tag_name") or "").strip()
    version = tag.lstrip("vV")
    if not version:
        raise UpdateError("parse", "release without tag_name")
    assets = [a for a in (payload.get("assets") or []) if isinstance(a, dict)]
    asset = select_exe_asset(assets)
    if asset is None:
        raise UpdateError("no_asset", "the release carries no launcher executable")
    return ReleaseInfo(
        version=version,
        tag=tag,
        page_url=str(payload.get("html_url") or RELEASES_PAGE),
        notes=str(payload.get("body") or ""),
        exe_url=str(asset.get("browser_download_url") or ""),
        exe_name=str(asset.get("name") or EXE_ASSETS[0]),
        exe_size=int(asset.get("size") or 0),
    )


def check_for_update(current: str | None = None, client=None) -> UpdateCheck:
    """Compare the running version with the latest release. Never raises."""
    from launcher import __version__

    running = current or __version__
    try:
        release = fetch_latest_release(client)
    except UpdateError as exc:
        return UpdateCheck(status="failed", current=running, error=exc.code)
    except Exception:  # noqa: BLE001 - a check must never take the GUI down
        return UpdateCheck(status="failed", current=running, error="network")
    status = "update_available" if is_newer(release.version, running) else "up_to_date"
    return UpdateCheck(status=status, current=running, latest=release.version, release=release)


def is_pe_file(path: Path) -> bool:
    """A Windows executable starts with the DOS magic ``MZ``."""
    try:
        with Path(path).open("rb") as handle:
            return handle.read(2) == b"MZ"
    except OSError:
        return False


def signature_is_valid(path: Path) -> bool:
    """Whether the file is signed by this project's certificate without being tampered with.

    The launcher ships a **self-signed** certificate, so on a normal machine the chain is untrusted
    and Windows reports ``UnknownError`` — that is expected and must not block an update. What must
    block one is a missing signature, a hash mismatch, or a signature by somebody else.
    """
    if os.name != "nt":
        return False
    command = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            f"$s = Get-AuthenticodeSignature -FilePath '{path}'; "
            '"$($s.Status)|$($s.SignerCertificate.Subject)"'
        ),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    status, _sep, subject = result.stdout.strip().partition("|")
    if status.strip().lower() not in ACCEPTED_SIGNATURE_STATUSES:
        return False
    return EXPECTED_SIGNER.lower() in subject.strip().lower()


def download_release_exe(release: ReleaseInfo, target_dir: Path, client=None, on_progress=None) -> Path:
    """Download the release EXE, verify size + Authenticode signature, and return the local path.

    The partial file is removed and :class:`UpdateError` raised as soon as a check fails, so a broken
    download can never be mistaken for a usable update.
    """
    from launcher.meta.manifest import _new_client

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / release.exe_name
    partial = target.with_name(target.name + ".part")
    owns_client = client is None
    client = client or _new_client()

    def _cleanup() -> None:
        partial.unlink(missing_ok=True)

    try:
        try:
            with client.stream("GET", release.exe_url) as response:
                if response.status_code != 200:
                    raise UpdateError("http", f"HTTP {response.status_code}")
                total = int(response.headers.get("Content-Length") or release.exe_size or 0)
                done = 0
                with partial.open("wb") as handle:
                    for chunk in response.iter_bytes(1 << 16):
                        handle.write(chunk)
                        done += len(chunk)
                        if on_progress is not None:
                            on_progress(done, total)
        except UpdateError:
            _cleanup()
            raise
        except Exception as exc:
            _cleanup()
            raise UpdateError("network", str(exc)) from exc

        actual_size = partial.stat().st_size if partial.is_file() else 0
        if release.exe_size and actual_size != release.exe_size:
            _cleanup()
            raise UpdateError("size", f"{actual_size} != {release.exe_size}")
        if not is_pe_file(partial):
            _cleanup()
            raise UpdateError("signature", "not a Windows executable")
        if os.name == "nt" and not signature_is_valid(partial):
            _cleanup()
            raise UpdateError("signature", "invalid Authenticode signature")
        target.unlink(missing_ok=True)
        partial.replace(target)
        return target
    finally:
        if owns_client:
            client.close()


def can_self_update() -> bool:
    """True only for a packaged build whose executable sits in a writable folder."""
    if not getattr(sys, "frozen", False):
        return False
    exe = Path(sys.executable)
    if not exe.is_file():
        return False
    probe = exe.with_name(f".update-probe-{os.getpid()}")
    try:
        probe.write_bytes(b"")
    except OSError:
        return False
    try:
        probe.unlink()
    except OSError:
        pass  # a leftover probe file is harmless: never report "not writable" just for that
    return True


def updates_dir() -> Path:
    """Where downloads are staged (inside the launcher data directory)."""
    from launcher import paths

    return paths.launcher_dir() / "updates"


def _console_encoding() -> str:
    """cmd.exe parses batch files in the OEM code page, so a non-ASCII path needs that encoding."""
    return "oem" if os.name == "nt" else "utf-8"


def write_install_script(new_exe: Path, target_exe: Path, restart: bool) -> Path:
    """Write the swap helper that replaces ``target_exe`` once this process has exited.

    The helper waits for this PID, keeps a ``.bak`` of the old file and puts it back when the move
    failed, so the worst case is "nothing changed" rather than "no launcher".
    """
    new_exe, target_exe = Path(new_exe), Path(target_exe)
    script = new_exe.parent / "apply-update.cmd"
    lines = [
        "@echo off",
        "setlocal",
        f'set "PID={os.getpid()}"',
        ":wait",
        'tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul',
        "if not errorlevel 1 (",
        "  ping -n 2 127.0.0.1 >nul",
        "  goto wait",
        ")",
        f'move /y "{target_exe}" "{target_exe}.bak" >nul',
        f'move /y "{new_exe}" "{target_exe}" >nul',
        f'if not exist "{target_exe}" move /y "{target_exe}.bak" "{target_exe}" >nul',
        f'if "{int(bool(restart))}"=="1" start "" "{target_exe}"',
        'del "%~f0"',
    ]
    script.write_bytes(("\r\n".join(lines) + "\r\n").encode(_console_encoding(), errors="replace"))
    return script


def launch_install_script(script: Path) -> bool:
    """Run the swap helper detached so it outlives this process. Returns whether it started."""
    if os.name != "nt":
        return False
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(
            ["cmd", "/c", str(script)],
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def pending_file() -> Path:
    return updates_dir() / "pending.json"


def save_pending(exe: Path, version: str) -> None:
    """Remember a downloaded update so a later session (or exit) can install it."""
    path = pending_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"exe": str(exe), "version": version}), encoding="utf-8")


def load_pending() -> tuple[Path, str] | None:
    """The staged update, if it is still on disk."""
    path = pending_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):  # valid JSON that is not an object: treat as absent
        return None
    exe = Path(str(payload.get("exe") or ""))
    if not exe.is_file():
        return None
    return exe, str(payload.get("version") or "")


def clear_pending() -> None:
    pending_file().unlink(missing_ok=True)


def cleanup_backups(target_exe: Path) -> None:
    """Best effort: drop the ``.bak`` left next to the executable by a finished update."""
    backup = Path(str(target_exe) + ".bak")
    try:
        backup.unlink(missing_ok=True)
    except OSError:
        pass
