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

from PySide6.QtGui import QColor, QPalette
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
# 韩文(Hangul)与日文需要在链里各有一个覆盖字体:雅黑只有简体字形,Segoe UI 只有拉丁/西里尔,
# 末尾的 sans-serif 在中文 Windows 上会映射回雅黑 —— 缺了这两项,韩语界面会整片显示成方块
FONT_FALLBACKS = '"Segoe UI", "Malgun Gothic", "Yu Gothic UI", "Microsoft YaHei", sans-serif'

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
            "ACCENT_HOVER": _darken(button, 0.10),
            "ACCENT_SEL": _lighten(base, 0.68),  # a real step below ACCENT_SOFT (0.82), not a 2-point one
            "ACCENT_SEL_TEXT": _darken(base, 0.72),
            "ACCENT_SOFT": _lighten(base, 0.82),
            "ACCENT_TINT": _lighten(base, 0.90),
            "FOCUS_RING": button,
        }
    button = readable_fill(base)
    return {
        "ACCENT": base,
        "ACCENT_BUTTON": button,
        "ACCENT_BUTTON_HOVER": _lighten(button, 0.10),
        "ACCENT_BUTTON_PRESS": _darken(button, 0.12),
        "ACCENT_HOVER": _darken(button, 0.10),
        "ACCENT_SEL": _darken(base, 0.20),
        "ACCENT_SEL_TEXT": "#ffffff",
        "ACCENT_SOFT": _darken(base, 0.68),
        "ACCENT_TINT": _darken(base, 0.80),
        "FOCUS_RING": base,
    }



# Neutral / semantic palette: one entry per role, one value per theme. Together with
# accent_palette() these are the only colours the QSS files may reference, through __TOKEN__
# placeholders; both sheets are checked to hold no colour literals by tests/test_qss_tokens.py.
NEUTRAL_TOKENS: dict[str, dict[str, str]] = {
    "BG_BUTTON_ICON": {"dark": "#1c2531", "light": "#eef0f4"},
    "BG_BUTTON_ICON_2": {"dark": "#161d27", "light": "#e2e6ec"},
    "BG_BUTTON_SECONDARY": {"dark": "#1c2531", "light": "#f1f3f6"},
    "BG_BUTTON_SECONDARY_2": {"dark": "#161d27", "light": "#e2e6ec"},
    "BG_DISABLED": {"dark": "#131a23", "light": "#f4f6f9"},
    "BG_DISABLED_2": {"dark": "#232c39", "light": "#d8dee6"},
    # dark rows hover with this; the light sheet uses ACCENT_TINT instead, so the light value
    # was a copy of the dark one that no rule could reach (FG_TEXT on it read 1.06:1).
    "BG_HOVER": {"dark": "#1c2531", "light": "#e6eaf0"},
    "BG_LIST": {"dark": "#161d27", "light": "#ffffff"},
    "BG_LIST_2": {"dark": "#1c2531", "light": "#ffffff"},
    "BG_OPTION": {"dark": "#161d27", "light": "#f1f3f6"},
    "BG_OVERLAY_CODE": {"dark": "#2a1a1e", "light": "#fdecea"},
    "BG_RAIL_DOT": {"dark": "#33404f", "light": "#b6c1cd"},
    "BG_SCROLLBAR": {"dark": "#6d7f95", "light": "#8a96a3"},
    "BG_SECTION": {"dark": "#1c2531", "light": "#f1f3f6"},
    "BG_SEPARATOR": {"dark": "#27303d", "light": "#dfe4ea"},
    "BG_SIDEBAR": {"dark": "#1c2531", "light": "#e7ebf0"},
    "BG_TITLEBAR_CLOSE": {"dark": "#cf3f3f", "light": "#cf3f3f"},
    "BG_TITLEBAR_MINIMIZE": {"dark": "#1c2531", "light": "#dfe4ea"},
    "BG_WINDOW": {"dark": "#0f141b", "light": "#fafbfc"},
    "BORDER_BUTTON_ICON": {"dark": "#27303d", "light": "#c9d2dc"},
    "BORDER_BUTTON_SECONDARY": {"dark": "#33404f", "light": "#b6c1cd"},
    "BORDER_BUTTON_SECONDARY_2": {"dark": "#232c39", "light": "#d8dee6"},
    "BORDER_HOVER": {"dark": "#33404f", "light": "#a7b4c2"},
    "BORDER_LIST": {"dark": "#27303d", "light": "#c9d2dc"},
    "BORDER_OVERLAY_CODE": {"dark": "#e5787f", "light": "#e5787f"},
    "BORDER_SWATCH": {"dark": "#3a4757", "light": "#b6c1cd"},
    "BORDER_TABLE": {"dark": "#212a36", "light": "#dfe4ea"},
    "DANGER_BG": {"dark": "#2a1a1e", "light": "#fbeceb"},
    "DANGER_BG_2": {"dark": "#221317", "light": "#f5ddda"},
    "DANGER_BORDER": {"dark": "#6d3a40", "light": "#e0b3ad"},
    "DANGER_BORDER_2": {"dark": "#e5787f", "light": "#b03a2e"},
    "DANGER_BORDER_3": {"dark": "#3a2a2d", "light": "#eddad7"},
    "DANGER_FG": {"dark": "#e5787f", "light": "#b03a2e"},
    "DANGER_FG_2": {"dark": "#7a5a5e", "light": "#c39a95"},
    "FG_BUTTON_SECONDARY": {"dark": "#b9c6d6", "light": "#33475c"},
    "FG_CARD_LATEST": {"dark": "#ffffff", "light": "#1f2a36"},
    "FG_DISABLED": {"dark": "#6b7c92", "light": "#9aa5b1"},
    "FG_DISABLED_2": {"dark": "#6b7c92", "light": "#78838f"},
    "FG_EMPTY_STATE": {"dark": "#7b8ca3", "light": "#677585"},
    "FG_HINT": {"dark": "#8fa2b8", "light": "#4f6070"},
    "FG_OPTION": {"dark": "#d8dee9", "light": "#26313d"},
    "FG_OPTION_2": {"dark": "#ffffff", "light": "#14503a"},
    "FG_OVERLAY_BODY": {"dark": "#d7e0ec", "light": "#1f2a36"},
    "FG_OVERLAY_CODE": {"dark": "#ffffff", "light": "#8c1d18"},
    "FG_PAGE_TITLE": {"dark": "#eef3fa", "light": "#16202b"},
    "FG_RAIL_ITEM": {"dark": "#7b8ca3", "light": "#5b6a7b"},
    "FG_SELECTED": {"dark": "#ffffff", "light": "#ffffff"},
    "FG_STATUS_WARNING": {"dark": "#e5c07b", "light": "#87691b"},
    "FG_TEXT": {"dark": "#e6ecf5", "light": "#1f2a36"},
}


def theme_palette(theme: str, accent: str | None = None) -> dict[str, str]:
    """Every __TOKEN__ value for one theme: the neutral table plus the accent family."""
    palette = {name: values.get(theme, values["dark"]) for name, values in NEUTRAL_TOKENS.items()}
    palette.update(accent_palette(theme, accent))
    return palette


# QPalette roles the stylesheet cannot reach.
#
# The QSS paints the widgets we wrote, but Qt still draws some surfaces itself: the frame and base of a
# native popup, menu shadows, the viewport inside a platform-drawn container, disabled text, the 3D
# shades. Those come from the application palette, and the palette the platform hands us follows the
# *system* colour scheme - on a dark-mode Windows that is a dark palette. A light QSS over a dark palette
# therefore painted dark surfaces wherever the stylesheet stopped, which is exactly what the user saw:
# "the light theme is inexplicably ugly", wrong page and dropdown backgrounds, a see-through wizard.
# The mapping below derives every role from the same tokens the QSS uses, so there is still exactly one
# source of truth for colour.
PALETTE_ROLES = {
    "Window": "BG_WINDOW",
    "WindowText": "FG_TEXT",
    "Base": "BG_LIST",
    "AlternateBase": "BG_LIST_2",
    "Text": "FG_TEXT",
    "Button": "BG_BUTTON_SECONDARY",
    "ButtonText": "FG_TEXT",
    "BrightText": "FG_PAGE_TITLE",
    "Highlight": "ACCENT_SEL",
    "HighlightedText": "ACCENT_SEL_TEXT",
    "ToolTipBase": "BG_LIST_2",
    "ToolTipText": "FG_TEXT",
    "PlaceholderText": "FG_HINT",
    "Link": "ACCENT",
    # The 3D-shade roles (Light/Midlight/Mid/Dark/Shadow) are deliberately not mapped: they paint frame
    # edges and container backgrounds with hardcoded light/dark offsets relative to Button, which showed
    # up as wrong panel backgrounds on the mods page. Qt falls back to its own derivation there, which is
    # what the light theme looked like before. The roles above are the ones the bug actually needed.
}

PALETTE_DISABLED = {
    "Window": "BG_DISABLED",
    "Base": "BG_DISABLED",
    "Button": "BG_DISABLED",
    "WindowText": "FG_DISABLED",
    "Text": "FG_DISABLED",
    "ButtonText": "FG_DISABLED",
    "Highlight": "BG_DISABLED_2",
    "HighlightedText": "FG_DISABLED_2",
}


def theme_qpalette(theme: str, accent: str | None = None) -> QPalette:
    """The application palette for one theme, built from the same tokens as the QSS.

    ``setColor(role, colour)`` fills every colour group, so an unfocused window keeps the same colours as
    a focused one - the platform default dims text in inactive windows, which in a themed window reads as
    "the background changed when I clicked away". The disabled group is then overridden explicitly.
    """
    tokens = theme_palette(theme, accent)
    palette = QPalette()
    for role_name, token in PALETTE_ROLES.items():
        role = getattr(QPalette.ColorRole, role_name, None)
        if role is not None:
            palette.setColor(role, QColor(tokens[token]))
    for role_name, token in PALETTE_DISABLED.items():
        role = getattr(QPalette.ColorRole, role_name, None)
        if role is not None:
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(tokens[token]))
    # Qt 6.6 added an Accent role; older builds simply do not have it.
    accent_role = getattr(QPalette.ColorRole, "Accent", None)
    if accent_role is not None:
        palette.setColor(accent_role, QColor(tokens["ACCENT"]))
    return palette

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


# The (application, theme, accent, font, radius, device scale) last handed to setStyleSheet.
_last_applied: tuple[int, str, str, str, str, int] | None = None

# The token table (role -> colour) behind the stylesheet currently in force. Widgets that must
# style themselves - because the application stylesheet is not adopted for them on every
# platform - read their colours from here, so colour still has exactly one source of truth.
_last_tokens: dict[str, str] = {}


def current_tokens() -> dict[str, str]:
    """The token values last applied; empty before the first apply_theme call."""
    return dict(_last_tokens)


def device_scale(app: QApplication) -> int:
    """The screen's device pixel ratio, clamped to the asset multiples we ship (1x/2x/3x)."""
    screen = app.primaryScreen()
    ratio = float(screen.devicePixelRatio()) if screen is not None else 1.0
    return max(1, min(3, round(ratio)))


def glyph_path(name: str, scale: int) -> str:
    """Absolute path of the crispest glyph for this screen.

    The small geometric glyphs (combo arrow, spin arrows, checkbox tick) ship as @2x/@3x bitmaps that
    tools/gen_ui_assets.py *draws* at that size. The stylesheet keeps the logical box, so on a 200%
    screen the @2x bitmap maps 1:1 onto the device grid instead of a 10x6 bitmap being stretched.
    """
    if scale > 1:
        candidate = paths.resource_path(f"gui/resources/{name}@{scale}x.png")
        if candidate.exists():
            return candidate.as_posix()
    return paths.resource_path(f"gui/resources/{name}.png").as_posix()


def apply_theme(
    theme: str,
    accent: str | None = None,
    font: str | None = None,
    radius: str | None = None,
) -> None:
    """Apply the theme; "system" follows the OS light/dark preference.

    Re-applying a stylesheet that is already in force is skipped deliberately. ``setStyleSheet`` makes
    Qt re-polish every widget in the application, and that cost *accumulates*: measured in a clean
    process with a single window, eight consecutive calls took 0.06s, 0.25s, 0.42s, 0.42s, 0.44s,
    1.72s, 2.16s. The settings page saves on every control change and re-applies the theme each time,
    so without this guard a session that touches a few settings pays seconds per change - and the test
    suite, which drives those saves, spends minutes in it.
    """
    global _last_applied, _last_tokens
    app = QApplication.instance()
    if app is None:
        return
    theme = resolve_theme(theme)
    scale = device_scale(app)
    key = (id(app), theme, accent or "", font or "", radius or "", scale)
    if key == _last_applied:
        return
    filename = "style_light.qss" if theme == "light" else "style.qss"
    path = paths.resource_path("gui/resources/" + filename)
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    # url() in QSS cannot reliably resolve relative paths: replace with the image's absolute path when
    # loading, choosing the bitmap that matches this screen's scaling (see glyph_path).
    suffix = "_light" if theme == "light" else ""
    # Rolled back at the user's request: pick the plain 1x bitmaps again. The @2x/@3x variants and their
    # generator stay in the tree (tests/test_ui_assets.py still guards them), they are simply unused.
    text = text.replace("__DOWN_ARROW__", paths.resource_path(f"gui/resources/down_arrow{suffix}.png").as_posix())
    text = text.replace("__SPIN_UP__", paths.resource_path(f"gui/resources/spin_up{suffix}.png").as_posix())
    text = text.replace("__SPIN_DOWN__", paths.resource_path(f"gui/resources/spin_down{suffix}.png").as_posix())
    text = text.replace("__CHECK__", paths.resource_path("gui/resources/check.png").as_posix())
    text = text.replace("__FONT__", font_stack(font))
    palette = theme_palette(theme, accent)
    # longest placeholders first so __ACCENT__ never eats the prefixed variants
    for token in sorted(palette, key=len, reverse=True):
        text = text.replace(f"__{token}__", palette[token])
    extra_small, small, large = radius_scale(radius)
    text = text.replace("__RADIUS_XS__", f"{extra_small}px")
    text = text.replace("__RADIUS_SM__", f"{small}px")
    text = text.replace("__RADIUS_LG__", f"{large}px")
    # NOTE: do not "clear first" here. `setStyleSheet("")` + `setStyleSheet(text)` is much faster (it puts
    # Qt back on a cheap path: about 0.2s per theme switch instead of ~5.8s once the cost has accumulated),
    # but the 0.4.0 build shipped unstyled widgets because of it: dropdown arrows and several page
    # backgrounds came out wrong and the first-run wizard was see-through. The offscreen renderer applies
    # the theme once and never reproduced it, so it reached the user before anyone saw it here.
    # The identical-apply guard below is safe and stays; clearing the application style is not.
    # The palette covers the surfaces Qt draws itself (native popup frames, menu shadows, platform-drawn
    # viewports, disabled text); the stylesheet covers the widgets we wrote. Both come from the same tokens.
    app.setPalette(theme_qpalette(theme, accent))
    # Publish the tokens before the sheet: a widget that reacts to StyleChange reads them there.
    _last_tokens = dict(palette)
    app.setStyleSheet(text)
    _last_applied = key
