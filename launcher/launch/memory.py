"""System memory helpers for the launcher (Windows focused)."""

from __future__ import annotations

import ctypes
import logging
import os


def trim_working_set() -> None:
    """Release the launcher process idle physical pages back to the OS.

    Best-effort only: on failure the launcher simply keeps its pages.
    Call this after the game process has started so the game gets the
    maximum amount of free RAM.
    """
    if os.name != "nt":
        return
    try:
        ctypes.windll.psapi.SetProcessWorkingSetSize(-1, -1, -1)  # type: ignore[attr-defined]
    except Exception:  # best effort
        logging.getLogger(__name__).debug("TrimWorkingSet failed", exc_info=True)

