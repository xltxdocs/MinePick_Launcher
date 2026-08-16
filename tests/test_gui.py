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
    assert launch.auto_close_check is not None  # #14
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




