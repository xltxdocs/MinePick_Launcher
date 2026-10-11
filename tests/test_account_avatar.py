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

"""The account avatar: nothing at all while there is no account, a readable letter when there is one.

Two reports are pinned here.

The first was "that question mark is ugly". With no account the page drew the *letter* avatar for the
string ``"?"``, so an empty account row carried a full-size coloured disc around a question mark. The slot
is now left transparent instead: the label is cleared, keeps its 42x42 size, and the page background shows
through it. The size is the part that must not be lost - the row's other widgets sit where they did, which
is asserted by comparing their coordinates in both states rather than by eye.

The second is the fill the letter sits on. The disc's hue comes from the username, so which colour the
white letter lands on is data, not design - the audit's pair table cannot enumerate it, and at the value it
originally used (150) the worst of the 360 hues, always 60 (yellow), put the white letter at 3.13:1: legible
as large text, below WCAG AA's 4.5:1 for a normal-size letter. ``AVATAR_VALUE`` is now 110, which lifts that
same hue to 5.35:1 and leaves the hue - the part that tells accounts apart - untouched. The whole circle is
walked below, and the old value is kept as a failing case so it cannot come back unnoticed.

Everything here runs on the offscreen platform, in a couple of seconds; tools/measure_account_avatar.py
measures the same thing on the real platform and writes the screenshots.
"""

from __future__ import annotations

import colorsys

import pytest

from gui.pages.login_page import (
    AVATAR_HUE_STEP,
    AVATAR_SATURATION,
    AVATAR_SIZE,
    AVATAR_VALUE,
)

# WCAG 1.4.3 for normal-size text: the number the white letter has to clear on every hue.
MIN_TEXT_RATIO = 4.5
# What the fill used before it was measured. A literal on purpose: it is a fact about the old code, not a
# second copy of the current constant, so a change to one does not silently rewrite the other.
OLD_AVATAR_VALUE = 150
# The hue that is always the worst one: yellow, the brightest point of the wheel.
WORST_HUE = 60


# ---------------------------------------------------------------------------------------------------
# The fill: the whole 360-hue circle, computed. No Qt, no render - the drawing is checked further down.
# ---------------------------------------------------------------------------------------------------


def hsv_hex(hue: int, saturation: int, value: int) -> str:
    """Qt's QColor.fromHsv scaling: hue 0-359, saturation and value 0-255."""
    red, green, blue = colorsys.hsv_to_rgb(hue / 360.0, saturation / 255.0, value / 255.0)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


def contrast(foreground: str, background: str) -> float:
    """WCAG ratio for two hex colours, so this module needs no QApplication for the arithmetic."""
    def luminance(value: str) -> float:
        value = value.lstrip("#")
        channels = []
        for index in (0, 2, 4):
            srgb = int(value[index : index + 2], 16) / 255
            channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def worst_hue(saturation: int = AVATAR_SATURATION, value: int = AVATAR_VALUE) -> tuple[float, int]:
    """(ratio, hue) of the least readable white letter over the whole circle."""
    return min((contrast("#ffffff", hsv_hex(hue, saturation, value)), hue) for hue in range(360))


def test_every_hue_clears_aa_for_the_white_letter():
    """The gate: all 360 hues a username can produce must clear 4.5:1 under the white letter."""
    ratio, hue = worst_hue()
    print(f"\navatar fill: worst hue {hue} measures {ratio:.2f}:1 (needs {MIN_TEXT_RATIO}:1)")
    assert ratio >= MIN_TEXT_RATIO, (
        f"the white letter reads {ratio:.2f}:1 at hue {hue} - the worst of the 360 - below the "
        f"{MIN_TEXT_RATIO}:1 WCAG AA needs. AVATAR_VALUE={AVATAR_VALUE} is too bright: the fill is "
        f"derived from the username, so some account name lands on that hue."
    )


def test_the_worst_hue_is_the_bright_one_that_forced_the_value_down():
    """The fill's weak point is fixed and known, so a change here is a decision, not a surprise."""
    _ratio, hue = worst_hue()
    assert hue == WORST_HUE, f"the worst hue moved from {WORST_HUE} to {hue}: remeasure the fill"


def test_the_old_value_150_would_not_have_been_readable():
    """The measurement behind the fix: the fill this replaced really did miss AA, and by how much.

    If this ever passes, the palette or Qt's HSV changed enough that the original fill was fine after all -
    a reason to revisit the value, not a silent reason to keep it.
    """
    ratio, hue = worst_hue(value=OLD_AVATAR_VALUE)
    assert ratio < MIN_TEXT_RATIO, (
        f"value {OLD_AVATAR_VALUE} now reads {ratio:.2f}:1 at hue {hue}, so AVATAR_VALUE="
        f"{AVATAR_VALUE} is no longer needed - say so in the constant's note before lowering it"
    )
    assert ratio >= 3.0, f"value {OLD_AVATAR_VALUE} reads {ratio:.2f}:1: worse than the report claimed"


def test_the_offline_hsv_matches_qt():
    """The circle above is walked with colorsys; the code draws with QColor.fromHsv.

    Both use hue 0-359 and saturation/value 0-255, and rounding could still differ by one, which would make
    the arithmetic above measure colours the launcher never paints. It does not - pinned so it stays true.
    """
    from PySide6.QtGui import QColor

    mismatches = [
        (hue, hsv_hex(hue, AVATAR_SATURATION, AVATAR_VALUE), QColor.fromHsv(hue, AVATAR_SATURATION, AVATAR_VALUE).name())
        for hue in range(360)
        if hsv_hex(hue, AVATAR_SATURATION, AVATAR_VALUE)
        != QColor.fromHsv(hue, AVATAR_SATURATION, AVATAR_VALUE).name()
    ]
    assert not mismatches, f"colorsys and Qt disagree on {len(mismatches)} hue(s), e.g. {mismatches[:3]}"


# ---------------------------------------------------------------------------------------------------
# The slot: rendered, on the account page of a real window.
# ---------------------------------------------------------------------------------------------------

# Every widget the account row (and the rest of the page under it) lays out: a transparent avatar slot must
# not move any of them, so their coordinates are compared between the two states.
PAGE_WIDGETS = (
    "avatar_label",
    "account_label",
    "accounts_list",
    "switch_button",
    "device_code",
    "ms_button",
    "offline_edit",
    "offline_button",
    "logout_button",
)


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def account_window(app, monkeypatch, ws_tmp):
    """The real window on its own empty data dir: laid out, styled, grabbable, never shown on screen."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    monkeypatch.setenv("MINECRAFT_GAME_DIR", str(ws_tmp / "game"))
    from PySide6.QtCore import Qt

    from gui.main_window import NAV_KEYS, MainWindow
    from gui.theme import apply_theme

    apply_theme("dark")
    window = MainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)  # never on the user's desktop
    window.resize(1000, 620)
    window.show()
    window.sidebar.setCurrentRow(NAV_KEYS.index("account"))
    _settle(app)
    try:
        yield window
    finally:
        window.close()
        apply_theme("dark")  # leave the default theme for the other cases


def _settle(app, rounds: int = 8) -> None:
    for _ in range(rounds):
        app.processEvents()


def _sign_in(name: str = "Steve") -> None:
    """Save and select an offline account, which is what the page reads on refresh()."""
    from launcher import config as config_mod
    from launcher.auth import AccountStore, create_offline_account

    account = create_offline_account(name)
    store = AccountStore()
    store.save({**store.load(), account.id: account})
    cfg, cfg_path = config_mod.load()
    cfg.selected_account = account.id
    config_mod.save(cfg, cfg_path)


def _sign_out() -> None:
    from launcher import config as config_mod
    from launcher.auth import AccountStore

    AccountStore().save({})
    cfg, cfg_path = config_mod.load()
    cfg.selected_account = None
    config_mod.save(cfg, cfg_path)


def _geometry(page) -> dict[str, tuple[int, int, int, int]]:
    return {name: getattr(page, name).geometry().getRect() for name in PAGE_WIDGETS}


def _artifact(name: str):
    """Where the two screenshots go: the suite's gitignored work dir, so nothing lands in the repository."""
    from pathlib import Path

    target = Path(__file__).resolve().parent / ".work" / "avatar"
    target.mkdir(parents=True, exist_ok=True)
    return target / name


class _WindowShot:
    """One grab of the window, with the avatar slot addressable in its own logical pixels."""

    def __init__(self, window, label) -> None:
        from PySide6.QtCore import QPoint

        self.pixmap = window.grab()
        self.image = self.pixmap.toImage()
        self.ratio = self.image.devicePixelRatio() or 1.0
        self.origin = label.mapTo(window, QPoint(0, 0))
        self.width, self.height = label.width(), label.height()

    def slot(self, dx: int, dy: int) -> tuple[int, int, int]:
        """The pixel at (dx, dy) inside the avatar slot, allowing for the screen's device ratio."""
        x = min(round((self.origin.x() + dx) * self.ratio), self.image.width() - 1)
        y = min(round((self.origin.y() + dy) * self.ratio), self.image.height() - 1)
        colour = self.image.pixelColor(x, y)
        return (colour.red(), colour.green(), colour.blue())

    def background(self) -> tuple[int, int, int]:
        """The page's own fill, sampled away from the slot: under it, and in the window's corner."""
        below = self.slot(self.width // 2, self.height + 6)
        corner = self.slot(-self.origin.x() + 5, -self.origin.y() + 5)
        assert below == corner, (
            f"the two background references disagree ({below} under the row, {corner} in the page corner), "
            "so this test cannot tell what 'the surrounding fill' is"
        )
        return below

    def slot_colours(self) -> set[tuple[int, int, int]]:
        return {self.slot(dx, dy) for dx in range(self.width) for dy in range(self.height)}


def test_no_account_leaves_the_avatar_slot_showing_the_page_background(account_window, app):
    """The whole point: an empty account row must paint nothing in the avatar slot.

    ``clear()`` and not a transparent pixmap: an empty QLabel paints no background of its own, so the page's
    fill is what the slot shows - which is what the pixels below are asked to prove, against the same fill
    sampled from two places outside the slot.
    """
    page = account_window.pages["account"]
    page.refresh()
    _settle(app)

    label = page.avatar_label
    assert label.pixmap().isNull(), "the avatar slot still holds a pixmap"
    assert label.text() == "", "the avatar slot still holds text"
    assert (label.width(), label.height()) == (AVATAR_SIZE, AVATAR_SIZE), "the slot changed size"

    shot = _WindowShot(account_window, label)
    colours = shot.slot_colours()
    assert colours == {shot.background()}, (
        f"the empty avatar slot is not transparent: it painted {sorted(colours)[:4]} where the page's fill "
        f"is {shot.background()}"
    )
    shot.pixmap.save(str(_artifact("slot_without_account.png")))


def test_an_account_paints_the_letter_and_the_slot_stops_being_background(account_window, app):
    """The other half of the comparison: with an account the slot is filled, and filled readably."""
    from PySide6.QtGui import QColor

    page = account_window.pages["account"]
    _sign_in("Steve")
    page.refresh()
    _settle(app)

    label = page.avatar_label
    pixmap = label.pixmap()
    assert not pixmap.isNull(), "no account avatar was drawn at all"
    assert (pixmap.width(), pixmap.height()) == (AVATAR_SIZE, AVATAR_SIZE)

    shot = _WindowShot(account_window, label)
    assert shot.slot(1, 1) == shot.background(), "the disc's corner is painted: the avatar is not round"
    assert shot.slot(3, label.height() // 2) != shot.background(), "the disc was not drawn"
    shot.pixmap.save(str(_artifact("slot_with_account.png")))

    # What is really painted, read off the pixmap rather than off the formula, then measured.
    from collections import Counter

    image = pixmap.toImage()
    counts = Counter(
        image.pixelColor(x, y).getRgb() for x in range(image.width()) for y in range(image.height())
    )
    fill, fill_pixels = counts.most_common(1)[0]
    hue = (sum(ord(c) for c in "Steve") * AVATAR_HUE_STEP) % 360
    expected = QColor.fromHsv(hue, AVATAR_SATURATION, AVATAR_VALUE)
    assert fill[:3] == (expected.red(), expected.green(), expected.blue()), (
        f"the disc is painted {fill[:3]}, not the fill the constants describe "
        f"({expected.name()}) - the note on AVATAR_VALUE measures the wrong colour"
    )
    assert fill_pixels > 0.4 * image.width() * image.height(), "the most common colour is not the disc fill"

    letter = counts[(255, 255, 255, 255)]
    assert letter, "no pure-white letter pixel was drawn"
    ratio = contrast("#ffffff", f"#{fill[0]:02x}{fill[1]:02x}{fill[2]:02x}")
    assert ratio >= MIN_TEXT_RATIO, (
        f"the rendered letter reads {ratio:.2f}:1 on the disc it is really drawn on ({expected.name()})"
    )


def test_logging_out_makes_the_slot_transparent_again(account_window, app):
    """The slot is cleared on the way out too, not merely never filled on the way in."""
    page = account_window.pages["account"]
    _sign_in("Alex")
    page.refresh()
    _settle(app)
    assert not page.avatar_label.pixmap().isNull()

    _sign_out()
    page.refresh()
    _settle(app)

    label = page.avatar_label
    assert label.pixmap().isNull()
    shot = _WindowShot(account_window, label)
    assert shot.slot_colours() == {shot.background()}


def test_a_name_with_no_letter_leaves_the_avatar_transparent(account_window, app):
    """The question-mark fallback is gone: a name with no letter in it draws no disc and no glyph."""
    page = account_window.pages["account"]
    page._set_letter_avatar("")
    _settle(app)
    assert page.avatar_label.pixmap().isNull()
    assert page.avatar_label.text() == ""

    page._set_letter_avatar("  ")
    _settle(app)
    assert page.avatar_label.pixmap().isNull(), "a blank name painted a disc again"


def test_the_page_does_not_move_between_the_two_states(account_window, app):
    """No layout shift: with or without an account, every widget is at exactly the same coordinates."""
    page = account_window.pages["account"]
    page.refresh()
    _settle(app)
    empty = _geometry(page)

    _sign_in("Steve")
    page.refresh()
    _settle(app)
    with_account = _geometry(page)

    assert empty == with_account, (
        "the account row moved when the avatar appeared: "
        f"{[name for name in PAGE_WIDGETS if empty[name] != with_account[name]]}"
    )
    assert empty["avatar_label"] == (empty["avatar_label"][0], empty["avatar_label"][1], AVATAR_SIZE, AVATAR_SIZE)
