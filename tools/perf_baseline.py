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

"""Performance baseline: startup, memory, per-page cost, theme switching, idle CPU.

USE IT LIKE THIS (repo root, the interpreter the GUI runs on):

    D:\\dsh-workspace\\minecraft-launcher\\.venv\\Scripts\\python.exe tools\\perf_baseline.py ^
        --mode offscreen --json build\\perf_offscreen.json

    D:\\dsh-workspace\\minecraft-launcher\\.venv\\Scripts\\python.exe tools\\perf_baseline.py ^
        --mode real --json build\\perf_real.json

HOW TO COMPARE LATER: run it twice with ``--json`` - before and after a change - and diff the two
files; each file's ``headline`` is a flat ``metric path -> number`` table, and
``perf_baseline.py --diff build\\perf_real_before.json build\\perf_real_after.json`` prints every
metric with its delta, marking the ones that moved by 10% or more.

THE TWO MODES:

* ``offscreen`` - the Qt ``offscreen`` platform plugin: no platform window at all.
* ``real`` - the actual platform (``windows``) with ``WA_DontShowOnScreen`` set: a real platform
  window that pays real font/style/backing-store costs but is never shown on screen. Both the plugin
  name and the attribute are asserted per phase, not assumed.

WHY EVERY PHASE RUNS IN ITS OWN PROCESS (the bug this rig was rebuilt for)
-------------------------------------------------------------------------
The first version measured every phase in one process. Its startup phase built three windows and
closed them with ``close() + deleteLater()``, draining only ``QApplication.processEvents()`` - which
does **not** deliver ``QEvent::DeferredDelete``. Those windows stayed attached to the application, so
every later ``setStyleSheet`` re-polished them as well. Measured offscreen with one window whose
eight pages are built (``QApplication.allWidgets()`` = the population Qt re-polishes):

=================  =========================  ==================  ============================
process history    live widgets while timing  median theme swap   probe
=================  =========================  ==================  ============================
first window       836                        ~170 ms             probe_isolation.py
3 leaked windows   1316                       ~1119 ms            probe_isolation.py
after a real drain 836                        ~1080 ms            probe_isolation.py
2nd window         867                        ~218 ms             probe_history.py
3rd window         898                        ~1147 ms            probe_history.py
=================  =========================  ==================  ============================

The probes live outside the repository, with the other diagnostics from this work:
``D:\\dsh-workspace\\tmp\\perf_baseline_probes\\``. They are scratch evidence, not product code; the
repository's header guard scans every ``.py`` file on disk, which is why they are no longer under
``Source_code_UI\\tmp\\``.

So the leak is real, but draining is not enough to isolate phases: the cost does **not** come back
when the extra widgets are deleted (836 widgets, 1080 ms), and it is not explained by the live widget
population either (867 vs 898 widgets, 218 ms vs 1147 ms). It follows the process history - how many
windows this process has built and destroyed. Only a fresh process removes it. Therefore **each phase
is a child process that builds exactly the windows that phase needs**, and the startup phase gets one
process per sample, because "startup" means the first window of a process, which is what a real
launch builds.

A second counting trap this rig avoids: ``len(window.findChildren(QWidget)) + 1`` is not the
population Qt polishes. A window that visited all eight pages leaves **31 widgets** behind (three
combo-box popup containers: 6 QScrollBar, 3 QListView, 3 QComboBox, 3 QFrame, 15 QWidget, 1 QLabel)
that belong to no window and survive the window's destruction; they show up in
``QApplication.allWidgets()`` and are re-polished on every stylesheet swap (measured: 45 -> 47 for a
launch-page window, 803 -> 834 for a full one, growing by 31 per full window: 33 -> 64 -> 95).

HOW ISOLATION IS PROVED (asserted on every execution; a failed check fails the run)
-----------------------------------------------------------------------------------
Each child reports an ``isolation`` block built from assertions:

1. ``virgin_process`` - before the phase builds anything the application holds no window and at most
   ``VIRGIN_WIDGET_CAP`` widgets (measured: 2).
2. ``only_this_phase_is_alive`` - while the phase's window is up there is exactly one window, and it
   carries ``WA_DontShowOnScreen``.
3. ``released_<label>`` - after ``close() + deleteLater()`` the deferred deletes are drained
   (``sendPostedEvents(None, QEvent.DeferredDelete)`` + ``gc.collect()``) and the population must be
   back to the phase's floor: **exactly** for a launch-page-only window (measured +0: 45 widgets
   released, back to 2), with the documented 31-widget budget for a window that visited all eight
   pages. Zero ``QMainWindow`` alive is asserted exactly in both cases.
4. ``expected_platform`` / ``windows_created`` - the QPA plugin is the one the mode promises, and the
   process built exactly the number of windows its phase declares (1 everywhere).
5. ``swaps_were_real`` / ``guard_holds`` (theme phases only) - every timed swap changed
   ``theme.current_tokens()`` and issued exactly two ``QApplication.setStyleSheet`` calls (clear, then
   install = the fast path), and repeating the last swap's parameters is a ~0 ms no-op. A series that
   silently measured guarded no-ops therefore cannot be published as a result.

``--self-test`` is the negative control for (3): it runs the *old* sequence (close + deleteLater +
``processEvents()`` only) and requires the detector to fire, then requires a real drain to clear it.
An assertion that cannot fail would make a polluted application look perfectly isolated.

WHAT IS MEASURED (per mode: 3 runs; each run repeats every phase as documented)

* startup - one fresh process per sample, reported as ``[min, median, max]`` plus every raw sample in
  order. Three boundaries, because earlier reports mixed them: ``app_create_ms`` (``create_app()``:
  stylesheet, palette, icon), ``main_window_ms`` (``MainWindow()`` + ``show()`` + first drain - the
  boundary the older numbers quoted, so it stays the headline) and ``app_ready_ms`` (both). A
  diagnostic ``startup-warm`` phase measures the *second* window of a process (27 ms offscreen against
  110+ ms for the first): the old rig's median came from its 2nd and 3rd windows, so this is the like
  for like bridge, not a headline. Window widgets are reported as ``findChildren+1`` **and** as the
  ``allWidgets()`` delta, which is what Qt polishes.
* session - RSS at startup and after visiting all eight pages (working set, commit, peak; read
  in-process, and the run fails if the value cannot be read), per-page first-visit cost, and 60 s of
  idle CPU split into six slices so a spike - or the tail of the setup work - is visible.
* theme - ten dark/light swaps at two widget scales (only the launch page built / all eight pages
  visited), each scale in its own process. Only ``apply_theme()`` is timed; the event drain that
  follows is timed separately, because the notification the theme code queues
  (``QTimer.singleShot(0, ...)``) lands there, not in the call. Each swap is split into the
  application-sheet clear/install and the widget-level restyles that notification triggers (the trace
  shape is folded in from the diagnostic variant another session left in
  ``D:\\dsh-workspace\\tmp\\perf_baseline_probes\\perf_baseline_trace_variant.py``).

Nothing here touches the network: the three fetches the pages would make are stubbed out. The
application writes into ``build/perf_data`` (override with ``PERF_BASELINE_DATA``); the path is fixed
on purpose - this sandbox refuses writes inside freshly created random directories.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# The eight pages, in navigation order. Reading a page through the registry builds it on first access,
# which is exactly the cost we want to measure.
NAV_KEYS = ["launch", "instances", "versions", "java", "account", "mods", "settings", "about"]
THEME_SWAPS = 10
IDLE_SECONDS = 60.0
IDLE_WINDOWS = 6  # idle is reported as this many equal slices as well as one average
MEMORY_SAMPLES = 5
STARTUP_SAMPLES = 3
VIRGIN_WIDGET_CAP = 8  # app-owned widgets before any window exists (measured: 2)
# Widgets that outlive a window whose eight pages were visited: three combo-box popup containers,
# measured 31. A launch-page-only window releases exactly (measured +0), so this budget applies only
# to full-scale windows, and the real number is always reported next to it.
LEAK_BUDGET_AFTER_CLOSE = 48
PHASES = ("warmup", "startup", "startup-warm", "session", "theme-startup-scale", "theme-full-scale")
JSON_BEGIN = "@@PERF-JSON-BEGIN@@"
JSON_END = "@@PERF-JSON-END@@"
CHILD_TIMEOUT_S = 900
INSTRUMENT_VERSION = "2.0"


# --------------------------------------------------------------------------------------
# process memory (in-process: no child process on the machine being timed)
# --------------------------------------------------------------------------------------
_MEMORY_PROBE: tuple[Any, Any, Any] | None = None


def _memory_probe():
    """(ctypes, function, counters type) for GetProcessMemoryInfo, built once.

    In-process on purpose: the previous rig shelled out to PowerShell for every reading, putting a
    ~1 s subprocess start (and its CPU) on the machine that was being timed. Raises when the probe is
    unavailable instead of returning a placeholder.
    """
    global _MEMORY_PROBE
    if _MEMORY_PROBE is None:
        if os.name != "nt":  # pragma: no cover - this baseline is Windows-only
            raise RuntimeError("the memory probe needs Windows (GetProcessMemoryInfo)")
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        function = getattr(kernel32, "K32GetProcessMemoryInfo", None)
        if function is None:  # pragma: no cover - pre-Vista fallback
            function = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        function.restype = wintypes.BOOL
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        _MEMORY_PROBE = (ctypes, function, ProcessMemoryCounters)
    return _MEMORY_PROBE


def memory_mb() -> dict[str, float]:
    """Working set (RSS), commit charge and peak working set of this process, in MB.

    Raises RuntimeError when the value cannot be read: a silent 0.0 would be published as a
    measurement, which is worse than reporting that the measurement is missing.
    """
    ctypes, function, counters_type = _memory_probe()
    counters = counters_type()
    counters.cb = ctypes.sizeof(counters_type)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    handle = kernel32.GetCurrentProcess()
    if not function(handle, ctypes.byref(counters), counters.cb):
        raise RuntimeError(f"GetProcessMemoryInfo failed (winerror {ctypes.get_last_error()})")
    mib = 1024.0 * 1024.0
    return {
        "working_set_mb": round(counters.WorkingSetSize / mib, 1),
        "commit_mb": round(counters.PagefileUsage / mib, 1),
        "peak_working_set_mb": round(counters.PeakWorkingSetSize / mib, 1),
    }


def memory_series(samples: int = MEMORY_SAMPLES) -> dict[str, Any]:
    """Several readings of the same point: the range shows how noisy the point is."""
    readings = [memory_mb() for _ in range(samples)]
    out: dict[str, Any] = {
        "probe": "GetProcessMemoryInfo (in-process, ctypes)",
        "samples": samples,
        "working_set_samples_mb": [reading["working_set_mb"] for reading in readings],
    }
    for key in ("working_set_mb", "commit_mb", "peak_working_set_mb"):
        out[key] = _range([reading[key] for reading in readings])
    return out


def _range(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 1),
        "median": round(statistics.median(values), 1),
        "max": round(max(values), 1),
    }


# --------------------------------------------------------------------------------------
# child process: Qt-side helpers
# --------------------------------------------------------------------------------------
def live_widgets() -> int:
    """Every widget the application owns - the population ``setStyleSheet`` re-polishes.

    ``len(window.findChildren(QWidget)) + 1`` is *not* that population: it misses the widgets the
    pages attach outside the window (31 widgets, measured) and it cannot see a second window that an
    earlier phase failed to release.
    """
    from PySide6.QtWidgets import QApplication

    return len(QApplication.allWidgets())


def live_windows() -> int:
    """Top-level windows still alive: a closed-but-not-deleted window still counts."""
    from PySide6.QtWidgets import QApplication, QMainWindow

    return sum(1 for widget in QApplication.allWidgets() if isinstance(widget, QMainWindow))


def drain() -> None:
    """Deliver what ``processEvents()`` alone does not: the deferred deletes, then the garbage.

    ``QApplication.processEvents()`` does not process ``QEvent::DeferredDelete``, so a widget closed
    with ``deleteLater()`` stays attached to the application - and keeps being polished by the next
    ``setStyleSheet`` - until the posted event is sent explicitly or a real event loop runs.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    for _ in range(3):
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    QApplication.processEvents()


def ensure_app() -> tuple[Any, float]:
    """Create the QApplication if this process has none; return it and how long that took.

    Every phase calls this *before* it measures anything: the widget floor and the QPA plugin can only
    be read once the application exists (without one ``allWidgets()`` is empty and ``platformName()``
    reports the desktop default rather than the plugin actually in use).
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        return app, 0.0
    from gui.main import create_app

    start = time.perf_counter()
    app = create_app([])
    return app, round((time.perf_counter() - start) * 1000, 1)


def build_window(isolation: Isolation):
    """Construct + configure the main window exactly as a launch does, off screen."""
    from PySide6.QtCore import Qt

    from gui.main_window import MainWindow

    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    isolation.window_built()
    return window


def visit_all_pages(window) -> dict[str, float]:
    """Build every page through the registry's lazy accessor, timing each first visit."""
    from PySide6.QtWidgets import QApplication

    per_page: dict[str, float] = {}
    for key in NAV_KEYS:
        start = time.perf_counter()
        window.pages[key]
        QApplication.processEvents()
        per_page[key] = round((time.perf_counter() - start) * 1000, 1)
    return per_page


def window_counters(window) -> dict[str, int]:
    """The window's own widget count and its built-page count (without iterating the registry)."""
    from PySide6.QtWidgets import QWidget

    stack = getattr(window, "stack", None)
    return {
        "window_widgets_findchildren": len(window.findChildren(QWidget)) + 1,
        "stack_pages": int(stack.count()) if stack is not None else -1,
    }


def scratch_dir() -> Path:
    """The application's data directory: a fixed path, never a random one.

    This sandbox refuses to create files inside a freshly created random directory, and a data
    directory that cannot be written makes the run fail for a reason that has nothing to do with
    speed. ``PERF_BASELINE_DATA`` overrides it.
    """
    return Path(os.environ.get("PERF_BASELINE_DATA") or (REPO / "build" / "perf_data"))


def reset_scratch_dir() -> Path:
    """Empty and recreate the scratch directory so every run starts from the same state."""
    scratch = scratch_dir()
    if scratch.exists():
        for child in scratch.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def stub_network() -> None:
    """Keep the run offline: the three remote fetches the pages make are replaced with failures."""

    def _fail(*_args, **_kwargs):
        raise RuntimeError("offline (perf baseline)")

    from gui.pages import java_page, versions_page
    from launcher.mods import modrinth

    versions_page.fetch_manifest = _fail
    modrinth._client = _fail
    java_page.list_java = lambda *a, **kw: []


class Isolation:
    """Assertions that prove a phase measured only its own window (see the module docstring)."""

    def __init__(self, phase: str, expected_windows: int, expected_platform: str) -> None:
        from PySide6.QtWidgets import QApplication

        self.phase = phase
        self.expected_windows = expected_windows
        self.expected_platform = expected_platform
        self.windows_created = 0
        self.checks: list[dict[str, Any]] = []
        self.floor = live_widgets()
        self.floor_windows = live_windows()
        self.add_check(
            "virgin_process",
            self.floor <= VIRGIN_WIDGET_CAP and self.floor_windows == 0,
            f"before the phase: allWidgets={self.floor} (cap {VIRGIN_WIDGET_CAP}), "
            f"windows={self.floor_windows}",
        )
        self.add_check(
            "expected_platform",
            QApplication.platformName() == expected_platform,
            f"QPA plugin {QApplication.platformName()!r}, the mode expects {expected_platform!r}",
        )

    def add_check(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def window_built(self) -> None:
        self.windows_created += 1

    def window_is_alone(self, window) -> int:
        """Record the population while the phase's window is up: this window and nothing else."""
        from PySide6.QtCore import Qt

        population = live_widgets()
        self.add_check(
            "only_this_phase_is_alive",
            live_windows() == 1 and window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen),
            f"allWidgets={population} (floor {self.floor}, +{population - self.floor}), "
            f"windows={live_windows()}, WA_DontShowOnScreen set",
        )
        return population

    def released(self, label: str, budget: int = 0) -> int:
        """After close + drain the window must be gone; ``budget`` allows documented leftovers."""
        population = live_widgets()
        windows = live_windows()
        delta = population - self.floor
        self.add_check(
            f"released_{label}",
            windows == 0 and delta <= budget,
            f"after close+drain: allWidgets={population} (floor {self.floor}, +{delta}, "
            f"budget {budget}), windows={windows}",
        )
        return delta

    def finish(self) -> dict[str, Any]:
        self.add_check(
            "windows_created",
            self.windows_created == self.expected_windows,
            f"this process built {self.windows_created} window(s), the phase declares "
            f"{self.expected_windows}",
        )
        return {
            "phase": self.phase,
            "expected_windows": self.expected_windows,
            "windows_created": self.windows_created,
            "floor_widgets": self.floor,
            "ok": all(check["ok"] for check in self.checks),
            "checks": self.checks,
        }


class SwapTrace:
    """Where one swap's time goes, and proof that the swap really happened.

    ``clear``/``install`` are the two application-sheet calls of the fast path, ``widget`` counts the
    stylesheet installed on the title-bar buttons by the queued notification - the part of the cost
    that lands in the drain rather than in ``apply_theme()``.
    """

    def __init__(self) -> None:
        self.clear_calls = 0
        self.install_calls = 0
        self.widget_calls = 0
        self.install_ms: list[float] = []
        self.widget_ms: list[float] = []
        self.notify_runs = 0
        self.notify_ms: list[float] = []
        self.body_ran = 0
        self.guard_skipped = 0
        self._mark = (0, 0, 0, 0)

    def mark(self) -> None:
        self._mark = (self.clear_calls, self.install_calls, self.widget_calls, self.notify_runs)

    def since_mark(self) -> dict[str, int]:
        clear, install, widget, notify = self._mark
        return {
            "clear_calls": self.clear_calls - clear,
            "install_calls": self.install_calls - install,
            "widget_style_calls": self.widget_calls - widget,
            "notify_runs": self.notify_runs - notify,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "body_ran": self.body_ran,
            "guard_skipped": self.guard_skipped,
            "clear_calls": self.clear_calls,
            "install_calls": self.install_calls,
            "widget_style_calls": self.widget_calls,
            "install_ms_median": (
                round(statistics.median(self.install_ms), 1) if self.install_ms else None
            ),
            "install_ms_max": round(max(self.install_ms), 1) if self.install_ms else None,
            "widget_style_ms_median": (
                round(statistics.median(self.widget_ms), 1) if self.widget_ms else None
            ),
            "notify_runs": self.notify_runs,
            "notify_ms": [round(value, 2) for value in self.notify_ms],
        }


def instrument_theme(app, trace: SwapTrace) -> None:
    """Wrap the application and widget stylesheet entry points plus the queued notification.

    Nothing in ``gui/`` changes. ``QApplication.setStyleSheet`` sees the application-wide replacement
    (the clear and the install); ``QWidget.setStyleSheet`` sees the per-widget sheets the title-bar
    buttons install from the queued notification, which is the part of the cost that lands in the
    drain instead of in ``apply_theme()``. The shape is folded in from the diagnostic variant another
    session left in ``D:\\dsh-workspace\\tmp\\perf_baseline_probes\\``.
    """
    from PySide6.QtWidgets import QApplication, QWidget

    from gui import theme

    original_app_set = QApplication.setStyleSheet
    original_widget_set = QWidget.setStyleSheet

    def counted_app_set(instance, text="", *args, **kwargs):  # mirrors the Qt slot's shape
        start = time.perf_counter()
        result = original_app_set(instance, text, *args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        if not text:
            trace.clear_calls += 1
        else:
            trace.install_calls += 1
            trace.install_ms.append(elapsed)
        return result

    def counted_widget_set(instance, text="", *args, **kwargs):  # mirrors the Qt slot's shape
        start = time.perf_counter()
        result = original_widget_set(instance, text, *args, **kwargs)
        trace.widget_calls += 1
        trace.widget_ms.append((time.perf_counter() - start) * 1000)
        return result

    QApplication.setStyleSheet = counted_app_set
    QWidget.setStyleSheet = counted_widget_set

    notify = theme._notify_self_styling  # apply_theme looks this name up when it queues the timer

    def counted_notify() -> None:
        trace.notify_runs += 1
        start = time.perf_counter()
        notify()
        trace.notify_ms.append((time.perf_counter() - start) * 1000)

    theme._notify_self_styling = counted_notify


# --------------------------------------------------------------------------------------
# children: one phase each, one process each
# --------------------------------------------------------------------------------------
def idle_cpu_sample(seconds: float, windows: int = IDLE_WINDOWS) -> dict[str, Any]:
    """Idle CPU over ``seconds`` of a live event loop, plus equal slices so a spike is visible.

    The process is kept responsive the way an idle GUI is: process events, sleep, repeat. Both the
    whole process and the calling thread are sampled, so a background thread waking up is not
    mistaken for the GUI doing work.
    """
    from PySide6.QtWidgets import QApplication

    slices: list[dict[str, float]] = []
    slice_seconds = seconds / windows
    process_total = 0.0
    thread_total = 0.0
    wall_total = 0.0
    for _ in range(windows):
        process_start = time.process_time()
        thread_start = time.thread_time()
        wall_start = time.perf_counter()
        deadline = wall_start + slice_seconds
        while time.perf_counter() < deadline:
            QApplication.processEvents()
            time.sleep(0.02)
        wall = time.perf_counter() - wall_start
        process_cpu = time.process_time() - process_start
        thread_cpu = time.thread_time() - thread_start
        process_total += process_cpu
        thread_total += thread_cpu
        wall_total += wall
        slices.append(
            {
                "wall_seconds": round(wall, 2),
                "cpu_percent": round(100.0 * process_cpu / wall, 2) if wall else 0.0,
                "main_thread_cpu_percent": round(100.0 * thread_cpu / wall, 2) if wall else 0.0,
            }
        )
    return {
        "wall_seconds": round(wall_total, 1),
        "cpu_seconds": round(process_total, 3),
        "main_thread_cpu_seconds": round(thread_total, 3),
        "cpu_percent": round(100.0 * process_total / wall_total, 2) if wall_total else None,
        "main_thread_cpu_percent": (
            round(100.0 * thread_total / wall_total, 2) if wall_total else None
        ),
        "slice_seconds": round(slice_seconds, 2),
        "slices": slices,
    }


def phase_warmup() -> dict[str, Any]:
    """Build and release one window before anything is measured.

    The measured phases must not pay first-run file creation (config, logs, the game-directory probe)
    or one-off import costs, and the data directory has to be proven writable before a run is
    reported as a baseline.
    """
    ensure_app()
    isolation = Isolation("warmup", expected_windows=1, expected_platform=_expected_platform())
    window = build_window(isolation)
    window.show()
    _drain_events()
    counters = window_counters(window)
    window.close()
    window.deleteLater()
    drain()
    delta = isolation.released("warmup", budget=0)
    scratch = scratch_dir()
    files = sorted(item.name for item in scratch.iterdir()) if scratch.exists() else []
    return {
        "counters": counters,
        "released_delta": delta,
        "data_dir": str(scratch),
        "data_dir_files": files,
        "isolation": isolation.finish(),
    }


def phase_startup() -> dict[str, Any]:
    """Time one window from construction to the first drained event loop - in a fresh process.

    Three numbers, because the earlier reports mixed two boundaries:

    * ``app_create_ms`` - ``create_app()``: stylesheet load, palette, window icon. The old rig paid
      this inside its *first* sample only and not in the two after it, so its reported
      min/median/max mixed two different things.
    * ``main_window_ms`` - ``MainWindow()`` construction, ``show()`` and the first
      ``processEvents()``: the boundary every earlier report quoted, so it stays the headline.
    * ``app_ready_ms`` - the two together: what a launch actually pays from "application object" to
      the first frame.
    """
    _app, app_create_ms = ensure_app()
    isolation = Isolation("startup", expected_windows=1, expected_platform=_expected_platform())
    start = time.perf_counter()
    window = build_window(isolation)
    window.show()
    _drain_events()
    main_window_ms = round((time.perf_counter() - start) * 1000, 1)
    population = isolation.window_is_alone(window)
    counters = window_counters(window)
    memory = memory_series(1)
    window.close()
    window.deleteLater()
    drain()
    delta = isolation.released("startup", budget=0)
    return {
        "app_create_ms": app_create_ms,
        "main_window_ms": main_window_ms,
        "app_ready_ms": round(app_create_ms + main_window_ms, 1),
        "window_widgets_findchildren": counters["window_widgets_findchildren"],
        "window_widgets_allwidgets_delta": population - isolation.floor,
        "pages_built": counters["stack_pages"],
        "rss_working_set_mb": memory["working_set_mb"]["median"],
        "released_delta": delta,
        "isolation": isolation.finish(),
    }


def phase_startup_warm() -> dict[str, Any]:
    """Diagnostic bridge: the *second* window of a process, which is what the older reports quoted.

    The old rig built three windows in one process and reported min/median/max over all three, so its
    27-30 ms median was a warm window, while a launch builds the first window of a fresh process
    (``startup``, ~110 ms offscreen). Both are real measurements of different things, and this phase
    reproduces the warm one on purpose - one throwaway window is built and released first - so the two
    reports can be compared instead of looking like a regression. It is a diagnostic, not a headline:
    the drain assertion runs on the throwaway window too.
    """
    _app, app_create_ms = ensure_app()
    isolation = Isolation("startup-warm", expected_windows=2, expected_platform=_expected_platform())
    throwaway = build_window(isolation)
    throwaway.show()
    _drain_events()
    throwaway.close()
    throwaway.deleteLater()
    drain()
    first_delta = isolation.released("warmup_window", budget=0)
    start = time.perf_counter()
    window = build_window(isolation)
    window.show()
    _drain_events()
    warm_ms = round((time.perf_counter() - start) * 1000, 1)
    isolation.window_is_alone(window)
    counters = window_counters(window)
    window.close()
    window.deleteLater()
    drain()
    second_delta = isolation.released("measured_window", budget=0)
    return {
        "ms": warm_ms,
        "app_create_ms": app_create_ms,
        "released_delta": second_delta,
        "first_window_released_delta": first_delta,
        "window_widgets_findchildren": counters["window_widgets_findchildren"],
        "pages_built": counters["stack_pages"],
        "isolation": isolation.finish(),
    }


def phase_session(idle_seconds: float) -> dict[str, Any]:
    """One window: RSS, per-page first-visit cost, RSS again, then the idle sample."""
    from collections import Counter

    ensure_app()
    isolation = Isolation("session", expected_windows=1, expected_platform=_expected_platform())
    window = build_window(isolation)
    window.show()
    _drain_events()
    isolation.window_is_alone(window)

    rss_before_window = memory_series(1)
    rss_at_startup = memory_series()
    counters_startup = window_counters(window)

    per_page = visit_all_pages(window)
    counters_full = window_counters(window)
    population_full = isolation.window_is_alone(window)  # still exactly this one window
    rss_after_pages = memory_series()
    built_keys = [key for key in NAV_KEYS if window.pages.peek(key) is not None]

    idle = idle_cpu_sample(idle_seconds) if idle_seconds > 0 else None

    window.close()
    window.deleteLater()
    drain()
    delta = isolation.released("session", budget=LEAK_BUDGET_AFTER_CLOSE)
    from PySide6.QtWidgets import QApplication

    live_classes = Counter(type(widget).__name__ for widget in QApplication.allWidgets())
    return {
        "rss_before_window": rss_before_window,
        "rss_at_startup": rss_at_startup,
        "rss_after_all_pages": rss_after_pages,
        "per_page_ms": per_page,
        "pages_built_at_startup": counters_startup["stack_pages"],
        "pages_built_after_all": counters_full["stack_pages"],
        "built_keys": len(built_keys),
        "window_widgets_at_startup": counters_startup["window_widgets_findchildren"],
        "window_widgets_after_all": counters_full["window_widgets_findchildren"],
        "window_widgets_allwidgets_delta_after_all": population_full - isolation.floor,
        "idle": idle,
        "released_delta": delta,
        "live_widget_classes_after_close": dict(live_classes.most_common(8)),
        "isolation": isolation.finish(),
    }


def phase_theme(scale: str) -> dict[str, Any]:
    """Ten dark/light swaps at one widget scale, in a fresh process.

    ``scale`` is "startup" (only the launch page is built) or "full" (all eight pages visited); the
    two are different baselines and are never mixed.
    """
    from gui import theme

    app, _create_ms = ensure_app()
    isolation = Isolation(
        f"theme-{scale}-scale", expected_windows=1, expected_platform=_expected_platform()
    )
    window = build_window(isolation)
    window.show()
    app.processEvents()
    per_page = visit_all_pages(window) if scale == "full" else {}
    population = isolation.window_is_alone(window)
    counters = window_counters(window)
    memory = memory_series(1)

    trace = SwapTrace()
    instrument_theme(app, trace)
    swaps: list[float] = []
    drains: list[float] = []
    tokens_changed: list[bool] = []
    per_swap: list[dict[str, Any]] = []
    for index in range(THEME_SWAPS):
        name = "light" if index % 2 == 0 else "dark"
        trace.mark()
        applied_before = theme._last_applied  # diagnostic only: did the call reach the body?
        tokens_before = theme.current_tokens()
        start = time.perf_counter()
        theme.apply_theme(name, None, None, None)
        apply_ms = round((time.perf_counter() - start) * 1000, 1)
        if theme._last_applied != applied_before:
            trace.body_ran += 1
            body_ran = True
        else:
            trace.guard_skipped += 1
            body_ran = False
        drain_start = time.perf_counter()
        app.processEvents()
        drain_ms = round((time.perf_counter() - drain_start) * 1000, 1)
        changed = theme.current_tokens() != tokens_before
        swaps.append(apply_ms)
        drains.append(drain_ms)
        tokens_changed.append(changed)
        per_swap.append(
            {
                "theme": name,
                "apply_ms": apply_ms,
                "drain_ms": drain_ms,
                "body_ran": body_ran,
                "tokens_changed": changed,
                **trace.since_mark(),
            }
        )
    summary = trace.summary()
    isolation.add_check(
        "swaps_were_real",
        all(tokens_changed) and all(entry["body_ran"] for entry in per_swap),
        f"tokens changed on {sum(tokens_changed)}/{len(tokens_changed)} swaps, "
        f"the apply body ran on {sum(1 for entry in per_swap if entry['body_ran'])}/{len(per_swap)}",
    )
    isolation.add_check(
        "fast_path_ran",
        all(
            entry["clear_calls"] == 1 and entry["install_calls"] == 1 for entry in per_swap
        ),
        f"setStyleSheet calls per swap: clear "
        f"{sorted({entry['clear_calls'] for entry in per_swap})}, install "
        f"{sorted({entry['install_calls'] for entry in per_swap})} (the clear-then-install path)",
    )
    guard = _guard_probe(app, theme, trace)
    isolation.add_check(
        "guard_holds",
        max(guard) < 50.0,
        f"repeating the last swap's parameters took {guard} ms (a guarded call must be a no-op)",
    )

    window.close()
    window.deleteLater()
    drain()
    delta = isolation.released(f"theme_{scale}", budget=LEAK_BUDGET_AFTER_CLOSE)
    return {
        "scale": scale,
        "swaps_ms": swaps,
        "drain_ms": drains,
        "per_swap": per_swap,
        "trace": summary,
        "range_ms": _range(swaps),
        "total_ms": round(sum(swaps), 1),
        "first_ms": swaps[0] if swaps else None,
        "last_ms": swaps[-1] if swaps else None,
        "drain_total_ms": round(sum(drains), 1),
        "drain_max_ms": round(max(drains), 1) if drains else None,
        "guard_repeat_ms": guard,
        "window_widgets_findchildren": counters["window_widgets_findchildren"],
        "window_widgets_allwidgets_delta": population - isolation.floor,
        "pages_built": counters["stack_pages"],
        "per_page_ms": per_page,
        "rss_working_set_mb": memory["working_set_mb"]["median"],
        "released_delta": delta,
        "isolation": isolation.finish(),
    }


def _guard_probe(app, theme, trace: SwapTrace) -> list[float]:
    """Call ``apply_theme`` again with the last swap's parameters: it must be skipped, not applied."""
    last = "light" if (THEME_SWAPS - 1) % 2 == 0 else "dark"
    guarded: list[float] = []
    for _ in range(3):
        trace.mark()
        applied_before = theme._last_applied
        tokens_before = theme.current_tokens()
        start = time.perf_counter()
        theme.apply_theme(last, None, None, None)
        guarded.append(round((time.perf_counter() - start) * 1000, 1))
        app.processEvents()
        if theme._last_applied != applied_before or theme.current_tokens() != tokens_before:
            guarded.append(-1.0)
    return guarded


def phase_self_test() -> dict[str, Any]:
    """Negative control: the leak detector must fire on the sequence that produced the bad numbers."""
    ensure_app()
    isolation = Isolation("self-test", expected_windows=2, expected_platform=_expected_platform())

    # 1) the old rig's sequence: close + deleteLater + processEvents() only
    window = build_window(isolation)
    window.show()
    _drain_events()
    owned = window_counters(window)["window_widgets_findchildren"]
    window.close()
    window.deleteLater()
    _drain_events()  # <- what the old _measure_startup did, and all it did
    leaked = live_widgets() - isolation.floor
    isolation.add_check(
        "leak_detector_fires",
        leaked >= owned,
        f"{owned} widgets closed with processEvents() only: {leaked} of them still attached "
        f"(allWidgets {live_widgets()}, floor {isolation.floor})",
    )

    # 2) the real drain must clean it up
    drain()
    isolation.add_check(
        "drain_releases",
        live_widgets() == isolation.floor and live_windows() == 0,
        f"after sendPostedEvents(DeferredDelete)+gc: allWidgets={live_widgets()} "
        f"(floor {isolation.floor}), windows={live_windows()}",
    )

    # 3) a correctly released window leaves nothing behind either
    second = build_window(isolation)
    second.show()
    _drain_events()
    second.close()
    second.deleteLater()
    drain()
    isolation.released("self_test_second_window", budget=0)
    block = isolation.finish()
    return {
        "widgets_owned": owned,
        "widgets_leaked_by_old_path": leaked,
        "isolation": block,
    }


def _expected_platform() -> str:
    return "offscreen" if os.environ.get("QT_QPA_PLATFORM") == "offscreen" else "windows"


def _drain_events() -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()


PHASE_FUNCTIONS = {
    "warmup": lambda idle: phase_warmup(),
    "startup": lambda idle: phase_startup(),
    "startup-warm": lambda idle: phase_startup_warm(),
    "session": phase_session,
    "theme-startup-scale": lambda idle: phase_theme("startup"),
    "theme-full-scale": lambda idle: phase_theme("full"),
    "self-test": lambda idle: phase_self_test(),
}


def run_child(phase: str, mode: str, idle_seconds: float) -> int:
    """Child entry point: run one phase and print its JSON between markers."""
    if mode == "offscreen":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    else:
        os.environ.pop("QT_QPA_PLATFORM", None)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(scratch_dir())
    stub_network()
    payload = PHASE_FUNCTIONS[phase](idle_seconds)
    payload["phase"] = phase
    payload["mode"] = mode
    payload["platform_plugin"] = _expected_platform()
    print(JSON_BEGIN)
    print(json.dumps(payload, ensure_ascii=False))
    print(JSON_END)
    return 0


# --------------------------------------------------------------------------------------
# parent: drive the children
# --------------------------------------------------------------------------------------
def child_environment(mode: str, scratch: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["MCLAUNCHER_DATA_DIR"] = str(scratch)
    if mode == "offscreen":
        env["QT_QPA_PLATFORM"] = "offscreen"
    else:
        env.pop("QT_QPA_PLATFORM", None)
    return env


def spawn(phase: str, mode: str, idle_seconds: float, scratch: Path, attempts: int = 2) -> dict[str, Any]:
    """Run one phase in its own process and return its payload; never invent a number.

    A phase that crashes (this repository has a known rare Qt crash) or times out is retried once; if
    it fails again the payload is a ``failed`` record, the run is marked not-ok, and the metric is
    reported as missing instead of as a value.
    """
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--phase",
        phase,
        "--mode",
        mode,
        "--idle-seconds",
        str(idle_seconds),
    ]
    env = child_environment(mode, scratch)
    history: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            done = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=CHILD_TIMEOUT_S,
                check=False,
                env=env,
                cwd=str(REPO),
            )
        except subprocess.TimeoutExpired:
            history.append({"attempt": attempt, "error": f"timeout after {CHILD_TIMEOUT_S}s"})
            continue
        except OSError as exc:  # pragma: no cover - environment dependent
            history.append({"attempt": attempt, "error": f"could not start: {exc}"})
            break
        elapsed = round(time.perf_counter() - started, 1)
        payload = _extract_json(done.stdout)
        if done.returncode == 0 and payload is not None:
            payload["child_seconds"] = elapsed
            payload["attempts"] = attempt
            return payload
        history.append(
            {
                "attempt": attempt,
                "returncode": done.returncode,
                "seconds": elapsed,
                "stderr_tail": (done.stderr or "")[-800:],
                "stdout_tail": (done.stdout or "")[-400:],
            }
        )
    return {"phase": phase, "failed": True, "attempts": attempts, "history": history}


def _extract_json(stdout: str) -> dict[str, Any] | None:
    start = stdout.find(JSON_BEGIN)
    end = stdout.find(JSON_END, start + 1)
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(stdout[start + len(JSON_BEGIN) : end].strip())
    except json.JSONDecodeError:
        return None


def host_busy_sample(seconds: float = 3.0) -> dict[str, Any]:
    """Machine-wide CPU around a run: the contamination check for a performance baseline.

    Two snapshots of the summed per-process CPU time; the difference over the interval divided by the
    logical core count. It does not measure the phases - it says whether something else was running
    while they were measured, because a second benchmark on this box invalidates the numbers.
    """
    script = (
        "$a=(Get-Process | Measure-Object -Property CPU -Sum).Sum; "
        f"Start-Sleep -Seconds {seconds}; "
        "$b=(Get-Process | Measure-Object -Property CPU -Sum).Sum; Write-Output ($b-$a)"
    )
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - a diagnostic must not kill the run
        return {"error": f"{type(exc).__name__}: {exc}"}
    value = None
    for line in reversed((done.stdout or "").splitlines()):
        try:
            value = float(line.strip())
            break
        except ValueError:
            continue
    if value is None:
        return {"error": f"unreadable output: {(done.stdout or '')[:120]!r}"}
    cores = os.cpu_count() or 1
    # A process that exits inside the interval takes its CPU time out of the second sum, which can
    # make the difference negative; clamp instead of publishing a negative usage.
    value = max(0.0, value)
    return {
        "seconds": seconds,
        "cpu_seconds": round(value, 2),
        "cores": cores,
        "busy_percent": round(100.0 * value / (seconds * cores), 1),
        "method": (
            "sum of Get-Process CPU over the interval / logical cores; a process that exits inside "
            "the interval reads low"
        ),
    }


def run_once(mode: str, idle_seconds: float, scratch: Path, run_index: int) -> dict[str, Any]:
    """One run: warm-up, three startup samples (one process each), then session and both themes."""
    print(f"  run {run_index}: warm-up", flush=True)
    warmup = spawn("warmup", mode, 0.0, scratch)
    if warmup.get("failed"):
        return {"run": run_index, "ok": False, "warmup": warmup}

    startup_samples = []
    for sample in range(STARTUP_SAMPLES):
        print(f"  run {run_index}: startup sample {sample + 1}/{STARTUP_SAMPLES}", flush=True)
        payload = spawn("startup", mode, 0.0, scratch)
        startup_samples.append(payload)
        if payload.get("failed"):
            break

    print(f"  run {run_index}: startup, warm second window (diagnostic)", flush=True)
    startup_warm = spawn("startup-warm", mode, 0.0, scratch)

    print(f"  run {run_index}: session (per-page + {idle_seconds:.0f}s idle)", flush=True)
    session = spawn("session", mode, idle_seconds, scratch)
    print(f"  run {run_index}: theme swaps at startup scale", flush=True)
    theme_startup = spawn("theme-startup-scale", mode, 0.0, scratch)
    print(f"  run {run_index}: theme swaps at full scale", flush=True)
    theme_full = spawn("theme-full-scale", mode, 0.0, scratch)

    phases = [warmup, *startup_samples, startup_warm, session, theme_startup, theme_full]
    ok = all(not phase.get("failed") for phase in phases) and all(
        phase.get("isolation", {}).get("ok", False) for phase in phases
    )
    return {
        "run": run_index,
        "ok": ok,
        "warmup": warmup,
        "startup_samples": startup_samples,
        "startup_warm": startup_warm,
        "session": session,
        "theme_startup_scale": theme_startup,
        "theme_full_scale": theme_full,
    }


def aggregate(mode: str, runs: int, idle_seconds: float) -> dict[str, Any]:
    """Run the phases ``runs`` times and fold the runs into one result document."""
    scratch = reset_scratch_dir()
    print(f"mode {mode}: {runs} run(s), data dir {scratch}", flush=True)
    host_before = host_busy_sample()
    _print_busy("3s sample before the runs (settled)", host_before)
    run_results = []
    for index in range(1, runs + 1):
        run = run_once(mode, idle_seconds, scratch, index)
        run["host_busy_after"] = host_busy_sample()
        _print_busy(
            f"3s sample right after run {index} (may include this rig's own teardown)",
            run["host_busy_after"],
        )
        run_results.append(run)
    host_after = host_busy_sample()
    _print_busy("3s sample after the last run (settled)", host_after)

    result: dict[str, Any] = {
        "instrument": {
            "name": "tools/perf_baseline.py",
            "version": INSTRUMENT_VERSION,
            "isolation": (
                "one phase per child process; every child asserts its own widget population before, "
                "during and after the measured work (see the module docstring)"
            ),
            "phases": list(PHASES),
            "startup_samples_per_run": STARTUP_SAMPLES,
            "theme_swaps_per_scale": THEME_SWAPS,
        },
        "mode": mode,
        "runs": runs,
        "idle_seconds": idle_seconds,
        "python": sys.version.split()[0],
        "pyside6": _pyside_version(),
        "host": {
            "cpu_count": os.cpu_count(),
            "machine": os.environ.get("PROCESSOR_ARCHITECTURE", ""),
            "busy_before_runs": host_before,
            "busy_per_run": [run.get("host_busy_after") for run in run_results],
            "busy_after_runs": host_after,
        },
        "data_dir": str(scratch),
        "ok": all(run["ok"] for run in run_results),
        "startup": _aggregate_startup(run_results),
        "startup_warm": _aggregate_startup_warm(run_results),
        "session": _aggregate_session(run_results),
        "theme": {
            "startup_scale": _aggregate_theme(run_results, "theme_startup_scale"),
            "full_scale": _aggregate_theme(run_results, "theme_full_scale"),
        },
        "runs_detail": run_results,
    }
    result["isolation"] = _isolation_summary(run_results)
    result["headline"] = headline(result)
    return result


def _print_busy(label: str, sample: dict[str, Any]) -> None:
    """Print one contamination indicator; a missing sample is reported, not invented."""
    if "busy_percent" not in sample:
        print(f"  host busy {label}: unavailable ({sample.get('error')})", flush=True)
        return
    note = ""
    if sample["busy_percent"] >= 10.0:
        note = "  <- the machine was busy: treat these numbers with suspicion"
    print(f"  host busy {label}: {sample['busy_percent']}%{note}", flush=True)


def _aggregate_startup(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    window_ms: list[float] = []
    create_ms: list[float] = []
    ready_ms: list[float] = []
    widgets: list[int] = []
    allwidgets: list[int] = []
    pages: list[int] = []
    per_run: list[dict[str, Any]] = []
    for run in run_results:
        samples = [s for s in run.get("startup_samples", []) if not s.get("failed")]
        values = [s["main_window_ms"] for s in samples]
        creates = [s["app_create_ms"] for s in samples]
        window_ms.extend(values)
        create_ms.extend(creates)
        ready_ms.extend(s["app_ready_ms"] for s in samples)
        widgets.extend(s["window_widgets_findchildren"] for s in samples)
        allwidgets.extend(s["window_widgets_allwidgets_delta"] for s in samples)
        pages.extend(s["pages_built"] for s in samples)
        if values:
            per_run.append(
                {
                    "run": run["run"],
                    "samples_ms": values,
                    "app_create_ms": creates,
                    "range_ms": _range(values),
                }
            )
    if not window_ms:
        return {"missing": "every startup sample failed"}
    return {
        "samples_ms": [round(value, 1) for value in window_ms],
        "app_create_samples_ms": [round(value, 1) for value in create_ms],
        "app_ready_samples_ms": [round(value, 1) for value in ready_ms],
        "range_ms": _range(window_ms),
        "app_create_range_ms": _range(create_ms),
        "app_ready_range_ms": _range(ready_ms),
        "per_run": per_run,
        "window_widgets_findchildren": sorted(set(widgets)),
        "window_widgets_allwidgets_delta": sorted(set(allwidgets)),
        "pages_built": sorted(set(pages)),
        "boundary": (
            "samples_ms = MainWindow() + show() + first drain (the boundary earlier reports used); "
            "app_create_samples_ms = create_app() on its own; app_ready_samples_ms = both"
        ),
    }


def _aggregate_startup_warm(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [run["startup_warm"] for run in run_results if not run.get("startup_warm", {}).get("failed")]
    if not payloads:
        return {"missing": "every warm-startup child failed"}
    values = [payload["ms"] for payload in payloads]
    return {
        "samples_ms": values,
        "range_ms": _range(values),
        "note": (
            "diagnostic only: the second window of a process, the boundary the older reports quoted "
            "as their median; the headline startup number is the first window of a fresh process"
        ),
    }


def _aggregate_session(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    sessions = [run["session"] for run in run_results if not run.get("session", {}).get("failed")]
    if not sessions:
        return {"missing": "every session child failed"}
    return {
        "per_page_ms": {
            key: _range([session["per_page_ms"][key] for session in sessions]) for key in NAV_KEYS
        },
        "per_page_runs_ms": {
            key: [session["per_page_ms"][key] for session in sessions] for key in NAV_KEYS
        },
        "pages_built_at_startup": sorted({s["pages_built_at_startup"] for s in sessions}),
        "pages_built_after_all": sorted({s["pages_built_after_all"] for s in sessions}),
        "window_widgets_at_startup": sorted({s["window_widgets_at_startup"] for s in sessions}),
        "window_widgets_after_all": sorted({s["window_widgets_after_all"] for s in sessions}),
        "window_widgets_allwidgets_delta_after_all": sorted(
            {s["window_widgets_allwidgets_delta_after_all"] for s in sessions}
        ),
        "rss_at_startup_mb": _aggregate_memory([s["rss_at_startup"] for s in sessions]),
        "rss_after_all_pages_mb": _aggregate_memory([s["rss_after_all_pages"] for s in sessions]),
        "rss_before_window_mb": _aggregate_memory([s["rss_before_window"] for s in sessions]),
        "idle": _aggregate_idle([s["idle"] for s in sessions if s.get("idle")]),
        "released_delta": [s["released_delta"] for s in sessions],
        "live_widget_classes_after_close": [s.get("live_widget_classes_after_close", {}) for s in sessions],
    }


def _aggregate_memory(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    aggregated: dict[str, Any] = {
        key: _range([payload[key]["median"] for payload in payloads])
        for key in ("working_set_mb", "commit_mb", "peak_working_set_mb")
    }
    aggregated["per_run_working_set_mb"] = [
        payload["working_set_samples_mb"] for payload in payloads
    ]
    return aggregated


def _aggregate_idle(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    if not payloads:
        return {"missing": "no idle sample"}
    return {
        "cpu_percent": _range([payload["cpu_percent"] for payload in payloads]),
        "main_thread_cpu_percent": _range(
            [payload["main_thread_cpu_percent"] for payload in payloads]
        ),
        "wall_seconds": _range([payload["wall_seconds"] for payload in payloads]),
        "cpu_seconds": _range([payload["cpu_seconds"] for payload in payloads]),
        "slices_percent": [
            slice_["cpu_percent"] for payload in payloads for slice_ in payload["slices"]
        ],
        "slice_seconds": payloads[0]["slice_seconds"],
        "per_run_percent": [payload["cpu_percent"] for payload in payloads],
    }


def _aggregate_theme(run_results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    payloads = [run[key] for run in run_results if not run.get(key, {}).get("failed")]
    if not payloads:
        return {"missing": "every theme child failed"}
    return {
        "swaps_ms_per_run": [payload["swaps_ms"] for payload in payloads],
        "median_ms": _range([payload["range_ms"]["median"] for payload in payloads]),
        "total_ms": _range([payload["total_ms"] for payload in payloads]),
        "min_ms": min(payload["range_ms"]["min"] for payload in payloads),
        "max_ms": max(payload["range_ms"]["max"] for payload in payloads),
        "first_swap_ms": [payload["first_ms"] for payload in payloads],
        "last_swap_ms": [payload["last_ms"] for payload in payloads],
        "drain_per_swap_ms": [payload["drain_ms"] for payload in payloads],
        "drain_max_ms": [payload["drain_max_ms"] for payload in payloads],
        "drain_total_ms": _range([payload["drain_total_ms"] for payload in payloads]),
        "guard_repeat_ms": [payload["guard_repeat_ms"] for payload in payloads],
        "trace": [payload["trace"] for payload in payloads],
        "per_swap_first_run": payloads[0]["per_swap"],
        "window_widgets_findchildren": sorted(
            {payload["window_widgets_findchildren"] for payload in payloads}
        ),
        "window_widgets_allwidgets_delta": sorted(
            {payload["window_widgets_allwidgets_delta"] for payload in payloads}
        ),
        "pages_built": sorted({payload["pages_built"] for payload in payloads}),
        "rss_working_set_mb": [payload["rss_working_set_mb"] for payload in payloads],
    }


def _isolation_summary(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    failed: list[dict[str, str]] = []
    checked = 0
    for run in run_results:
        for key in ("warmup", "startup_warm", "session", "theme_startup_scale", "theme_full_scale"):
            block = run.get(key) or {}
            if block.get("failed"):
                failed.append(
                    {"run": str(run["run"]), "phase": key, "check": "child failed: "
                     + json.dumps(block.get("history", []), ensure_ascii=False)[:400]}
                )
                continue
            _collect_failed(run["run"], block, failed)
            checked += 1
        for sample in run.get("startup_samples", []):
            if sample.get("failed"):
                failed.append(
                    {"run": str(run["run"]), "phase": "startup", "check": "child failed"}
                )
                continue
            _collect_failed(run["run"], sample, failed)
            checked += 1
    return {"phases_checked": checked, "failed_checks": failed, "ok": not failed}


def _collect_failed(run_index: int, payload: dict[str, Any], failed: list[dict[str, str]]) -> None:
    for check in payload.get("isolation", {}).get("checks", []):
        if not check["ok"]:
            failed.append(
                {
                    "run": str(run_index),
                    "phase": payload.get("isolation", {}).get("phase", "?"),
                    "check": f"{check['name']}: {check['detail']}",
                }
            )


def _pyside_version() -> str:
    try:
        import PySide6

        return PySide6.__version__
    except Exception:  # noqa: BLE001 - the parent only reports it
        return "unknown"


# --------------------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------------------
def headline(result: dict[str, Any]) -> dict[str, float]:
    """Flat ``metric path -> number`` table: the printed summary and ``--diff`` both read this."""
    flat: dict[str, float] = {}
    startup = result.get("startup", {})
    if "range_ms" in startup:
        for key, value in startup["range_ms"].items():
            flat[f"startup.ms.{key}"] = value
        flat["startup.ms.sample_count"] = float(len(startup["samples_ms"]))
        flat["startup.app_create_ms.median"] = startup["app_create_range_ms"]["median"]
        flat["startup.app_ready_ms.median"] = startup["app_ready_range_ms"]["median"]
        flat["startup.widgets.findchildren"] = float(startup["window_widgets_findchildren"][0])
        flat["startup.widgets.allwidgets_delta"] = float(
            startup["window_widgets_allwidgets_delta"][0]
        )
        flat["startup.pages_built"] = float(startup["pages_built"][0])
    warm = result.get("startup_warm", {})
    if "range_ms" in warm:
        flat["startup.warm_second_window_ms.median"] = warm["range_ms"]["median"]
    session = result.get("session", {})
    if "per_page_ms" in session:
        for key, value in session["per_page_ms"].items():
            flat[f"session.per_page_ms.{key}.median"] = value["median"]
            flat[f"session.per_page_ms.{key}.max"] = value["max"]
        flat["session.per_page_ms.total_median"] = round(
            sum(value["median"] for value in session["per_page_ms"].values()), 1
        )
        flat["session.pages_built_after_all"] = float(session["pages_built_after_all"][0])
        flat["session.widgets.after_all"] = float(session["window_widgets_after_all"][0])
        flat["session.widgets.allwidgets_delta_after_all"] = float(
            session["window_widgets_allwidgets_delta_after_all"][0]
        )
        for point in ("rss_at_startup_mb", "rss_after_all_pages_mb"):
            for key in ("working_set_mb", "commit_mb", "peak_working_set_mb"):
                flat[f"session.{point}.{key}.median"] = session[point][key]["median"]
                flat[f"session.{point}.{key}.max"] = session[point][key]["max"]
        idle = session.get("idle", {})
        if "cpu_percent" in idle:
            flat["session.idle.cpu_percent.median"] = idle["cpu_percent"]["median"]
            flat["session.idle.cpu_percent.max"] = idle["cpu_percent"]["max"]
            flat["session.idle.main_thread_cpu_percent.median"] = idle[
                "main_thread_cpu_percent"
            ]["median"]
            flat["session.idle.slice_percent.max"] = max(idle["slices_percent"])
            flat["session.idle.wall_seconds"] = idle["wall_seconds"]["median"]
    for scale, block in result.get("theme", {}).items():
        if "median_ms" not in block:
            continue
        flat[f"theme.{scale}.median_ms.median"] = block["median_ms"]["median"]
        flat[f"theme.{scale}.median_ms.min"] = block["median_ms"]["min"]
        flat[f"theme.{scale}.median_ms.max"] = block["median_ms"]["max"]
        flat[f"theme.{scale}.total_ms.median"] = block["total_ms"]["median"]
        flat[f"theme.{scale}.drain_total_ms.median"] = block["drain_total_ms"]["median"]
        flat[f"theme.{scale}.widgets"] = float(block["window_widgets_findchildren"][0])
    host = result.get("host", {})
    if isinstance(host.get("busy_before_runs"), dict) and "busy_percent" in host["busy_before_runs"]:
        flat["host.busy_percent.before_runs"] = host["busy_before_runs"]["busy_percent"]
    busy = [
        sample["busy_percent"]
        for sample in host.get("busy_per_run", [])
        if isinstance(sample, dict) and "busy_percent" in sample
    ]
    if busy:
        flat["host.busy_percent.max_run"] = max(busy)
    after_runs = host.get("busy_after_runs")
    if isinstance(after_runs, dict) and "busy_percent" in after_runs:
        flat["host.busy_percent.after_runs"] = after_runs["busy_percent"]
    flat["isolation.failed_checks"] = float(len(result.get("isolation", {}).get("failed_checks", [])))
    return flat


def print_report(result: dict[str, Any]) -> None:
    def line(label: str, value: Any) -> None:
        print(f"  {label:<44} {value}")

    isolation_ok = result["isolation"]["ok"]
    print(
        f"mode: {result['mode']}   runs: {result['runs']}   ok: {result['ok']}   "
        f"isolation ok: {isolation_ok}   ({result['isolation']['phases_checked']} phase processes "
        f"checked)"
    )
    print("startup (construction + show + first drain; one fresh process per sample)")
    startup = result.get("startup", {})
    if "range_ms" in startup:
        line(
            "ms min / median / max",
            f"{startup['range_ms']['min']} / {startup['range_ms']['median']} / "
            f"{startup['range_ms']['max']}",
        )
        line("ms samples (in order)", startup["samples_ms"])
        line(
            "app_create ms (median, raw)",
            f"{startup['app_create_range_ms']['median']}  {startup['app_create_samples_ms']}",
        )
        line(
            "app ready -> first frame ms (median)",
            startup["app_ready_range_ms"]["median"],
        )
        line(
            "window widgets findChildren+1 / allWidgets",
            f"{startup['window_widgets_findchildren']} / "
            f"+{startup['window_widgets_allwidgets_delta']}",
        )
        line("pages built at startup", startup["pages_built"])
        warm = result.get("startup_warm", {})
        if "range_ms" in warm:
            line(
                "warm 2nd window ms (diagnostic, raw)",
                f"{warm['range_ms']['median']}  {warm['samples_ms']}",
            )
    else:
        line("startup", startup)

    print("session")
    session = result.get("session", {})
    if "per_page_ms" in session:
        line(
            "pages built at startup / after visiting all",
            f"{session['pages_built_at_startup']} / {session['pages_built_after_all']}",
        )
        line(
            "window widgets startup / after all",
            f"{session['window_widgets_at_startup']} / {session['window_widgets_after_all']} "
            f"(+{session['window_widgets_allwidgets_delta_after_all']} detached)",
        )
        for point, label in (
            ("rss_at_startup_mb", "RSS at startup WS/commit MB (median,raw)"),
            ("rss_after_all_pages_mb", "RSS after all pages WS/commit MB (median,raw)"),
        ):
            block = session[point]
            line(
                label,
                f"{block['working_set_mb']['median']} / {block['commit_mb']['median']}  "
                f"{block['per_run_working_set_mb']}",
            )
        line(
            "per-page first visit ms (median of runs)",
            {key: value["median"] for key, value in session["per_page_ms"].items()},
        )
        line("per-page runs (raw)", session["per_page_runs_ms"])
        idle = session.get("idle", {})
        if "cpu_percent" in idle:
            line(
                f"idle {idle['wall_seconds']['median']:.0f}s CPU all-threads/main-thread %",
                f"{idle['cpu_percent']['median']} / {idle['main_thread_cpu_percent']['median']}  "
                f"per run {idle['per_run_percent']}",
            )
            line("idle 10s slices % (all runs)", idle["slices_percent"])
    else:
        line("session", session)

    print(f"theme switching ({result['instrument']['theme_swaps_per_scale']} swaps per scale)")
    for scale in ("startup_scale", "full_scale"):
        block = result.get("theme", {}).get(scale, {})
        if "median_ms" not in block:
            line(scale, block)
            continue
        line(
            f"{scale}: median ms (min..max over runs)",
            f"{block['median_ms']['median']} ({block['median_ms']['min']}.."
            f"{block['median_ms']['max']})",
        )
        line(f"{scale}: total ms per run", block["total_ms"])
        line(f"{scale}: swaps ms per run", block["swaps_ms_per_run"])
        line(f"{scale}: drain per swap (median total ms)", block["drain_total_ms"]["median"])
        line(
            f"{scale}: widgets findChildren+1 / allWidgets",
            f"{block['window_widgets_findchildren']} / +{block['window_widgets_allwidgets_delta']}",
        )
        trace = block["trace"][0]
        line(
            f"{scale}: swap attribution (run 1)",
            f"install median {trace['install_ms_median']} ms, widget-level styles "
            f"{trace['widget_style_calls']} calls median {trace['widget_style_ms_median']} ms, "
            f"notify runs {trace['notify_runs']}",
        )

    host = result.get("host", {})
    busy = [
        sample.get("busy_percent")
        for sample in [
            host.get("busy_before_runs"),
            *host.get("busy_per_run", []),
            host.get("busy_after_runs"),
        ]
        if isinstance(sample, dict)
    ]
    line("host busy % around the runs", busy)
    if result["isolation"]["failed_checks"]:
        print("isolation failures")
        for failure in result["isolation"]["failed_checks"]:
            line(f"run {failure['run']} {failure['phase']}", failure["check"])
    print(
        "compare later: keep both --json files and run "
        "`perf_baseline.py --diff <before.json> <after.json>`"
    )


def print_diff(before: dict[str, Any], after: dict[str, Any], threshold: float = 10.0) -> int:
    old = before.get("headline") or headline(before)
    new = after.get("headline") or headline(after)
    print(
        f"diff: {before.get('mode')} -> {after.get('mode')}   (instrument "
        f"{before.get('instrument', {}).get('version')} -> "
        f"{after.get('instrument', {}).get('version')})"
    )
    if before.get("mode") != after.get("mode"):
        print("  WARNING: the two files were measured in different modes")
    rows: list[tuple[str, float | None, float | None, float | None]] = []
    for key in sorted(set(old) | set(new)):
        left, right = old.get(key), new.get(key)
        if left is None or right is None:
            rows.append((key, left, right, None))
            continue
        percent = (100.0 * (right - left) / left) if left else None
        rows.append((key, left, right, percent))
    rows.sort(key=lambda row: -abs(row[3]) if row[3] is not None else 1e9)
    print(f"  {'metric':<52} {'before':>12} {'after':>12} {'delta':>10} {'%':>9}")
    for key, left, right, percent in rows:
        if left is None or right is None:
            left_text = "-" if left is None else f"{left:.1f}"
            right_text = "-" if right is None else f"{right:.1f}"
            print(f"  {key:<52} {left_text:>12} {right_text:>12} {'-':>10} {'-':>9}")
            continue
        if percent is None:  # before was 0, so a percentage is undefined
            print(f"  {key:<52} {left:>12.1f} {right:>12.1f} {right - left:>+10.1f} {'n/a':>9}")
            continue
        marker = "*" if percent is not None and abs(percent) >= threshold else " "
        print(
            f"  {key:<52} {left:>12.1f} {right:>12.1f} {right - left:>+10.1f} "
            f"{percent:>+8.1f}%{marker}"
        )
    moved = [row for row in rows if row[3] is not None and abs(row[3]) >= threshold]
    print(f"  {len(moved)} metric(s) moved by {threshold:.0f}% or more; * marks them")
    missing = [row[0] for row in rows if row[3] is None]
    if missing:
        print(f"  {len(missing)} metric(s) exist in only one file: {missing}")
    return 0


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the launcher's performance baseline (one process per phase).",
    )
    parser.add_argument("--mode", choices=["offscreen", "real"], default="offscreen")
    parser.add_argument("--runs", type=int, default=3, help="how many times the phase set is run")
    parser.add_argument("--json", type=Path, default=None, help="also write the results here")
    parser.add_argument(
        "--idle-seconds",
        type=float,
        default=IDLE_SECONDS,
        help="length of the idle CPU sample (default 60; anything shorter is not a baseline)",
    )
    parser.add_argument(
        "--skip-idle",
        action="store_true",
        help="smoke-test only: 1 s idle instead of 60 s (NOT a baseline sample)",
    )
    parser.add_argument(
        "--phase",
        choices=[*PHASES, "self-test"],
        default=None,
        help="internal: run one phase in this process and print its JSON",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="negative control: prove the isolation checks fire on the old leaky rig",
    )
    parser.add_argument(
        "--diff",
        nargs=2,
        type=Path,
        metavar=("BEFORE", "AFTER"),
        default=None,
        help="compare the headline metrics of two --json files",
    )
    args = parser.parse_args(argv)

    if args.diff:
        before = json.loads(args.diff[0].read_text(encoding="utf-8"))
        after = json.loads(args.diff[1].read_text(encoding="utf-8"))
        return print_diff(before, after)

    if args.phase:
        return run_child(args.phase, args.mode, args.idle_seconds)

    if args.self_test:
        scratch = reset_scratch_dir()
        payload = spawn("self-test", args.mode, 0.0, scratch)
        if payload.get("failed"):
            print("self-test could not run:", json.dumps(payload, indent=2, ensure_ascii=False))
            return 2
        for check in payload["isolation"]["checks"]:
            print(f"  [{'ok' if check['ok'] else 'FAIL'}] {check['name']}: {check['detail']}")
        print(f"self-test {'PASSED' if payload['isolation']['ok'] else 'FAILED'}")
        return 0 if payload["isolation"]["ok"] else 1

    idle_seconds = 1.0 if args.skip_idle else args.idle_seconds
    if idle_seconds < IDLE_SECONDS:
        print(
            f"note: idle sample is {idle_seconds:.0f}s, not the {IDLE_SECONDS:.0f}s baseline length "
            f"- do not publish this as an idle CPU baseline"
        )
    result = aggregate(args.mode, max(1, args.runs), idle_seconds)
    print_report(result)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"written: {args.json}")
    return 0 if (result["ok"] and result["isolation"]["ok"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
