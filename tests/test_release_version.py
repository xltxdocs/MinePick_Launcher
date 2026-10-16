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

"""Release-version guards for ``launcher.__version__``.

Two failures this file is written against, both silent in the GUI:

- a version string the updater cannot parse. ``launcher.updates.parse_version`` returns ``None`` for
  it, ``is_newer`` then returns False - "unparsable versions never are" - so the launcher reports
  "up to date" forever instead of raising anything;
- a version that drifted apart from the packaging metadata. The build reads the version from
  ``launcher/__init__.py`` while ``pyproject.toml`` carries its own copy, so nothing but a test keeps
  them equal.

The floor comparison is deliberately the strict direction: ``is_newer(__version__, LAST_RELEASED)``
asks whether this build is *ahead of* the last release, so leaving the constant at the released
number - the exact shape of the 0.4.1 miss, whose build reported the release before it - turns the
test red. The loose direction, ``is_newer(LAST_RELEASED, __version__)``, is satisfied by equality and
would have accepted that build, so it is not what this file asserts. ``is_newer`` is called inside
``assert`` directly (never pre-assigned to a name) so neither check disappears under ``python -O``.

Layer 3 is best-effort by construction: it reads local ``v*`` tags and returns without asserting when
the checkout has no tags (a source zip, or a CI checkout without tags fetched).

What these guards still cannot see: a release that raises the constant for the *wrong* version, or
one that ships without tagging at all. Raising ``LAST_RELEASED`` is part of publishing, so the
release checklist remains the only place where the constant, the tag and the release notes are
reconciled.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from launcher import __version__
from launcher.updates import is_newer, parse_version

ROOT = Path(__file__).resolve().parents[1]

# The last version published to users: the build under test has to be strictly newer than this.
LAST_RELEASED = "0.4.1"


def test_version_is_parsable() -> None:
    """Layer 1: the updater can compare this string, so a malformed one can never ship silently."""
    assert parse_version(__version__) is not None, (
        f"launcher.__version__ = {__version__!r} does not parse as a version; the update check "
        "would report 'up to date' forever"
    )


def test_version_is_newer_than_the_last_release() -> None:
    """Layer 1: this build must be strictly ahead of the released version, not level with it.

    The released version sits *below* this one, never at it: a build that reports the last released
    number is a build that forgot to raise the constant (0.4.1 shipped reporting 0.4.0), and the
    updater would keep offering the user the release they already installed.
    """
    assert is_newer(__version__, LAST_RELEASED), (
        f"launcher.__version__ = {__version__!r} is not newer than the released {LAST_RELEASED}; "
        "raise the version constant (and LAST_RELEASED in this file) when publishing a release"
    )


def test_version_matches_pyproject() -> None:
    """Layer 2: the build-time constant and the packaging metadata are the same version."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["project"]["version"]
    assert declared == __version__, (
        f"pyproject.toml says {declared!r} while launcher.__version__ is {__version__!r}; the release "
        "checklist expects the version to live in both places"
    )


def test_version_is_not_behind_the_newest_local_tag() -> None:
    """Layer 3: no local ``v*`` tag is newer than this build. Skipped without tags (zip, CI checkout)."""
    tag = _newest_local_tag()
    if tag is None:
        return
    assert not is_newer(tag, __version__), (
        f"the newest local tag {tag!r} is newer than launcher.__version__ = {__version__!r}; the "
        "version constant was left behind the release it is meant to be"
    )


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
