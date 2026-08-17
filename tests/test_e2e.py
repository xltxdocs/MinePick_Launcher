"""E2E 测试（#35）：pytest + offscreen GUI，模拟界面操作验证核心流程。

覆盖：离线登录联动、多账号切换、模组搜索（respx 模拟 Modrinth）、
版本卸载流程（确认弹窗模拟）、启动页 JVM 参数持久化、崩溃报告查看器。
"""

import json
import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from launcher import config as config_mod
from launcher.auth import AccountStore, create_offline_account


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


def _wait_until(app, cond, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


SEARCH_RAW = {
    "hits": [
        {
            "project_id": "AANobbMI",
            "slug": "sodium",
            "title": "Sodium",
            "description": "渲染优化",
            "downloads": 123456,
        }
    ]
}


def test_e2e_offline_login_updates_launch_page(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data"))
    # 离线模式门槛：先标记已通过正版验证
    _cfg, _p = config_mod.load()
    _cfg.offline_unlocked = True
    config_mod.save(_cfg, _p)
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["account"]
        page.offline_edit.setText("Steve")
        page.offline_login()
        app.processEvents()
        cfg, _ = config_mod.load()
        accounts = AccountStore().load()
        assert cfg.selected_account in accounts
        # 联动：启动页账号下拉更新
        combo = window.pages["launch"].account_combo
        assert combo.count() >= 2  # （无） + Steve
        assert "Steve" in combo.itemText(combo.count() - 1)
        # 多账号列表出现该账号（#2）
        assert page.accounts_list.count() == 1
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_e2e_account_switch(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data2"))
    store = AccountStore()
    first = create_offline_account("Alice")
    second = create_offline_account("Bob")
    store.save({first.id: first, second.id: second})
    cfg, cfg_path = config_mod.load()
    cfg.selected_account = first.id
    config_mod.save(cfg, cfg_path)

    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["account"]
        assert page.accounts_list.count() == 2
        # 选中第二个账号并切换（#2）
        row = next(
            i for i in range(page.accounts_list.count())
            if page.accounts_list.item(i).data(Qt.UserRole) == second.id
        )
        page.accounts_list.setCurrentRow(row)
        page.switch_account()
        app.processEvents()
        cfg, _ = config_mod.load()
        assert cfg.selected_account == second.id
        assert "Bob" in window.pages["launch"].account_combo.currentText()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_e2e_mods_search_flow(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data3"))
    # 工作线程内不受 respx contextvar 影响：注入线程安全的 MockTransport
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SEARCH_RAW)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "launcher.mods.modrinth._client",
        lambda: httpx.Client(transport=transport, headers={"User-Agent": "e2e"}),
    )
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        tab = window.pages["mods"].mods_tab
        tab.search_edit.setText("sodium")
        QTest.mouseClick(tab.search_button, Qt.LeftButton)  # 模拟点击搜索
        assert _wait_until(app, lambda: tab.list.count() >= 1)
        assert "Sodium" in tab.list.item(0).text()
        assert "123,456" in tab.list.item(0).text()  # 下载量显示
        assert "渲染优化" in tab.desc_label.text()
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_e2e_version_uninstall_flow(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data4"))
    game = ws_tmp / "mc"
    vdir = game / "versions" / "1.20.1"
    vdir.mkdir(parents=True)
    (vdir / "1.20.1.json").write_text(json.dumps({"id": "1.20.1"}), encoding="utf-8")
    (vdir / "1.20.1.jar").write_bytes(b"jar")
    cfg, cfg_path = config_mod.load()
    cfg.game_dir = game
    config_mod.save(cfg, cfg_path)
    # 模拟确认弹窗点“是”
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )

    from gui.main_window import MainWindow
    from launcher.meta import ManifestVersion

    window = None
    try:
        window = MainWindow()
        page = window.pages["versions"]
        page._on_manifest(
            SimpleNamespace(
                versions=[ManifestVersion(id="1.20.1", type="release", url="https://x/1.20.1.json", time="", release_time="2023-06-07")],
                latest={},
            )
        )
        assert page.table.rowCount() == 1
        assert page.table.item(0, 3).text() == "已安装"
        page.table.selectRow(0)
        page.uninstall_selected()
        assert _wait_until(app, lambda: "已卸载" in page.status.text())
        assert not vdir.exists()
        # 状态列刷新
        assert page.table.item(0, 3).text() == "—"
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_e2e_launch_jvm_args_persist(app, monkeypatch, ws_tmp):
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data5"))
    _cfg, _p = config_mod.load()
    _cfg.offline_unlocked = True
    config_mod.save(_cfg, _p)
    import gui.pages.launch_page as launch_page_mod
    from launcher.launch import JavaMissingError

    def fake_prepare(*args, **kwargs):
        raise JavaMissingError(8)

    monkeypatch.setattr(launch_page_mod, "prepare_launch", fake_prepare)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )

    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["launch"]
        page.version_combo.setEditText("1.20.1")
        page.jvm_args_edit.setText("-XX:+UseG1GC")
        page.launch()
        app.processEvents()
        cfg, _ = config_mod.load()
        assert cfg.jvm_args == "-XX:+UseG1GC"  # 启动时持久化（#11）
        assert _wait_until(app, lambda: "已取消" in page.status.text())
    finally:
        if window is not None:
            window.close()
            app.processEvents()


def test_e2e_crash_viewer_lists_reports(app, ws_tmp):
    game = ws_tmp / "mc2"
    reports = game / "crash-reports"
    reports.mkdir(parents=True)
    (reports / "crash-2024-01-01_00.00.00-client.txt").write_text("boom", encoding="utf-8")

    from gui.crash_viewer import CrashViewerDialog

    dialog = CrashViewerDialog(game)
    assert dialog.list.count() == 1
    assert "boom" in dialog.viewer.toPlainText()
    dialog.close()

def test_e2e_launch_flow_log_tail(app, monkeypatch, ws_tmp):
    """#33：模拟完整启动流程（prepare -> run -> 日志尾部 -> 退出码）。"""
    monkeypatch.setenv("MCLAUNCHER_DATA_DIR", str(ws_tmp / "data6"))
    _cfg, _p = config_mod.load()
    _cfg.offline_unlocked = True
    config_mod.save(_cfg, _p)
    from types import SimpleNamespace

    import gui.pages.launch_page as launch_page_mod

    cwd = ws_tmp / "mc"
    (cwd / "logs").mkdir(parents=True)
    (cwd / "logs" / "latest.log").write_text("Hello from game\n", encoding="utf-8")

    def fake_prepare(*args, **kwargs):
        return SimpleNamespace(
            command=SimpleNamespace(argv=["java"], cwd=cwd),
            account=SimpleNamespace(username="Steve"),
            version=SimpleNamespace(id="1.20.1"),
            java=SimpleNamespace(major=17),
            isolated=False,
        )

    monkeypatch.setattr(launch_page_mod, "prepare_launch", fake_prepare)
    monkeypatch.setattr(
        launch_page_mod,
        "run_process",
        lambda argv, cwd, on_started=None: (on_started() if on_started else None) or 0,
    )

    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        page = window.pages["launch"]
        page.version_combo.setEditText("1.20.1")
        page.launch()
        assert _wait_until(app, lambda: "Hello from game" in page.log_view.toPlainText())
        assert _wait_until(app, lambda: "退出码" in page.status.text())
    finally:
        if window is not None:
            window.close()
            app.processEvents()

