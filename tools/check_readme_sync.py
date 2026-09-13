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

"""Compare the nine README translations for structural drift.

Translations are edited by hand, so a language can silently lose a link, an inline code
identifier or a version token while the prose still looks complete. This compares every
translation against the English README and reports what is missing or extra.

Two differences are intentional and must never be reported as drift:
- only the Chinese READMEs list the built-in Chinese mod-name table (it is a Chinese-only feature);
- the Chinese READMEs link the Chinese developer docs while the others link docs/*_en.md.

Usage: python tools/check_readme_sync.py [--json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "README.md"
TRANSLATIONS = [
    "README_zh.md",
    "README_zh_TW.md",
    "README_ja.md",
    "README_ko.md",
    "README_ru.md",
    "README_fr.md",
    "README_es.md",
    "README_de.md",
]

# things that legitimately differ per language and must not be reported as drift
LINK_EXCEPTIONS = {"README.md", "README_zh.md", "README_zh_TW.md", "README_ja.md", "README_ko.md",
                   "README_ru.md", "README_fr.md", "README_es.md", "README_de.md"}


def links(text: str) -> set[str]:
    """Markdown link targets, minus the language switcher and the language files themselves."""
    found = set(re.findall(r"\]\((?!https?:)([^)#]+)\)", text))
    return {link for link in found if link not in LINK_EXCEPTIONS}


def normalise_docs(values: set[str]) -> set[str]:
    """The two Chinese READMEs legitimately link the Chinese developer docs."""
    return {re.sub(r"(docs/[a-z_]+)_en\.md$", r"\1.md", value) for value in values}


def identifiers(text: str) -> set[str]:
    """Inline code spans that look like paths, files or commands (the contract of the doc)."""
    spans = set(re.findall(r"`([^`\n]+)`", text))
    keep = set()
    for span in spans:
        if (re.search(r"\.(py|md|zip|exe|toml|spec|ps1|png|txt|json|qss)$", span)
                or "/" in span or "\\" in span
                or re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", span)):  # MCLAUNCHER_TOKEN_PASSWORD …
            keep.add(span)
    return keep


def versions(text: str) -> set[str]:
    return set(re.findall(r"\b\d+\.\d+\.\d+\b", text))


def images(text: str) -> set[str]:
    return set(re.findall(r'src="([^"]+)"', text))


def main() -> int:
    base_text = BASE.read_text(encoding="utf-8")
    base = {
        "links": links(base_text),
        "identifiers": normalise_docs(identifiers(base_text)),
        "versions": versions(base_text),
        "images": images(base_text),
    }
    problems: dict[str, dict[str, list[str]]] = {}
    for name in TRANSLATIONS:
        text = (ROOT / name).read_text(encoding="utf-8")
        current = {
            # the zh files keep their own screenshot set, so images are compared per language
            "links": links(text),
            "identifiers": normalise_docs(identifiers(text)),
            "versions": versions(text),
            "images": images(text),
        }
        diff = {}
        for kind, values in current.items():
            missing = sorted(base[kind] - values)
            if kind == "images":
                # screenshots are localised: only complain when a language has no image at all
                missing = [] if values else sorted(base[kind])
            extra = sorted(values - base[kind]) if kind != "images" else []
            if missing or extra:
                diff[kind] = {"missing": missing, "extra": extra}
        if diff:
            problems[name] = diff

    if "--json" in sys.argv:
        print(json.dumps({"ok": not problems, "drift": problems}, ensure_ascii=False))
        return 0

    print(f"baseline: README.md  ({len(base['links'])} links, {len(base['identifiers'])} identifiers, "
          f"{len(base['versions'])} version tokens)")
    if not problems:
        print("readme sync: 0 drift across", len(TRANSLATIONS), "translations")
        return 0
    for name, diff in problems.items():
        print(f"  {name}:")
        for kind, missing in diff.items():
            print(f"    {kind}: missing {missing.get('missing')} extra {missing.get('extra')}")
    print(f"readme sync: drift in {len(problems)}/{len(TRANSLATIONS)} translations")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
