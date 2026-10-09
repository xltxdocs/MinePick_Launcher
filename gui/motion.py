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

r"""Should the UI animate? Ask the system once, then remember the answer.

The UI guideline (§5.2) says reduced motion must be honoured, and the approved decision (B4) is to
follow the system setting only - no in-app switch, because a preference like this belongs to the
operating system and an extra toggle would cost nine translations, a config field and a test surface.

Degrading does **not** mean "no feedback at all": transparency and colour changes are kept (they help
read a state change), while movement and scaling are dropped - those are what cause discomfort.

Windows exposes this as SPI_GETCLIENTAREAANIMATION, which is the same switch behind
Settings > Accessibility > Visual effects > Animation effects. The older MinAnimate value in the
desktop WindowMetrics key is the fallback. The Themes\Personalize key that the guideline also mentions
governs light/dark appearance rather than motion, so it is deliberately not consulted here.
"""

from __future__ import annotations

import sys

__all__ = ["animations_enabled", "refresh", "set_override_for_tests"]

SPI_GETCLIENTAREAANIMATION = 0x1042
_UNKNOWN = object()
_cached: object = _UNKNOWN
_override: object = _UNKNOWN


def _read_spi() -> bool | None:
    """Ask Windows directly; None when the call is unavailable or fails."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        enabled = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        if not ok:
            return None
        return bool(enabled.value)
    except Exception:  # noqa: BLE001 - any failure falls through to the registry or the default
        return None


def _read_registry() -> bool | None:
    """MinAnimate: "0" disables window animations; None when it cannot be read."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop\WindowMetrics"
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "MinAnimate")
        return str(value).strip() != "0"
    except Exception:  # noqa: BLE001 - a missing value means "no opinion"
        return None


def _detect() -> bool:
    """System preference with the documented fallback chain; defaults to animating."""
    for reader in (_read_spi, _read_registry):
        answer = reader()
        if answer is not None:
            return answer
    return True


def animations_enabled() -> bool:
    """True when the UI may animate. Cached: call :func:`refresh` after a theme reload."""
    global _cached
    if _override is not _UNKNOWN:
        return bool(_override)
    if _cached is _UNKNOWN:
        _cached = _detect()
    return bool(_cached)


def refresh() -> bool:
    """Re-read the system preference (the user may have changed it while we ran)."""
    global _cached
    _cached = _detect()
    return bool(_cached)


def set_override_for_tests(value: bool | None) -> None:
    """Force a value (True/False) or clear the override (None). Tests only."""
    global _override
    _override = _UNKNOWN if value is None else bool(value)
