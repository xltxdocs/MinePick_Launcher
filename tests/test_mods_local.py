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

"""Unit tests for launcher/mods/local.py: scanning, metadata parsing, enable/disable, copy install."""

import json
import zipfile

from launcher.mods.local import (
    install_mod_file,
    read_mod_metadata,
    scan_mods,
    set_mod_enabled,
)


def _make_jar(path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_scan_mods_detects_enabled_disabled(ws_tmp):
    mods = ws_tmp / "mods"
    mods.mkdir()
    _make_jar(mods / "fabric-a.jar", {
        "fabric.mod.json": json.dumps({"id": "mod_a", "name": "Mod A", "version": "1.2.3"}),
    })
    _make_jar(mods / "old.jar.disabled", {"mcmod.info": json.dumps({"modid": "old", "name": "Old Mod"})})
    (mods / "not-a-mod.txt").write_text("x", encoding="utf-8")
    (mods / "empty.jar").write_bytes(b"not a zip")

    result = scan_mods(mods)
    assert len(result) == 3
    by_id = {m.mod_id: m for m in result}
    assert by_id["mod_a"].enabled is True
    assert by_id["mod_a"].name == "Mod A"
    assert by_id["mod_a"].version == "1.2.3"
    assert by_id["mod_a"].loader == "fabric"
    assert by_id["old"].enabled is False
    assert by_id["old"].file == "old.jar"
    assert by_id["old"].name == "Old Mod"
    assert by_id["old"].loader == "forge"
    empty = next(m for m in result if m.file == "empty.jar")
    assert empty.loader == "unknown"
    assert empty.name == "empty"


def test_metadata_loaders(ws_tmp):
    cases = {
        "neoforge.jar": ("META-INF/neoforge.mods.toml",
                         "[neoforge]\nloaderVersion=\"[2,)\"\n[[mods]]\nmodId=\"nf_mod\"\nversion=\"2.0\"\ndisplayName=\"NeoForge Mod\""),
        "forge.jar": ("META-INF/mods.toml",
                      "[[mods]]\nmodId=\"fg_mod\"\nversion=\"3.0\"\ndisplayName=\"Forge Mod\""),
        "quilt.jar": ("quilt.mod.json",
                      json.dumps({"quilt_loader": {"id": "q_mod", "version": "0.5", "metadata": {"name": "Quilt Mod"}}})),
    }
    for filename, (inner, content) in cases.items():
        p = ws_tmp / filename
        _make_jar(p, {inner: content})
        name, mod_id, version, loader = read_mod_metadata(p)
        assert loader in ("neoforge", "forge", "quilt")
        assert name.endswith("Mod")
        assert mod_id.endswith("_mod")
        assert version


def test_toggle_enabled_roundtrip(ws_tmp):
    mods = ws_tmp / "mods"
    mods.mkdir()
    p = mods / "x.jar"
    _make_jar(p, {"fabric.mod.json": json.dumps({"id": "x", "name": "X"})})
    mod = scan_mods(mods)[0]
    new = set_mod_enabled(mod, False)
    assert new.name == "x.jar.disabled" and new.exists() and not p.exists()
    assert set_mod_enabled(mod, True).name == "x.jar"
    assert p.exists()


def test_install_mod_file_copies_and_cleans_disabled(ws_tmp):
    src = ws_tmp / "src" / "m.jar"
    src.parent.mkdir()
    _make_jar(src, {"fabric.mod.json": "{}"})
    mods = ws_tmp / "mods"
    mods.mkdir()
    disabled = mods / "m.jar.disabled"
    disabled.write_bytes(b"old")
    target = install_mod_file(src, mods)
    assert target.exists()
    assert not disabled.exists()

