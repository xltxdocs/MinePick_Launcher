"""Memory sizing helpers: suggest a JVM heap size from system memory and mod count.

The suggestion follows the same tiered idea as popular community launchers:
targets grow with the mod count, but each tier only takes a fraction of the
available system memory, so the OS is never starved.
"""

from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path

MAX_MEMORY_GB = 16.0
MIN_MEMORY_GB = 0.5


def count_mods(mods_dir: Path) -> int:
    """Count mod files in a directory (enabled *.jar and disabled *.jar.disabled)."""
    if not mods_dir.is_dir():
        return 0
    try:
        return sum(
            1
            for p in mods_dir.iterdir()
            if p.name.lower().endswith((".jar", ".jar.disabled"))
        )
    except OSError:
        return 0


def system_memory_gb() -> tuple[float, float]:
    """Return (total physical GB, available physical GB) of the system."""
    if os.name == "nt":
        try:
            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                gib = 1024 ** 3
                return status.ullTotalPhys / gib, status.ullAvailPhys / gib
        except Exception:  # fall through to the fallback below
            logging.getLogger(__name__).debug("GlobalMemoryStatusEx failed", exc_info=True)
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page / 1024 ** 3
        avail = os.sysconf("SC_AVPHYS_PAGES") * page / 1024 ** 3
        return total, avail
    except (AttributeError, ValueError, OSError):
        return 8.0, 4.0


def suggest_memory_gb(
    mod_count: int = 0,
    *,
    total_gb: float | None = None,
    available_gb: float | None = None,
) -> float:
    """Suggest a JVM heap size in GB, rounded to 0.5 GB steps.

    Tier targets grow with the mod count; each tier only claims a fraction
    (100% / 70% / 40% / 15%) of the remaining available memory, and the
    result is clamped to [minimum, 75% of total, MAX_MEMORY_GB].
    """
    if total_gb is None or available_gb is None:
        total_gb, available_gb = system_memory_gb()
    if mod_count > 0:
        minimum = MIN_MEMORY_GB + mod_count / 150
        targets = (1.5 + mod_count / 90, 2.7 + mod_count / 50, 4.5 + mod_count / 25)
    else:
        minimum = MIN_MEMORY_GB
        targets = (1.5, 2.5, 4.0)
    boundaries = (targets[0], targets[1], targets[2], targets[2] * 2)
    fractions = (1.0, 0.7, 0.4, 0.15)
    avail = max(available_gb, 0.0)
    ram_give = 0.0
    prev = 0.0
    for boundary, fraction in zip(boundaries, fractions):
        delta = boundary - prev
        ram_give += min(avail * fraction, delta)
        avail -= delta / fraction
        if avail < 0.1:
            break
        prev = boundary
    ram_give = max(ram_give, minimum)
    ram_give = min(ram_give, total_gb * 0.75, MAX_MEMORY_GB)
    return round(ram_give * 2) / 2

