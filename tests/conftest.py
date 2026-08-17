"""pytest shared fixtures.

Note: this development sandbox locks writes inside mkdtemp-style (random-suffix) directories,
so it provides an ordinary mkdir directory via ws_tmp instead of pytest's built-in tmp_path.
"""

import shutil
from pathlib import Path

import pytest

WORK_DIR = Path(__file__).resolve().parent / ".work"
_counter = 0


@pytest.fixture()
def ws_tmp():
    """A writable ordinary temporary directory inside the workspace (function-scoped, auto-cleaned)."""
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
