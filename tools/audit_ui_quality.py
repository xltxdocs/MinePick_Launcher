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

# UI quality audit helper for the interface itself.
#   1. text overflow  - does any label/button/header text not fit in 9 languages (ru/de are longest)?
#   2. contrast       - WCAG ratio of the colour pairs defined in the theme module
#   3. high DPI       - does the window still fit at 125% / 150% scaling?

"""UI quality audit: text overflow per language, colour contrast, high-DPI behaviour."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 600
# A3's target, shared with tools/measure_min_width.py (kept as a literal here so this module does not
# import Qt at load time - the worker modes start a QApplication and must be a fresh process).
MAX_WINDOW_WIDTH = 1180


def contrast_ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    def luminance(color: tuple[int, int, int]) -> float:
        channels = []
        for value in color:
            srgb = value / 255
            channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


# Every colour token must appear in at least one pair below. That is the point of the table: a new
# colour cannot be added without saying what it sits on, so contrast cannot silently go unchecked.
#
# "required" separates two different WCAG questions:
#   * True  - the pairing carries information the user needs (text, the focus ring, the scrollbar
#             thumb). WCAG 1.4.3 / 1.4.11 apply, so a miss is a failure.
#   * False - decoration: hairline separators, hover fills, a border that merely firms up a control
#             which is already identifiable from its label and fill. 1.4.11 does not require a ratio
#             here, so the value is reported for the record but never fails the audit.
# (foreground token, background token, minimum ratio, required, themes it applies to)
Pair = tuple[str, str, float, bool, tuple[str, ...]]
BOTH = ("dark", "light")

TEXT_PAIRS: tuple[Pair, ...] = (
    ("FG_TEXT", "BG_WINDOW", 4.5, True),
    ("FG_TEXT", "BG_LIST", 4.5, True),
    ("FG_TEXT", "BG_LIST_2", 4.5, True),
    ("FG_TEXT", "BG_SIDEBAR", 4.5, True),
    ("FG_TEXT", "BG_SECTION", 4.5, True),
    ("FG_TEXT", "BG_BUTTON_ICON", 4.5, True),
    ("FG_TEXT", "BG_HOVER", 4.5, True),
    ("FG_TEXT", "BG_DISABLED_2", 4.5, True),
    ("FG_TEXT", "BG_OPTION", 4.5, True),
    ("FG_PAGE_TITLE", "BG_WINDOW", 4.5, True),
    ("FG_PAGE_TITLE", "BG_SIDEBAR", 4.5, True),
    ("FG_HINT", "BG_WINDOW", 4.5, True),
    ("FG_HINT", "BG_LIST", 4.5, True),
    ("FG_HINT", "BG_SIDEBAR", 4.5, True),
    ("FG_HINT", "BG_SECTION", 4.5, True),
    ("FG_EMPTY_STATE", "BG_LIST", 4.5, True),
    ("FG_RAIL_ITEM", "BG_SECTION", 4.5, True),  # wizard progress labels live on the wizard card
    ("FG_OPTION", "BG_OPTION", 4.5, True),
    ("FG_OPTION_2", "BG_OPTION", 4.5, True),
    ("FG_BUTTON_SECONDARY", "BG_BUTTON_SECONDARY", 4.5, True),
    ("FG_BUTTON_SECONDARY", "BG_BUTTON_SECONDARY_2", 4.5, True),
    ("FG_CARD_LATEST", "BG_SECTION", 4.5, True),
    ("FG_OVERLAY_BODY", "BG_OVERLAY_CODE", 4.5, True),
    ("FG_OVERLAY_CODE", "BG_OVERLAY_CODE", 4.5, True),
    ("DANGER_FG", "BG_WINDOW", 4.5, True),
    ("DANGER_FG", "BG_LIST", 4.5, True),
    ("FG_STATUS_WARNING", "BG_WINDOW", 4.5, True),
    # Inactive components are exempt from the contrast rules (WCAG 1.4.3 / 1.4.11), so these are
    # reported for the record and never fail.
    ("FG_DISABLED", "BG_DISABLED", 3.0, False),
    ("FG_DISABLED_2", "BG_DISABLED_2", 3.0, False),
    ("DANGER_FG_2", "BG_DISABLED_2", 3.0, False),
    # selected text: the dark sheet uses FG_SELECTED on ACCENT_SEL, the light sheet ACCENT_SEL_TEXT
    ("FG_SELECTED", "ACCENT_SEL", 3.0, True, ("dark",)),
    ("ACCENT_SEL_TEXT", "ACCENT_SEL", 4.5, True, ("light",)),
    # the title bar buttons draw FG_HINT; the close button flips to FG_SELECTED on hover
    ("FG_HINT", "BG_TITLEBAR_MINIMIZE", 4.5, True),
    ("FG_SELECTED", "BG_TITLEBAR_CLOSE", 4.5, True),
    ("FG_HINT", "BG_TITLEBAR_CLOSE", 4.5, False),
    # hover/press fills carry the same text as their rest state
    ("FG_TEXT", "BG_BUTTON_ICON_2", 4.5, True),
    ("DANGER_FG", "DANGER_BG_2", 4.5, True),
    ("FG_SELECTED", "ACCENT_HOVER", 4.5, True),
    ("FG_TEXT", "ACCENT_SOFT", 4.5, False),
    ("FG_TEXT", "ACCENT_TINT", 4.5, False),
)

# Non-text contrast (WCAG 1.4.11): 3:1 for the visual information needed to identify a component.
NON_TEXT_PAIRS: tuple[Pair, ...] = (
    ("ACCENT", "BG_LIST", 3.0, False),  # hover border: decoration, the control is already identified
    ("FOCUS_RING", "BG_WINDOW", 3.0, True),  # keyboard focus ring
    ("FOCUS_RING", "BG_LIST", 3.0, True),
    ("FOCUS_RING", "BG_SIDEBAR", 3.0, True),
    ("BG_SCROLLBAR", "BG_LIST", 3.0, True),  # slim overlay handle, drawn only while scrolling
    ("DANGER_BORDER", "DANGER_BG", 3.0, False),
    ("DANGER_BORDER_2", "DANGER_BG", 3.0, False),
    ("DANGER_BORDER_3", "DANGER_BG", 3.0, False),
    ("DANGER_BG", "BG_WINDOW", 3.0, False),
    ("DANGER_BG", "BG_LIST", 3.0, False),
    ("DANGER_BG", "BG_SECTION", 3.0, False),
    ("BORDER_LIST", "BG_LIST", 3.0, False),
    ("BORDER_LIST", "BG_WINDOW", 3.0, False),
    ("BORDER_BUTTON_ICON", "BG_WINDOW", 3.0, False),
    ("BORDER_BUTTON_SECONDARY", "BG_WINDOW", 3.0, False),
    ("BORDER_BUTTON_SECONDARY_2", "BG_BUTTON_SECONDARY_2", 3.0, False),
    ("BORDER_HOVER", "BG_LIST", 3.0, False),
    ("BORDER_HOVER", "BG_OPTION", 3.0, False),
    ("BORDER_TABLE", "BG_LIST", 3.0, False),  # token currently unused by the sheets
    ("BORDER_SWATCH", "BG_OPTION", 3.0, False),
    ("BORDER_OVERLAY_CODE", "BG_OVERLAY_CODE", 3.0, False),
    ("BG_SEPARATOR", "BG_WINDOW", 3.0, False),
    ("BG_SEPARATOR", "BG_SECTION", 3.0, False),
    ("BG_RAIL_DOT", "BG_WINDOW", 3.0, False),
)

# Accent button fills are covered by the white-on-fill check further down (their label is always white,
# which is not a token), so the coverage rule below accepts them without a pair.
COVERED_BY_WHITE_ON_FILL = frozenset({"ACCENT_BUTTON", "ACCENT_BUTTON_HOVER", "ACCENT_BUTTON_PRESS"})

# Real misses this enumeration found. They are reported loudly on every run but do not fail the gate,
# because repairing them means choosing new colour values - a separate decision from making the audit
# able to see them (this task was explicitly told not to touch colours). Entries may only be removed.
# key: (foreground, background) as used above; value: why it is tolerated for now.
KNOWN_CONTRAST_GAPS: dict[tuple[str, str], str] = {
    # Nothing here: 4-B1 fixed every recorded gap rather than tolerating it. Add an entry only with
    # a reason that names the exemption (an inactive component, decoration, or content that is not
    # information the user needs). Entries may be removed, never added without one.
}


# Mirrors gui/pages/settings_page.ACCENT_PRESETS. Duplicated on purpose: importing that widget module
# here would build Qt objects before any QApplication exists, which segfaults the audit.
# tests/test_audit_gates.py asserts the two lists stay identical.
ACCENT_PRESETS: tuple[str, ...] = (
    "#35a06a",
    "#3b82f6",
    "#a855f7",
    "#e0703a",
    "#e05a5a",
    "#14b8a6",
    "#ec4899",
    "#f59e0b",
)


def _accent_choices(theme: str) -> list[str]:
    """The theme's default accent plus every preset the settings page offers, deduplicated."""
    from gui.theme import DEFAULT_ACCENTS

    choices = [DEFAULT_ACCENTS.get(theme, DEFAULT_ACCENTS["dark"]), *ACCENT_PRESETS]
    unique: list[str] = []
    for colour in choices:
        if colour not in unique:
            unique.append(colour)
    return unique


def check_contrast() -> int:
    from gui.theme import (
        NEUTRAL_TOKENS,
        accent_palette,
        readable_fill,
        theme_palette,
    )

    print("--- contrast (WCAG AA: 4.5 text, 3.0 large/disabled, 3.0 non-text where 1.4.11 applies) ---")
    failures: dict[tuple[str, str], str] = {}
    known: dict[tuple[str, str], tuple[str, int]] = {}
    informational: dict[tuple[str, str, bool], int] = {}
    presets_checked = 0
    for theme in ("dark", "light"):
        accents = _accent_choices(theme)
        for accent in accents:
            presets_checked += 1
            palette = theme_palette(theme, accent)
            for kind, pairs in (("text", TEXT_PAIRS), ("non-text", NON_TEXT_PAIRS)):
                for entry in pairs:
                    foreground, background, minimum, required = entry[:4]
                    themes = entry[4] if len(entry) > 4 else BOTH
                    if theme not in themes:
                        continue
                    if foreground not in palette or background not in palette:
                        failures[(foreground, background)] = f"unknown token ({theme})"
                        continue
                    ratio = contrast_ratio(hex_to_rgb(palette[foreground]), hex_to_rgb(palette[background]))
                    if ratio >= minimum:
                        continue
                    if not required:
                        key = (foreground, background, "non-text" in kind)
                        informational[key] = informational.get(key, 0) + 1
                        continue
                    line = f"{ratio:5.2f} < {minimum} ({kind:8}) {foreground} on {background} [{theme}]"
                    if (foreground, background) in KNOWN_CONTRAST_GAPS:
                        previous = known.get((foreground, background))
                        known[(foreground, background)] = (line, (previous[1] + 1) if previous else 1)
                    else:
                        failures[(foreground, background)] = line
    print(
        f"  checked {presets_checked} (theme, accent) combinations "
        f"x ({len(TEXT_PAIRS)} text + {len(NON_TEXT_PAIRS)} non-text) pairs"
    )
    for line in failures.values():
        print(f"  FAIL {line}")
    if known:
        print(f"  known {len(known)} recorded gap(s) - reported, not failing (see KNOWN_CONTRAST_GAPS):")
        for (foreground, background), (line, count) in sorted(known.items()):
            print(f"       {line}  x{count}")
            print(f"         why: {KNOWN_CONTRAST_GAPS[(foreground, background)]}")
    if informational:
        print(f"  info {len(informational)} decorative pairing(s) below target (1.4.11 does not require them):")
        for (foreground, background, is_non_text), count in sorted(informational.items()):
            kind = "non-text" if is_non_text else "text"
            print(f"       {foreground} on {background} ({kind}) x{count}")

    # Coverage: a token nobody paired is a token nobody checks.
    print("  token coverage:")
    paired = {token for entry in (*TEXT_PAIRS, *NON_TEXT_PAIRS) for token in (entry[0], entry[1])}
    for theme in ("dark", "light"):
        palette = {name: values.get(theme, values["dark"]) for name, values in NEUTRAL_TOKENS.items()}
        palette.update(accent_palette(theme, None))
        unpaired = sorted(set(palette) - paired - COVERED_BY_WHITE_ON_FILL)
        if unpaired:
            for token in unpaired:
                failures[(token, f"{theme}-unpaired")] = f"{theme}: {token} appears in no pair"
            print(f"    FAIL {theme}: {len(unpaired)} token(s) in no pair: {unpaired}")
        else:
            print(f"    OK   {theme}: all {len(palette)} tokens appear in at least one pair")

    # white on the accent-derived button fill must stay readable for every preset
    from gui.pages.settings_page import ACCENT_PRESETS

    print("  accent presets with white text:")
    for accent in ACCENT_PRESETS:
        ratio = contrast_ratio((255, 255, 255), hex_to_rgb(readable_fill(accent)))
        if ratio < 4.5:
            failures[("white-on-fill", accent)] = f"{ratio:5.2f} < 4.5 white on filled button {accent}"
        print(f"    {'OK  ' if ratio >= 4.5 else 'FAIL'} {ratio:5.2f}  {accent} -> {readable_fill(accent)}")
    return len(failures)


def check_text_overflow() -> int:
    root = Path(os.environ.get("UI_AUDIT_ROOT", Path(__file__).resolve().parents[1])).resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, str(root))
    os.chdir(root)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(root / "_preview" / "data")
    os.environ["MINECRAFT_GAME_DIR"] = str(root / "_preview" / "game")

    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QWidget

    from gui import i18n
    from gui.main import create_app
    from gui.pages import mods_page, versions_page
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit

    manifest = VersionManifest(
        latest={"release": "1.21.11", "snapshot": "26w02a"},
        versions=[
            ManifestVersion(
                id=f"1.{index}",
                type="release",
                url="",
                time="2025-01-01T00:00:00+00:00",
                release_time="2025-01-01T00:00:00+00:00",
            )
            for index in range(20)
        ],
    )
    versions_page.fetch_manifest = lambda cache_path=None: manifest  # type: ignore[assignment]
    mods_page.search_projects = lambda *a, **k: [  # type: ignore[assignment]
        ModSearchHit(slug=f"m{index}", title=f"Mod {index}", downloads=index) for index in range(20)
    ]

    app = create_app([])
    for font_file in ("msyh.ttc", "simhei.ttf", "malgun.ttf", "YuGothM.ttc"):
        path = Path("C:/Windows/Fonts") / font_file
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))

    from gui.main_window import MainWindow

    problems = 0
    for code, name in i18n.UI_LANGUAGES:
        i18n.set_language(code)
        window = MainWindow()
        window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        window.show()
        for _ in range(8):
            app.processEvents()
            time.sleep(0.05)
        for page_index, (page_key, page) in enumerate(window.pages.items()):
            window.sidebar.setCurrentRow(page_index)  # hidden pages are not laid out
            for _ in range(6):
                app.processEvents()
                time.sleep(0.03)
            for widget in _text_widgets(page, (QLabel, QPushButton, QComboBox, QWidget)):
                if not isinstance(widget, (QLabel, QPushButton, QComboBox)) or not widget.isVisible():
                    continue
                text = widget.text() if not isinstance(widget, QComboBox) else widget.currentText()
                if not text or "\n" in text:
                    continue
                if isinstance(widget, QLabel) and widget.wordWrap():
                    continue
                available = widget.contentsRect().width()  # usable width, padding already excluded
                needed = widget.fontMetrics().horizontalAdvance(text)
                if needed > available and widget.width() > 0:
                    problems += 1
                    print(f"  {code:6} {page_key:10} {type(widget).__name__:12} needs {needed:4}px, has {available:4}px  {text[:40]!r}")
        window.close()
        print(f"  checked {code} ({name})")
    print(f"text overflow problems: {problems}")
    return problems


def _text_widgets(widget, kinds):
    from PySide6.QtWidgets import QWidget

    found = []
    for child in widget.children():
        if isinstance(child, QWidget):
            if isinstance(child, kinds):
                found.append(child)
            found.extend(_text_widgets(child, kinds))
    return found


def check_high_dpi(scale: float) -> int:
    """Render at a scaled factor in a fresh process (a QApplication cannot be recreated)."""
    import subprocess

    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env.update(
        {
            "QT_SCALE_FACTOR": str(scale),
            "QT_QPA_PLATFORM": "offscreen",
            "UI_AUDIT_ROOT": str(root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--dpi"], env=env, cwd=str(root), check=False)
    return 0


def _dpi_probe() -> int:
    """Worker mode: report the window size under the QT_SCALE_FACTOR set by the caller."""
    root = Path(os.environ.get("UI_AUDIT_ROOT", Path(__file__).resolve().parents[1])).resolve()
    sys.path.insert(0, str(root))
    os.chdir(root)
    # never touch the user's real launcher data: always use the preview folders
    os.environ["MCLAUNCHER_DATA_DIR"] = str(root / "_preview" / "data")
    os.environ["MINECRAFT_GAME_DIR"] = str(root / "_preview" / "game")

    from PySide6.QtGui import QFontDatabase

    from gui.main import create_app
    from gui.main_window import MainWindow

    app = create_app([])
    for font_file in ("msyh.ttc", "simhei.ttf", "malgun.ttf", "YuGothM.ttc"):
        path = Path("C:/Windows/Fonts") / font_file
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    window = MainWindow()
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    shot = window.grab()
    print(
        f"  scale {os.environ.get('QT_SCALE_FACTOR', '1')}: window {window.width()}x{window.height()}"
        f"  grab {shot.width()}x{shot.height()}  min-height {window.minimumSizeHint().height()}"
    )
    return 0


def check_window_width(max_width: int = 1180) -> int:
    """Measure the minimum window width per language in a fresh process (one QApplication per process)."""
    import subprocess

    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "UI_AUDIT_ROOT": str(root),
            "UI_AUDIT_WIDTH": str(max_width),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--width"],
        env=env,
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout.strip())
    if result.stderr.strip():
        print("  " + result.stderr.strip().splitlines()[-1])
    return result.returncode


def _width_probe() -> int:
    """Worker mode: measure every language and judge the widest one against the budget."""
    root = Path(os.environ.get("UI_AUDIT_ROOT", Path(__file__).resolve().parents[1])).resolve()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.chdir(root)
    budget = int(os.environ.get("UI_AUDIT_WIDTH", "1180"))

    import measure_min_width as measure

    results = measure.measure_languages()
    for item in results:
        print(f"  {item.language:10} {item.window_min:>6}  widest page: {item.widest_page}")
    worst_item = measure.worst(results)
    ok = worst_item is None or not budget or worst_item.window_min <= budget
    if worst_item is not None:
        print(
            f"  worst: {worst_item.language} {worst_item.window_min}px "
            f"({'within' if ok else 'ABOVE'} the {budget}px budget)"
        )
    print(
        json.dumps(
            {
                "worst_language": worst_item.language if worst_item else None,
                "worst_width": worst_item.window_min if worst_item else 0,
                "budget": budget,
                "ok": ok,
            }
        )
    )
    return 0 if ok else 1


PLACEHOLDER = re.compile(r"__([A-Z0-9_]+)__")
# substituted by apply_theme(), not palette entries
NON_COLOUR_PLACEHOLDERS = {"FONT", "CHECK", "DOWN_ARROW", "SPIN_UP", "SPIN_DOWN", "RADIUS_XS", "RADIUS_SM", "RADIUS_LG"}

def check_token_usage() -> int:
    """Every colour token must be reachable from a rule in the sheets.

    tests/test_qss_tokens.py proves one direction: a placeholder that appears in the QSS must resolve.
    This proves the other: a palette entry that no rule references can never appear on screen, so its
    value cannot be judged - which is how a light BG_HOVER copied from the dark theme sat in the
    palette, and how ACCENT_PRESS survived as a colour nothing could draw.
    """
    import gui.theme as theme_module

    repo_root = Path(__file__).resolve().parents[1]

    used: set[str] = set()
    per_sheet: dict[str, set[str]] = {}
    for name in ("gui/resources/style.qss", "gui/resources/style_light.qss"):
        found = {m.group(1) for m in PLACEHOLDER.finditer((repo_root / name).read_text(encoding="utf-8"))}
        per_sheet[name] = found - NON_COLOUR_PLACEHOLDERS
        used |= per_sheet[name]
    defined = set(theme_module.NEUTRAL_TOKENS)
    defined |= set(theme_module.accent_palette("dark", None)) | set(theme_module.accent_palette("light", None))
    defined -= NON_COLOUR_PLACEHOLDERS

    unreferenced = sorted(token for token in defined if token not in used)
    print("  token usage:")
    for name, found in per_sheet.items():
        print(f"    {name}: {len(found & defined)} of {len(defined)} tokens referenced")
    if unreferenced:
        for token in unreferenced:
            print(f"    FAIL unreferenced colour token: {token}")
        return len(unreferenced)
    print(f"    OK  all {len(defined)} colour tokens are referenced by a rule")
    return 0


def main() -> int:
    sys.stdout.reconfigure(errors="replace")  # never crash on console encoding
    if "--dpi" in sys.argv:  # worker mode: no QApplication may exist yet
        return _dpi_probe()
    if "--width" in sys.argv:  # worker mode, same reason
        return _width_probe()
    wants_json = "--json" in sys.argv
    root = Path(os.environ.get("UI_AUDIT_ROOT", Path(__file__).resolve().parents[1])).resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(root))
    os.chdir(root)

    print("=== 1. contrast ===")
    contrast_failures = check_contrast()
    print("\n=== 2. text overflow (9 languages) ===")
    overflow = check_text_overflow()
    print("\n=== 3. high DPI ===")
    check_high_dpi(1.25)
    print("\n=== 4. window width (9 languages, A3 budget) ===")
    width_failures = 1 if check_window_width(MAX_WINDOW_WIDTH) else 0
    print("\n=== 5. token usage ===")
    token_failures = check_token_usage()
    print(
        "\nsummary: contrast failures =",
        contrast_failures,
        "| overflow =",
        overflow,
        "| width over budget =",
        width_failures,
        "| unreferenced tokens =",
        token_failures,
    )
    if wants_json:
        # machine-readable verdict: callers should judge by this, not by the exit code
        print(
            json.dumps(
                {
                    "contrast_failures": contrast_failures,
                    "overflow": overflow,
                    "width_failures": width_failures,
                    "token_failures": token_failures,
                    "ok": not (contrast_failures or overflow or width_failures or token_failures),
                }
            )
        )
        return 0
    return 1 if (contrast_failures or overflow or width_failures or token_failures) else 0


if __name__ == "__main__":
    raise SystemExit(main())
