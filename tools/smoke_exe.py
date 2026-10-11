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

"""Smoke-test a *packaged* EXE headlessly: it must start, prove it came up, and leave on its own.

USE IT LIKE THIS (repo root, the interpreter the GUI runs on):

    D:\\dsh-workspace\\minecraft-launcher\\.venv\\Scripts\\python.exe tools\\smoke_exe.py

    D:\\dsh-workspace\\minecraft-launcher\\.venv\\Scripts\\python.exe tools\\smoke_exe.py ^
        --exe dist\\MinePick_Launcher.exe --timeout 120

Exit codes: ``0`` PASS, ``1`` FAIL, ``2`` the rig itself could not run (bad arguments / unsafe paths).
``--expect-fail-demo`` inverts the verdict: a deliberate defect must make the smoke FAIL, otherwise
the command fails - that is the negative control for this instrument.

WHY A PACKAGED EXE CANNOT SIMPLY BE LAUNCHED HERE (measured, not assumed)
------------------------------------------------------------------------
``dist\\MinePick_Launcher.exe`` is a **PyInstaller --onefile** build, and this agent's process runs at
**Low** integrity (``whoami /groups`` -> ``Mandatory Label\\Low Mandatory Level``, S-1-16-4096). The
EXE inherits that label, so two ordinary writes are refused:

1. the bootloader's unpack step, which goes to ``%TEMP%`` - Medium integrity - is denied, and the
   windowed bootloader reports it with a native ``Error`` message box (a Win32 dialog, *not* a Qt
   window, so ``QT_QPA_PLATFORM`` cannot suppress it);
2. the application's own data directory, which for a development run is ``%APPDATA%`` /
   ``%LOCALAPPDATA%`` (platformdirs) - also Medium - is denied.

Copying the EXE somewhere writable does not help: ``Releases\\`` is Medium, so a Low process cannot
write there either. The way through - and the reason this rig exists - is to **redirect every write
the EXE performs into a Low-writable directory, through environment variables**:

==============================  =================================================  ==========================
variable                        what it moves                                      set to
==============================  =================================================  ==========================
``TEMP`` / ``TMP``              the onefile unpack root (``_MEIxxxxxx``)            ``--temp-dir``
``MCLAUNCHER_DATA_DIR``         the launcher data dir (config / accounts / logs)    ``--data-dir``
``QT_QPA_PLATFORM=offscreen``   the Qt platform plugin: **no window is ever made**  (hard requirement)
``MCLAUNCHER_GUI_AUTOQUIT_MS``  a self-quit timer, so the EXE leaves *on its own*   ``--autoquit-ms``
==============================  =================================================  ==========================

``MCLAUNCHER_DATA_DIR`` is the launcher's documented override, read in ``launcher/paths.py:52``
(constant ``ENV_LAUNCHER_DIR`` at ``launcher/paths.py:45``) ahead of portable mode and of the
platformdirs default. ``MCLAUNCHER_GUI_AUTOQUIT_MS`` is the application's own headless hook
(``gui/main.py:145`` and ``gui/main.py:156``): it suppresses the first-run wizard and starts a
``QTimer`` that calls ``app.quit()``, so the EXE can be asked to end *cleanly* instead of being
killed. Killing is still available (``--exit-mode terminate``) and is reported as what it is: a
forced end, **not** a clean exit, and no evidence about the event loop.

WHAT COUNTS AS EVIDENCE (no ``sleep``-and-hope)
-----------------------------------------------
Readiness is polled, never guessed:

* ``<data-dir>/logs/launcher.log`` - ``configure_logging()`` is the first statement of
  ``gui.main.main()`` (``gui/main.py:125``), so the file proves the bootloader unpacked, the frozen
  interpreter booted and ``main()`` was entered;
* ``<data-dir>/config.json`` - written by ``initialize_language()`` inside ``create_app()``
  (``gui/main.py:100`` -> ``launcher/config.py:289``), so it proves the config layer ran;
* a ``_MEIxxxxxx`` folder under the temp dir - sampled **while the EXE is alive**, because a clean
  onefile exit deletes it again (``launcher/paths.py:61`` documents the leftovers a *killed* run
  leaves behind);
* a **zero** count of visible top-level windows owned by the process, read with ``EnumWindows`` -
  the offscreen plugin should make this structurally impossible, and that is exactly why it is
  measured rather than assumed.

The strongest signal is kept as its own verdict instead of being folded into readiness: with
``MCLAUNCHER_GUI_AUTOQUIT_MS`` set, the timer is registered *after* ``MainWindow()`` and
``window.show()`` (``gui/main.py:148``-``160``), so an exit code of ``0`` reached without us killing
anything proves the process ran to ``app.exec()`` and unwound. A startup that hung in initialisation
cannot produce it - which is the failure this test exists to catch.

A --onefile EXE is two processes
--------------------------------
PyInstaller re-executes the same binary: the process we launch is the bootloader and the application
is its child, so terminating only what we hold would leak the application. The child is therefore put
in a Windows **job object** with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``, assigned right after
``Popen`` - comfortably ahead of the multi-second unpack that precedes the child's creation - and the
handle is the last thing released, on every exit path including this script's own failure.

WHAT THIS RIG MEASURED HERE, AND WHY THE VERDICT IS *FAIL* (2026-10-11)
----------------------------------------------------------------------
Redirecting ``TEMP`` is necessary but **not sufficient**: ``dist\\MinePick_Launcher.exe`` still fails
to unpack in this sandbox, and the run below reports that failure rather than hiding it. Measured with
the launch described above:

* the bootloader creates its ``_MEIxxxxxx`` folder at ``+0.6s`` and **nothing is ever written into
  it** - zero entries, sampled for 120 s, and again for 28 s in a second run with the same result;
* the process then stays alive indefinitely (it had to be terminated at the timeout) and shows a
  **visible top-level window titled ``Error``** - the Win32 message box the bootloader uses to report
  a fatal unpack error, i.e. exactly the failure the ``TEMP`` redirect was supposed to prevent;
* ``<data-dir>`` stays completely empty, because the application is never reached at all;
* the cause is an access-control mismatch on that folder, not a path problem. The bootloader creates
  ``_MEIxxxxxx`` with its own single-ACE DACL (``<user>:(F)``, inheritance replaced), while every
  directory this sandbox provisions carries an extra grant for the confinement SID
  (``S-1-4-881433480-240957246:(I)(OI)(CI)(W,D,DC)``). Measured: writing a file into the
  bootloader's own ``_MEI`` folder from the confined process returns ``Permission denied``, while the
  same write into a sandbox-provisioned scratch directory succeeds. The bootloader is confined too,
  so it cannot write into the folder it just created - which is why the folder stays empty and the
  dialog appears.

Two consequences are built into this script rather than left to the reader:

* **``visible_windows_zero`` is sampled on every poll, and a single visible window ends the run
  immediately** (the tree is killed at the next poll, ``ended early: a visible window appeared``).
  A native message box is the one window ``QT_QPA_PLATFORM=offscreen`` cannot suppress, so a poll
  interval is the longest it is allowed to exist.
* **``--stall-timeout`` ends a run whose extraction folder never fills**, so a broken unpack costs
  seconds instead of the whole ``--timeout``.

THE PRE-LAUNCH REFUSAL (the strongest of the three, because nothing starts at all)
----------------------------------------------------------------------------------
Waiting for the dialog and then killing it is the second-best answer. The first is to never launch,
and that is now the default: ``confinement_defects()`` reads two facts before ``Popen`` and refuses
with exit code 2 when **both** hold -

* the target's mandatory label is **low**: ``dist\\MinePick_Launcher.exe`` reads
  ``S:AI(ML;ID;NW;;;LW)`` - the low label it inherits from the workspace tree. Measured contrast:
  ``Releases\\MinePick_Launcher.exe`` reads ``S:AI(ML;;NW;;;ME)``, medium, because a medium process
  wrote that copy;
* this process's token carries **restricting SIDs** (measured here: 4, with the token itself at
  ``S-1-16-4096``). ``whoami /all`` does not print that list, so it is read with
  ``GetTokenInformation(TokenRestrictedSids)`` rather than inferred. That second access check is
  exactly what the bootloader's re-written ``_MEI`` DACL fails.

Nothing is launched, so nothing can appear on screen; the refusal names the measured values and the
way forward, and ``--ignore-integrity-preflight`` is the deliberate, loudly-labelled override. A
medium-integrity copy, or any unconfined session, does not trip it - so this script stays useful
against ``Releases\\`` once the EXE is copied there, which is the case it is meant to serve.

RESIDUAL RISK, STATED PLAINLY
-----------------------------
The refusal above covers the one failure mode that was measured here; it is a guard, not a proof. For
any *other* reason a launch fails at the bootloader, sampling on every poll still bounds a native
dialog to about one ``--poll`` (0.25 s) rather than making it impossible. Removing even that needs the
child started on a private Win32 desktop (``CreateDesktopW`` plus ``STARTUPINFO.lpDesktop``, which
means raw ``CreateProcessW``, because ``subprocess`` cannot set ``lpDesktop``). That is deliberately
not done: it would replace the whole process-launching path with hand-written ``ctypes`` for a rig
whose measured problem is already refused up front. Treat "no window, ever" as *bounded*, and treat
the refused combination as *impossible*.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
# The workspace scratch root: a sibling of the checkout. D:\dsh-workspace\tmp is Low-writable
# (measured); the default TEMP and the platformdirs data directory are not.
WORKSPACE_TMP = REPO.parent / "tmp"
DEFAULT_TEMP_DIR = WORKSPACE_TMP / "smoke_tmp"
DEFAULT_DATA_DIR = WORKSPACE_TMP / "smoke_data"
DEFAULT_EXE = REPO / "dist" / "MinePick_Launcher.exe"

ENV_DATA_DIR = "MCLAUNCHER_DATA_DIR"  # launcher/paths.py:45
ENV_AUTOQUIT = "MCLAUNCHER_GUI_AUTOQUIT_MS"  # gui/main.py:145,156
ENV_PLATFORM = "QT_QPA_PLATFORM"
PLATFORM_VALUE = "offscreen"
ENV_TEMP = ("TEMP", "TMP")

# Startup evidence, in the order the application produces it.
EVIDENCE_ORDER = (Path("logs") / "launcher.log", Path("config.json"))

STARTUP_TIMEOUT_S = 60.0  # --timeout: the unpack alone is a 68 MB onefile payload
EXIT_TIMEOUT_S = 30.0  # --exit-timeout: how long the EXE gets to leave on its own
POLL_INTERVAL_S = 0.25
STALL_TIMEOUT_S = 15.0  # 0 disables; a real unpack starts filling its folder within seconds
AUTOQUIT_MS = 3000
FORCED_WAIT_S = 20.0  # after a job-object termination, how long the handle may take to settle

DEMO_CHOICES = ("missing-exe", "bad-data-dir", "no-offscreen-env")

STDOUT_FILE = WORKSPACE_TMP / "smoke_child_stdout.txt"
STDERR_FILE = WORKSPACE_TMP / "smoke_child_stderr.txt"

EPILOG_TEXT = (
    "exit codes: 0 = PASS, 1 = FAIL, 2 = the rig could not run (bad arguments, unsafe paths, or the "
    "pre-launch integrity refusal below). --expect-fail-demo inverts the verdict: it applies a "
    "deliberate defect and requires the smoke to FAIL, so a rig that cannot fail cannot silently "
    "pass.\n\n"
    "pre-launch integrity refusal: when the target's mandatory label is low AND this process runs "
    "under a restricted token (both are measured - see mandatory_label and restricted_sid_count), "
    "the onefile bootloader cannot write the _MEI directory it creates, so the run can only end in "
    "an empty folder, a native Win32 Error message box and a process that never exits. That "
    "combination is refused with exit code 2 before anything is launched; "
    "--ignore-integrity-preflight overrides the refusal.\n\n"
    "the same script stays useful elsewhere: a medium-integrity copy (for example Releases\\ after "
    "the EXE is copied there) does not trip the preflight, and neither does an unconfined session."
)


class SmokeError(RuntimeError):
    """The rig cannot run at all (exit code 2), as opposed to the EXE failing (exit code 1)."""


@dataclass
class Scratch:
    """The two Low-writable directories the child is redirected into, plus how the wipe went."""

    temp_dir: Path
    data_dir: Path
    removed: tuple[int, int] = (0, 0)
    lingering: tuple[list[str], list[str]] = (field(default_factory=list), field(default_factory=list))


# --------------------------------------------------------------------------------------
# Windows helpers (each degrades to None / a no-op off Windows)
# --------------------------------------------------------------------------------------
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100


def _create_kill_on_close_job() -> int:
    """A job object whose handle close terminates every process still inside it."""
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        wintypes.HANDLE(handle),
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    )
    if not ok:
        error = ctypes.get_last_error()
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        raise OSError(error, "SetInformationJobObject failed")
    return int(handle)


class ProcessTree:
    """Own a launched EXE *and everything it spawns*, so no stray process outlives this script.

    A PyInstaller --onefile EXE is two processes: the bootloader we hold a handle to, and the
    application it re-executes. ``Popen.terminate()`` would reach only the first. The job object
    covers both, and closing its handle kills whatever is left even if this script dies first.
    """

    def __init__(self) -> None:
        self.handle: int | None = None
        self.note = "job object not created"
        if os.name != "nt":
            self.note = "not Windows: falling back to terminate()"
            return
        try:
            self.handle = _create_kill_on_close_job()
            self.note = "job object created (KILL_ON_JOB_CLOSE)"
        except OSError as exc:  # pragma: no cover - environment dependent
            self.handle = None
            self.note = f"job object unavailable ({exc}); falling back to terminate()"

    def assign(self, pid: int) -> str:
        """Put ``pid`` - and, later, its children - inside the job. Returns a note for the report."""
        if self.handle is None or os.name != "nt":
            return self.note
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        process = kernel32.OpenProcess(_PROCESS_TERMINATE | _PROCESS_SET_QUOTA, False, pid)
        if not process:
            self.note += "; OpenProcess failed, the tree is not owned"
            return self.note
        try:
            if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(self.handle), process):
                self.note += "; AssignProcessToJobObject refused, the tree is not owned"
        finally:
            kernel32.CloseHandle(process)
        return self.note

    def terminate(self) -> bool:
        """Kill the whole tree at once. True when the job object did it."""
        if self.handle is None or os.name != "nt":
            return False
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        return bool(kernel32.TerminateJobObject(wintypes.HANDLE(self.handle), 1))

    def close(self) -> None:
        if self.handle is None or os.name != "nt":
            return
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(wintypes.HANDLE(self.handle))
        self.handle = None


def visible_windows(pid: int) -> list[str] | None:
    """Titles of the *visible* top-level windows ``pid`` owns right now (None off Windows).

    The offscreen Qt platform plugin makes this structurally empty; measuring it keeps that a fact
    about the run instead of a claim about the environment. It is also the only guard that catches a
    window the Qt platform plugin never had a say in - the onefile bootloader reports a fatal error
    with a **native Win32 message box**, which no Qt variable can suppress.
    """
    if os.name != "nt":
        return None
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    titles: list[str] = []

    def _visit(hwnd: int, _param: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(wintypes.HWND(hwnd)):
            text = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(wintypes.HWND(hwnd), text, 512)
            titles.append(text.value or "<untitled>")
        return True

    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_visit)
    user32.EnumWindows(callback, 0)
    return sorted(titles)


# --------------------------------------------------------------------------------------
# pre-launch refusal: a low-integrity EXE cannot start inside a confined session
# --------------------------------------------------------------------------------------
_SE_FILE_OBJECT = 1
_LABEL_SECURITY_INFORMATION = 0x00000010
_SDDL_REVISION_1 = 1
_TOKEN_QUERY = 0x0008
_TOKEN_INTEGRITY_LEVEL = 25
_TOKEN_RESTRICTED_SIDS = 11

# The mandatory label as SDDL names it: "S:AI(ML;ID;NW;;;LW)" is low, "(ML;;NW;;;ME)" is medium.
INTEGRITY_CODES = {"UN": "untrusted", "LW": "low", "ME": "medium", "HI": "high", "SI": "system"}
_LABEL_PATTERN = re.compile(r"\(ML;[^)]*;;;([A-Z]{2})\)")
# S-1-16-* is the integrity SID family; its last sub-authority is the level.
INTEGRITY_RIDS = {0: "untrusted", 0x1000: "low", 0x2000: "medium", 0x3000: "high", 0x4000: "system"}

PREFLIGHT_GUIDANCE = (
    "low-integrity EXE in a sandboxed session: the PyInstaller bootloader cannot write its own "
    "_MEI directory; smoke a medium-integrity copy instead (e.g. Releases\\ after the user copies it)"
)


def _sddl_of(path: Path, info: int) -> str | None:
    """One component of a filesystem object's security descriptor, as SDDL (None: unreadable)."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    remote = ctypes.POINTER(ctypes.c_void_p)
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
        remote, remote, remote, remote, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    descriptor = ctypes.c_void_p()
    if advapi32.GetNamedSecurityInfoW(
        str(path), _SE_FILE_OBJECT, info, None, None, None, None, ctypes.byref(descriptor)
    ):
        return None
    try:
        text = wintypes.LPWSTR()
        length = wintypes.DWORD()
        if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, _SDDL_REVISION_1, info, ctypes.byref(text), ctypes.byref(length)
        ):
            return None
        try:
            return text.value or ""
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.LocalFree(descriptor)


def mandatory_label(path: Path) -> str | None:
    """Integrity level the filesystem records for ``path`` (None: no label, unreadable, off Windows).

    Measured in this workspace: ``dist\\MinePick_Launcher.exe`` reads ``S:AI(ML;ID;NW;;;LW)`` (low, the
    label it inherits from the workspace tree) while ``Releases\\MinePick_Launcher.exe`` reads
    ``S:AI(ML;;NW;;;ME)`` (medium, set when that copy was written).
    """
    sddl = _sddl_of(path, _LABEL_SECURITY_INFORMATION)
    if not sddl:
        return None
    match = _LABEL_PATTERN.search(sddl)
    return INTEGRITY_CODES.get(match.group(1)) if match else None


def _token_information(info_class: int) -> ctypes.Array | None:
    """The raw token information block, or None when it cannot be read.

    The *buffer* is returned rather than its bytes on purpose: a TOKEN_MANDATORY_LABEL is a pointer
    to a SID that lives inside this allocation, so copying the bytes out and freeing the buffer would
    leave a dangling SID - which is exactly what ConvertSidToStringSidW reports as
    ERROR_INVALID_SID (1337).
    """
    if os.name != "nt":
        return None
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
    if not kernel32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        return None
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, info_class, None, 0, ctypes.byref(size))
        if not size.value:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, info_class, buffer, size.value, ctypes.byref(size)
        ):
            return None
        return buffer
    finally:
        kernel32.CloseHandle(token)


def process_integrity() -> str | None:
    """This process's own integrity level (None off Windows / unreadable)."""
    if os.name != "nt":
        return None
    from ctypes import wintypes

    class _SidAndAttributes(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class _TokenMandatoryLabel(ctypes.Structure):
        _fields_ = [("Label", _SidAndAttributes)]

    buffer = _token_information(_TOKEN_INTEGRITY_LEVEL)
    if buffer is None or len(buffer) < ctypes.sizeof(_TokenMandatoryLabel):
        return None
    label = _TokenMandatoryLabel.from_buffer_copy(buffer)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    text = wintypes.LPWSTR()
    if not advapi32.ConvertSidToStringSidW(label.Label.Sid, ctypes.byref(text)):
        return None
    try:
        # ConvertSidToStringSidW prints S-1-16-<decimal>, so the last field parses as decimal even
        # though the integrity RIDs are conventionally quoted in hex (0x1000 low, 0x2000 medium).
        return INTEGRITY_RIDS.get(int((text.value or "").rsplit("-", 1)[-1], 10))
    except ValueError:
        return None


def restricted_sid_count() -> int | None:
    """How many restricting SIDs this token carries (None off Windows / unreadable).

    A non-zero count is the sandbox's own signature: the confined token must satisfy *two* access
    checks, its normal SIDs and this list. A directory the bootloader re-creates with a fresh
    single-ACE DACL satisfies only the first, which is why its writes are refused.
    """
    buffer = _token_information(_TOKEN_RESTRICTED_SIDS)
    if buffer is None or len(buffer) < 4:
        return None
    return int.from_bytes(buffer[:4], "little")


def confinement_defects(command: list[str]) -> list[str]:
    """Why launching ``command`` here cannot work, and would put a native dialog on screen.

    The rule, both halves measured rather than assumed: the target's mandatory label is **low** and
    this process runs under a **restricted** token. A low-integrity onefile EXE then gets a low
    ``_MEI`` directory whose DACL the bootloader replaces, so the restricting SIDs stop matching and
    the bootloader - itself confined - cannot write into the folder it just created. The run can only
    end in an empty folder, a native ``Error`` message box, and a process that never exits.

    Refusing *before* the launch is the point: it turns "remember not to run that" into a property of
    this script. ``--ignore-integrity-preflight`` is the deliberate, loudly-labelled way past it.
    """
    if os.name != "nt":
        return []
    target = Path(shutil.which(command[0]) or command[0])
    label = mandatory_label(target)
    if label != "low":
        return []
    restricted = restricted_sid_count()
    if not restricted:
        return []
    return [
        (
            f"{PREFLIGHT_GUIDANCE} [measured: {target} label={label}, process integrity="
            f"{process_integrity()}, restricting SIDs={restricted}]"
        )
    ]


# --------------------------------------------------------------------------------------
# command line and scratch directories
# --------------------------------------------------------------------------------------
def split_command(text: str) -> list[str]:
    """Split a ``--command`` string, keeping Windows path backslashes intact.

    ``shlex`` in POSIX mode eats backslashes, which would silently mangle ``C:\\...``; non-POSIX mode
    keeps them but leaves the surrounding quotes on, so those are stripped here.
    """
    parts = shlex.split(text, posix=False)
    out = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        out.append(part)
    if not out:
        raise SmokeError("--command is empty")
    return out


def resolve_command(args: argparse.Namespace) -> list[str]:
    if args.command:
        return split_command(args.command)
    return [str(args.exe), *args.extra_args]


def assert_safe_to_wipe(path: Path) -> Path:
    """Never let ``--temp-dir`` / ``--data-dir`` point a recursive delete at something precious."""
    resolved = path.resolve()
    if resolved.parent == resolved:
        raise SmokeError(f"refusing to wipe a filesystem root: {resolved}")
    if len(resolved.parts) < 3:
        raise SmokeError(f"refusing to wipe a top-level directory: {resolved}")
    if resolved == REPO or resolved in REPO.parents:
        raise SmokeError(f"refusing to wipe the checkout or one of its parents: {resolved}")
    return resolved


def reset_dir(path: Path) -> tuple[int, list[str]]:
    """Create ``path``, or empty it when it exists. Returns (entries removed, entries left behind).

    Deliberately not ``mkdtemp`` and deliberately not a random suffix: this sandbox locks writes
    inside random-suffix directories (the downloader's own note records it), and a stable name is
    also what makes a failed run inspectable afterwards.

    A child that cannot be removed is reported instead of raising. Directories this workspace's
    sandbox has tagged reject a delete from a Low-integrity process, and one such leftover - a
    ``_MEI*`` folder an earlier, differently-tagged run abandoned - must not stop a new run: the
    extraction evidence counts only folders that appear *after* the launch for exactly this reason.
    """
    resolved = assert_safe_to_wipe(path)
    if not resolved.exists():
        resolved.mkdir(parents=True)
        return 0, []
    if not resolved.is_dir():
        raise SmokeError(f"{resolved} exists and is not a directory")
    removed = 0
    lingering: list[str] = []
    for child in sorted(resolved.iterdir()):
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed += 1
        except OSError:
            lingering.append(child.name)
    return removed, lingering


# --------------------------------------------------------------------------------------
# child environment
# --------------------------------------------------------------------------------------
def child_environment(args: argparse.Namespace, temp_dir: Path, data_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in ENV_TEMP:
        env[name] = str(temp_dir)
    env[ENV_DATA_DIR] = str(data_dir)
    env[ENV_PLATFORM] = PLATFORM_VALUE
    if args.exit_mode == "autoquit":
        env[ENV_AUTOQUIT] = str(args.autoquit_ms)
    else:
        env.pop(ENV_AUTOQUIT, None)
    return env


def environment_defects(
    env: dict[str, str], temp_dir: Path, data_dir: Path, exit_mode: str
) -> list[str]:
    """Reasons this child environment is not the one the smoke test claims to exercise.

    Checked *before* anything is launched, because two of these failure modes are reported by the
    windowed bootloader with a native message box - a dialog no environment variable can suppress.
    Refusing to start is the only way to keep "no window, ever" true by construction rather than by
    hope.
    """
    defects = []
    if env.get(ENV_PLATFORM) != PLATFORM_VALUE:
        defects.append(
            f"{ENV_PLATFORM}={env.get(ENV_PLATFORM)!r}, expected {PLATFORM_VALUE!r}: a real platform "
            f"plugin would put a window on the user's desktop"
        )
    for name in ENV_TEMP:
        if env.get(name) != str(temp_dir):
            defects.append(
                f"{name}={env.get(name)!r}, expected {str(temp_dir)!r}: the onefile unpack would go "
                f"to a Medium-integrity location and be refused, and the bootloader reports that "
                f"with a native message box"
            )
    if env.get(ENV_DATA_DIR) != str(data_dir):
        defects.append(
            f"{ENV_DATA_DIR}={env.get(ENV_DATA_DIR)!r}, expected {str(data_dir)!r}: startup evidence "
            f"would be looked for in a directory the EXE never writes"
        )
    if exit_mode == "autoquit":
        raw = env.get(ENV_AUTOQUIT)
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            defects.append(
                f"{ENV_AUTOQUIT}={raw!r}: no positive self-quit timer, so the EXE would never leave "
                f"on its own and a clean exit could not be observed"
            )
    return defects


# --------------------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------------------
@dataclass
class Observation:
    """Everything the run actually saw, with the timestamps that make it evidence."""

    started: float = 0.0
    ready_at: float | None = None
    ready_files: list[str] = field(default_factory=list)
    extraction_dirs: list[str] = field(default_factory=list)
    extraction_seen_at: float | None = None
    extraction_nonempty: bool = False
    extraction_entries: int = 0
    extraction_filled_at: float | None = None
    windows_seen_max: int | None = None
    windows_first_at: float | None = None
    window_titles: list[str] = field(default_factory=list)
    exit_code: int | None = None
    exited_at: float | None = None
    left_on_its_own: bool = False
    forced: bool = False
    abort_reason: str = ""
    startup_timed_out: bool = False
    exit_timed_out: bool = False
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    stderr_tail: str = ""

    def elapsed(self, moment: float | None) -> str:
        if moment is None:
            return "n/a"
        return f"+{moment - self.started:.1f}s"


def sample(
    obs: Observation,
    temp_dir: Path,
    data_dir: Path,
    pid: int,
    now: float,
    preexisting: frozenset[str],
) -> None:
    """Take one observation of the running child; called repeatedly while it is alive.

    ``preexisting`` holds the ``_MEI*`` names that were already in the temp directory before the
    launch, so a leftover from an earlier run can never be published as this run's extraction.
    """
    if obs.extraction_seen_at is None:
        found = sorted(
            p.name for p in temp_dir.glob("_MEI*") if p.is_dir() and p.name not in preexisting
        )
        if found:
            obs.extraction_dirs = found
            obs.extraction_seen_at = now
    if obs.extraction_dirs and not obs.extraction_nonempty:
        for name in obs.extraction_dirs:
            folder = temp_dir / name
            try:
                # A clean onefile exit deletes the folder again, and this may race with it.
                if folder.is_dir() and next(folder.iterdir(), None) is not None:
                    obs.extraction_nonempty = True
                    obs.extraction_entries = sum(1 for _ in folder.rglob("*"))
                    obs.extraction_filled_at = now
                    break
            except OSError:
                continue
    if obs.ready_at is None:
        present = [name for name in EVIDENCE_ORDER if (data_dir / name).exists()]
        if len(present) == len(EVIDENCE_ORDER):
            obs.ready_at = now
            obs.ready_files = [str(name) for name in EVIDENCE_ORDER]
    titles = visible_windows(pid)
    if titles is not None:
        obs.windows_seen_max = max(obs.windows_seen_max or 0, len(titles))
        if titles:
            obs.windows_first_at = obs.windows_first_at or now
            obs.window_titles = sorted(set(obs.window_titles) | set(titles))


def launch(command: list[str], env: dict[str, str], cwd: Path) -> tuple[subprocess.Popen, ProcessTree]:
    """Start the child with no console of its own, then claim the whole tree."""
    tree = ProcessTree()
    STDOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STDOUT_FILE, "wb") as stdout, open(STDERR_FILE, "wb") as stderr:
        try:
            proc = subprocess.Popen(
                command,
                env=env,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            tree.close()
            raise
    tree.assign(proc.pid)
    return proc, tree


@dataclass
class RunResult:
    observation: Observation
    command: list[str]
    cwd: Path
    tree_note: str


def run_smoke(args: argparse.Namespace, command: list[str], temp_dir: Path, data_dir: Path) -> RunResult:
    """Launch, wait for evidence, then let the EXE leave - or force it and say so."""
    env = child_environment(args, temp_dir, data_dir)
    cwd = (args.cwd or Path(command[0]).resolve().parent).resolve()
    obs = Observation()
    # Snapshot before launching: only folders that appear afterwards are this run's extraction.
    preexisting = frozenset(p.name for p in temp_dir.glob("_MEI*") if p.is_dir())
    obs.started = time.monotonic()

    proc, tree = launch(command, env, cwd)
    tree_note = tree.note
    try:
        deadline = obs.started + args.timeout
        while True:
            now = time.monotonic()
            if proc.poll() is not None:
                obs.exit_code = proc.returncode
                obs.exited_at = now
                obs.left_on_its_own = True
                break
            sample(obs, temp_dir, data_dir, proc.pid, now, preexisting)
            if obs.windows_first_at is not None:
                # A native message box the Qt platform plugin has no say in. Every further poll
                # would leave it on the user's desktop, so the run ends here.
                obs.abort_reason = "a visible window appeared"
                break
            if obs.ready_at is not None:
                break
            if (
                args.stall_timeout > 0
                and now - obs.started >= args.stall_timeout
                and not obs.extraction_nonempty
            ):
                obs.abort_reason = (
                    f"the extraction folder stayed empty and no startup evidence appeared within "
                    f"{args.stall_timeout:.0f}s"
                )
                break
            if now >= deadline:
                obs.startup_timed_out = True
                break
            time.sleep(args.poll)

        # One last look: a process that died right after writing its evidence must still be credited.
        sample(obs, temp_dir, data_dir, proc.pid, time.monotonic(), preexisting)

        wait_for_exit = (
            obs.ready_at is not None
            and not obs.left_on_its_own
            and not obs.abort_reason
            and args.exit_mode == "autoquit"
        )
        if wait_for_exit:
            try:
                obs.exit_code = proc.wait(timeout=args.exit_timeout)
                obs.left_on_its_own = True
                obs.exited_at = time.monotonic()
            except subprocess.TimeoutExpired:
                obs.exit_timed_out = True

        if proc.poll() is None:
            obs.forced = True
            if not tree.terminate():
                proc.terminate()
            try:
                obs.exit_code = proc.wait(timeout=FORCED_WAIT_S)
            except subprocess.TimeoutExpired:  # pragma: no cover - the job object should not miss
                proc.kill()
                obs.exit_code = proc.wait(timeout=FORCED_WAIT_S)
            obs.exited_at = time.monotonic()
    finally:
        tree.close()
        for handle, name in ((STDOUT_FILE, "stdout"), (STDERR_FILE, "stderr")):
            try:
                size = handle.stat().st_size
            except OSError:
                size = 0
            if name == "stdout":
                obs.stdout_bytes = size
            else:
                obs.stderr_bytes = size
                if size:
                    obs.stderr_tail = handle.read_bytes()[-600:].decode("utf-8", "replace")
    return RunResult(observation=obs, command=command, cwd=cwd, tree_note=tree_note)


# --------------------------------------------------------------------------------------
# checks and report
# --------------------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    ok: bool | None  # None = not applicable here, so reported but never a failure
    detail: str


def build_checks(obs: Observation, args: argparse.Namespace, temp_dir: Path, data_dir: Path) -> list[Check]:
    checks: list[Check] = []

    if obs.extraction_nonempty:
        detail = (
            f"{', '.join(obs.extraction_dirs)} under {temp_dir} appeared at "
            f"{obs.elapsed(obs.extraction_seen_at)} and held {obs.extraction_entries} entry(ies) at "
            f"{obs.elapsed(obs.extraction_filled_at)}"
        )
        if obs.left_on_its_own and obs.exit_code == 0:
            detail += "; a clean onefile exit deletes it again, which is why it was sampled live"
        checks.append(Check("extraction_dir_created", True, detail))
    elif obs.extraction_dirs:
        checks.append(
            Check(
                "extraction_dir_created",
                False,
                f"{', '.join(obs.extraction_dirs)} appeared under {temp_dir} at "
                f"{obs.elapsed(obs.extraction_seen_at)} but stayed EMPTY: the bootloader created its "
                f"private folder and then could not write into it, so nothing was ever unpacked",
            )
        )
    else:
        checks.append(
            Check(
                "extraction_dir_created",
                False,
                f"no _MEI* folder appeared under {temp_dir}: the onefile unpack never started, or "
                f"was refused",
            )
        )

    if obs.ready_at is not None:
        sizes = ", ".join(f"{name} ({(data_dir / name).stat().st_size} B)" for name in obs.ready_files)
        checks.append(
            Check(
                "data_dir_startup_evidence",
                True,
                f"{sizes} in {data_dir} at {obs.elapsed(obs.ready_at)}",
            )
        )
    else:
        present = []
        if data_dir.exists():
            present = sorted(str(p.relative_to(data_dir)) for p in data_dir.rglob("*") if p.is_file())
        checks.append(
            Check(
                "data_dir_startup_evidence",
                False,
                f"neither of {[str(n) for n in EVIDENCE_ORDER]} appeared in {data_dir} within "
                f"{args.timeout:.0f}s (files present: {present[:8] or 'none'})",
            )
        )

    early = obs.ready_at is None and obs.left_on_its_own
    checks.append(
        Check(
            "no_early_exit",
            not early,
            (
                f"the process left at {obs.elapsed(obs.exited_at)} with code {obs.exit_code} before "
                f"any startup evidence appeared: that is a startup-stage failure"
                if early
                else (
                    f"alive when startup evidence arrived at {obs.elapsed(obs.ready_at)}"
                    if obs.ready_at is not None
                    else f"still alive at {obs.elapsed(obs.exited_at or time.monotonic())} when the "
                         f"run was ended"
                )
            ),
        )
    )

    if args.exit_mode == "terminate":
        checks.append(
            Check(
                "clean_self_exit",
                None,
                f"not applicable: --exit-mode terminate forced the end (code {obs.exit_code}). A "
                f"forced termination is NOT a clean exit and says nothing about the event loop",
            )
        )
    elif obs.left_on_its_own and obs.exit_code == 0:
        checks.append(
            Check(
                "clean_self_exit",
                True,
                f"the EXE called app.quit() itself and returned 0 at {obs.elapsed(obs.exited_at)}: it "
                f"reached app.exec() (gui/main.py:160) and unwound",
            )
        )
    elif obs.left_on_its_own:
        checks.append(
            Check(
                "clean_self_exit",
                False,
                f"the EXE left on its own but returned {obs.exit_code} at "
                f"{obs.elapsed(obs.exited_at)}: an abnormal end",
            )
        )
    elif obs.ready_at is None:
        checks.append(
            Check(
                "clean_self_exit",
                False,
                f"the EXE never started far enough to be asked to quit, so it had to be terminated "
                f"forcibly at {obs.elapsed(obs.exited_at)} - that is not a clean exit",
            )
        )
    else:
        checks.append(
            Check(
                "clean_self_exit",
                False,
                f"the EXE never left on its own within {args.exit_timeout:.0f}s of the startup "
                f"evidence; it was terminated forcibly, which is not a clean exit",
            )
        )

    if obs.windows_seen_max is None:
        checks.append(Check("visible_windows_zero", None, "window enumeration unavailable (not Windows)"))
    else:
        detail = (
            f"at most {obs.windows_seen_max} visible top-level window(s) owned by the child "
            f"(sampled every poll)"
        )
        if obs.window_titles:
            detail += f", first at {obs.elapsed(obs.windows_first_at)}: {obs.window_titles}"
        checks.append(Check("visible_windows_zero", obs.windows_seen_max == 0, detail))
    return checks


def print_report(
    result: RunResult,
    checks: list[Check],
    args: argparse.Namespace,
    scratch: Scratch,
) -> bool:
    obs = result.observation
    temp_dir, data_dir = scratch.temp_dir, scratch.data_dir
    width = 30
    print("== packaged EXE smoke ==")
    print(f"  {'command':<{width}} {result.command}")
    print(f"  {'cwd':<{width}} {result.cwd}")
    for label, path, removed, lingering in (
        ("temp dir (TEMP/TMP)", temp_dir, scratch.removed[0], scratch.lingering[0]),
        ("data dir (MCLAUNCHER_DATA_DIR)", data_dir, scratch.removed[1], scratch.lingering[1]),
    ):
        note = f"[{removed} entry(ies) cleared"
        note += f"; left behind {lingering}]" if lingering else "]"
        print(f"  {label:<{width}} {path}  {note}")
    autoquit = f"; {ENV_AUTOQUIT}={args.autoquit_ms}" if args.exit_mode == "autoquit" else "; no auto-quit"
    print(f"  {'child env':<{width}} {ENV_PLATFORM}={PLATFORM_VALUE}{autoquit}")
    print(f"  {'process ownership':<{width}} {result.tree_note}")
    print(
        f"  {'child output':<{width}} {STDOUT_FILE.name} {obs.stdout_bytes} B, "
        f"{STDERR_FILE.name} {obs.stderr_bytes} B (in {STDOUT_FILE.parent})"
    )
    print()
    print("  timeline")
    print(f"    {obs.elapsed(obs.extraction_seen_at):>9}  onefile unpack folder: "
          f"{obs.extraction_dirs or 'no _MEI* folder seen'}")
    if obs.extraction_nonempty:
        unpacked = f"{obs.extraction_entries} entry(ies)"
    elif obs.extraction_dirs:
        unpacked = "NONE - the folder was created but nothing was ever unpacked into it"
    else:
        unpacked = "n/a"
    print(f"    {obs.elapsed(obs.extraction_filled_at):>9}  unpacked content: {unpacked}")
    print(f"    {obs.elapsed(obs.ready_at):>9}  startup evidence: {obs.ready_files or 'none'}")
    titles = f" {obs.window_titles}" if obs.window_titles else ""
    print(f"    {obs.elapsed(obs.windows_first_at):>9}  visible windows: "
          f"{'n/a' if obs.windows_seen_max is None else obs.windows_seen_max}{titles}")
    end = "self" if obs.left_on_its_own else ("forced" if obs.forced else "unknown")
    print(f"    {obs.elapsed(obs.exited_at):>9}  process end: code {obs.exit_code} ({end})")
    if obs.abort_reason:
        print(f"    {'':>9}  ended early: {obs.abort_reason}")
    if obs.stderr_tail:
        print("\n  child stderr (tail):\n    " + obs.stderr_tail.replace("\n", "\n    "))
    print()
    print("  checks")
    for check in checks:
        mark = "n/a " if check.ok is None else ("ok  " if check.ok else "FAIL")
        print(f"    [{mark}] {check.name:<26} {check.detail}")
    print()
    if obs.forced:
        print("  EXIT: forced termination - NOT a clean exit (the exit code alone proves nothing here)")
    elif obs.left_on_its_own and obs.exit_code == 0:
        print("  EXIT: clean self-exit, exit code 0")
    elif obs.left_on_its_own:
        print(f"  EXIT: left on its own with code {obs.exit_code} - not a clean exit")
    else:
        print("  EXIT: no verdict - the process never ran to completion")
    ok = all(check.ok is not False for check in checks)
    failed = ", ".join(c.name for c in checks if c.ok is False)
    print(f"\n{'PASS' if ok else 'FAIL'}: tools/{Path(__file__).name}{'' if ok else f'  ({failed})'}")
    return ok


# --------------------------------------------------------------------------------------
# negative control
# --------------------------------------------------------------------------------------
def apply_demo_defect(
    args: argparse.Namespace, temp_dir: Path, data_dir: Path
) -> tuple[Path, tuple[str, ...], str]:
    """Break exactly one thing the smoke depends on; the run must then FAIL.

    Returns the (possibly redirected) data dir, environment variables to *remove* from the child
    environment, and a note for the report.

    Only defects that cannot produce a window are offered. Pointing the EXE back at the real TEMP, or
    at the real platform plugin, is deliberately *not* among them: the first is reported by the
    windowed bootloader with a native message box and the second would show a window - both would
    break the guarantee this script exists to keep.
    """
    if args.expect_fail_demo == "missing-exe":
        args.exe = REPO / "dist" / "_does_not_exist_.exe"
        args.command = None
        return data_dir, (), f"--exe pointed at a file that does not exist ({args.exe})"
    if args.expect_fail_demo == "bad-data-dir":
        # A regular file where a directory is needed: mkdir(parents=True) raises, so the application
        # cannot create its data directory and no startup evidence can ever appear.
        blocker = temp_dir / "_data_blocker"
        blocker.write_text("a file where a directory is needed\n", encoding="utf-8")
        args.data_dir = blocker / "data"
        return (
            args.data_dir.resolve(),
            (),
            (
                f"{ENV_DATA_DIR} pointed under a regular file ({args.data_dir}): the EXE cannot "
                f"create it, so no startup evidence can appear"
            ),
        )
    return data_dir, (ENV_PLATFORM,), f"{ENV_PLATFORM} removed from the child environment"


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------
def _missing_command_report(
    args: argparse.Namespace, command: list[str], scratch: Scratch
) -> bool:
    """Report the not-found case through the same shape as a real run, so the output stays uniform."""
    obs = Observation(started=time.monotonic())
    result = RunResult(
        observation=obs, command=command, cwd=scratch.data_dir, tree_note="nothing was started"
    )
    checks = [
        Check("extraction_dir_created", False, f"{command[0]} does not exist: nothing was run"),
        Check("data_dir_startup_evidence", False, f"no process ran, so {scratch.data_dir} stayed empty"),
        Check("no_early_exit", False, "the command could not be started at all"),
        Check("clean_self_exit", False, "the command could not be started at all"),
        Check("visible_windows_zero", None, "no process was started, so none could show a window"),
    ]
    return print_report(result, checks, args, scratch)


def _verdict(ok: bool, demo: str | None) -> int:
    """Turn the run's verdict into an exit code, inverting it when this was a negative control."""
    if demo:
        if ok:
            print(
                f"\nNEGATIVE CONTROL FAILED: {demo} was supposed to break the smoke and did not; a "
                f"rig that cannot fail cannot be trusted when it passes"
            )
            return 1
        print(f"\nNEGATIVE CONTROL PASSED: {demo} made the smoke FAIL, as it must")
        return 0
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="smoke_exe.py",
        description=(
            "Run a packaged EXE headlessly (no window, ever) and prove it starts and leaves on its "
            "own. Every write it makes is redirected into Low-integrity scratch directories by "
            "environment variable, because the default locations are refused for a Low process."
        ),
        epilog=EPILOG_TEXT,
    )
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE, help=f"the packaged EXE (default {DEFAULT_EXE})")
    parser.add_argument(
        "--arg", action="append", default=[], dest="extra_args", metavar="ARG",
        help="extra argument for --exe; repeatable",
    )
    parser.add_argument(
        "--command", default=None, metavar="STRING",
        help="run this command instead of --exe (quotes allowed; used by the tests)",
    )
    parser.add_argument(
        "--temp-dir", type=Path, default=DEFAULT_TEMP_DIR,
        help=f"TEMP/TMP for the child; created, then emptied (default {DEFAULT_TEMP_DIR})",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help=f"MCLAUNCHER_DATA_DIR for the child; created, then emptied (default {DEFAULT_DATA_DIR})",
    )
    parser.add_argument("--cwd", type=Path, default=None, help="working directory for the child")
    parser.add_argument(
        "--timeout", type=float, default=STARTUP_TIMEOUT_S,
        help=f"seconds to wait for startup evidence (default {STARTUP_TIMEOUT_S:.0f})",
    )
    parser.add_argument(
        "--exit-timeout", type=float, default=EXIT_TIMEOUT_S,
        help=f"seconds the EXE gets to leave on its own (default {EXIT_TIMEOUT_S:.0f})",
    )
    parser.add_argument(
        "--poll", type=float, default=POLL_INTERVAL_S,
        help=f"evidence poll interval in seconds (default {POLL_INTERVAL_S})",
    )
    parser.add_argument(
        "--stall-timeout", type=float, default=STALL_TIMEOUT_S,
        help="give up when the extraction folder is still empty and no startup evidence has appeared "
             f"after this many seconds; 0 disables (default {STALL_TIMEOUT_S:.0f})",
    )
    parser.add_argument(
        "--autoquit-ms", type=int, default=AUTOQUIT_MS,
        help=f"{ENV_AUTOQUIT} for the child (default {AUTOQUIT_MS})",
    )
    parser.add_argument(
        "--exit-mode", choices=("autoquit", "terminate"), default="autoquit",
        help="autoquit: the app quits itself, so a clean exit is provable; terminate: force the end "
             "after the startup evidence (reported as NOT clean)",
    )
    parser.add_argument(
        "--expect-fail-demo", choices=DEMO_CHOICES, default=None, metavar="DEFECT",
        help="negative control: apply this defect and require the smoke to FAIL "
             f"({', '.join(DEMO_CHOICES)})",
    )
    parser.add_argument(
        "--ignore-integrity-preflight", action="store_true",
        help="launch even when the target is a low-integrity EXE and this session runs under a "
             "restricted token. Off by default: that combination cannot unpack, and the attempt "
             "itself puts a native Win32 message box on screen that QT_QPA_PLATFORM cannot suppress",
    )
    args = parser.parse_args(argv)

    try:
        temp_removed, temp_left = reset_dir(args.temp_dir)
        data_removed, data_left = reset_dir(args.data_dir)
    except (SmokeError, OSError) as exc:
        print(f"cannot prepare the scratch directories: {exc}", file=sys.stderr)
        return 2
    scratch = Scratch(
        temp_dir=args.temp_dir.resolve(),
        data_dir=args.data_dir.resolve(),
        removed=(temp_removed, data_removed),
        lingering=(temp_left, data_left),
    )
    temp_dir, data_dir = scratch.temp_dir, scratch.data_dir

    demo_note = ""
    drop_env: tuple[str, ...] = ()
    if args.expect_fail_demo:
        data_dir, drop_env, demo_note = apply_demo_defect(args, temp_dir, data_dir)
        scratch.data_dir = data_dir
        print(f"negative control [{args.expect_fail_demo}]: {demo_note}\n")

    command = resolve_command(args)
    env = child_environment(args, temp_dir, data_dir)
    for name in drop_env:
        env.pop(name, None)
    defects = environment_defects(env, temp_dir, data_dir, args.exit_mode)
    if defects:
        print("refusing to launch: this child environment is not the one the smoke claims to test")
        for defect in defects:
            print(f"  [FAIL] {defect}")
        if args.expect_fail_demo:
            print(
                f"\nNEGATIVE CONTROL PASSED: {args.expect_fail_demo} produced a FAIL before any "
                f"process started, so nothing could appear on screen"
            )
            return 0
        return 2

    if not Path(command[0]).exists() and shutil.which(command[0]) is None:
        return _verdict(_missing_command_report(args, command, scratch), args.expect_fail_demo)

    if not args.ignore_integrity_preflight:
        defects = confinement_defects(command)
        if defects:
            print("refusing to launch: this EXE cannot start here, and trying would put a native "
                  "message box on the user's screen")
            for defect in defects:
                print(f"  [REFUSED] {defect}")
            print("\n  nothing was started. --ignore-integrity-preflight launches anyway (a Win32 "
                  "dialog may appear; QT_QPA_PLATFORM cannot suppress it).")
            if args.expect_fail_demo:
                print(f"  note: the {args.expect_fail_demo} negative control did not run.")
            return 2

    try:
        result = run_smoke(args, command, temp_dir, data_dir)
    except OSError as exc:
        print(f"could not start {command[0]}: {exc}", file=sys.stderr)
        return 1

    checks = build_checks(result.observation, args, temp_dir, data_dir)
    return _verdict(print_report(result, checks, args, scratch), args.expect_fail_demo)


if __name__ == "__main__":
    raise SystemExit(main())
