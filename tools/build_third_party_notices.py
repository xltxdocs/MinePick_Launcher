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

"""Generate THIRD_PARTY_NOTICES.md from ``launcher/notices.py`` and the GUI translations.

The About page renders the very same entries, so generating the file from them is what keeps the two
in sync; ``tests/test_notices.py`` fails whenever the checked-in file no longer matches this output.

Usage: python tools/build_third_party_notices.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.i18n import TRANSLATIONS
from launcher import __version__, notices
from launcher.updates import REPO

TARGET = ROOT / "THIRD_PARTY_NOTICES.md"


def render() -> str:
    """The full notices document (English first, Simplified Chinese underneath)."""
    en = TRANSLATIONS["en_us"]
    zh = TRANSLATIONS["zh_cn"]
    lines = [
        "# Third-party notices / 第三方许可声明",
        "",
        f"MinePick Launcher {__version__} — <https://github.com/{REPO}>",
        "",
        (
            "MinePick Launcher itself is released under **GPL-3.0-only** (see [LICENSE](LICENSE)). "
            "It uses the third-party components and services listed below; their own licences and terms "
            "apply to those parts."
        ),
        "",
        (
            "Qt for Python (PySide6) is licensed under **LGPL-3.0** and is shipped as a dynamically loaded "
            "library that the launcher does not modify. The About page inside the application shows the "
            "same list, translated into the interface language."
        ),
        "",
        (
            "MinePick Launcher 本体以 **GPL-3.0-only** 发布(见 [LICENSE](LICENSE))。下列第三方组件与服务"
            "各自适用其自身许可与条款;Qt for Python(PySide6)以 **LGPL-3.0** 授权,以动态库形式提供且未作修改。"
            "应用内的「关于」页展示同一份清单(按界面语言翻译)。"
        ),
        "",
    ]
    for group_key, entries in notices.groups():
        lines += [f"## {en[group_key]} / {zh[group_key]}", ""]
        for entry in entries:
            head = f"- **{entry.name}**"
            if entry.license:
                head += f" — `{entry.license}`"
            lines.append(head)
            lines.append(f"  - {en[entry.detail_key]}")
            lines.append(f"  - {zh[entry.detail_key]}")
            if entry.url:
                lines.append(f"  - <{entry.url}>")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    text = render()
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(text)} chars, {len(notices.all_entries())} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
