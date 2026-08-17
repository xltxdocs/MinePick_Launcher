"""pytest 共享 fixture。

注意：本开发沙箱会锁定 mkdtemp 风格（随机后缀）目录内的写入，
因此不使用 pytest 内置 tmp_path，而以 ws_tmp 提供普通 mkdir 目录。
"""

import shutil
from pathlib import Path

import pytest

WORK_DIR = Path(__file__).resolve().parent / ".work"
_counter = 0


@pytest.fixture()
def ws_tmp():
    """workspace 内可写的普通临时目录（函数级，自动清理）。"""
    global _counter
    WORK_DIR.mkdir(exist_ok=True)
    d = WORK_DIR / f"case{_counter:03d}"
    _counter += 1
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
