# -*- mode: python ; coding: utf-8 -*-
# MinePick Launcher PyInstaller 打包：只产出 GUI 版
#   MinePick_Launcher.exe —— GUI（无控制台窗口，双击启动）
# 本仓库不提供 CLI 版，因此不构建 MinePick_Launcher_cli.exe
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
        # 崩溃/启动失败知识库（launcher/diagnostics/rules.py 经 resource_path() 读取）
        ("launcher/diagnostics/data", "launcher/diagnostics/data"),
        # 第三方许可声明随包携带（关于页展示的同一份清单，仓库里由工具生成）
        ("THIRD_PARTY_NOTICES.md", "."),
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
    name="MinePick_Launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="gui/resources/icon.ico",  # 由 icon.svg 渲染生成（钻石镐+齿轮）
)
