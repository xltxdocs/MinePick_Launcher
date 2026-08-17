"""平台识别、库规则评估与 natives 分类器解析。

规则语义（与官方启动器一致，经 1.8.9 / 1.20.1 真实版本 JSON 核对）：
- 无 rules 的库默认允许；
- 有 rules 时初始为 False，按顺序评估，末条命中规则生效；
- 无 os/features 条件的规则对所有平台命中；
- natives 分类器来源：库名第 4 段（现代格式）或 natives 映射（旧格式，含 ${arch} 占位符）。
"""

from __future__ import annotations

import platform as _platform
import re
from dataclasses import dataclass

from launcher.meta.version import Library, OsRule, Rule

_OS_ALIASES = {
    "darwin": "osx",
    "macos": "osx",
    "win32": "windows",
    "windows": "windows",
    "linux": "linux",
}
_ARCH_ALIASES = {
    "amd64": "x64",
    "x86_64": "x64",
    "i386": "x86",
    "i686": "x86",
    "x86": "x86",
    "aarch64": "arm64",
    "arm64": "arm64",
}
_ARCH_TAGS = {"x64": "64", "x86": "32", "arm64": "arm64"}


@dataclass(frozen=True)
class Platform:
    os: str  # windows / osx / linux
    arch: str  # x86 / x64 / arm64
    version: str  # 系统版本字符串，用于规则正则


def detect_platform() -> Platform:
    system = _platform.system().lower()
    machine = _platform.machine().lower()
    return Platform(
        os=_OS_ALIASES.get(system, system),
        arch=_ARCH_ALIASES.get(machine, machine),
        version=_platform.version(),
    )


def os_matches(rule: OsRule, p: Platform) -> bool:
    if rule.name is not None and _OS_ALIASES.get(rule.name, rule.name) != p.os:
        return False
    if rule.arch is not None and _ARCH_ALIASES.get(rule.arch, rule.arch) != p.arch:
        return False
    if rule.version is not None:
        try:
            if re.fullmatch(rule.version, p.version) is None:
                return False
        except re.error:
            return False
    return True


def rule_applies(rule: Rule, p: Platform, features: frozenset[str] = frozenset()) -> bool:
    """规则是否命中当前平台/特性集（未命中 = 该规则不生效）。"""
    if rule.os is not None and not os_matches(rule.os, p):
        return False
    if rule.features:
        for key, required in rule.features.items():
            if (key in features) != required:
                return False
    return True


def allowed(
    rules: list[Rule] | None, p: Platform, features: frozenset[str] = frozenset()
) -> bool:
    """按顺序评估规则链；无规则默认允许，有规则初始为 False、末条命中生效。"""
    if not rules:
        return True
    result = False
    for rule in rules:
        if rule_applies(rule, p, features):
            result = rule.action == "allow"
    return result


@dataclass(frozen=True)
class ResolvedLibrary:
    library: Library
    classifier: str | None  # None = 主 artifact；非 None = natives 分类器名


def _arch_tag(arch: str) -> str:
    return _ARCH_TAGS.get(arch, arch)


def _classifier_arch_ok(classifier: str, p: Platform) -> bool:
    """按分类器后缀判断是否匹配当前架构（无后缀视为 x64 默认）。"""
    if classifier.endswith("-arm64"):
        return p.arch == "arm64"
    if classifier.endswith(("-x86", "-32")):
        return p.arch == "x86"
    if classifier.endswith("-64"):
        return p.arch == "x64"
    if classifier.endswith("-" + p.arch):
        return True
    return p.arch == "x64"


def native_classifier(lib: Library, p: Platform) -> str | None:
    """按平台选出 natives 分类器；无 natives 需求时返回 None。"""
    parts = lib.name.split(":")
    classifiers = (lib.downloads.classifiers if lib.downloads else None) or {}

    # 现代格式：库名第 4 段为 natives 分类器（仅 natives- 前缀；
    # 其它分类器如 forge 的 :client 是主 jar，不作为 natives 处理）
    if len(parts) == 4 and parts[3].startswith("natives-"):
        return parts[3]

    # 旧格式：natives 映射（值可能含 ${arch} 占位符）
    if lib.natives:
        base = lib.natives.get(p.os)
        if base is None:
            return None
        base = base.replace("${arch}", _arch_tag(p.arch))
        keys = [k for k in classifiers if k.startswith("natives-" + p.os)]
        exact = "natives-" + p.os + "-" + p.arch
        if exact in keys:
            return exact
        if p.arch == "x64" and base in keys:
            return base
        for k in keys:
            if k.endswith("-" + p.arch):
                return k
        return base

    # 无 natives 映射，但带 natives-* 分类器
    keys = [k for k in classifiers if k.startswith("natives-" + p.os)]
    if not keys:
        return None
    exact = "natives-" + p.os + "-" + p.arch
    if exact in keys:
        return exact
    plain = "natives-" + p.os
    if p.arch == "x64" and plain in keys:
        return plain
    for k in keys:
        if k.endswith("-" + p.arch):
            return k
    return keys[0]


def resolve_libraries(
    libs: list[Library], p: Platform, features: frozenset[str] = frozenset()
) -> list[ResolvedLibrary]:
    """按平台过滤库并解析 natives 分类器，返回 (库, 分类器) 列表。"""
    out: list[ResolvedLibrary] = []
    for lib in libs:
        if not allowed(lib.rules, p, features):
            continue
        classifier = native_classifier(lib, p)
        if lib.natives and classifier is None:
            continue
        # 名称派生分类器的条目按架构过滤（同 OS 下存在 x86/arm64 变体）
        if (
            classifier is not None
            and len(lib.name.split(":")) == 4
            and not _classifier_arch_ok(classifier, p)
        ):
            continue
        out.append(ResolvedLibrary(library=lib, classifier=classifier))
    return out
