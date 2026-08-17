"""游戏进程运行（stdio 继承模式）。

沙箱/打包兼容：不使用管道捕获输出（受限环境禁用管道 stdio）；
输出直接继承控制台/日志重定向由调用方决定。GUI（M6）用 QProcess 执行同一 argv。
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


def run_process(
    argv: list[str], cwd: Path, on_started: Callable[[], None] | None = None
) -> int:
    """以 stdio 继承方式运行并等待退出；Ctrl+C 转发终止信号。

    on_started 在进程成功启动后调用一次（GUI #14 自动隐藏用）。
    """
    # GUI（无控制台父进程）下不弹出命令行窗口（控制台闪现修复）；CLI 保持继承。
    # creationflags 仅 Windows 支持，其它平台不能传入（否则 ValueError）。
    extra: dict = {}
    if os.name == "nt" and sys.stdout is None and sys.stdin is None:
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(argv, cwd=str(cwd), **extra)
    if on_started is not None:
        on_started()
    try:
        return proc.wait()
    except KeyboardInterrupt:
        print()
        print("正在关闭游戏进程...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return 130


def find_new_crash_reports(game_dir: Path, since: float) -> list[Path]:
    """返回 since 之后生成的崩溃报告。"""
    reports_dir = game_dir / "crash-reports"
    if not reports_dir.exists():
        return []
    out: list[Path] = []
    for report in reports_dir.glob("crash-*.txt"):
        try:
            if report.stat().st_mtime >= since:
                out.append(report)
        except OSError:
            continue
    return out
