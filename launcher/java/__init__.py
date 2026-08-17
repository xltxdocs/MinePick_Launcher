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

"""Java runtime detection and Adoptium download."""

from launcher.java.install import JavaAsset, fetch_assets, install_java
from launcher.java.locate import (
    JavaError,
    JavaRuntime,
    has_suitable_java,
    list_java,
    match_java,
    parse_java_major,
    probe_java_major,
)

__all__ = [
    "JavaAsset",
    "JavaError",
    "JavaRuntime",
    "fetch_assets",
    "has_suitable_java",
    "install_java",
    "list_java",
    "match_java",
    "parse_java_major",
    "probe_java_major",
]
