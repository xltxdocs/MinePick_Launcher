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

"""Generic downloader (sha1 verification, retry, concurrency, progress)."""

from launcher.net.downloader import (
    Downloader,
    DownloadError,
    DownloadProgress,
    DownloadResult,
    DownloadTask,
    sha1_file,
)

__all__ = [
    "DownloadError",
    "DownloadProgress",
    "DownloadResult",
    "DownloadTask",
    "Downloader",
    "sha1_file",
]
