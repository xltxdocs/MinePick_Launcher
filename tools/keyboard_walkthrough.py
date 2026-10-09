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

"""Keyboard-only walkthrough: send Tab through every page and record where focus lands.

The UI guideline requires "unplug the mouse, then walk the whole main flow with Tab and the arrow
keys, confirming every step shows where focus is". A claim like that is worth little in a changelog;
what is worth something is a record that can be regenerated on demand and diffed between commits.

This tool drives the real window offscreen, presses nothing but Tab, and writes a Markdown report:

* the focus path per page (class, object name, readable label, focus policy);
* pages where Tab never moves focus at all (a hard failure - exit code 1);
* interactive widgets that are explicitly *not* focusable, i.e. the exception list that has to stay
  short and deliberate;
* every `:focus` selector in the stylesheets, so a missing focus visual can be spotted by eye.

Usage:
    python tools/keyboard_walkthrough.py --out <report.md> [--theme dark] [--max-steps 80]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _qss_focus_selectors(root: Path) -> list[str]:
    """Every selector that mentions :focus in either stylesheet."""
    selectors: list[str] = []
    for name in ("style.qss", "style_light.qss"):
        path = root / "gui" / "resources" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"([^{}]*:focus[^{}]*)\{", text):
            for part in block.split(","):
                part = part.strip()
                if part and ":focus" in part:
                    selectors.append(part)
    return selectors


def _readable(widget) -> str:
    """What a human (or a screen reader) would call this widget."""
    for getter in ("accessibleName", "text", "currentText", "placeholderText", "title", "toolTip"):
        value = None
        try:
            attr = getattr(widget, getter, None)
            value = attr() if callable(attr) else None
        except Exception:  # noqa: BLE001 - a widget without that getter is normal
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip().replace("\n", " ")[:60]
    return ""


def _describe(widget) -> tuple[str, str, str, str]:
    return (
        type(widget).__name__,
        widget.objectName() or "-",
        _readable(widget),
        str(widget.focusPolicy()).replace("Qt.FocusPolicy.", ""),
    )


def _selector_target(selector: str) -> str:
    """The widget part of a selector, with pseudo-states and sub-controls stripped.

    `QListWidget::item:selected:focus` -> `QListWidget`; `QPushButton#dangerButton:focus` keeps the
    id so an object-name rule can be told apart from a class rule.
    """
    base = selector.split("::")[0]
    return base.split(":")[0].strip()


def _has_focus_rule(widget, selectors: list[str]) -> bool:
    """Does any stylesheet `:focus` selector apply to this widget?

    Qt style-sheet type selectors match the class **and its subclasses** (a `QDoubleSpinBox:focus`
    rule does apply to a custom subclass), so the whole MRO counts - checking only the concrete class
    name produces false alarms.
    """
    names = {cls.__name__ for cls in type(widget).__mro__}
    obj = widget.objectName()
    for selector in selectors:
        base = _selector_target(selector)
        if not base:
            continue
        if "#" in base:
            if base.split("#", 1)[1].strip() == obj:
                return True
        elif base.split()[-1] in names or base.split()[-1] == "*":
            return True
    return False


INTERACTIVE = (
    "QAbstractButton",
    "QLineEdit",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QCheckBox",
    "QRadioButton",
    "QAbstractItemView",
    "QTextEdit",
    "QPlainTextEdit",
    "QSlider",
    "QTabBar",
)


def _find_non_focusable(page) -> list[tuple[str, str, str]]:
    """Interactive children that cannot take focus - the exception list must stay deliberate."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    out: list[tuple[str, str, str]] = []
    for child in page.findChildren(QWidget):
        if child.focusPolicy() != Qt.FocusPolicy.NoFocus:
            continue
        if not any(child.inherits(name) for name in INTERACTIVE):
            continue
        if not child.isVisibleTo(page):
            continue
        kind, name, label, _ = _describe(child)
        out.append((kind, name, label))
    return out


def _walk(
    app, page, max_steps: int, selectors: list[str]
) -> tuple[list[tuple[str, str, str, str, bool]], list]:
    """Press Tab until focus returns to where it started (or the step budget runs out).

    The focus-rule flag is decided here, while the widget itself is at hand: a rule naming a *base*
    class still applies (Qt matches subclasses), which cannot be told from a recorded class name.
    The live widgets are returned alongside the recorded rows so the visual pass can reuse the exact
    traversal the report describes.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    page.setFocus(Qt.FocusReason.OtherFocusReason)
    app.processEvents()

    path: list[tuple[str, str, str, str, bool]] = []
    widgets: list = []
    target = app.focusWidget() or page
    for _ in range(max_steps):
        QTest.keyClick(target, Qt.Key.Key_Tab)
        app.processEvents()
        widget = app.focusWidget()
        if widget is None:
            break
        step = (*_describe(widget), _has_focus_rule(widget, selectors))
        if step in path:
            break  # wrapped around: the focus chain for this page is closed
        path.append(step)
        widgets.append(widget)
        target = widget
    return path, widgets


GRAB_PAD = 4  # pixels of margin around the widget, so a ring drawn outside its rect is visible


NEUTRAL_RETRIES = 3  # how many times the neutral frame may be re-taken before calling it unstable


def _repolish(app, *widgets) -> None:
    """Force a fresh stylesheet evaluation after a focus change.

    Changing focus alone can leave Qt re-using the style it already computed, which made two grabs of
    supposedly different states byte-identical - and made this whole check report "no visible focus"
    for controls whose appearance does change.
    """
    for widget in widgets:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
    app.processEvents()


def _focus_visual(app, window, widget, neutral) -> str:
    """Does focusing this widget change the pixels around it?

    Returns `yes`, `no`, `unknown:moved` (the widget shifted between the grabs, e.g. focus scrolling it
    into view) or `unknown:unstable` (the neutral frame never settled - async status text is the usual
    culprit). `unknown` is never treated as a defect.
    """
    from PySide6.QtCore import QPoint, QRect, Qt

    top_left = widget.mapTo(window, QPoint(0, 0))
    rect = QRect(top_left, widget.size()).adjusted(-GRAB_PAD, -GRAB_PAD, GRAB_PAD, GRAB_PAD)
    rect = rect.intersected(window.rect())
    if rect.isEmpty():
        return "unknown:moved"

    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    _repolish(app, widget, neutral)
    if widget.mapTo(window, QPoint(0, 0)) != top_left:
        return "unknown:moved"
    # The grab must stay alive while its buffer is read: `window.grab(rect).toImage().constBits()`
    # in one expression hands back a view into an already-destroyed image (access violation).
    focused_image = window.grab(rect).toImage()
    focused = bytes(focused_image.constBits())

    for _attempt in range(NEUTRAL_RETRIES):
        neutral.setFocus(Qt.FocusReason.OtherFocusReason)
        _repolish(app, neutral, widget)
        if widget.mapTo(window, QPoint(0, 0)) != top_left:
            return "unknown:moved"
        baseline_image = window.grab(rect).toImage()
        baseline = bytes(baseline_image.constBits())
        app.processEvents()
        repeat_image = window.grab(rect).toImage()
        repeat = bytes(repeat_image.constBits())
        if baseline == repeat:
            return "yes" if focused != baseline else "no"
    return "unknown:unstable"


def _focus_visual_confirmed(app, window, widget, neutral) -> str:
    """`no` and `unknown` are re-tested once: an async repaint must not be reported as a defect."""
    first = _focus_visual(app, window, widget, neutral)
    if first == "yes":
        return "yes"
    second = _focus_visual(app, window, widget, neutral)
    if first == second:
        return first
    for verdict in (second, first):
        if verdict.startswith("unknown"):
            return verdict
    return "flaky"


def _has_focus_rule_name(kind: str, object_name: str, selectors: list[str]) -> bool:
    """Same as :func:`_has_focus_rule` but from the recorded (class name, object name) pair.

    Kept for callers that only have the recorded names; the walkthrough itself decides the flag from
    the live widget so that base-class rules are honoured.
    """
    for selector in selectors:
        base = _selector_target(selector)
        if not base:
            continue
        if "#" in base:
            if base.split("#", 1)[1].strip() == object_name:
                return True
        elif base.split()[-1] == kind or base.split()[-1] == "*":
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a keyboard-only walkthrough of every page.")
    parser.add_argument("--root", default=".", help="checkout root (default: current directory)")
    parser.add_argument("--out", required=True, help="where to write the Markdown report")
    parser.add_argument("--theme", default="dark", choices=["dark", "light"])
    parser.add_argument("--max-steps", type=int, default=80)
    parser.add_argument("--preview", default=None, help="where to keep _preview data (default: root)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_path = Path(args.out).resolve()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "tools"))
    os.chdir(root)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    import shot_pages

    data_dir, game_dir = shot_pages.ensure_preview(
        Path(args.preview).resolve() if args.preview else root,
        Path("%APPDATA%\\.minecraft"),
    )
    os.environ["MCLAUNCHER_DATA_DIR"] = str(data_dir)
    os.environ["MINECRAFT_GAME_DIR"] = str(game_dir)

    from PySide6.QtCore import QThreadPool
    from PySide6.QtGui import QFontDatabase

    from gui.main import create_app
    from gui.pages import java_page, mods_page, versions_page
    from gui.theme import apply_theme
    from launcher import config
    from launcher.auth import AccountStore, create_offline_account
    from launcher.meta.manifest import ManifestVersion, VersionManifest
    from launcher.mods.models import ModSearchHit

    versions_page.fetch_manifest = lambda cache_path=None: VersionManifest(  # type: ignore[assignment]
        latest={"release": "1.21.11", "snapshot": "26w02a"},
        versions=[
            ManifestVersion(
                id=vid,
                type=vtype,  # type: ignore[arg-type]
                url="https://example.invalid/version.json",
                time=f"{date}T12:00:00+00:00",
                release_time=f"{date}T12:00:00+00:00",
            )
            for vid, vtype, date in shot_pages.FAKE_VERSIONS
        ],
    )
    mods_page.search_projects = lambda *a, **k: [  # type: ignore[assignment]
        ModSearchHit(slug=slug, title=title, description=desc, downloads=dl)
        for slug, title, desc, dl in shot_pages.FAKE_MODS
    ]
    java_page.list_java = lambda *a, **k: []  # type: ignore[assignment]

    app = create_app([])
    apply_theme(args.theme, None, None, "default")
    for font_file in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/consola.ttf",
    ):
        if Path(font_file).exists():
            QFontDatabase.addApplicationFont(font_file)

    cfg, cfg_path = config.load()
    cfg.game_dir = str(game_dir)
    cfg.theme = args.theme
    config.save(cfg, cfg_path)
    apply_theme(args.theme, None, None, cfg.ui_radius)
    store = AccountStore()
    if not store.load():
        account = create_offline_account("Steve")
        store.save({account.uuid: account})

    from gui.main_window import NAV_KEYS, MainWindow

    window = MainWindow()
    window.resize(1000, 600)
    window.apply_window_mode()
    window.show()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 5.0)
    for key in ("versions", "java"):
        page = window.pages.get(key)
        if page is not None and hasattr(page, "refresh"):
            page.refresh()
    shot_pages.wait_for_workers(app, QThreadPool.globalInstance(), 15.0)

    selectors = list(dict.fromkeys(_qss_focus_selectors(root)))  # both stylesheets, duplicates merged
    lines: list[str] = []
    failures: list[str] = []
    total = 0
    invisible: list[tuple[str, str, str, str, str]] = []  # page, class, objectName, label, rect
    visual_tally: dict[str, int] = {"yes": 0, "no": 0, "unknown": 0, "flaky": 0}
    unknown_causes: dict[str, int] = {}
    neutral = window.stack  # a container with no :focus rule, used to park focus for the comparison

    lines.append("# MinePick 键盘走查记录")
    lines.append("")
    lines.append("> 由 `tools/keyboard_walkthrough.py` 自动生成:离屏启动真实窗口,**只发送 Tab 键**,")
    lines.append("> 记录每个页面的焦点落点。重新生成即可与上一次对比(界面改动后必须重出)。")
    lines.append("")
    lines.append(f"- 主题:`{args.theme}`;窗口:`1000x600`;页面数:`{len(NAV_KEYS)}`")
    lines.append("")

    detail: list[str] = []
    for index, key in enumerate(NAV_KEYS):
        page = window.pages.get(key)
        if page is None:
            failures.append(f"页面 `{key}` 不存在")
            continue
        window.stack.setCurrentIndex(index)
        app.processEvents()
        path, widgets = _walk(app, page, args.max_steps, selectors)
        total += len(path)
        if not path:
            failures.append(f"页面 `{key}`:Tab 完全不动(没有任何可获得焦点的控件)")
        visuals: list[str] = []
        for widget in widgets:
            verdict = _focus_visual_confirmed(app, window, widget, neutral)
            visuals.append(verdict)
            bucket = "unknown" if verdict.startswith("unknown") else verdict
            visual_tally[bucket] = visual_tally.get(bucket, 0) + 1
            if verdict.startswith("unknown:"):
                cause = verdict.split(":", 1)[1]
                unknown_causes[cause] = unknown_causes.get(cause, 0) + 1
            if verdict == "no":
                from PySide6.QtCore import QPoint

                point = widget.mapTo(window, QPoint(0, 0))
                rect = f"{point.x()},{point.y()} {widget.width()}x{widget.height()}"
                kind, name, label, _policy, _has_rule = path[len(visuals) - 1]
                invisible.append((key, kind, name, label, rect))
        without_rule = [
            f"`{kind}` `{name}`" for kind, name, _label, _policy, has_rule in path if not has_rule
        ]
        detail.append(f"### {key}({len(path)} 个落点)")
        detail.append("")
        if without_rule:
            detail.append(f"- ⚠️ 未在样式表里找到 `:focus` 规则:{', '.join(without_rule)}")
            detail.append("")
        detail.append("| # | 控件 | objectName | 可读名称 | 焦点策略 | 焦点样式 | 焦点可见 |")
        detail.append("|---|---|---|---|---|---|---|")
        for step_index, (kind, name, label, policy, has_rule) in enumerate(path):
            mark = "✅" if has_rule else "⚠️"
            visual = visuals[step_index] if step_index < len(visuals) else "—"
            visual_mark = {"yes": "✅", "no": "❌", "unknown": "❓", "flaky": "〰️"}.get(visual, "—")
            detail.append(
                f"| {step_index + 1} | `{kind}` | `{name}` | {label or '—'} | {policy} "
                f"| {mark} | {visual_mark} {visual} |"
            )
        detail.append("")

        exceptions = _find_non_focusable(page)
        if exceptions:
            detail.append(f"- 不可获得焦点的交互控件({len(exceptions)} 个,须为有意为之):")
            for kind, name, label in exceptions:
                detail.append(f"  - `{kind}` `{name}` {label}")
            detail.append("")

    lines.append("## 概览")
    lines.append("")
    lines.append(f"- 焦点落点总数:`{total}`")
    lines.append(f"- 硬失败:`{len(failures)}`")
    for failure in failures:
        lines.append(f"  - ❌ {failure}")
    unknown_detail = ", ".join(f"{name} `{count}`" for name, count in sorted(unknown_causes.items()))
    lines.append(
        f"- 焦点可见性实测:可见 `{visual_tally.get('yes', 0)}` /"
        f" **不可见 `{visual_tally.get('no', 0)}`** / 无法判定 `{visual_tally.get('unknown', 0)}`"
        + (f"({unknown_detail})" if unknown_detail else "")
        + f" / 不稳定 `{visual_tally.get('flaky', 0)}`"
    )
    lines.append("")
    lines.append(f"## 无可辨焦点效果的控件({len(invisible)} 个)")
    lines.append("")
    lines.append("> 判据:把焦点放到该控件与把焦点移开后,**窗口同一区域(控件矩形外扩 4px)的像素完全相同**")
    lines.append("> ⇒ 用户看不出焦点在哪。两个 `no` 才算数;`unknown`(控件被滚动移动 / 中性帧不稳定)不算缺陷。")
    lines.append("")
    if invisible:
        lines.append("| 页面 | 控件 | objectName | 可读名称 | 矩形(窗口坐标) |")
        lines.append("|---|---|---|---|---|")
        for page_key, kind, name, label, rect in invisible:
            lines.append(f"| {page_key} | `{kind}` | `{name}` | {label or '—'} | {rect} |")
    else:
        lines.append("(无)")
    lines.append("")
    lines.append(f"## 样式表中的 `:focus` 选择器({len(selectors)} 条)")
    lines.append("")
    for selector in selectors:
        lines.append(f"- `{selector}`")
    lines.append("")
    lines.append("## 各页面焦点路径")
    lines.append("")
    lines.extend(detail)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {out_path}")
    print(f"focus stops: {total}; pages: {len(NAV_KEYS)}; hard failures: {len(failures)}")
    print(
        "focus visual: "
        + ", ".join(f"{name}={count}" for name, count in sorted(visual_tally.items()) if count)
    )
    print(f"no visible focus effect: {len(invisible)}")
    for page_key, kind, name, label, rect in invisible:
        print(f"  INVISIBLE {page_key}: {kind} {name or '-'} {label or '-'} @ {rect}")
    for failure in failures:
        print(f"  FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
