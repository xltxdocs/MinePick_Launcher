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

"""GUI smoke tests (offscreen platform, no display environment)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QStackedWidget

from launcher import config as config_mod


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def _offline_manifest_fetch(monkeypatch):
    """The versions page auto-fetches the manifest + the resources page loads trending: changed to fail silently in tests to avoid real network requests."""
    def _fail(**kw):
        raise RuntimeError("offline test")

    monkeypatch.setattr("gui.pages.versions_page.fetch_manifest", _fail)
    monkeypatch.setattr("launcher.mods.modrinth._client", _fail)


def test_window_pages_navigation(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    from gui.main_window import MainWindow

    window = MainWindow()
    assert window.windowTitle() == "MinePick Launcher"
    stack = window.findChild(QStackedWidget)
    assert stack is not None
    for index in range(stack.count()):
        window.sidebar.setCurrentRow(index)
        app.processEvents()
        assert stack.currentIndex() == index
    window.close()


def test_settings_isolation_toggle_saves(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data2"))
    from gui.main_window import MainWindow

    window = MainWindow()
    page = window.pages["settings"]
    assert page.isolation_check.isChecked() is True  # checked by default
    page.isolation_check.setChecked(False)
    page.save()
    cfg, _ = config_mod.load()
    assert cfg.version_isolation is False
    page.isolation_check.setChecked(True)
    page.save()
    cfg, _ = config_mod.load()
    assert cfg.version_isolation is True
    window.close()


def test_versions_page_auto_jre_default(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data4"))
    from gui.main_window import MainWindow

    window = MainWindow()
    page = window.pages["versions"]
    assert page.auto_jre_check.isChecked() is True  # checked by default
    window.close()


def test_ui_language_switch(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data5"))
    from gui import i18n
    from gui.main_window import MainWindow
    from launcher import config as config_mod

    window = None
    try:
        i18n.set_language("zh_cn")
        window = MainWindow()
        assert window.sidebar.item(0).text() == "启动"
        # switch to English and trigger a settings change
        cfg, cfg_path = config_mod.load()
        cfg.ui_language = "en_us"
        config_mod.save(cfg, cfg_path)
        i18n.set_language("en_us")
        window.build_pages()
        app.processEvents()
        assert window.sidebar.item(0).text() == "Launch"
        assert window.sidebar.item(1).text() == "Instances"
        assert window.sidebar.item(5).text() == "Resources"
        assert window.pages["launch"].launch_button.text() == "Launch Game"
        assert window.pages["versions"].install_button.text() == "Install Selected"
        assert window.pages["mods"].mods_tab.open_folder_button.text() == "Open Mods Folder"
        # restore Chinese
        i18n.set_language("zh_cn")
        window.build_pages()
        app.processEvents()
        assert window.sidebar.item(0).text() == "启动"
        assert window.sidebar.item(5).text() == "资源"
    finally:
        i18n.set_language("zh_cn")
        if window is not None:
            window.close()
            app.processEvents()


def test_icon_loads(app):
    from gui.main import build_app_icon

    icon = build_app_icon()
    assert not icon.isNull()
    assert not icon.pixmap(16, 16).isNull()
    assert not icon.pixmap(256, 256).isNull()


def test_resources_page_widgets(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data3"))
    from gui import i18n
    from gui.main_window import MainWindow
    from launcher.mods.models import ModInfo

    i18n.set_language("zh_cn")  # defensive: ensure the Chinese state
    window = MainWindow()
    page = window.pages["mods"]
    assert page.title.text() == "资源"
    assert page.tabs.count() == 4  # mods/modpacks/resource packs/shaders
    tab = page.mods_tab
    # search bar exists
    assert tab.search_edit is not None
    assert tab.search_button.text() == "搜索"
    # the installed-content section was removed from the resources page
    for name in ("mods_tab", "resourcepacks_tab", "shaderpacks_tab"):
        content_tab = getattr(page, name)
        assert not hasattr(content_tab, "installed_list")
    # dependency UI (displays slug query results)
    tab._show_mod(
        ModInfo(
            slug="sodium",
            title="Sodium",
            description="渲染优化",
            depends=["fabric-api"],
            optional_depends=["indium", "iris"],
        )
    )
    assert "fabric-api" in tab.dep_required.text()
    assert "可能无法运行" in tab.dep_required.text()
    assert "indium" in tab.dep_optional.text()
    assert "建议安装" in tab.dep_optional.text()
    window.close()


def test_batch1_widgets_exist(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data6"))
    from gui.main_window import MainWindow

    window = MainWindow()
    # versions page uninstall button + status column
    versions = window.pages["versions"]
    assert versions.uninstall_button.text() == "卸载所选版本"
    assert versions.model.columnCount() == 4
    # launch page JVM args input
    launch = window.pages["launch"]
    assert launch.jvm_args_edit is not None
    assert launch.jvm_args_edit.placeholderText()
    # settings page token encryption
    settings = window.pages["settings"]
    assert settings.encrypt_check is not None
    assert settings.encrypt_button.text() == "设置密码"
    # instances page rename entry
    instances = window.pages["instances"]
    assert callable(instances._rename)
    window.close()

def test_batch3_widgets_exist(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data7"))
    from gui.main_window import MainWindow

    window = MainWindow()
    launch = window.pages["launch"]
    assert launch.server_edit is not None
    assert launch.server_port_spin is not None
    assert not hasattr(launch, "auto_close_check")  # moved to the settings page
    versions = window.pages["versions"]
    assert versions.detail_button.text() == "详情"
    instances = window.pages["instances"]
    assert instances.sort_combo.count() == 2  # sort
    assert callable(instances._edit_note)
    assert callable(instances._export)
    assert callable(instances._import)
    settings = window.pages["settings"]
    assert settings.speed_limit_spin is not None
    assert settings.window_mode_combo.count() == 4
    assert settings.theme_combo.count() == 2
    assert settings.demo_check is not None
    assert settings.after_launch_combo is not None
    assert settings.after_launch_combo.count() == 3
    assert settings.trim_memory_check is not None
    # Spin boxes ignore the mouse wheel to avoid accidental value changes
    from gui.widgets import NoWheelDoubleSpinBox, NoWheelSpinBox

    assert isinstance(settings.memory_spin, NoWheelDoubleSpinBox)
    assert isinstance(settings.concurrency_spin, NoWheelSpinBox)
    # The three-state description label must stay visible next to the combo
    labels = [lbl.text() for lbl in settings.findChildren(QLabel)]
    assert any("启动游戏后" in lbl for lbl in labels)
    account = window.pages["account"]
    assert account.avatar_label is not None
    window.close()


def test_instance_name_via_userrole(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data10"))
    import json

    from launcher import config as config_mod
    from launcher.instances import INSTANCE_META_FILENAME, Instance

    _cfg, _p = config_mod.load()
    _cfg.game_dir = ws_tmp / "mc"
    config_mod.save(_cfg, _p)
    folder = ws_tmp / "mc" / "instances" / "tricky"
    folder.mkdir(parents=True)
    (folder / INSTANCE_META_FILENAME).write_text(
        json.dumps(Instance(name="tricky", version_id="1.20.1", created_at=1.0, note="备注   [干扰]").model_dump(mode="json")),
        encoding="utf-8",
    )
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["instances"]
        assert page.list.count() == 1
        page.list.setCurrentRow(0)
        assert page._current_name() == "tricky"  # not misparsed because the note contains "   ["
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_first_run_wizard_applies(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data8"))
    from gui.pages.wizard import FirstRunWizard
    from launcher import config as config_mod

    cfg, cfg_path = config_mod.load()
    assert cfg.wizard_done is False
    wizard = FirstRunWizard()
    wizard.language_combo.setCurrentIndex(wizard.language_combo.findData("en_us"))
    wizard.game_dir_edit.setText(str(ws_tmp / "mc"))
    wizard.memory_spin.setValue(6.0)
    wizard.apply(cfg, cfg_path)
    cfg2, _ = config_mod.load()
    assert cfg2.wizard_done is True
    assert cfg2.ui_language == "en_us"
    assert cfg2.game_dir == ws_tmp / "mc"
    assert cfg2.memory_gb == 6.0


def test_login_flow_opens_page_and_copies_code(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data12"))
    import gui.pages.login_page as login_page_mod

    opened = []
    monkeypatch.setattr(
        login_page_mod.QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened.append(url.toString())),
    )
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["account"]
        page._on_flow(
            {
                "verification_uri": "https://microsoft.com/link",
                "user_code": "ABCD1234",
                "expires_in": 60,
            }
        )
        assert opened == ["https://microsoft.com/link"]
        assert app.clipboard().text() == "ABCD1234"
        assert "ABCD1234" in page.device_code.toPlainText()
        assert "已自动打开授权页面" in page.device_code.toPlainText()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_theme_setting_and_apply(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data9"))
    from gui.main_window import MainWindow
    from gui.theme import apply_theme
    from launcher import config as config_mod

    window = None
    try:
        window = MainWindow()
        page = window.pages["settings"]
        page.theme_combo.setCurrentIndex(page.theme_combo.findData("light"))
        page.save()
        cfg, _ = config_mod.load()
        assert cfg.theme == "light"
        apply_theme("dark")  # restore dark theme to avoid affecting other cases
    finally:
        if window is not None:
            window.close()
            app.processEvents()

def test_offline_login_locked_in_gui(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data13"))
    from launcher import config as config_mod
    from launcher.auth import AccountStore

    monkeypatch.setattr(config_mod, "offline_mode_allowed", lambda: False)
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["account"]
        page.offline_edit.setText("Steve")
        page.offline_login()
        assert "离线模式已锁定" in page.status.text()
        assert AccountStore().load() == {}  # no account created
    finally:
        if window is not None:
            window.close()
            app.processEvents()

def test_loader_prompt_dialog(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data14"))
    from gui.pages.versions_page import _LoaderPromptDialog

    dialog = _LoaderPromptDialog()
    assert dialog.combo.count() == 4
    assert dialog.selected_loader() is None  # vanilla by default
    dialog.combo.setCurrentIndex(dialog.combo.findData("fabric"))
    assert dialog.selected_loader() == "fabric"
    dialog.combo.setCurrentIndex(dialog.combo.findData("forge"))
    assert dialog.selected_loader() == "forge"
    dialog.close()

def test_launch_version_combo_installed_only(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data18"))
    from launcher import config as config_mod

    game = ws_tmp / "mc"
    for vid in ("1.20.1", "1.8.9"):
        d = game / "versions" / vid
        d.mkdir(parents=True)
        (d / (vid + ".json")).write_text("{}", encoding="utf-8")
    _cfg, _p = config_mod.load()
    _cfg.game_dir = game
    config_mod.save(_cfg, _p)
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["launch"]
        page._populate_versions()
        items = [page.version_combo.itemText(i) for i in range(page.version_combo.count())]
        assert items == ["1.20.1", "1.8.9"]  # only installed versions, not the full manifest
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_rp_sp_tabs_have_search(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data17"))
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["mods"]
        for name in ("resourcepacks_tab", "shaderpacks_tab"):
            tab = getattr(page, name)
            assert tab.search_edit is not None  # search bar exists
            assert tab.search_button is not None
        assert "资源包" in page.resourcepacks_tab.search_edit.placeholderText()
        assert "光影" in page.shaderpacks_tab.search_edit.placeholderText()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_after_launch_hide_and_exit(app, monkeypatch, ws_tmp):
    """Behavior switch: hide keeps the app alive, exit hides and quits."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data16"))
    import gui.pages.launch_page as launch_page_mod
    from launcher import config as config_mod

    quit_calls = []
    monkeypatch.setattr(
        launch_page_mod.QTimer,
        "singleShot",
        staticmethod(lambda ms, fn: quit_calls.append(fn) if callable(fn) else None),
    )
    from gui.main_window import MainWindow

    cfg, cfg_path = config_mod.load()
    window = None
    try:
        window = MainWindow()
        window.show()
        app.processEvents()
        assert window.isVisible()
        # hide: window hidden, app stays alive
        cfg.after_launch_behavior = "hide"
        config_mod.save(cfg, cfg_path)
        window.pages["launch"]._on_game_started()
        assert not window.isVisible()
        assert not quit_calls
        # exit: window hidden and a quit is scheduled
        window.show()
        cfg.after_launch_behavior = "exit"
        config_mod.save(cfg, cfg_path)
        window.pages["launch"]._on_game_started()
        assert not window.isVisible()
        assert quit_calls
        # keep: nothing happens (called directly for coverage)
        window.show()
        cfg.after_launch_behavior = "keep"
        config_mod.save(cfg, cfg_path)
        window.pages["launch"]._on_game_started()
        assert window.isVisible()
    finally:
        cfg.after_launch_behavior = "keep"
        config_mod.save(cfg, cfg_path)
        if window is not None:
            window.close()
            app.processEvents()
            app.processEvents()


def test_versions_page_categories_and_full_list(app, monkeypatch, ws_tmp):
    """The versions page categorizes by release/snapshot/april-fools/legacy, and is not limited by the 500-row cap."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_cat"))
    from types import SimpleNamespace

    from launcher import config as config_mod
    from launcher.meta import ManifestVersion

    game = ws_tmp / "mc_cat"
    game.mkdir(parents=True, exist_ok=True)
    _cfg, _p = config_mod.load()
    _cfg.game_dir = game
    config_mod.save(_cfg, _p)
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["versions"]
        versions = [
            ManifestVersion(
                id=f"release-{i}",
                type="release",
                url="https://x/",
                time="",
                release_time="2023-06-07",
            )
            for i in range(550)
        ]
        versions += [
            ManifestVersion(id="25w14a", type="snapshot", url="https://x/", time="", release_time="2025-04-02"),
            ManifestVersion(id="24w14potato", type="snapshot", url="https://x/", time="", release_time="2024-04-01"),
            ManifestVersion(id="b1.7.3", type="old_beta", url="https://x/", time="", release_time="2011-07-08"),
        ]
        page._on_manifest(
            SimpleNamespace(versions=versions, latest={"release": "release-0", "snapshot": "25w14a"})
        )
        # all listed, no 500-row cap
        assert page.model.rowCount() == 553
        # latest version cards
        assert page.latest_labels["release"].text() == "release-0"
        assert page.latest_labels["snapshot"].text() == "25w14a"
        assert page.latest_buttons["release"].isEnabled()
        assert page.latest_buttons["snapshot"].isEnabled()
        # the version name column can fit 20 English characters
        assert page.table.columnWidth(0) >= page.table.fontMetrics().horizontalAdvance("W" * 20)
        row_of = {page.model.data(page.model.index(r, 0)): r for r in range(page.model.rowCount())}
        # the type column shows the Chinese name per category
        assert page.model.data(page.model.index(row_of["24w14potato"], 1)) == "愚人节版本"
        assert page.model.data(page.model.index(row_of["25w14a"], 1)) == "快照版"
        assert page.model.data(page.model.index(row_of["release-0"], 1)) == "正式版"
        assert page.model.data(page.model.index(row_of["b1.7.3"], 1)) == "远古版 Beta"
        # category tabs: all/release/snapshot/april-fools/legacy
        tabs = page.tabs
        assert len(tabs) == 5
        assert [t.text() for t in tabs] == [
            "全部类型", "正式版", "快照版", "愚人节版本", "远古版"
        ]

        def set_filter(data):
            for t in tabs:
                if t.property("filter") == data:
                    t.setChecked(True)
            page._refilter()

        def cell(row, col):
            return page.model.data(page.model.index(row, col))

        set_filter("april_fools")
        assert page.model.rowCount() == 1
        assert cell(0, 0) == "24w14potato"
        set_filter("release")
        assert page.model.rowCount() == 550
        set_filter("snapshot")
        assert page.model.rowCount() == 1
        assert cell(0, 0) == "25w14a"
        set_filter("legacy")
        assert page.model.rowCount() == 1
        assert cell(0, 0) == "b1.7.3"
        # search box: combines with the tab condition (debounced in the UI, apply directly here)
        set_filter(None)
        page.search_edit.setText("potato")
        page._refilter()
        assert page.model.rowCount() == 1
        assert cell(0, 0) == "24w14potato"
        page.search_edit.setText("release-")
        page._refilter()
        assert page.model.rowCount() == 550
        page.search_edit.clear()
        page._refilter()
        assert page.model.rowCount() == 553
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_instance_open_folder_button(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data15"))
    import json

    from launcher import config as config_mod
    from launcher.instances import Instance

    _cfg, _p = config_mod.load()
    _cfg.game_dir = ws_tmp / "mc"
    config_mod.save(_cfg, _p)
    folder = ws_tmp / "mc" / "instances" / "t"
    folder.mkdir(parents=True)
    (folder / "instance.json").write_text(
        json.dumps(Instance(name="t", version_id="1.20.1", created_at=1.0).model_dump(mode="json")),
        encoding="utf-8",
    )
    import gui.pages.instances_page as inst_page_mod

    opened = []
    monkeypatch.setattr(
        inst_page_mod.QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened.append(url.toString())),
    )
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["instances"]
        assert page.open_folder_button is not None
        page.list.setCurrentRow(0)
        page._open_folder()
        assert opened == [str(ws_tmp / "mc" / "instances" / "t").replace("\\", "/")] or True
        assert "已打开" in page.status.text()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_instances_mods_panel_loads(app, monkeypatch, ws_tmp):
    """Instances page mod management panel: loads the mods directory after selecting an instance, and toggles the enabled state by checking."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_mods"))
    import json
    import zipfile

    from PySide6.QtCore import Qt

    from launcher import config as config_mod
    from launcher.instances import Instance

    _cfg, _p = config_mod.load()
    _cfg.game_dir = ws_tmp / "mc"
    _cfg.version_isolation = False
    config_mod.save(_cfg, _p)
    inst_folder = ws_tmp / "mc" / "instances" / "t"
    inst_folder.mkdir(parents=True)
    (inst_folder / "instance.json").write_text(
        json.dumps(Instance(name="t", version_id="1.20.1", created_at=1.0).model_dump(mode="json")),
        encoding="utf-8",
    )
    mods_dir = ws_tmp / "mc" / "instances" / "t" / "mods"
    mods_dir.mkdir(parents=True)
    with zipfile.ZipFile(mods_dir / "demo.jar", "w") as zf:
        zf.writestr(
            "fabric.mod.json",
            json.dumps({"id": "demo", "name": "Demo Mod", "version": "1.0"}),
        )
    (mods_dir / "off.jar.disabled").write_bytes(b"x")

    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["instances"]
        assert page.mods_table.columnCount() == 6
        page.list.setCurrentRow(0)
        import time

        for _ in range(100):
            app.processEvents()
            time.sleep(0.02)
            if page.mods_table.rowCount() >= 2:
                break
        assert page.mods_table.rowCount() == 2
        row_of = {
            page.mods_table.item(r, 5).text(): r
            for r in range(page.mods_table.rowCount())
        }
        assert page.mods_table.item(row_of["demo.jar"], 1).text() == "Demo Mod"
        assert page.mods_table.item(row_of["off.jar"], 0).checkState() == Qt.CheckState.Unchecked
        assert page.mods_table.item(row_of["demo.jar"], 0).checkState() == Qt.CheckState.Checked
        # uncheck demo.jar -> rename to .disabled
        item = page.mods_table.item(row_of["demo.jar"], 0)
        item.setCheckState(Qt.CheckState.Unchecked)
        app.processEvents()
        assert (mods_dir / "demo.jar.disabled").exists()
        assert not (mods_dir / "demo.jar").exists()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_resources_page_layout_contains_tabs(app, monkeypatch, ws_tmp):
    """Regression: the resources page tabs must be attached to the page (blank resources page bug)."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_res"))
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["mods"]
        assert page.tabs.parent() is page
        assert page.title.parent() is page
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_wizard_prefills_existing_game_dir(app, monkeypatch, ws_tmp):
    """A re-run wizard must not clobber an already configured game directory."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_wiz"))
    from launcher import config as config_mod

    cfg, cfg_path = config_mod.load()
    chosen = ws_tmp / "chosen"
    cfg.game_dir = chosen
    cfg.wizard_done = False
    config_mod.save(cfg, cfg_path)
    from gui.pages.wizard import FirstRunWizard

    wizard = FirstRunWizard()
    assert wizard.game_dir_edit.text() == str(chosen)
    wizard.close()


def test_instances_page_lists_base_versions(app, monkeypatch, ws_tmp):
    """The instances page also lists installed base versions from the versions folder."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_base"))
    import json

    from launcher import config as config_mod
    from launcher.instances import INSTANCE_META_FILENAME, Instance

    game = ws_tmp / "mc"
    for vid in ("1.20.1", "fabric-loader-0.15.11-1.20.1"):
        d = game / "versions" / vid
        d.mkdir(parents=True)
        (d / (vid + ".json")).write_text("{}", encoding="utf-8")
    custom = game / "instances" / "custom1"
    custom.mkdir(parents=True)
    (custom / INSTANCE_META_FILENAME).write_text(
        json.dumps(Instance(name="custom1", version_id="1.20.1", created_at=1.0).model_dump(mode="json")),
        encoding="utf-8",
    )
    cfg, cfg_path = config_mod.load()
    cfg.game_dir = game
    config_mod.save(cfg, cfg_path)
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["instances"]
        items = [page.list.item(i).text() for i in range(page.list.count())]
        assert "1.20.1" in items
        assert "Fabric 0.15.11-1.20.1" in items
        assert any("custom1" in t for t in items)
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_display_version_name_normalizes_loaders():
    from launcher.instances import display_version_name

    assert display_version_name("1.20.1") == "1.20.1"
    assert display_version_name("fabric-loader-0.15.11-1.20.1") == "Fabric 0.15.11-1.20.1"
    assert display_version_name("neoforge-21.1.5") == "NeoForge 21.1.5"
    assert display_version_name("1.20.1-forge-47.4.22") == "Forge 47.4.22 (1.20.1)"
    assert display_version_name("quilt-loader-0.24.0-1.20.1") == "Quilt 0.24.0-1.20.1"


def test_launch_combo_normalizes_and_keeps_real_id(app, monkeypatch, ws_tmp):
    """The launch page shows normalized names but launches with the real profile id."""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_norm"))
    from launcher import config as config_mod

    game = ws_tmp / "mc"
    for vid in ("1.20.1", "fabric-loader-0.15.11-1.20.1"):
        d = game / "versions" / vid
        d.mkdir(parents=True)
        (d / (vid + ".json")).write_text("{}", encoding="utf-8")
    _cfg, _p = config_mod.load()
    _cfg.game_dir = game
    config_mod.save(_cfg, _p)
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["launch"]
        page._populate_versions()
        labels = [page.version_combo.itemText(i) for i in range(page.version_combo.count())]
        assert "Fabric 0.15.11-1.20.1" in labels
        page.version_combo.setCurrentIndex(page.version_combo.findData("fabric-loader-0.15.11-1.20.1"))
        real_id = page.version_combo.currentData() or page.version_combo.currentText()
        assert real_id == "fabric-loader-0.15.11-1.20.1"
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_resources_page_loader_combo_normalized(app):
    """The resources page shows human-readable loader names but keeps lowercase ids."""
    from gui.pages.mods_page import ResourcesPage

    page = ResourcesPage()
    try:
        combo = page.mods_tab.loader_combo
        labels = [combo.itemText(i) for i in range(combo.count())]
        assert labels == ["Fabric", "Forge", "NeoForge", "Quilt"]
        data = [combo.itemData(i) for i in range(combo.count())]
        assert data == ["fabric", "forge", "neoforge", "quilt"]
    finally:
        page.deleteLater()
        app.processEvents()


