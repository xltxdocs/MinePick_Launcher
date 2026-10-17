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

"""Release-version guards for ``launcher.__version__`` and the nine READMEs.

Four failures this file is written against, every one of them silent in the GUI:

- a version string the updater cannot parse. ``launcher.updates.parse_version`` returns ``None`` for
  it, ``is_newer`` then returns False - "unparsable versions never are" - so the launcher reports
  "up to date" forever instead of raising anything;
- a version that drifted apart from the packaging metadata. The build reads the version from
  ``launcher/__init__.py`` while ``pyproject.toml`` carries its own copy, so nothing but a test keeps
  them equal;
- a release that tags and bumps the package but leaves the nine READMEs announcing the version
  before it. That banner means "newest published release", so the repository keeps advertising a
  version users have already moved past. 0.4.2 shipped exactly this way: tagged, published, and
  every README still said 0.4.1. Layer 5 reads the banner back against the newest local tag.

The floor comparison is deliberately the strict direction: ``is_newer(__version__, LAST_RELEASED)``
asks whether this build is *ahead of* the last release, so leaving the constant at the released
number - the exact shape of the 0.4.1 miss, whose build reported the release before it - turns the
test red. The loose direction, ``is_newer(LAST_RELEASED, __version__)``, is satisfied by equality and
would have accepted that build, so it is not what this file asserts. ``is_newer`` is called inside
``assert`` directly (never pre-assigned to a name) so neither check disappears under ``python -O``.

Layers 4 and 5 are best-effort by construction: they read local ``v*`` tags and return without
asserting when the checkout has no tags (a source zip, or a CI checkout without tags fetched).

What these guards still cannot see: a release that raises the constant for the *wrong* version, or
one that ships without tagging at all. Raising ``LAST_RELEASED`` is part of publishing, so the
release checklist remains the only place where the constant, the tag and the release notes are
reconciled. A checkout with no tags stands both tag-based layers down, so it proves nothing about
the READMEs either.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from launcher import __version__
from launcher.updates import is_newer, parse_version

ROOT = Path(__file__).resolve().parents[1]

# The last version published to users: the build under test has to be strictly newer than this.
LAST_RELEASED = "0.4.1"

# Each of the nine READMEs announces the newest published release on one bolded line near the top.
# The wording is per language ("**Current release: X.Y.Z**", "**当前版本 X.Y.Z**", ...), so the line
# is recognised by its shape instead of its words, and only the head of the file is scanned: the
# bodies mention older versions in changelogs, and matching those would fire on history, not on the
# banner.
README_RELEASE_FILES = (
    "README.md",
    "README_zh.md",
    "README_zh_TW.md",
    "README_ja.md",
    "README_ko.md",
    "README_ru.md",
    "README_fr.md",
    "README_es.md",
    "README_de.md",
)
README_HEAD_LINES = 20
README_RELEASE_SHAPE = "**<release wording> X.Y.Z**"
VERSION_TOKEN = re.compile(r"\d+\.\d+\.\d+")


def test_version_is_parsable() -> None:
    """Layer 1: the updater can compare this string, so a malformed one can never ship silently."""
    assert parse_version(__version__) is not None, (
        f"launcher.__version__ = {__version__!r} does not parse as a version; the update check "
        "would report 'up to date' forever"
    )


def test_version_is_newer_than_the_last_release() -> None:
    """Layer 2: this build must be strictly ahead of the released version, not level with it.

    The released version sits *below* this one, never at it: a build that reports the last released
    number is a build that forgot to raise the constant (0.4.1 shipped reporting 0.4.0), and the
    updater would keep offering the user the release they already installed.
    """
    assert is_newer(__version__, LAST_RELEASED), (
        f"launcher.__version__ = {__version__!r} is not newer than the released {LAST_RELEASED}; "
        "raise the version constant (and LAST_RELEASED in this file) when publishing a release"
    )


def test_version_matches_pyproject() -> None:
    """Layer 3: the build-time constant and the packaging metadata are the same version."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["project"]["version"]
    assert declared == __version__, (
        f"pyproject.toml says {declared!r} while launcher.__version__ is {__version__!r}; the release "
        "checklist expects the version to live in both places"
    )


def test_version_is_not_behind_the_newest_local_tag() -> None:
    """Layer 4: no local ``v*`` tag is newer than this build. Skipped without tags (zip, CI checkout)."""
    tag = _newest_local_tag()
    if tag is None:
        return
    assert not is_newer(tag, __version__), (
        f"the newest local tag {tag!r} is newer than launcher.__version__ = {__version__!r}; the "
        "version constant was left behind the release it is meant to be"
    )


@pytest.mark.parametrize("name", README_RELEASE_FILES)
def test_readme_release_matches_the_newest_local_tag(name: str) -> None:
    """Layer 5: every README advertises the newest released version, not the one before it.

    The banner means "newest published release", so tagging without raising the READMEs leaves the
    repository advertising a version users have already moved past - the shape of the 0.4.2 publish,
    which tagged and bumped the package while all nine READMEs still said 0.4.1. Every file is
    checked, because a release that updates nine of them is exactly as wrong as one that updates
    none. Skipped without local tags, like the check above.
    """
    tag = _newest_local_tag()
    if tag is None:
        return
    released = parse_version(tag)
    number, declared = _readme_release(name)
    assert parse_version(declared) == released, (
        f"{name}:{number} advertises {declared!r} as the current release, but the newest local tag "
        f"is {tag!r}; after a release, raise that line in all nine READMEs to {released}"
    )


def _readme_release(name: str) -> tuple[int, str]:
    """The (line number, version) of the head line of ``name`` that announces a release."""
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    found: list[tuple[int, str]] = []
    for number, line in enumerate(lines[:README_HEAD_LINES], start=1):
        token = VERSION_TOKEN.search(line)
        if token is not None and line.lstrip().startswith("**"):
            found.append((number, token.group()))
    assert len(found) == 1, (
        f"{name} has {len(found)} release-shaped lines in its first {README_HEAD_LINES} lines "
        f"(line numbers {[number for number, _ in found]}); each README carries exactly one, "
        f"shaped {README_RELEASE_SHAPE}"
    )
    return found[0]


def _newest_local_tag() -> str | None:
    """The newest ``v*`` git tag by version order, or None when there is no local tag to read."""
    if not (ROOT / ".git").exists():
        return None
    try:
        # fixed argv, no shell, no user input
        result = subprocess.run(
            ["git", "tag", "--list", "v*", "--sort=-v:refname"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    parsed = [(version, tag) for tag in tags if (version := parse_version(tag)) is not None]
    if not parsed:
        return None
    return max(parsed)[1]
