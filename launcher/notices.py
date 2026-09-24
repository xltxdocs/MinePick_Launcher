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

"""Credits and third-party notices: the single source of truth for the About page and the notices file.

The About page renders these entries with translated descriptions, and
``tools/build_third_party_notices.py`` turns the very same entries into ``THIRD_PARTY_NOTICES.md``, so
the two can never drift apart. Proper nouns (project, library and service names) are never translated;
the description of each entry is an i18n key.

The wording of the "inspiration and community" entries is part of the licence hygiene of this project:
the PCL entry states explicitly that this is an independent implementation that contains none of the
upstream source code, and that statement must stay equivalent in every translation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Credit:
    """One acknowledgment: a proper noun, a translated description key and an optional link."""

    name: str
    detail_key: str
    license: str = ""
    url: str = ""


DEPENDENCIES: tuple[Credit, ...] = (
    Credit("Qt for Python (PySide6)", "about.credit.pyside6", "LGPL-3.0-only", "https://doc.qt.io/qtforpython-6/"),
    Credit("httpx", "about.credit.httpx", "BSD-3-Clause", "https://www.python-httpx.org/"),
    Credit("msal", "about.credit.msal", "MIT", "https://github.com/AzureAD/microsoft-authentication-library-for-python"),
    Credit("pydantic", "about.credit.pydantic", "MIT", "https://docs.pydantic.dev/"),
    Credit("platformdirs", "about.credit.platformdirs", "MIT", "https://github.com/platformdirs/platformdirs"),
    Credit("tenacity", "about.credit.tenacity", "Apache-2.0", "https://github.com/jd/tenacity"),
    Credit("rich", "about.credit.rich", "MIT", "https://github.com/Textualize/rich"),
    Credit("packaging", "about.credit.packaging", "Apache-2.0 or BSD-2-Clause", "https://github.com/pypa/packaging"),
    Credit(
        "cryptography (with OpenSSL)",
        "about.credit.cryptography",
        "Apache-2.0 or BSD-3-Clause",
        "https://cryptography.io/",
    ),
    Credit("truststore", "about.credit.truststore", "MIT", "https://github.com/sethmlarson/truststore"),
)

DEV_TOOLS: tuple[Credit, ...] = (
    Credit("pytest, respx, ruff, PyInstaller", "about.credit.devtools", "MIT / BSD-3-Clause / GPL-2.0 with exception"),
)

SERVICES: tuple[Credit, ...] = (
    Credit("Mojang & Microsoft", "about.credit.mojang", url="https://www.minecraft.net/"),
    Credit("Modrinth", "about.credit.modrinth", url="https://modrinth.com/"),
    Credit("CurseForge", "about.credit.curseforge", url="https://www.curseforge.com/minecraft"),
    Credit("Fabric", "about.credit.fabric", url="https://fabricmc.net/"),
    Credit("Forge", "about.credit.forge", url="https://files.minecraftforge.net/"),
    Credit("NeoForge", "about.credit.neoforge", url="https://neoforged.net/"),
    Credit("Adoptium (Eclipse Temurin)", "about.credit.adoptium", url="https://adoptium.net/"),
    Credit("GitHub", "about.credit.github", url="https://github.com/"),
)

COMMUNITY: tuple[Credit, ...] = (
    Credit(
        "Plain Craft Launcher 2 (PCL2) & PCL Community Edition (PCL CE)",
        "about.credit.pcl",
        url="https://github.com/PCL-Community/PCL-CE",
    ),
    Credit(
        "MinePick Launcher Classic",
        "about.credit.classic",
        url="https://github.com/xltxdocs/MinePick_Launcher_Classic",
    ),
    Credit(
        "TheDarkLord234",
        "about.credit.darklord",
        url="https://github.com/TheDarkLord234",
    ),
    Credit("Prism Launcher", "about.credit.prism", url="https://prismlauncher.org/"),
)


def groups() -> tuple[tuple[str, tuple[Credit, ...]], ...]:
    """The three groups in display order: (i18n section key, entries)."""
    return (
        ("about.credits.dependencies", DEPENDENCIES + DEV_TOOLS),
        ("about.credits.services", SERVICES),
        ("about.credits.community", COMMUNITY),
    )


def all_entries() -> tuple[Credit, ...]:
    """Every entry, in display order (used by the notices generator)."""
    return tuple(entry for _key, entries in groups() for entry in entries)
