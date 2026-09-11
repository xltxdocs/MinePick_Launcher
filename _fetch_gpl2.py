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

import io
import sys

sys.path.insert(0, "D:\\dsh-workspace\\minecraft-launcher")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from launcher.meta.manifest import _new_client

try:
    client = _new_client()
    try:
        resp = client.get("https://www.gnu.org/licenses/gpl-3.0.txt")
        resp.raise_for_status()
        text = resp.text
    finally:
        client.close()
    with open("D:\\dsh-workspace\\minecraft-launcher\\LICENSE", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("LEN=", len(text))
    print("HEAD=", text[:50].replace(chr(10), " "))
    print("OK")
except Exception as exc:
    print("FAIL:", type(exc).__name__, str(exc)[:300])
