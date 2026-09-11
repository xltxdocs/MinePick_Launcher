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

"""Instance folder-recognition tests: listing scans folders, legacy registry only backfills metadata."""

import json


def test_list_scans_instance_folders(ws_tmp, monkeypatch):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    from launcher import config as config_mod
    from launcher.instances import INSTANCE_META_FILENAME, Instance, list_instances

    cfg, cfg_path = config_mod.load()
    cfg.game_dir = ws_tmp / "mc"
    config_mod.save(cfg, cfg_path)
    # A folder with metadata
    a = ws_tmp / "mc" / "instances" / "alpha"
    a.mkdir(parents=True)
    (a / INSTANCE_META_FILENAME).write_text(
        json.dumps(Instance(name="alpha", version_id="1.20.1", created_at=1.0).model_dump(mode="json")),
        encoding="utf-8",
    )
    # A bare folder is still listed, but its version needs <id>/<id>.json (same
    # detection rule as the launch page dropdown).
    b = ws_tmp / "mc" / "instances" / "beta" / "versions" / "1.19.4"
    b.mkdir(parents=True)
    (b / "1.19.4.json").write_text("{}", encoding="utf-8")
    # A stray file is ignored
    (ws_tmp / "mc" / "instances" / "notes.txt").write_text("x", encoding="utf-8")
    found = list_instances()
    assert sorted(found) == ["alpha", "beta"]
    assert found["alpha"].version_id == "1.20.1"
    assert found["beta"].version_id == "1.19.4"


def test_custom_folder_is_independent(ws_tmp, monkeypatch):
    """Instances in one game dir never leak into another."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    from launcher import config as config_mod
    from launcher.instances import INSTANCE_META_FILENAME, Instance, list_instances

    cfg, cfg_path = config_mod.load()
    cfg.game_dir = ws_tmp / "dir_a"
    config_mod.save(cfg, cfg_path)
    a = ws_tmp / "dir_a" / "instances" / "only_a"
    a.mkdir(parents=True)
    (a / INSTANCE_META_FILENAME).write_text(
        json.dumps(Instance(name="only_a", version_id="1.20.1", created_at=1.0).model_dump(mode="json")),
        encoding="utf-8",
    )
    assert sorted(list_instances()) == ["only_a"]
    cfg.game_dir = ws_tmp / "dir_b"
    config_mod.save(cfg, cfg_path)
    assert list_instances() == {}
