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

"""Shared HTTP client tests: reuse, safe close, reset."""

from launcher.meta.manifest import _new_client, reset_http_client


def test_new_client_returns_same_shared_instance() -> None:
    a = _new_client()
    b = _new_client()
    assert a is b
    a.close()  # no-op close keeps the shared pool alive
    assert a is _new_client()


def test_reset_builds_fresh_client() -> None:
    a = _new_client()
    reset_http_client()
    b = _new_client()
    assert b is not a
    reset_http_client()  # restore a clean default for other tests

