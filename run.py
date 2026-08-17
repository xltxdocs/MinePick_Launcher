"""打包入口（PyInstaller 与 python run.py 通用）。

行为按构建类型区分：
- GUI 构建（MinePick_Launcher.exe）：始终启动图形界面（忽略参数）；
- CLI 构建（MinePick_Launcher_cli.exe，走 run_cli.py 入口，不引用 GUI）；
- 开发模式（python run.py）：无参数 → GUI，带参数 → CLI。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _is_cli_build() -> bool:
    """冻结后按可执行文件名判断是否 CLI 构建（MinePick_Launcher_cli.exe）。"""
    if not getattr(sys, "frozen", False):
        return False
    return "cli" in Path(sys.executable).name.lower()


def main() -> int:
    if _is_cli_build():
        from launcher.cli import build_parser
        from launcher.cli import main as cli_main

        if len(sys.argv) <= 1:
            build_parser().print_help()
            return 0
        return cli_main(sys.argv[1:])
    if getattr(sys, "frozen", False):
        # GUI build: double-clicking always starts the graphical interface
        from gui.main import main as gui_main

        return gui_main()
    if len(sys.argv) > 1:
        from launcher.cli import main as cli_main

        return cli_main(sys.argv[1:])
    from gui.main import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
