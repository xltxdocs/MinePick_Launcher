# -*- mode: python ; coding: utf-8 -*-
# MinePick Launcher（UI 分支）PyInstaller 打包：只产出 GUI 版
#   MinePick_Launcher.exe —— GUI（无控制台窗口，双击启动）
# 本分支不提供 CLI 版，因此不构建 MinePick_Launcher_cli.exe
# 用法: pyinstaller build_exe.spec
# 前置: pip install .[gui] pyinstaller

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    # 随包资源：GUI 图标/QSS（运行时经 launcher.paths.resource_path() 读取）
    datas=[
        ("gui/resources", "gui/resources"),
        ("launcher/mods/data", "launcher/mods/data"),
        # CurseForge 内置 Key：来自 gitignored 的 build/cf_key.txt，不进入源码仓库
        ("build/cf_key.txt", "launcher/mods/data"),
    ],
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MinePick_UI_Trial",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="gui/resources/icon.ico",  # 由 icon.svg 渲染生成（钻石镐+齿轮）
)
