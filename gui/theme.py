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

"""Theme application: dark / light QSS with a custom accent color and UI font (applied immediately)."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QApplication

from launcher import paths

# Default accent per theme; the tint steps below are derived from whichever base is in use
DEFAULT_ACCENTS = {"dark": "#35a06a", "light": "#2f9e6f"}

# Corner radius presets: (extra small, small, large) in px
RADIUS_SCALES = {
    "compact": (3, 4, 6),
    "default": (4, 6, 8),
    "round": (6, 9, 12),
}
DEFAULT_RADIUS = "default"
DEFAULT_FONT = "Microsoft YaHei UI"
FONT_FALLBACKS = '"Segoe UI", "Microsoft YaHei", sans-serif'

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalize_hex(value: str | None) -> str | None:
    """Return "#rrggbb" for a user supplied color, or None when it is not a valid hex color."""
    if not value:
        return None
    match = _HEX_RE.match(str(value).strip())
    if match is None:
        return None
    return "#" + match.group(1).lower()


def _mix(color: str, target: str, ratio: float) -> str:
    """Blend color toward target by ratio (0..1)."""
    base = normalize_hex(color) or "#000000"
    other = normalize_hex(target) or "#000000"
    out = []
    for index in (1, 3, 5):
        left = int(base[index : index + 2], 16)
        right = int(other[index : index + 2], 16)
        out.append(round(left + (right - left) * ratio))
    return "#" + "".join(f"{value:02x}" for value in out)


def _lighten(color: str, ratio: float) -> str:
    return _mix(color, "#ffffff", ratio)


def _darken(color: str, ratio: float) -> str:
    return _mix(color, "#000000", ratio)


def _relative_luminance(color: str) -> float:
    base = normalize_hex(color) or "#000000"
    channels = []
    for index in (1, 3, 5):
        value = int(base[index : index + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two hex colours."""
    light, dark = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (light + 0.05) / (dark + 0.05)


def readable_fill(accent: str, target: float = 4.5) -> str:
    """Darken an accent until white text on it reaches the WCAG AA contrast target.

    Filled elements that carry white text (primary buttons, chips) use this shade;
    the pure accent stays for borders, pills and other non-text accents.
    """
    shade = accent
    for step in range(61):
        if contrast_ratio("#ffffff", shade) >= target:
            return shade
        shade = _darken(accent, step / 100)
    return shade


def accent_palette(theme: str, accent: str | None = None) -> dict[str, str]:
    """All accent-derived colors used by the style sheets.

    Keys map onto the __ACCENT*__ placeholders inside the QSS files, so a user
    supplied hex color re-tints buttons, selections, chips and cards at once.
    """
    base = normalize_hex(accent) or DEFAULT_ACCENTS.get(theme, DEFAULT_ACCENTS["dark"])
    if theme == "light":
        button = readable_fill(base)
        return {
            "ACCENT": base,
            "ACCENT_BUTTON": button,
            "ACCENT_BUTTON_HOVER": _lighten(button, 0.10),
            "ACCENT_BUTTON_PRESS": _darken(button, 0.12),
            "ACCENT_HOVER": _lighten(base, 0.10),
            "ACCENT_PRESS": _darken(base, 0.12),
            "ACCENT_SEL": _lighten(base, 0.80),
            "ACCENT_SEL_TEXT": _darken(base, 0.62),
            "ACCENT_SOFT": _lighten(base, 0.82),
            "ACCENT_TINT": _lighten(base, 0.90),
        }
    button = readable_fill(base)
    return {
        "ACCENT": base,
        "ACCENT_BUTTON": button,
        "ACCENT_BUTTON_HOVER": _lighten(button, 0.10),
        "ACCENT_BUTTON_PRESS": _darken(button, 0.12),
        "ACCENT_HOVER": _lighten(base, 0.14),
        "ACCENT_PRESS": _darken(base, 0.16),
        "ACCENT_SEL": _darken(base, 0.20),
        "ACCENT_SEL_TEXT": "#ffffff",
        "ACCENT_SOFT": _darken(base, 0.68),
        "ACCENT_TINT": _darken(base, 0.80),
    }


def font_stack(family: str | None = None) -> str:
    """Font-family value for the QSS: the chosen family first, then safe fallbacks."""
    name = (family or "").strip() or DEFAULT_FONT
    return f'"{name}", {FONT_FALLBACKS}'


def system_theme() -> str:
    """The OS colour preference: Windows light/dark setting, dark elsewhere."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(value) else "dark"
    except Exception:  # noqa: BLE001 - any failure means "no preference available"
        return "dark"


def resolve_theme(theme: str) -> str:
    """Turn the configured theme into a concrete one ("system" follows the OS)."""
    return system_theme() if theme == "system" else theme


def radius_scale(radius: str | None) -> tuple[int, int, int]:
    return RADIUS_SCALES.get(radius or DEFAULT_RADIUS, RADIUS_SCALES[DEFAULT_RADIUS])


def apply_theme(
    theme: str,
    accent: str | None = None,
    font: str | None = None,
    radius: str | None = None,
) -> None:
    """Apply the theme; "system" follows the OS light/dark preference."""
    app = QApplication.instance()
    if app is None:
        return
    theme = resolve_theme(theme)
    filename = "style_light.qss" if theme == "light" else "style.qss"
    path = paths.resource_path("gui/resources/" + filename)
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # url() in QSS cannot reliably resolve relative paths: replace with the image's absolute path when loading
    arrow = "down_arrow_light.png" if theme == "light" else "down_arrow.png"
    arrow_path = paths.resource_path("gui/resources/" + arrow)
    text = text.replace("__DOWN_ARROW__", arrow_path.as_posix())
    check_path = paths.resource_path("gui/resources/check.png")
    text = text.replace("__CHECK__", check_path.as_posix())
    text = text.replace("__FONT__", font_stack(font))
    palette = accent_palette(theme, accent)
    # longest placeholders first so __ACCENT__ never eats the prefixed variants
    for key in sorted(palette, key=len, reverse=True):
        text = text.replace(f"__{key}__", palette[key])
    extra_small, small, large = radius_scale(radius)
    text = text.replace("__RADIUS_XS__", f"{extra_small}px")
    text = text.replace("__RADIUS_SM__", f"{small}px")
    text = text.replace("__RADIUS_LG__", f"{large}px")
    app.setStyleSheet(text)
