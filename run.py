"""打包入口（PyInstaller 与 python run.py 通用）。

无参数 → 启动 GUI；带参数 → 透传给 CLI（mclauncher.exe <命令> ...）。
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from launcher.cli import main as cli_main

        return cli_main(sys.argv[1:])
    from gui.main import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
