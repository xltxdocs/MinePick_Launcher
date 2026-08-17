"""纯 CLI 入口（MinePick_Launcher_cli.exe 专用，完全不引用 GUI/PySide6）。

无参数时打印帮助；带参数时透传给 launcher.cli。
"""

from __future__ import annotations

import sys

from launcher.cli import build_parser, main

if __name__ == "__main__":
    if len(sys.argv) <= 1:
        build_parser().print_help()
        raise SystemExit(0)
    raise SystemExit(main())
