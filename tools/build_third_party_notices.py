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

Versions are read from the installed distribution metadata rather than typed by hand: a notice that
claims a version nobody verified is worse than no version at all. Runtime dependencies and build/test
tools are listed separately, because only the former are redistributed inside the EXE.

Usage: python tools/build_third_party_notices.py
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.i18n import TRANSLATIONS
from launcher import __version__, notices
from launcher.updates import REPO

TARGET = ROOT / "THIRD_PARTY_NOTICES.md"

# notice entry name -> the distributions that realise it (a notice may cover more than one)
VERSION_SOURCES: dict[str, tuple[str, ...]] = {
    "Qt for Python (PySide6)": ("PySide6", "shiboken6"),
    "httpx": ("httpx",),
    "msal": ("msal",),
    "pydantic": ("pydantic",),
    "platformdirs": ("platformdirs",),
    "tenacity": ("tenacity",),
    "rich": ("rich",),
    "packaging": ("packaging",),
    "cryptography (with OpenSSL)": ("cryptography",),
    "truststore": ("truststore",),
    "pytest, respx, ruff, PyInstaller": ("pytest", "respx", "ruff", "pyinstaller"),
}

# shipped inside the EXE but never imported directly: they arrive with httpx
TRANSITIVE: tuple[tuple[str, str], ...] = (
    ("anyio", "anyio"),
    ("certifi", "certifi"),
    ("httpcore", "httpcore"),
    ("h11", "h11"),
    ("idna", "idna"),
)


def installed_version(distribution: str) -> str:
    """The version on disk, or an empty string when the distribution is absent."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return ""


def versions_for(name: str) -> str:
    """`PySide6 6.11.1, shiboken6 6.11.1` - only what is actually installed."""
    parts = [
        f"{distribution} {version}" if version else distribution
        for distribution in VERSION_SOURCES.get(name, ())
        if (version := installed_version(distribution))
    ]
    return ", ".join(parts)


def transitive_line() -> str:
    """`anyio 4.14.2, certifi 2026.7.22, ...` for the libraries httpx brings along."""
    parts = [
        f"{label} {version}" if version else label
        for label, distribution in TRANSITIVE
        if (version := installed_version(distribution))
    ]
    return ", ".join(parts)


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
            "apply to those parts. Versions are read from the installed distribution metadata."
        ),
        "",
        (
            "Qt for Python (PySide6) is licensed under **LGPL-3.0** and is shipped as a dynamically "
            "loaded library that the launcher does not modify. The single-file build unpacks those Qt "
            "libraries from the archive into a temporary directory when it starts; Qt's source code is "
            "available from <https://code.qt.io/> and from the Qt release archives at "
            "<https://download.qt.io/official_releases/qt/>. The About page inside the application "
            "shows the same list, translated into the interface language."
        ),
        "",
        (
            "MinePick Launcher 本体以 **GPL-3.0-only** 发布（见 [LICENSE](LICENSE)）。下列第三方组件与服务"
            "各自适用其自身许可与条款；版本号取自实际安装的发行版元数据。Qt for Python（PySide6）以 "
            "**LGPL-3.0** 授权，以动态库形式提供且未作修改；单文件构建在启动时会把这些 Qt 库从压缩包解压到"
            "临时目录。Qt 源码可从 <https://code.qt.io/> 与 <https://download.qt.io/official_releases/qt/> 获取。"
            "应用内的「关于」页展示同一份清单（按界面语言翻译）。"
        ),
        "",
    ]

    def entry_block(entry: notices.Credit) -> list[str]:
        head = f"- **{entry.name}**"
        if entry.license:
            head += f" — `{entry.license}`"
        versions = versions_for(entry.name)
        if versions:
            head += f" — installed: {versions}"
        block = [head, f"  - {en[entry.detail_key]}", f"  - {zh[entry.detail_key]}"]
        if entry.url:
            block.append(f"  - <{entry.url}>")
        return block

    dependency_key = notices.groups()[0][0]
    lines += [f"## {en[dependency_key]} / {zh[dependency_key]}", ""]
    lines += ["### Runtime dependencies / 运行时随程序分发", ""]
    for entry in notices.DEPENDENCIES:
        lines += entry_block(entry)
    lines += [
        f"- **{transitive_line()}**",
        (
            "  - pulled in by httpx; no separate notice applies, their licences are listed per "
            "package in the distribution metadata"
        ),
        "  - 由 httpx 引入；各自的许可条款见对应发行版的元数据",
        "",
        "### Build & test tools / 仅构建与测试时使用", "",
    ]
    for entry in notices.DEV_TOOLS:
        lines += entry_block(entry)
    lines.append("")

    for group_key, entries in notices.groups()[1:]:
        lines += [f"## {en[group_key]} / {zh[group_key]}", ""]
        for entry in entries:
            lines += entry_block(entry)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    text = render()
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(text)} chars, {len(notices.all_entries())} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
