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

"""Update logic tests: release lookup, version comparison, asset choice, download checks and refusal."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from launcher import updates

API = updates.RELEASES_API
EXE_URL = "https://example.invalid/launcher.exe"


def _payload(tag: str = "v0.2.0", assets: list[dict] | None = None, body: str = "notes") -> dict:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/{updates.REPO}/releases/tag/{tag}",
        "body": body,
        "assets": assets
        if assets is not None
        else [
            {"name": "MinePick_Launcher.exe", "browser_download_url": EXE_URL, "size": 6},
            {"name": "Source_code.zip", "browser_download_url": "https://example.invalid/src.zip", "size": 9},
        ],
    }


def _release(size: int = 6, name: str = "MinePick_Launcher.exe") -> updates.ReleaseInfo:
    return updates.ReleaseInfo(
        version="0.2.0",
        tag="v0.2.0",
        page_url="https://example.invalid/release",
        notes="",
        exe_url=EXE_URL,
        exe_name=name,
        exe_size=size,
    )


# ---------- version handling ----------


def test_version_comparison() -> None:
    assert updates.is_newer("0.2.0", "0.1.5") is True
    assert updates.is_newer("v0.2.0", "0.1.5") is True
    assert updates.is_newer("0.1.10", "0.1.9") is True
    assert updates.is_newer("0.1.5", "0.2.0") is False  # a local build newer than the release
    assert updates.is_newer("0.2.0", "0.2.0") is False
    assert updates.is_newer("nonsense", "0.1.5") is False  # unparsable never looks newer
    assert updates.parse_version("v0.2.0") == updates.parse_version("0.2.0")
    assert updates.parse_version("") is None


def test_select_exe_asset_prefers_current_then_legacy_then_single() -> None:
    both = [
        {"name": "MinePick_UI_Trial.exe"},
        {"name": "MinePick_Launcher.exe"},
    ]
    assert updates.select_exe_asset(both)["name"] == "MinePick_Launcher.exe"
    legacy = [{"name": "MinePick_UI_Trial.exe"}, {"name": "Source_code.zip"}]
    assert updates.select_exe_asset(legacy)["name"] == "MinePick_UI_Trial.exe"
    renamed = [{"name": "MinePick.exe"}]
    assert updates.select_exe_asset(renamed)["name"] == "MinePick.exe"
    assert updates.select_exe_asset([{"name": "a.exe"}, {"name": "b.exe"}]) is None
    assert updates.select_exe_asset([]) is None


# ---------- release lookup ----------


@respx.mock
def test_fetch_latest_release() -> None:
    respx.get(API).mock(return_value=httpx.Response(200, json=_payload()))
    release = updates.fetch_latest_release(httpx.Client())
    assert release.version == "0.2.0"
    assert release.tag == "v0.2.0"
    assert release.exe_name == "MinePick_Launcher.exe"
    assert release.exe_size == 6
    assert release.page_url.endswith("/v0.2.0")


@respx.mock
def test_fetch_latest_release_failures() -> None:
    respx.get(API).mock(return_value=httpx.Response(404, json={}))
    with pytest.raises(updates.UpdateError) as http_error:
        updates.fetch_latest_release(httpx.Client())
    assert http_error.value.code == "http"

    respx.get(API).mock(return_value=httpx.Response(200, text="not json"))
    with pytest.raises(updates.UpdateError) as parse_error:
        updates.fetch_latest_release(httpx.Client())
    assert parse_error.value.code == "parse"

    respx.get(API).mock(return_value=httpx.Response(200, json=_payload(assets=[{"name": "x.zip"}])))
    with pytest.raises(updates.UpdateError) as asset_error:
        updates.fetch_latest_release(httpx.Client())
    assert asset_error.value.code == "no_asset"

    respx.get(API).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(updates.UpdateError) as net_error:
        updates.fetch_latest_release(httpx.Client())
    assert net_error.value.code == "network"


@respx.mock
def test_check_for_update_statuses() -> None:
    respx.get(API).mock(return_value=httpx.Response(200, json=_payload(tag="v0.3.0")))
    assert updates.check_for_update("0.2.0", httpx.Client()).status == "update_available"

    respx.get(API).mock(return_value=httpx.Response(200, json=_payload(tag="v0.2.0")))
    same = updates.check_for_update("0.2.0", httpx.Client())
    assert same.status == "up_to_date" and same.latest == "0.2.0"

    # a release older than what we run must never nag (0.2.0 is not out in the wild yet)
    respx.get(API).mock(return_value=httpx.Response(200, json=_payload(tag="v0.1.5")))
    assert updates.check_for_update("0.2.0", httpx.Client()).status == "up_to_date"

    respx.get(API).mock(side_effect=httpx.ConnectError("boom"))
    failed = updates.check_for_update("0.2.0", httpx.Client())
    assert failed.status == "failed" and failed.error == "network"


@respx.mock
def test_check_for_update_never_raises() -> None:
    respx.get(API).mock(side_effect=RuntimeError("unexpected"))
    result = updates.check_for_update("0.2.0", httpx.Client())
    assert result.status == "failed" and result.error == "network"


# ---------- download checks ----------


@respx.mock
def test_download_happy_path(ws_tmp, monkeypatch) -> None:
    monkeypatch.setattr(updates, "signature_is_valid", lambda _path: True)
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=b"MZ" + b"0" * 4))
    seen: list[tuple[int, int]] = []
    path = updates.download_release_exe(
        _release(), ws_tmp, client=httpx.Client(), on_progress=lambda d, t: seen.append((d, t))
    )
    assert path.read_bytes().startswith(b"MZ")
    assert seen and seen[-1][0] == 6
    assert not list(ws_tmp.glob("*.part"))


@respx.mock
def test_download_refuses_size_mismatch(ws_tmp) -> None:
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=b"MZ"))
    with pytest.raises(updates.UpdateError) as exc:
        updates.download_release_exe(_release(size=999), ws_tmp, client=httpx.Client())
    assert exc.value.code == "size"
    assert not list(ws_tmp.iterdir())  # nothing left behind


@respx.mock
def test_download_refuses_non_pe(ws_tmp) -> None:
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=b"not an exe"))
    with pytest.raises(updates.UpdateError) as exc:
        updates.download_release_exe(_release(size=10), ws_tmp, client=httpx.Client())
    assert exc.value.code == "signature"
    assert not list(ws_tmp.iterdir())


@respx.mock
def test_download_refuses_invalid_signature(ws_tmp, monkeypatch) -> None:
    monkeypatch.setattr(updates, "signature_is_valid", lambda _path: False)
    respx.get(EXE_URL).mock(return_value=httpx.Response(200, content=b"MZ" + b"0" * 4))
    with pytest.raises(updates.UpdateError) as exc:
        updates.download_release_exe(_release(), ws_tmp, client=httpx.Client())
    assert exc.value.code == "signature"
    assert not list(ws_tmp.iterdir())


@respx.mock
def test_download_reports_network_failure(ws_tmp) -> None:
    respx.get(EXE_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(updates.UpdateError) as exc:
        updates.download_release_exe(_release(), ws_tmp, client=httpx.Client())
    assert exc.value.code == "network"


def test_is_pe_file(ws_tmp) -> None:
    exe = ws_tmp / "a.exe"
    exe.write_bytes(b"MZ" + b"\x00" * 10)
    assert updates.is_pe_file(exe) is True
    exe.write_bytes(b"PK\x03\x04")
    assert updates.is_pe_file(exe) is False
    assert updates.is_pe_file(ws_tmp / "missing.exe") is False


def test_signature_policy_accepts_our_self_signed_build(monkeypatch) -> None:
    """The certificate is self-signed: an untrusted chain is fine, a foreign signer or tampering is not."""
    reply = {"stdout": ""}

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(_command, **_kwargs):
        return _Completed(reply["stdout"])

    monkeypatch.setattr(updates.subprocess, "run", fake_run)
    ours = "CN=WDNDXLTX, E=wdndxltx@gmail.com"
    for accepted in (f"Valid|{ours}", f"UnknownError|{ours}", f"NotTrusted|{ours}"):
        reply["stdout"] = accepted
        assert updates.signature_is_valid(Path("candidate.exe")) is True, accepted
    for rejected in (f"HashMismatch|{ours}", "NotSigned|", "Valid|CN=Evil Corp"):
        reply["stdout"] = rejected
        assert updates.signature_is_valid(Path("candidate.exe")) is False, rejected


# ---------- install helper ----------


def test_can_self_update_is_false_without_a_frozen_build() -> None:
    assert updates.can_self_update() is False  # pytest runs from source


def _restart_line_is_environment_clean(text: str) -> bool:
    """True only when the helper resets the PyInstaller environment before it restarts the build.

    Both halves matter: without the reset the restarted build is treated as a worker of the process
    that is exiting and reuses its ``_MEI`` directory, and a reset that came *after* the restart line
    would not reach the process at all. The guard is a function so the negative self-checks below can
    feed it the script this fix was added to.
    """
    reset = 'set "PYINSTALLER_RESET_ENVIRONMENT=1"'
    restart = 'start ""'
    if reset not in text or restart not in text:
        return False
    return text.index(reset) < text.index(restart)


def test_the_restart_line_resets_the_pyinstaller_environment(ws_tmp) -> None:
    """The one line the user's "the specified module could not be found" box turned on.

    PyInstaller 6.9 changed the bootloader's assumption: a process started from the same executable
    is a *worker* that may reuse the parent's unpacked files, unless
    ``PYINSTALLER_RESET_ENVIRONMENT=1`` tells it to be an independent instance ("the spawned
    subprocess would end up missing files", PyInstaller's "Implementing application restart"; the
    reset "forces the application to unpack itself again", "Environment Variables Used by Frozen
    Applications"). The parent bootloader deletes that directory as it exits, which is the Windows
    error box 0.3.1 and 0.4.0 showed.
    """
    new_exe = ws_tmp / "new.exe"
    new_exe.write_bytes(b"MZ")
    target = ws_tmp / "MinePick_Launcher.exe"
    target.write_bytes(b"MZ")
    text = updates.write_install_script(new_exe, target, restart=True).read_text(encoding="utf-8")
    reset = 'set "PYINSTALLER_RESET_ENVIRONMENT=1"'
    # Quoted, like every other set in this helper: unquoted, cmd folds the trailing space into the
    # value and the bootloader never sees the "1" it looks for.
    assert reset in text
    assert _restart_line_is_environment_clean(text) is True  # and before the line that starts it
    # Negative self-checks: the guard must reject the very script this fix was added to. Without them
    # a guard that passes for reasons of its own would keep looking healthy after the line is deleted.
    dropped = "\r\n".join(
        line for line in text.splitlines() if "PYINSTALLER_RESET_ENVIRONMENT" not in line
    )
    assert _restart_line_is_environment_clean(dropped) is False
    unquoted = text.replace(reset, "set PYINSTALLER_RESET_ENVIRONMENT=1")
    assert _restart_line_is_environment_clean(unquoted) is False


def test_write_install_script_swaps_and_restores(ws_tmp) -> None:
    new_exe = ws_tmp / "new.exe"
    new_exe.write_bytes(b"MZ")
    target = ws_tmp / "MinePick_Launcher.exe"
    target.write_bytes(b"MZ")
    script = updates.write_install_script(new_exe, target, restart=True)
    text = script.read_text(encoding="utf-8")
    assert str(target) in text and str(new_exe) in text
    assert 'tasklist' in text  # waits for this process to exit
    assert '.bak"' in text  # keeps a backup
    assert f'move /y "{target}.bak" "{target}"' in text  # and restores it when the move failed
    assert 'start ""' in text  # restart flag honoured
    assert _restart_line_is_environment_clean(text) is True  # and the environment is reset first
    assert '(goto) 2>nul & del /f /q "%~f0"' in text  # the reliable way for a batch to remove itself


def test_write_install_script_without_restart(ws_tmp) -> None:
    new_exe = ws_tmp / "new.exe"
    new_exe.write_bytes(b"MZ")
    target = ws_tmp / "app.exe"
    target.write_bytes(b"MZ")
    text = updates.write_install_script(new_exe, target, restart=False).read_text(encoding="utf-8")
    assert 'if "0"=="1" start' in text
    assert "goto swap" in text  # the wait loop is bounded and can always reach the swap
    assert "apply-update.log" in text  # a silent no-op must be impossible


def test_install_script_really_swaps_the_executable(ws_tmp) -> None:
    """Run the helper for real: it must swap the file, keep a backup and delete itself.

    Asserting the script's text is not enough. The helper was once started with DETACHED_PROCESS,
    which left it without a console: it wrote its first log line and died, so the update was staged
    and the launcher unchanged. Only actually running it proves an update installs.
    """
    import time

    target = ws_tmp / "app" / "MinePick_Launcher.exe"
    staged = ws_tmp / "data" / "updates" / "MinePick_Launcher.exe"
    target.parent.mkdir(parents=True, exist_ok=True)
    staged.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"OLD-BUILD")
    staged.write_bytes(b"NEW-BUILD")

    # wait_pid points at a PID that is not running, so the helper swaps immediately
    script = updates.write_install_script(staged, target, restart=False, wait_pid=999999)
    assert updates.launch_install_script(script) is True

    deadline = time.time() + 30
    while time.time() < deadline and script.exists():
        time.sleep(0.3)

    assert target.read_bytes() == b"NEW-BUILD"  # the swap happened
    assert Path(str(target) + ".bak").read_bytes() == b"OLD-BUILD"
    assert not staged.exists()
    assert not script.exists()  # the helper cleaned up after itself
    assert (script.parent / "apply-update.log").is_file()


def test_pending_roundtrip(ws_tmp, monkeypatch) -> None:
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    exe = ws_tmp / "staged.exe"
    exe.write_bytes(b"MZ")
    assert updates.load_pending() is None
    updates.save_pending(exe, "0.2.0")
    assert updates.load_pending() == (exe, "0.2.0")
    exe.unlink()
    assert updates.load_pending() is None  # a stale entry is ignored
    exe.write_bytes(b"MZ")
    updates.save_pending(exe, "0.2.0")
    updates.clear_pending()
    assert updates.load_pending() is None


# ---------- the restart itself (slow: freezes a real build with PyInstaller) ----------
#
# The text assertions above cannot see this defect: the restart line looked right in 0.3.1 and 0.4.0
# while every real update ended in a Windows "the specified module could not be found" box, because
# what goes wrong happens inside the PyInstaller bootloader of the *restarted* process. These tests
# therefore freeze tests/restart_probe.py and drive a real self-update through the production helper.
#
# They are opt-in because freezing takes about a minute, and they skip with a measured reason where
# the session cannot run a frozen build at all.

ROOT = Path(__file__).resolve().parents[1]
# Outside the checkout and outside tests/.work: this section builds EXEs and launches processes while
# the user may be running the rest of the suite - the same convention tests/test_smoke_exe.py uses.
SCRATCH = ROOT.parent / "tmp" / "update_restart"
PROBE = ROOT / "tests" / "restart_probe.py"
UPDATES_SOURCE = ROOT / "launcher" / "updates.py"  # the module the frozen probe bundles
PAYLOAD = "probe-payload-ok"
SLOW_ENV = "MINE_PICK_SLOW_TESTS"

CONFINED_REASON = (
    "confined session (restricting SIDs={restricted}): the onefile bootloader creates its _MEI "
    "directory with a fresh single-ACE DACL, the restricted token then fails the second access check, "
    "and the folder stays empty - measured here as \"[PYI-5628:ERROR] Failed to create parent "
    "directory structure.\" with TEMP redirected, \"Could not create temporary directory!\" otherwise, "
    "and an empty _MEI folder either way (tools/smoke_exe.py:94-113 measured the same wall). A "
    "windowed build reports that with a native Error box, so this test skips instead of putting one on "
    f"screen. Run it in an ordinary terminal: set {SLOW_ENV}=1 && python -m pytest "
    "tests/test_updates.py -k restart"
)


def _slow_skip_reason() -> str | None:
    """Why the restart tests cannot run here (None: they can)."""
    if os.name != "nt":
        return "the restart defect only exists on Windows"
    if os.environ.get(SLOW_ENV) != "1":
        return f"slow: set {SLOW_ENV}=1 to freeze a build with PyInstaller and restart it for real"
    if importlib.util.find_spec("PyInstaller") is None:
        return "PyInstaller is not installed"
    return None


SLOW_SKIP = _slow_skip_reason()


def _restricted_sid_count() -> int:
    """How many restricting SIDs this process's token carries (0: unreadable, or off Windows).

    A non-zero count is the signature of a confined session; the code mirrors
    ``tools/smoke_exe.py:541``. The onefile test needs it because the failure mode it guards against
    is a native message box, and refusing to launch is the only way to keep "no window, ever" true by
    construction. The other confinement failure - a low-integrity build with a medium-integrity TEMP -
    cannot happen here, because every build these tests run unpacks into a TEMP inside the scratch
    tree.
    """
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
    ]
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    token = wintypes.HANDLE()
    if not kernel32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        return 0  # TOKEN_QUERY
    try:
        restricted_sids = 11  # TokenRestrictedSids
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, restricted_sids, None, 0, ctypes.byref(size))
        if not size.value:
            return 0
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, restricted_sids, buffer, size.value, ctypes.byref(size)
        ):
            return 0
        return int.from_bytes(buffer[:4], "little")
    finally:
        kernel32.CloseHandle(token)


def _build_probe(kind: str) -> Path:
    """Freeze tests/restart_probe.py with PyInstaller (``kind``: onefile or onedir), and cache it.

    The digest covers the probe *and* the production module it bundles, because the code under test
    ends up inside the executable: editing either one rebuilds, and a second run of these tests does
    not pay for the freeze again.
    """
    digest = hashlib.sha256(PROBE.read_bytes() + UPDATES_SOURCE.read_bytes()).hexdigest()[:12]
    build = SCRATCH / "build" / f"{kind}-{digest}"
    dist = build / "dist"
    exe = dist / "restart_probe.exe" if kind == "onefile" else dist / "restart_probe" / "restart_probe.exe"
    if exe.is_file():
        return exe
    build.mkdir(parents=True, exist_ok=True)
    payload = build / "probe-payload.txt"
    payload.write_bytes(PAYLOAD.encode("ascii"))
    log = build / "pyinstaller.log"
    # --windowed, not --console: the helper starts the restarted build with `start`, and a console
    # build would open a console window on the user's desktop for as long as that build runs.
    command = [
        sys.executable, "-m", "PyInstaller", str(PROBE), f"--{kind}", "--windowed", "--name",
        "restart_probe", "--noconfirm", "--log-level", "WARN", "--paths", str(ROOT),
        "--distpath", str(dist), "--workpath", str(build / "work"), "--specpath", str(build),
        "--add-data", f"{payload};.",
    ]
    with log.open("wb") as sink:
        done = subprocess.run(command, stdout=sink, stderr=subprocess.STDOUT, timeout=900, check=False)
    assert done.returncode == 0 and exe.is_file(), (
        f"PyInstaller could not freeze the {kind} probe (exit {done.returncode}):\n"
        f"{log.read_text(encoding='utf-8', errors='replace')[-3000:]}"
    )
    return exe


def _records(rec: Path) -> dict:
    """What the two processes reported, plus the helper the frozen build generated for itself."""
    out: dict = {"script_bytes": b""}
    for key in ("parent", "child", "parent-launched", "error"):
        path = rec / f"{key}.json"
        out[key] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    generated = rec / "generated-apply-update.cmd"
    if generated.is_file():
        out["script_bytes"] = generated.read_bytes()  # the helper deletes the original
    return out


def _run_restart_flow(exe: Path, name: str, *, drop_reset: bool = False) -> dict:
    """Run the real sequence: frozen build -> our helper -> swap -> ``start`` -> restarted build.

    The waiting process is kept alive on purpose, and that is a deliberate trade. With it alive, a
    restarted build that reuses the old extraction directory has a *silent* failure mode (it runs,
    from the directory that is about to be deleted) instead of the crash, which makes the guard
    deterministic and keeps the native bootloader dialog - a dialog no environment variable can
    suppress, see tools/smoke_exe.py - out of the run entirely.
    """
    run = SCRATCH / "runs" / name
    shutil.rmtree(run, ignore_errors=True)
    bundle = run / "app"
    if (exe.parent / "_internal").is_dir():  # one-folder build: the executable needs its _internal
        shutil.copytree(exe.parent, bundle)
    else:
        bundle.mkdir(parents=True)
        shutil.copy2(exe, bundle / exe.name)
    target = bundle / exe.name
    staged = run / "updates" / exe.name
    staged.parent.mkdir(parents=True)
    shutil.copy2(target, staged)
    temp = run / "temp"  # a onefile build unpacks here, inside the scratch tree
    temp.mkdir()
    env = dict(os.environ)
    env.update(
        {
            "PROBE_RECORD_DIR": str(run / "rec"),
            "PROBE_STAGED": str(staged),
            "PROBE_ALIVE_SECONDS": "45",
            "TEMP": str(temp),
            "TMP": str(temp),
        }
    )
    if drop_reset:
        env["PROBE_DROP_RESET"] = "1"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    with open(os.devnull, "wb") as null:
        proc = subprocess.Popen(
            [str(target), "--parent"],
            env=env,
            cwd=str(run),
            stdin=subprocess.DEVNULL,
            stdout=null,
            stderr=null,
            creationflags=flags,
        )
    try:
        proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("the frozen stand-in never exited, so the restart never completed") from None
    result = {
        "run": run,
        "target": target,
        "staged": staged,
        "script": staged.parent / "apply-update.cmd",
        "records": _records(run / "rec"),
    }
    log = staged.parent / "apply-update.log"
    result["helper_log"] = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    return result


def _assert_the_helper_restarted_a_frozen_build(result: dict) -> dict:
    """The restart must have gone through the helper we generate and come back as a frozen build.

    Both kinds of build share this half: the old executable is really replaced, the helper cleans up
    after itself, and the process it started runs and reads the data file bundled next to it. Returns
    the restarted process's record.
    """
    records, run = result["records"], result["run"]
    assert records["parent"] is not None, f"the frozen stand-in never reported ({run})"
    launched = records["parent-launched"]
    assert launched and launched["started"] is True, (
        f"the helper never started: {launched} (helper log: {result['helper_log']!r})"
    )
    child = records["child"]
    assert child is not None, (
        "the helper swapped the build but nothing restarted. error record: "
        f"{records['error']!r}, helper log: {result['helper_log']!r}"
    )
    assert child["frozen"] is True and child["payload"] == PAYLOAD, (
        f"the restarted process is not a working frozen build: {child!r}"
    )
    assert Path(f"{result['target']}.bak").is_file(), "the helper kept no backup of the old build"
    assert not result["staged"].exists(), "the staged build is still there: nothing was swapped"
    assert not result["script"].exists(), "the helper did not delete itself"
    assert "swap finished" in result["helper_log"], f"no swap in the log: {result['helper_log']!r}"
    return child


def _assert_the_restarted_onefile_build_unpacked_its_own_files(result: dict) -> None:
    """The restarted onefile build must unpack its own files, not inherit the old extraction root.

    PyInstaller 6.9 and newer treat a process started from the same executable as a worker of the
    process that spawned it: it reuses the inherited ``_MEI`` directory instead of unpacking its own,
    and that directory is deleted while the old process exits, so the restarted launcher dies with
    ERROR_MOD_NOT_FOUND (126) - the user's "the specified module could not be found" box. This asserts
    the consequence of the reset line, not the line.
    """
    child = _assert_the_helper_restarted_a_frozen_build(result)
    parent = result["records"]["parent"]
    assert child["meipass"] != parent["meipass"], (
        "the restarted build reused the extraction directory of the process that was exiting "
        f"({child['meipass']!r}) instead of unpacking its own; with that directory deleted this is the "
        f"user's native \"cannot find the module\" box. helper log: {result['helper_log']!r}"
    )


@pytest.mark.skipif(SLOW_SKIP is not None, reason=SLOW_SKIP or "")
def test_a_restarted_frozen_build_comes_back_after_the_swap() -> None:
    """The restart half end to end, on a build a confined session can still run (one folder).

    A one-folder build unpacks nothing at run time, so PyInstaller never exports the private
    ``_PYI_APPLICATION_HOME_DIR`` for it - measured: a restarted one-folder process records the same
    environment with and without the reset line, because there is no extraction directory to reuse.
    This is therefore a regression gate for the *restart path* - the helper waits, swaps, keeps a
    backup, starts the new build and deletes itself - and it is **not** the gate for the reset line.
    That gate is ``test_a_restarted_onefile_build_unpacks_its_own_files`` below.
    """
    result = _run_restart_flow(_build_probe("onedir"), "onedir")
    _assert_the_helper_restarted_a_frozen_build(result)
    # The frozen build carries this repository's production code, so this reads the packaged version
    # of the same guard the fast tests check on the source.
    generated = result["records"]["script_bytes"].decode("oem", errors="replace")
    assert _restart_line_is_environment_clean(generated) is True


@pytest.mark.skipif(SLOW_SKIP is not None, reason=SLOW_SKIP or "")
def test_a_restarted_onefile_build_unpacks_its_own_files() -> None:
    """The defect itself: restart a real onefile build through our helper and see what it became.

    Asserting the script's text is not enough - the restart line looked right in 0.3.1 and 0.4.0 while
    every real update ended in that box. This freezes a onefile build, has it update itself through
    ``updates.write_install_script`` and ``updates.launch_install_script``, and checks the process
    that comes back. See ``CONFINED_REASON`` for why it cannot run inside a confined session.
    """
    restricted = _restricted_sid_count()
    if restricted:
        pytest.skip(CONFINED_REASON.format(restricted=restricted))
    result = _run_restart_flow(_build_probe("onefile"), "onefile")
    _assert_the_restarted_onefile_build_unpacked_its_own_files(result)


@pytest.mark.skipif(SLOW_SKIP is not None, reason=SLOW_SKIP or "")
def test_the_onefile_restart_guard_rejects_a_script_without_the_reset() -> None:
    """The built-in negative control: the same restart with that one line removed must go red.

    Without it, a guard that passes for reasons of its own would look healthy forever. The variant is
    the same script minus ``set "PYINSTALLER_RESET_ENVIRONMENT=1"`` - the pre-fix script - so deleting
    the line from ``launcher/updates.py`` later turns this test red instead of quietly disarming the
    test above. It runs by itself under the same opt-in switch.
    """
    restricted = _restricted_sid_count()
    if restricted:
        pytest.skip(CONFINED_REASON.format(restricted=restricted))
    dropped = _run_restart_flow(_build_probe("onefile"), "onefile-without-reset", drop_reset=True)
    assert b"PYINSTALLER_RESET_ENVIRONMENT" not in dropped["records"]["script_bytes"], (
        "the negative control did not remove the line, so its result would prove nothing"
    )
    with pytest.raises(AssertionError):
        _assert_the_restarted_onefile_build_unpacked_its_own_files(dropped)
