# -*- mode: python ; coding: utf-8 -*-
# MinePick Launcher PyInstaller 打包：一个构建产出两个 EXE
#   MinePick_Launcher.exe      —— GUI（无控制台窗口，双击启动）
#   MinePick_Launcher_cli.exe  —— CLI（控制台，终端内运行全部命令）
# 用法: pyinstaller build_exe.spec
# 前置: pip install .[gui] pyinstaller

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    # 随包资源：GUI 图标/QSS（运行时经 launcher.paths.resource_path() 读取）
    datas=[("gui/resources", "gui/resources")],
    hiddenimports=[
        # pydantic 动态导入与常用可选模块
        "pydantic",
        "pydantic.deprecated.decorator",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# GUI 版：无控制台窗口
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MinePick_Launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="gui/resources/icon.ico",  # 由 icon.svg 渲染生成（钻石镐+齿轮）
)

# CLI 版：纯 CLI（run_cli.py 入口，不引用 GUI，排除 PySide6 减小体积）
a_cli = Analysis(
    ["run_cli.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pydantic",
        "pydantic.deprecated.decorator",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6", "shiboken6"],
    noarchive=False,
)

pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    a_cli.binaries,
    a_cli.datas,
    [],
    name="MinePick_Launcher_cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon="gui/resources/icon.ico",
)
