from pathlib import Path

from launcher.java.locate import (
    JavaRuntime,
    has_suitable_java,
    match_java,
    parse_java_major,
)


def test_parse_java_major():
    assert parse_java_major('java version "1.8.0_401"') == 8
    assert parse_java_major('openjdk version "17.0.10" 2024-01-16') == 17
    assert parse_java_major('openjdk version "21-ea" 2023-09-19') == 21
    assert parse_java_major('openjdk version "21.0.5" 2024-10-15') == 21
    assert parse_java_major("no version here") is None
    assert parse_java_major("") is None


def _rt(major: int, provider: str = "system") -> JavaRuntime:
    return JavaRuntime(path=Path("/fake/java" + str(major)), major=major, provider=provider)


def test_match_java_prefers_managed_exact():
    runtimes = [_rt(8), _rt(17), _rt(21, "managed")]
    assert match_java(runtimes, 21).major == 21
    assert match_java(runtimes, 21).provider == "managed"


def test_match_java_minimum_ge():
    runtimes = [_rt(8), _rt(17), _rt(21)]
    assert match_java(runtimes, 16).major == 17
    assert match_java(runtimes, 17).major == 17
    assert match_java(runtimes, 21).major == 21


def test_match_java_fallback():
    runtimes = [_rt(8)]
    assert match_java(runtimes, 17).major == 8  # 没有满足的，退回最大
    assert match_java([], 17) is None
    assert match_java(runtimes, None).major == 8


def test_has_suitable_java():
    assert has_suitable_java([], 8) is False
    assert has_suitable_java([_rt(21), _rt(25)], 8) is False  # 旧版本必须精确 Java 8
    assert has_suitable_java([_rt(8)], 8) is True
    assert has_suitable_java([_rt(21)], 17) is True  # 17+ 用 >= 匹配
    assert has_suitable_java([_rt(17)], 21) is False
    assert has_suitable_java([_rt(21)], 21) is True
