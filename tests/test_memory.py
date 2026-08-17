"""launcher/memory.py unit tests: system memory probe and heap sizing."""

import zipfile

from launcher.memory import (
    MAX_MEMORY_GB,
    MIN_MEMORY_GB,
    count_mods,
    suggest_memory_gb,
    system_memory_gb,
)


def test_system_memory_gb_returns_positive_pair() -> None:
    total, avail = system_memory_gb()
    assert total > 0
    assert avail > 0


def test_suggest_grows_with_mod_count() -> None:
    small = suggest_memory_gb(0, total_gb=16, available_gb=12)
    heavy = suggest_memory_gb(200, total_gb=16, available_gb=12)
    assert heavy > small
    assert small >= MIN_MEMORY_GB
    assert heavy <= MAX_MEMORY_GB


def test_suggest_is_conservative_when_memory_is_tight() -> None:
    tight = suggest_memory_gb(0, total_gb=8, available_gb=2)
    assert tight <= 2.0 + 0.5


def test_suggest_capped_by_total_and_max() -> None:
    huge = suggest_memory_gb(1000, total_gb=64, available_gb=64)
    assert huge <= MAX_MEMORY_GB


def test_count_mods_counts_jar_and_disabled(ws_tmp) -> None:
    mods = ws_tmp / "mods"
    mods.mkdir()
    (mods / "a.jar").write_bytes(b"x")
    (mods / "b.jar.disabled").write_bytes(b"x")
    (mods / "c.txt").write_text("x", encoding="utf-8")
    with zipfile.ZipFile(mods / "c.jar", "w"):
        pass
    assert count_mods(mods) == 3
    assert count_mods(ws_tmp / "missing") == 0

