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

"""BOM tolerance tests: config and instance registry must load files with a UTF-8 BOM."""

import json


def test_config_loads_utf8_bom(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp))
    from launcher import config as config_mod

    cfg, cfg_path = config_mod.load()
    config_mod.save(cfg, cfg_path)
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    raw["memory_gb"] = 3.5
    cfg_path.write_bytes(b"\xef\xbb\xbf" + json.dumps(raw).encode("utf-8"))
    cfg2, _ = config_mod.load()
    assert cfg2.memory_gb == 3.5

