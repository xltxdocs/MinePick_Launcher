"""Version uninstall (uninstall_version / list_installed_versions / dependents)."""

import json

import pytest

from launcher.install import (
    find_version_dependents,
    list_installed_versions,
    uninstall_version,
)
from launcher.meta import MetaError


def _prepare(ws_tmp):
    game = ws_tmp / "mc"
    versions = game / "versions"
    vdir = versions / "1.20.1"
    vdir.mkdir(parents=True)
    (vdir / "1.20.1.json").write_text(json.dumps({"id": "1.20.1"}), encoding="utf-8")
    (vdir / "1.20.1.jar").write_bytes(b"jar")
    # a Fabric profile that depends on 1.20.1
    fab = versions / "fabric-loader-0.19.3-1.20.1"
    fab.mkdir(parents=True)
    (fab / "fabric-loader-0.19.3-1.20.1.json").write_text(
        json.dumps({"id": "fabric-loader-0.19.3-1.20.1", "inheritsFrom": "1.20.1"}),
        encoding="utf-8",
    )
    # an empty directory without a json is not considered installed
    (versions / "empty-dir").mkdir()
    return game, versions, vdir, fab


def test_list_and_dependents(ws_tmp):
    game, _versions, _vdir, _fab = _prepare(ws_tmp)
    assert list_installed_versions(game) == ["1.20.1", "fabric-loader-0.19.3-1.20.1"]
    assert find_version_dependents(game, "1.20.1") == ["fabric-loader-0.19.3-1.20.1"]
    assert find_version_dependents(game, "fabric-loader-0.19.3-1.20.1") == []


def test_uninstall_removes_dir_and_reports_dependents(ws_tmp):
    game, _versions, vdir, fab = _prepare(ws_tmp)
    deps = uninstall_version("1.20.1", game)
    assert deps == ["fabric-loader-0.19.3-1.20.1"]
    assert not vdir.exists()
    assert fab.exists()  # other profile directories are kept
    assert list_installed_versions(game) == ["fabric-loader-0.19.3-1.20.1"]
    with pytest.raises(MetaError):
        uninstall_version("1.20.1", game)  # already uninstalled
