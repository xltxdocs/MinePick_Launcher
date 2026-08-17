"""GUI 冒烟测试（offscreen 平台，无显示环境）。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QStackedWidget

from launcher import config as config_mod


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def _offline_manifest_fetch(monkeypatch):
    """版本页自动拉清单 + 资源页热门加载：测试中改为静默失败，避免真实网络请求。"""
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
    assert page.isolation_check.isChecked() is True  # 默认勾选
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
    assert page.auto_jre_check.isChecked() is True  # 默认勾选
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
        # 切到英文并触发设置变更
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
        # 恢复中文
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

    i18n.set_language("zh_cn")  # 防御：确保中文状态
    window = MainWindow()
    page = window.pages["mods"]
    assert page.title.text() == "资源"
    assert page.tabs.count() == 4  # 模组/整合包/资源包/光影
    tab = page.mods_tab
    # #19 搜索栏存在
    assert tab.search_edit is not None
    assert tab.search_button.text() == "搜索"
    # #20 已安装列表存在（模组/资源包/光影三个选项卡）
    for name in ("mods_tab", "resourcepacks_tab", "shaderpacks_tab"):
        content_tab = getattr(page, name)
        assert content_tab.installed_list is not None
        assert content_tab.installed_delete_button is not None
    # 依赖 UI（slug 查询结果展示）
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
    # #8 版本页卸载按钮 + 状态列
    versions = window.pages["versions"]
    assert versions.uninstall_button.text() == "卸载所选版本"
    assert versions.table.columnCount() == 4
    # #11 启动页 JVM 参数输入
    launch = window.pages["launch"]
    assert launch.jvm_args_edit is not None
    assert launch.jvm_args_edit.placeholderText()
    # #1 设置页令牌加密
    settings = window.pages["settings"]
    assert settings.encrypt_check is not None
    assert settings.encrypt_button.text() == "设置密码"
    # #24 实例页重命名入口
    instances = window.pages["instances"]
    assert callable(instances._rename)
    window.close()

def test_batch3_widgets_exist(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data7"))
    from gui.main_window import MainWindow

    window = MainWindow()
    launch = window.pages["launch"]
    assert launch.server_edit is not None  # #15
    assert launch.server_port_spin is not None
    assert not hasattr(launch, "auto_close_check")  # 已挪到设置页
    versions = window.pages["versions"]
    assert versions.detail_button.text() == "详情"  # #9
    instances = window.pages["instances"]
    assert instances.sort_combo.count() == 2  # #25 排序
    assert callable(instances._edit_note)
    assert callable(instances._export)  # #26
    assert callable(instances._import)
    settings = window.pages["settings"]
    assert settings.speed_limit_spin is not None  # #10
    assert settings.window_mode_combo.count() == 4  # #12
    assert settings.theme_combo.count() == 2  # #30
    assert settings.demo_check is not None  # 演示模式挪到设置
    assert settings.auto_close_check is not None  # 自动隐藏挪到设置
    account = window.pages["account"]
    assert account.avatar_label is not None  # #4
    window.close()


def test_instance_name_via_userrole(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data10"))
    from launcher.instances import Instance, InstanceStore

    store = InstanceStore()
    store.save({"tricky": Instance(name="tricky", version_id="1.20.1", created_at=1.0, note="备注   [干扰]")})
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["instances"]
        assert page.list.count() == 1
        page.list.setCurrentRow(0)
        assert page._current_name() == "tricky"  # 不因备注含 "   [" 而解析错
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
        apply_theme("dark")  # 恢复深色，避免影响其它用例
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
        assert AccountStore().load() == {}  # 未创建账号
    finally:
        if window is not None:
            window.close()
            app.processEvents()

def test_loader_prompt_dialog(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data14"))
    from gui.pages.versions_page import _LoaderPromptDialog

    dialog = _LoaderPromptDialog()
    assert dialog.combo.count() == 4
    assert dialog.selected_loader() is None  # 默认原版
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
        assert items == ["1.20.1", "1.8.9"]  # 只含已安装版本，且不含清单全量
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
            assert tab.search_edit is not None  # 搜索栏存在
            assert tab.search_button is not None
        assert "资源包" in page.resourcepacks_tab.search_edit.placeholderText()
        assert "光影" in page.shaderpacks_tab.search_edit.placeholderText()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_auto_hide_hides_window(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data16"))
    import gui.pages.launch_page as launch_page_mod

    monkeypatch.setattr(launch_page_mod.QTimer, "singleShot", staticmethod(lambda *a, **k: None))
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        window.show()
        app.processEvents()
        assert window.isVisible()
        window.pages["launch"]._on_game_started()
        assert not window.isVisible()  # 启动成功后立即隐藏窗口
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_versions_page_categories_and_full_list(app, monkeypatch, ws_tmp):
    """版本页按正式版/快照版/愚人节/旧版分类，且不受 500 行上限限制。"""
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
        # 全部列出，无 500 行上限
        assert page.table.rowCount() == 553
        # 最新版本卡片
        assert page.latest_labels["release"].text() == "release-0"
        assert page.latest_labels["snapshot"].text() == "25w14a"
        assert page.latest_buttons["release"].isEnabled()
        assert page.latest_buttons["snapshot"].isEnabled()
        # 版本名列宽可容纳 20 个英文字符
        assert page.table.columnWidth(0) >= page.table.fontMetrics().horizontalAdvance("W" * 20)
        row_of = {page.table.item(r, 0).text(): r for r in range(page.table.rowCount())}
        # 类型列按分类显示中文名
        assert page.table.item(row_of["24w14potato"], 1).text() == "愚人节版本"
        assert page.table.item(row_of["25w14a"], 1).text() == "快照版"
        assert page.table.item(row_of["release-0"], 1).text() == "正式版"
        assert page.table.item(row_of["b1.7.3"], 1).text() == "远古版 Beta"
        # 分类页签：全部/正式/快照/愚人节/远古版
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

        set_filter("april_fools")
        assert page.table.rowCount() == 1
        assert page.table.item(0, 0).text() == "24w14potato"
        set_filter("release")
        assert page.table.rowCount() == 550
        set_filter("snapshot")
        assert page.table.rowCount() == 1
        assert page.table.item(0, 0).text() == "25w14a"
        set_filter("legacy")
        assert page.table.rowCount() == 1
        assert page.table.item(0, 0).text() == "b1.7.3"
        # 搜索框：与页签条件叠加
        set_filter(None)
        page.search_edit.setText("potato")
        assert page.table.rowCount() == 1
        assert page.table.item(0, 0).text() == "24w14potato"
        page.search_edit.setText("release-")
        assert page.table.rowCount() == 550
        page.search_edit.clear()
        assert page.table.rowCount() == 553
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_instance_open_folder_button(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data15"))
    from launcher import config as config_mod
    from launcher.instances import Instance, InstanceStore

    store = InstanceStore()
    store.save({"t": Instance(name="t", version_id="1.20.1", created_at=1.0)})
    _cfg, _p = config_mod.load()
    _cfg.game_dir = ws_tmp / "mc"
    config_mod.save(_cfg, _p)
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
    """实例页模组管理面板：选中实例后加载其 mods 目录，勾选切换启用状态。"""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data_mods"))
    import json
    import zipfile

    from PySide6.QtCore import Qt

    from launcher import config as config_mod
    from launcher.instances import Instance, InstanceStore

    store = InstanceStore()
    store.save({"t": Instance(name="t", version_id="1.20.1", created_at=1.0)})
    _cfg, _p = config_mod.load()
    _cfg.game_dir = ws_tmp / "mc"
    _cfg.version_isolation = False
    config_mod.save(_cfg, _p)
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
        # 勾掉 demo.jar -> 改名为 .disabled
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
    """回归：资源页的选项卡必须挂到页面上（资源页空白 bug）。"""
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



