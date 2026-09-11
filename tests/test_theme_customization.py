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

"""Custom accent color and UI font (UI trial): parsing, palette derivation and QSS placeholders."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gui import theme
from launcher import paths


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_normalize_hex_accepts_and_rejects() -> None:
    assert theme.normalize_hex("35a06a") == "#35a06a"
    assert theme.normalize_hex("#35A06A") == "#35a06a"
    assert theme.normalize_hex("  #ff8800  ") == "#ff8800"
    assert theme.normalize_hex("") is None
    assert theme.normalize_hex(None) is None
    assert theme.normalize_hex("#12345") is None
    assert theme.normalize_hex("zzzzzz") is None


def test_accent_palette_uses_the_custom_base() -> None:
    palette = theme.accent_palette("dark", "#3b82f6")
    assert palette["ACCENT"] == "#3b82f6"
    assert palette["ACCENT_SEL_TEXT"] == "#ffffff"
    # derived steps must differ from the base and stay valid hex colors
    for key in ("ACCENT_HOVER", "ACCENT_PRESS", "ACCENT_SEL", "ACCENT_SOFT"):
        value = palette[key]
        assert value != palette["ACCENT"]
        assert theme.normalize_hex(value) == value


def test_accent_palette_falls_back_to_theme_default() -> None:
    assert theme.accent_palette("dark", None)["ACCENT"] == theme.DEFAULT_ACCENTS["dark"]
    assert theme.accent_palette("light", "not-a-color")["ACCENT"] == theme.DEFAULT_ACCENTS["light"]


def test_light_palette_keeps_text_readable() -> None:
    palette = theme.accent_palette("light", "#2f9e6f")
    # light theme selection uses a pale tint with a dark foreground
    assert palette["ACCENT_SEL"] > palette["ACCENT"]
    assert palette["ACCENT_SEL_TEXT"] < palette["ACCENT"]


def test_font_stack_default_and_custom() -> None:
    assert theme.DEFAULT_FONT in theme.font_stack(None)
    assert theme.DEFAULT_FONT in theme.font_stack("")
    assert theme.font_stack("Consolas").startswith('"Consolas"')
    # fallbacks stay in place so unknown families still resolve
    assert "Segoe UI" in theme.font_stack("No Such Font 12345")


def test_stylesheets_use_placeholders_not_hardcoded_accent() -> None:
    """Regression guard: the QSS files must stay re-tintable."""
    for name, accent in (("style.qss", "#35a06a"), ("style_light.qss", "#2f9e6f")):
        text = paths.resource_path("gui/resources/" + name).read_text(encoding="utf-8")
        assert "__ACCENT__" in text, name
        assert "__FONT__" in text, name
        assert accent not in text, f"{name} still hardcodes {accent}"


def test_radius_presets_and_placeholders(monkeypatch, ws_tmp) -> None:
    """Every radius preset must produce a full set of sizes, and the QSS must stay placeholder-based."""
    from gui import theme
    from launcher import paths

    assert theme.radius_scale(None) == theme.RADIUS_SCALES["default"]
    assert theme.radius_scale("nonsense") == theme.RADIUS_SCALES["default"]
    small, medium, large = (theme.radius_scale(name) for name in ("compact", "default", "round"))
    assert small[0] < medium[0] < large[0]
    assert small[2] < medium[2] < large[2]

    for name in ("style.qss", "style_light.qss"):
        text = paths.resource_path("gui/resources/" + name).read_text(encoding="utf-8")
        assert "__RADIUS_SM__" in text and "__RADIUS_LG__" in text, name
        assert "border-radius: 6px" not in text, name  # still hard-coded


def test_system_theme_resolves_to_a_concrete_theme() -> None:
    from gui import theme

    assert theme.resolve_theme("dark") == "dark"
    assert theme.resolve_theme("light") == "light"
    assert theme.resolve_theme("system") in ("dark", "light")


def test_accent_preset_buttons_apply_colour(app, monkeypatch, ws_tmp) -> None:
    """Clicking a preset swatch writes that colour into the config."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_presets"))
    from gui.main_window import MainWindow
    from gui.pages import settings_page as settings_module
    from launcher import config as config_mod

    window = MainWindow()
    page = window.pages["settings"]
    assert len(page.accent_preset_buttons) == len(settings_module.ACCENT_PRESETS)
    page.accent_preset_buttons[1].click()
    cfg, _ = config_mod.load()
    assert cfg.accent_color == settings_module.ACCENT_PRESETS[1].lower()
    window.close()
