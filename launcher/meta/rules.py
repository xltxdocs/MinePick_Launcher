"""Platform detection, library-rule evaluation, and natives-classifier resolution.

Rule semantics (matching the official launcher, verified against real 1.8.9 / 1.20.1 version JSON):
- a library without rules is allowed by default;
- with rules it starts False, rules are evaluated in order, and the last matching rule wins;
- a rule without os/features conditions matches all platforms;
- the natives classifier comes from: the 4th segment of the library name (modern format) or the natives mapping (old format, with an ${arch} placeholder).
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
    version: str  # system version string, used for rule regex


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
    """Whether the rule matches the current platform/feature set (no match = the rule doesn't apply)."""
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
    """Evaluate the rule chain in order; no rules defaults to allow, with rules it starts False and the last matching rule wins."""
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
    classifier: str | None  # None = main artifact; non-None = natives classifier name


def _arch_tag(arch: str) -> str:
    return _ARCH_TAGS.get(arch, arch)


def _classifier_arch_ok(classifier: str, p: Platform) -> bool:
    """Check the classifier suffix against the current architecture (no suffix is treated as x64 default)."""
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
    """Pick the natives classifier for the platform; return None when no natives are needed."""
    parts = lib.name.split(":")
    classifiers = (lib.downloads.classifiers if lib.downloads else None) or {}

    # Modern format: the 4th segment of the library name is the natives classifier (natives- prefix only;
    # other classifiers such as forge's :client are the main jar, not treated as natives)
    if len(parts) == 4 and parts[3].startswith("natives-"):
        return parts[3]

    # Old format: natives mapping (value may contain the ${arch} placeholder)
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

    # No natives mapping, but has natives-* classifiers
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
    """Filter libraries by platform and resolve their natives classifiers, returning a (library, classifier) list."""
    out: list[ResolvedLibrary] = []
    for lib in libs:
        if not allowed(lib.rules, p, features):
            continue
        classifier = native_classifier(lib, p)
        if lib.natives and classifier is None:
            continue
        # Filter name-derived classifier entries by architecture (x86/arm64 variants exist under the same OS)
        if (
            classifier is not None
            and len(lib.name.split(":")) == 4
            and not _classifier_arch_ok(classifier, p)
        ):
            continue
        out.append(ResolvedLibrary(library=lib, classifier=classifier))
    return out
