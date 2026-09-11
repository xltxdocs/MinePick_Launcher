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

"""M0 引导脚本：把 Python 自带 pip/setuptools wheel 直接解压进 venv（绕开 ensurepip 的临时目录）。"""
import glob
import zipfile

SRC = r'D:\dsh-workspace\.tools\python\cpython-3.12.13-windows-x86_64-none\Lib\ensurepip\_bundled'
DEST = r'D:\dsh-workspace\minecraft-launcher\.venv\Lib\site-packages'

for whl in sorted(glob.glob(SRC + '\\*.whl')):
    print('extracting', whl)
    with zipfile.ZipFile(whl) as z:
        z.extractall(DEST)
print('bootstrap done')
