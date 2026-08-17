"""GUI 入口。"""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from launcher import paths
from launcher.logging_setup import configure_logging


def build_app_icon() -> QIcon:
    """多尺寸应用图标：小尺寸（标题栏 16/24）用简洁版保持清晰，
    32px 及以上（任务栏）用完整设计。全部用 PNG（EXE 内不依赖 QtSvg 插件）。"""
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QPixmap

    icon = QIcon()
    for name in ("window_icon_16.png", "window_icon_24.png"):
        path = paths.resource_path("gui/resources/" + name)
        if path.exists():
            icon.addPixmap(QPixmap(str(path)))
    full = paths.resource_path("gui/resources/icon.png")
    if full.exists():
        base = QPixmap(str(full))
        for size in (32, 48, 64, 128, 256):
            icon.addPixmap(
                base.scaled(
                    QSize(size, size),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
    return icon


def _unlock_token_vault() -> None:
    """令牌加密开启时交互输入密码解锁（内存缓存）；失败保持锁定，相关操作会报错。"""
    from gui import i18n
    from launcher import config
    from launcher.auth import secure

    cfg, _ = config.load()
    if not cfg.token_encryption or not secure.vault_exists():
        return
    try:
        if secure.unlock_vault(interactive=False):
            return
    except secure.VaultError:
        pass
    from PySide6.QtWidgets import QInputDialog, QLineEdit

    for _attempt in range(3):
        text, ok = QInputDialog.getText(
            None,
            "MinePick Launcher",
            i18n.tr("settings.encrypt.current.prompt"),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        if secure.verify_password(text):
            secure.set_password(text)
            return


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("MinePick Launcher")
    app.setOrganizationName("mclauncher")
    # 用 Fusion 作为基础样式：Windows 原生样式（windows11）会自行绘制
    # 选项卡/菜单/下拉列表的白色圆角框，覆盖 QSS；Fusion 完全遵循 QSS。
    app.setStyle("Fusion")
    from gui import i18n
    from launcher import config

    cfg, cfg_path = config.load()
    # 首次启动：自动初始化游戏语言（同步启动器语言/系统语言，仅一次）
    config.initialize_language(cfg, cfg_path)
    i18n.set_language(cfg.ui_language)
    _unlock_token_vault()
    app.setWindowIcon(build_app_icon())
    # 主题（#30）：深色 / 浅色 QSS
    from gui.theme import apply_theme

    apply_theme(cfg.theme)
    return app


def main() -> int:
    configure_logging(log_file=paths.launcher_dir() / "logs" / "launcher.log")
    app = create_app()

    # 首次使用向导（#29）：语言 / 游戏目录 / 默认内存
    # （无头冒烟测试 MCLAUNCHER_GUI_AUTOQUIT_MS 时跳过，避免模态对话框阻塞）
    from launcher import config as config_mod

    cfg, cfg_path = config_mod.load()
    auto_quit = __import__("os").environ.get("MCLAUNCHER_GUI_AUTOQUIT_MS")
    if not cfg.wizard_done and not auto_quit:
        from PySide6.QtWidgets import QDialog

        from gui.pages.wizard import FirstRunWizard

        wizard = FirstRunWizard()
        if wizard.exec() == QDialog.DialogCode.Accepted:
            wizard.apply(cfg, cfg_path)
            from gui import i18n

            i18n.set_language(cfg.ui_language)

    from gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    window.apply_window_mode()

    # 无头/CI 验证：MCLAUNCHER_GUI_AUTOQUIT_MS=3000 时自动退出
    auto_quit = __import__("os").environ.get("MCLAUNCHER_GUI_AUTOQUIT_MS")
    if auto_quit:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(int(auto_quit), app.quit)

    return app.exec()
