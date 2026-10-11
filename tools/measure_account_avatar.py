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

"""Measure the account avatar on the real platform, without ever showing a window.

Why a tool and not just a test: two of the three claims are about pixels, and the third is about the wheel.

* "no account means the slot is transparent" is a statement about what is *not* painted. Only a render can
  show that the 42x42 slot shows the page's own fill and nothing else - the label being empty in the object
  tree is not the same thing.
* "with an account the white letter is readable" depends on the fill, and the fill's hue comes from the
  username: tools/audit_ui_quality.py can walk the circle with arithmetic, but the colour that really lands
  under the letter is what the render paints, at the device ratio the user's screen has.
* "the row does not move" is a comparison of coordinates between the two states, measured on the real
  layout rather than on a rebuilt one.

It renders the real account page with ``WA_DontShowOnScreen`` (laid out and grabbable, never on screen, never
focused), then per theme and per state:
  * samples every pixel of the avatar slot and reports the distinct colours in it;
  * compares them against the page's own fill, sampled above, below and beside the slot;
  * reads the disc's fill and the letter's core colour out of the label's own pixmap, and measures the WCAG
    ratio of the pair that is really painted, next to the ratio the formula predicts;
  * renders the whole 360-hue circle for the worst case, and one username that lands exactly on that hue;
  * compares the coordinates of every widget on the page between the two states;
  * writes each render, and a crop of the slot, as PNGs beside the JSON verdict.

Run:
    python tools/measure_account_avatar.py --out D:\\dsh-workspace\\tmp\\avatar
"""

from __future__ import annotations

import argparse
import colorsys
import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["PYTHONIOENCODING"] = "utf-8"

# Usernames to render. "Steve"/"Alex" are the ordinary case, "玩家一号" covers a non-Latin name (its first
# character is the letter), and the tool adds a synthetic name that lands on the worst hue of the circle.
NAMES = ("Steve", "Alex", "玩家一号")

# What the fill's white letter has to clear: WCAG 1.4.3, normal-size text.
MIN_TEXT_RATIO = 4.5


def luminance(color) -> float:
    channels = []
    for value in color[:3]:
        srgb = value / 255
        channels.append(srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground, background) -> float:
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def hsv_rgb(hue: int, saturation: int, value: int) -> tuple[int, int, int]:
    """Qt's QColor.fromHsv scaling: hue 0-359, saturation and value 0-255."""
    red, green, blue = colorsys.hsv_to_rgb(hue / 360.0, saturation / 255.0, value / 255.0)
    return round(red * 255), round(green * 255), round(blue * 255)


def worst_hue(saturation: int, value: int) -> tuple[float, int, tuple[int, int, int]]:
    """The least readable white letter over the whole circle: (ratio, hue, rgb)."""
    best = (99.0, 0, (0, 0, 0))
    for hue in range(360):
        rgb = hsv_rgb(hue, saturation, value)
        ratio = contrast_ratio((255, 255, 255), rgb)
        if ratio < best[0]:
            best = (ratio, hue, rgb)
    return best


def name_for_hue(target: int, step: int) -> str:
    """A four-character account name whose hue is exactly ``target``.

    The hue only depends on the sum of the character codes (mod 360), and ``step`` is coprime with 360, so
    the needed sum is one modular inverse away. Four printable ASCII characters can sum to any value in
    132..504, and one of ``sum``, ``sum + 360``, ``sum + 720`` always lands in that window - so the name is
    constructed, not searched for. It is deliberately an odd-looking name: the point is a real account that
    paints the worst hue of the circle, so the render can be measured there.
    """
    printable = range(33, 127)  # '!' .. '~': no spaces, nothing a name box would reject for being blank
    needed = (target * pow(step, -1, 360)) % 360
    for total in (needed, needed + 360, needed + 720):
        if 132 <= total <= 318:
            first = second = 33
        elif 319 <= total <= 504:
            first = second = 126
        else:
            continue
        rest = total - first - second
        for third in printable:
            fourth = rest - third
            if fourth in printable:
                return "".join(chr(code) for code in (first, second, third, fourth))
    raise AssertionError(f"no name can reach hue {target}")


def slot_pixels(image, origin, size, ratio: float):
    """Every pixel of the avatar slot, in the window image's own device pixels."""
    width, height = size
    for dy in range(height):
        for dx in range(width):
            x = min(round((origin[0] + dx) * ratio), image.width() - 1)
            y = min(round((origin[1] + dy) * ratio), image.height() - 1)
            color = image.pixelColor(x, y)
            yield dx, dy, (color.red(), color.green(), color.blue())


def sample(image, x: float, y: float, ratio: float) -> tuple[int, int, int]:
    color = image.pixelColor(
        min(round(x * ratio), image.width() - 1), min(round(y * ratio), image.height() - 1)
    )
    return (color.red(), color.green(), color.blue())


def file_tag(state: str) -> str:
    """A state name that is safe as a filename: the synthetic name can hold ``*`` and ``~``.

    ``*`` is a wildcard on Windows, so ``QPixmap.save`` fails and returns False there - which is why the
    caller checks the result instead of trusting it.
    """
    cleaned = "".join(character if character.isalnum() else "_" for character in state)
    return cleaned if state == "no_account" else f"name_{cleaned}"


def _slot_crop(pixmap, origin, label):
    """The avatar slot plus a 6px frame around it, in the grab's own device pixels."""
    ratio = pixmap.devicePixelRatio() or 1.0
    return pixmap.copy(
        round((origin.x() - 6) * ratio),
        round((origin.y() - 6) * ratio),
        round((label.width() + 12) * ratio),
        round((label.height() + 12) * ratio),
    )


def analyse_slot(pixmap, origin, size, label_pixmap) -> dict:
    """Everything measurable about one avatar slot, from the window grab and the label's own pixmap."""
    image = pixmap.toImage()
    ratio = image.devicePixelRatio() or 1.0
    width, height = size
    colours = Counter(rgb for _dx, _dy, rgb in slot_pixels(image, origin, size, ratio))
    # The page's own fill, sampled twice outside the slot but in the same row: in the block gap under it and
    # in the layout's spacing beside it. Both must agree, or "the slot shows the background" means nothing.
    below = sample(image, origin[0] + width // 2, origin[1] + height + 4, ratio)
    beside = sample(image, origin[0] + width + 3, origin[1] + height // 2, ratio)
    background = Counter((below, beside)).most_common(1)[0][0]

    entry = {
        "slot_rect_in_window": [origin[0], origin[1], width, height],
        "device_pixel_ratio": ratio,
        "slot_colours": len(colours),
        "slot_most_common": list(colours.most_common(1)[0][0]),
        "slot_most_common_pixels": colours.most_common(1)[0][1],
        "background_samples": {
            "below_slot": list(below),
            "beside_slot": list(beside),
        },
        "background": list(background),
        "background_samples_agree": below == beside,
        "slot_is_one_colour": len(colours) == 1,
        "slot_equals_background": colours.most_common(1)[0][0] == background and len(colours) == 1,
        "slot_brightest": list(max(colours, key=luminance)),
        "label_pixmap_is_null": label_pixmap.isNull(),
    }
    if not label_pixmap.isNull():
        drawn = label_pixmap.toImage()
        painted = Counter(
            drawn.pixelColor(x, y).getRgb() for x in range(drawn.width()) for y in range(drawn.height())
        )
        opaque = {rgb: count for rgb, count in painted.items() if rgb[3] == 255}
        fill = max(opaque.items(), key=lambda item: item[1])[0] if opaque else None
        letter = max(opaque, key=lambda rgb: luminance(rgb)) if opaque else None
        transparent = sum(count for rgb, count in painted.items() if rgb[3] == 0)
        entry.update(
            pixmap_fill=list(fill[:3]) if fill else None,
            pixmap_fill_pixels=fill[1] if fill else None,
            pixmap_letter=list(letter[:3]) if letter else None,
            pixmap_transparent_corner_pixels=transparent,
            ratio_pixmap_letter_vs_fill=round(contrast_ratio(letter, fill), 3) if fill and letter else None,
            ratio_composited_letter_vs_fill=round(
                contrast_ratio(entry["slot_brightest"], colours.most_common(1)[0][0]), 3
            ),
        )
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--out", required=True, help="directory for the PNGs and the JSON verdict")
    parser.add_argument("--themes", default="dark,light")
    parser.add_argument("--names", default=",".join(NAMES))
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.chdir(root)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # A scratch data dir: this must never read or write the user's real launcher data.
    data = out / "_data"
    (data / "game").mkdir(parents=True, exist_ok=True)
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data)
    os.environ["MINECRAFT_GAME_DIR"] = str(data / "game")

    from PySide6.QtCore import QPoint, Qt

    from gui import theme as theme_module

    try:
        from gui.main import create_app
    except ModuleNotFoundError as exc:  # wrong --root: say so instead of a bare traceback
        print(f"cannot import the launcher from {root}: {exc}", file=sys.stderr)
        return 2

    app = create_app([])
    platform = app.platformName()
    if platform == "offscreen":
        print("refusing to run: the offscreen platform is what this tool exists to avoid", file=sys.stderr)
        return 2

    from gui.main_window import NAV_KEYS, MainWindow
    from gui.pages.login_page import (
        AVATAR_HUE_STEP,
        AVATAR_SATURATION,
        AVATAR_SIZE,
        AVATAR_VALUE,
    )
    from launcher import config as config_mod
    from launcher.auth import AccountStore, create_offline_account

    circle = worst_hue(AVATAR_SATURATION, AVATAR_VALUE)
    old_circle = worst_hue(AVATAR_SATURATION, 150)
    report = {
        "platform": platform,
        "qt": __import__("PySide6").__version__,
        "avatar_size": AVATAR_SIZE,
        "fill": {
            "hue_step": AVATAR_HUE_STEP,
            "saturation": AVATAR_SATURATION,
            "value": AVATAR_VALUE,
            "worst_hue": circle[1],
            "worst_ratio_over_360_hues": round(circle[0], 3),
            "worst_rgb": list(circle[2]),
            "transparent": "the slot is cleared when there is no account (no disc, no glyph)",
        },
        "previous_fill": {
            "value": 150,
            "worst_hue": old_circle[1],
            "worst_ratio_over_360_hues": round(old_circle[0], 3),
            "worst_rgb": list(old_circle[2]),
        },
        "themes": [],
    }
    print(
        f"white letter on QColor.fromHsv(hue, {AVATAR_SATURATION}, {AVATAR_VALUE}): worst of the 360 hues is"
        f" {circle[1]} at {circle[0]:.2f}:1 (value 150 was {old_circle[0]:.2f}:1 at hue {old_circle[1]})"
    )

    names = [name for name in args.names.split(",") if name]
    worst_name = name_for_hue(circle[1], AVATAR_HUE_STEP)
    names.append(worst_name)

    def wipe_accounts() -> None:
        AccountStore().save({})
        cfg, cfg_path = config_mod.load()
        cfg.selected_account = None
        config_mod.save(cfg, cfg_path)

    def sign_in(name: str) -> None:
        account = create_offline_account(name)
        store = AccountStore()
        store.save({account.id: account})
        cfg, cfg_path = config_mod.load()
        cfg.selected_account = account.id
        config_mod.save(cfg, cfg_path)

    failures: list[str] = []
    for theme_name in args.themes.split(","):
        wipe_accounts()
        # The theme must be in force before the window exists: the pages read the token table while they are
        # built, and a window built first would be polished against the previous theme.
        theme_module.apply_theme(theme_name, None, None, "default")
        window = MainWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.resize(1000, 620)
        window.show()
        window.sidebar.setCurrentRow(NAV_KEYS.index("account"))
        page = window.pages["account"]
        for _ in range(10):
            app.processEvents()

        label = page.avatar_label
        observed: dict[str, dict] = {}
        for state in ["no_account", *names]:
            # Exactly one account, or none, before every render: the account *list* is fitted to whole rows,
            # so a second account would grow it and move everything below it - a real layout change, but not
            # the one being measured here.
            wipe_accounts()
            if state != "no_account":
                sign_in(state)
            page.refresh()
            for _ in range(8):
                app.processEvents()

            origin = label.mapTo(window, QPoint(0, 0))
            pixmap = window.grab()
            tag = f"{theme_name}_{file_tag(state)}"
            for name, image in (
                (f"page_{tag}.png", pixmap),
                (f"slot_{tag}.png", _slot_crop(pixmap, origin, label)),
            ):
                if not image.save(str(out / name)):
                    failures.append(f"{theme_name}/{state}: could not write {name}")

            entry = analyse_slot(pixmap, (origin.x(), origin.y()), (label.width(), label.height()), label.pixmap())
            entry["state"] = state
            entry["theme"] = theme_name
            entry["account_label_text"] = page.account_label.text()
            entry["page_widgets"] = {
                name: list(getattr(page, name).geometry().getRect())
                for name in (
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
            }
            if state != "no_account":
                hue = (sum(ord(c) for c in state) * AVATAR_HUE_STEP) % 360
                entry["hue"] = hue
                entry["formula_fill"] = list(hsv_rgb(hue, AVATAR_SATURATION, AVATAR_VALUE))
                entry["formula_ratio"] = round(contrast_ratio((255, 255, 255), hsv_rgb(hue, AVATAR_SATURATION, AVATAR_VALUE)), 3)
                entry["is_worst_hue"] = hue == circle[1]
            observed[state] = entry
            print(json.dumps({k: v for k, v in entry.items() if k != "page_widgets"}, ensure_ascii=False))

        # No layout shift: every widget at the same coordinates with and without an account.
        empty = observed["no_account"]["page_widgets"]
        for state in names:
            moved = [name for name, rect in observed[state]["page_widgets"].items() if empty[name] != rect]
            observed[state]["moved_widgets"] = moved
            if moved:
                failures.append(f"{theme_name}/{state}: these widgets moved: {moved}")

        empty_entry = observed["no_account"]
        if not empty_entry["background_samples_agree"]:
            failures.append(
                f"{theme_name}: the two background references disagree"
                f" ({empty_entry['background_samples']}), so 'transparent' cannot be judged"
            )
        if not empty_entry["slot_equals_background"]:
            failures.append(
                f"{theme_name}: the empty avatar slot is not transparent: {empty_entry['slot_colours']} colour(s),"
                f" most common {empty_entry['slot_most_common']} against a background of {empty_entry['background']}"
            )
        if not empty_entry["label_pixmap_is_null"]:
            failures.append(f"{theme_name}: an empty slot still holds a pixmap")
        for state in names:
            entry = observed[state]
            if entry["label_pixmap_is_null"]:
                failures.append(f"{theme_name}/{state}: no avatar was drawn")
                continue
            if entry["pixmap_fill"] != entry["formula_fill"]:
                failures.append(
                    f"{theme_name}/{state}: the disc is {entry['pixmap_fill']}, the formula says"
                    f" {entry['formula_fill']}"
                )
            if entry["ratio_pixmap_letter_vs_fill"] < MIN_TEXT_RATIO:
                failures.append(
                    f"{theme_name}/{state}: the letter reads {entry['ratio_pixmap_letter_vs_fill']}:1 on the"
                    f" disc at hue {entry.get('hue')}"
                )
            if entry["ratio_composited_letter_vs_fill"] < MIN_TEXT_RATIO:
                failures.append(
                    f"{theme_name}/{state}: as composited, the letter reads"
                    f" {entry['ratio_composited_letter_vs_fill']}:1 at hue {entry.get('hue')}"
                )
            if entry["pixmap_transparent_corner_pixels"] == 0:
                failures.append(f"{theme_name}/{state}: the avatar is a square, not a disc")

        report["themes"].append({"theme": theme_name, "states": observed})
        window.close()
        window.deleteLater()
        for _ in range(4):
            app.processEvents()

    report["worst_hue_name"] = worst_name
    report["failures"] = failures
    (out / "account_avatar.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("report:", out / "account_avatar.json")
    for failure in failures:
        print("FAIL:", failure)
    print("PASS: tools/measure_account_avatar.py" if not failures else "FAIL: tools/measure_account_avatar.py")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
