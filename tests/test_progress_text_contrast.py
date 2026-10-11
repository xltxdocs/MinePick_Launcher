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

"""The download progress percentage must stay readable while the bar fills underneath it.

The user report was "the download progress text is too faint to read". The cause is not a colour that
was chosen badly but the surface it was chosen for: Qt paints a progress bar's percentage *inside* the
bar, centred, and the bar is two surfaces - the accent chunk growing from the left and the unfilled
background behind it. A centred value sits on the unfilled half early in a download and on the accent
fill for most of it, where ``FG_HINT`` measures 1.26:1 (dark) / 1.93:1 (light) against WCAG AA's 4.5:1.
The accent is also user-chosen, so no single token could clear both halves for all eight presets.

The fix moves the text one slot to the right, onto the static fill the row already uses. These tests pin
that down three ways: the ratios, the geometry that keeps the text off the chunk, and the behaviour that
keeps the pair working as one control. The last group covers the same defect class elsewhere.

tools/measure_progress_text.py measures the same thing on the real platform and writes screenshots; this
file is the part that can run anywhere, on the offscreen platform, in a couple of seconds.
"""

from __future__ import annotations

import colorsys

import pytest

from gui import theme
from gui.pages.settings_page import ACCENT_PRESETS
from gui.widgets import PROGRESS_TEXT_MIN_WIDTH, build_download_progress

# What the audit table uses for text: WCAG 1.4.3, normal-size text.
MIN_TEXT_RATIO = 4.5


def contrast(foreground: str, background: str) -> float:
    """WCAG ratio for two hex colours, computed locally so this module needs no QApplication."""
    def luminance(value: str) -> float:
        value = value.lstrip("#")
        channels = []
        for index in (0, 2, 4):
            srgb = int(value[index : index + 2], 16) / 255
            channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("name", ("dark", "light"))
def test_percentage_text_clears_aa_on_the_surface_it_sits_on(name: str):
    """FG_HINT on the label's BG_LIST fill is what the user reads; it must clear 4.5:1."""
    tokens = theme.theme_palette(name)
    ratio = contrast(tokens["FG_HINT"], tokens["BG_LIST"])
    assert ratio >= MIN_TEXT_RATIO, (
        f"{name}: the progress percentage reads {ratio:.2f}:1 on {tokens['BG_LIST']}, "
        f"below the {MIN_TEXT_RATIO}:1 WCAG AA needs for body text"
    )


@pytest.mark.parametrize("name", ("dark", "light"))
@pytest.mark.parametrize("accent", ACCENT_PRESETS)
def test_the_accent_preset_cannot_reach_the_percentage_text(name: str, accent: str):
    """The whole point of moving the text off the bar: no accent may change its contrast.

    The old placement failed for the opposite reason - the text sat on the accent, so its ratio moved
    with the preset. The label's surface is drawn from BG_LIST, which no preset touches, so this holds
    for every colour the settings page offers as well as the theme default.
    """
    tokens = theme.theme_palette(name, accent)
    assert contrast(tokens["FG_HINT"], tokens["BG_LIST"]) >= MIN_TEXT_RATIO
    # And the surface is genuinely independent of the accent, not accidentally close to it.
    assert tokens["BG_LIST"] != tokens["ACCENT"]


@pytest.mark.parametrize("name", ("dark", "light"))
def test_the_text_would_not_have_been_readable_on_the_fill(name: str):
    """The measurement behind the fix, pinned so the old placement cannot come back unnoticed.

    If this ever passes, the palette changed enough that the text could sit on the chunk after all -
    which is a reason to revisit the split, not a silent reason to keep it.
    """
    tokens = theme.theme_palette(name)
    ratio = contrast(tokens["FG_HINT"], tokens["ACCENT"])
    assert ratio < MIN_TEXT_RATIO, (
        f"{name}: FG_HINT on ACCENT now reads {ratio:.2f}:1 - the bar could carry its own text again"
    )


@pytest.fixture()
def app():
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def progress_row(app):
    """A themed, shown progress row, torn down by conftest's settle fixture."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    theme._last_applied = None
    theme.apply_theme("dark", None, None, "default")
    host = QWidget()
    row, bar, label = build_download_progress("downloadProgress")
    # The scale every page drives the bar with: one step per tenth of a percent.
    bar.setRange(0, 1000)
    layout = QVBoxLayout(host)
    layout.addWidget(row)
    host.resize(600, 40)
    host.show()
    app.processEvents()
    row.setVisible(True)
    app.processEvents()
    yield row, bar, label
    host.hide()


def test_the_percentage_is_a_label_beside_the_bar_not_inside_it(progress_row):
    """Geometry: the text's own widget starts at or after the bar's right edge."""
    _row, bar, label = progress_row
    assert not bar.isTextVisible(), "Qt would paint the value on the chunk again"
    assert label.text() == "0%"
    bar.setValue(420)
    assert label.text() == "42%"
    assert label.x() >= bar.x() + bar.width(), (
        f"the label at x={label.x()} overlaps the bar ending at {bar.x() + bar.width()}"
    )
    assert label.width() >= PROGRESS_TEXT_MIN_WIDTH


def test_the_label_follows_the_bar_without_a_per_call_site_change(progress_row):
    """Callers only ever show and hide the row; the label must not be left behind."""
    row, _bar, label = progress_row
    assert label.isVisible()
    row.setVisible(False)
    assert not label.isVisible()
    row.setVisible(True)
    assert label.isVisible()


def test_no_text_pixel_can_land_on_the_fill_at_any_value(progress_row):
    """Render the row at seven values and prove the glyphs and the chunk never share a pixel.

    The chunk is found by colour, not by arithmetic, so this stays honest if Qt's rounding changes.
    """
    from PySide6.QtWidgets import QApplication

    app_instance = QApplication.instance()
    row, bar, label = progress_row
    tokens = theme.theme_palette("dark")
    accent = _rgb(tokens["ACCENT"])

    for value in (0, 200, 450, 500, 550, 800, 1000):
        bar.setValue(value)
        for _ in range(4):
            app_instance.processEvents()
        with_text = row.grab().toImage()
        real = label.text()
        label.setText("")
        for _ in range(4):
            app_instance.processEvents()
        without_text = row.grab().toImage()
        label.setText(real)
        for _ in range(4):
            app_instance.processEvents()

        dpr = with_text.devicePixelRatio() or 1.0
        width = round(with_text.width() / dpr)
        height = round(with_text.height() / dpr)
        middle = height // 2

        def sample(image, x, y, scale=dpr):
            color = image.pixelColor(
                min(round(x * scale), image.width() - 1), min(round(y * scale), image.height() - 1)
            )
            return (color.red(), color.green(), color.blue())

        chunk_end = 0
        for x in range(2, width):
            if _distance(sample(with_text, x, middle), accent) > 40:
                break
            chunk_end = x

        text_pixels = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if _distance(sample(with_text, x, y), sample(without_text, x, y)) > 8
        ]
        assert text_pixels, f"value {value}: the row drew no percentage at all"
        over_chunk = [point for point in text_pixels if point[0] <= chunk_end]
        assert not over_chunk, (
            f"value {value}: {len(over_chunk)} text pixel(s) sit on the accent fill "
            f"(chunk ends at x={chunk_end}), e.g. {over_chunk[:3]}"
        )


def _rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def _distance(a, b) -> int:
    return sum(abs(p - q) for p, q in zip(a, b))


# ---------------------------------------------------------------------------------------------------
# The same class of defect, found by looking for it: text on a fill the stylesheet does not paint.
# ---------------------------------------------------------------------------------------------------


def test_the_audit_still_names_the_text_it_cannot_enumerate():
    """The progress row must stay in the audit's dynamic-text list, and every token in it must resolve.

    That list is the only place a reader is told these cases exist; a token typo in it would print a
    ratio of nothing while the gate stayed green. tools/audit_ui_quality.py imports no Qt, so this needs
    no QApplication and runs anywhere.
    """
    from tools.audit_ui_quality import DYNAMIC_TEXT

    assert DYNAMIC_TEXT, "the audit reports no text on a dynamic background: the progress case is gone"
    assert any("progress" in what.lower() for what, *_rest in DYNAMIC_TEXT), (
        "the progress percentage is no longer listed as text on a dynamic background"
    )
    for what, foreground, _placement, backgrounds, _how, _fixed in DYNAMIC_TEXT:
        for mode in ("dark", "light"):
            palette = theme.theme_palette(mode)
            assert foreground in palette or foreground.startswith("#"), (
                f"{what}: foreground {foreground!r} is neither a token nor a colour literal"
            )
        for background in backgrounds:
            if "@" in background:  # a painted formula, not a token: the audit computes its hue circle
                continue
            for mode in ("dark", "light"):
                assert background in theme.theme_palette(mode), (
                    f"{what}: background {background!r} is not a token in the {mode} palette"
                )


def test_the_default_avatar_letter_is_documented_as_below_aa():
    """The account page's letter avatar: the leftover of the same class, pinned with its real ratio.

    The fill is a hue derived from the username (login_page._set_letter_avatar), so which colour the
    white letter lands on is data, not design - the reason the audit cannot enumerate it either. The
    measurement here is the computation the audit prints, and it is the number to decide on: the letter
    is 30px bold, so WCAG's large-text threshold (3:1) is met and its normal-text one (4.5:1) is not.
    """
    ratio, hue = min((contrast("#ffffff", _hsv_to_hex(hue, 160, 150)), hue) for hue in range(360))
    assert ratio >= 3.0, f"the worst hue ({hue}) is now below even the large-text threshold: {ratio:.2f}"
    assert ratio < 4.5, (
        "the avatar now clears 4.5:1 for every hue - update the audit's DYNAMIC_TEXT entry, "
        "which currently reports this case as OPEN"
    )


def _hsv_to_hex(hue: int, saturation: int, value: int) -> str:
    """Qt's QColor.fromHsv scaling: hue 0-359, saturation and value 0-255."""
    red, green, blue = colorsys.hsv_to_rgb(hue / 360.0, saturation / 255.0, value / 255.0)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"
