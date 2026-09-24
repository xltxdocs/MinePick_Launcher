# SPDX-FileCopyrightText: 2026 WDNDXLTX
# SPDX-License-Identifier: GPL-3.0-only
#
# This file is part of MinePick Launcher.
#
# MinePick Launcher is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# MinePick Launcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MinePick Launcher. If not, see <https://www.gnu.org/licenses/>.

"""The knowledge base: load and validate ``data/rules.json``.

The rules are **plain data** — adding a finding never touches code. Loading is
strict on purpose: a typo in a code, a source or a regex must fail loudly at
startup/test time instead of silently disabling a rule.

Validation raises :class:`RulesError` for

* a duplicate code, a wrong prefix for the phase, or a reserved code (0000/0001);
* an unknown phase, source, confidence or key (anywhere in the file);
* an uncompilable regex;
* a rule whose matcher is empty;
* a malformed advice list.

Matching stays bounded: every matcher is applied to single lines of an already
windowed log (see ``prepare.py``), so a regex never sees an unbounded input.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from launcher import paths
from launcher.diagnostics.codes import validate_code
from launcher.diagnostics.prepare import MATCHABLE_KINDS

_LOGGER = logging.getLogger(__name__)

RULE_RELATIVE_PATH = "launcher/diagnostics/data/rules.json"
#: Default knowledge base (packaging-aware: bundled data under PyInstaller).
RULE_FILE: Path = paths.resource_path(RULE_RELATIVE_PATH)

PHASES = ("launcher", "fatal", "primary", "secondary")
CONFIDENCES = ("high", "medium", "low")
SOURCES = MATCHABLE_KINDS

RULE_KEYS = frozenset({"code", "phase", "source", "match", "cause", "advice", "confidence", "stop"})
MATCH_KEYS = frozenset({"all", "any", "none"})
TOP_KEYS = frozenset({"version", "rules"})
MATCHER_KEYS = frozenset({"regex"})
#: A pure ``{name}`` entry in an advice list is an argument for the previous key.
_PLACEHOLDER_RE = re.compile(r"^\{[a-z_][a-z0-9_]*\}$")


class RulesError(ValueError):
    """The rule file is missing, unreadable or invalid."""


@dataclass(frozen=True)
class Matcher:
    """One matching primitive: a literal substring or a compiled regex."""

    pattern: str
    regex: bool = False
    _compiled: re.Pattern[str] | None = field(default=None, repr=False, compare=False)

    def hits(self, line: str) -> bool:
        """Whether one (already clipped) line matches this primitive."""
        if self.regex:
            compiled = self._compiled
            if compiled is None:  # pragma: no cover - only for hand-built matchers
                compiled = re.compile(self.pattern)
            return bool(compiled.search(line))
        return self.pattern in line

    def find_line(self, lines: Iterable[str]) -> str | None:
        """First line matching this primitive (bounded: lines are already clipped)."""
        for line in lines:
            if self.hits(line):
                return line
        return None


@dataclass(frozen=True)
class Rule:
    """One knowledge-base entry (immutable; `order` is the file order)."""

    code: str
    phase: str
    source: str
    cause: str
    advice: tuple[str, ...]
    confidence: str
    stop: bool
    order: int
    all: tuple[Matcher, ...] = ()
    any: tuple[Matcher, ...] = ()
    none: tuple[Matcher, ...] = ()

    def match_lines(self, lines: Sequence[str]) -> list[str] | None:
        """Evidence lines when the rule matches, else None.

        ``all`` must be satisfied by every matcher, ``any`` by at least one and
        ``none`` by no matcher at all — each against the same windowed log.
        """
        hits: list[str] = []
        for matcher in self.all:
            line = matcher.find_line(lines)
            if line is None:
                return None
            hits.append(line)
        if self.any:
            for matcher in self.any:
                line = matcher.find_line(lines)
                if line is not None:
                    hits.append(line)
                    break
            else:
                return None
        for matcher in self.none:
            if matcher.find_line(lines) is not None:
                return None
        # Keep the evidence short and stable (the report shows at most a few lines).
        unique: dict[str, None] = {}
        for line in hits:
            unique.setdefault(line, None)
        return list(unique)


def _fail(message: str) -> None:
    raise RulesError(message)


def _build_matcher(raw: object, where: str) -> Matcher:
    if isinstance(raw, str):
        if not raw:
            _fail(f"{where}: empty matcher")
        return Matcher(pattern=raw)
    if isinstance(raw, dict):
        unknown = set(raw) - MATCHER_KEYS
        if unknown:
            _fail(f"{where}: unknown matcher keys {sorted(unknown)}")
        pattern = raw.get("regex")
        if not isinstance(pattern, str) or not pattern:
            _fail(f"{where}: regex matcher needs a non-empty 'regex' string")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            _fail(f"{where}: uncompilable regex {pattern!r}: {exc}")
        return Matcher(pattern=pattern, regex=True, _compiled=compiled)
    _fail(f"{where}: a matcher must be a string or {{'regex': ...}}")
    raise AssertionError("unreachable")  # pragma: no cover


def _build_matchers(raw: object, where: str) -> tuple[Matcher, ...]:
    if not isinstance(raw, list):
        _fail(f"{where}: expected a list of matchers")
    return tuple(_build_matcher(item, f"{where}[{index}]") for index, item in enumerate(raw))


def _build_rule(raw: object, order: int) -> Rule:
    where = f"rule #{order + 1}"
    if not isinstance(raw, dict):
        _fail(f"{where}: expected an object")
    code = raw.get("code")
    if not isinstance(code, str) or not code:
        _fail(f"{where}: missing 'code'")
    where = f"rule {code}"

    unknown = set(raw) - RULE_KEYS
    if unknown:
        _fail(f"{where}: unknown keys {sorted(unknown)}")

    phase = raw.get("phase")
    if phase not in PHASES:
        _fail(f"{where}: unknown phase {phase!r} (expected one of {list(PHASES)})")
    source = raw.get("source")
    if source not in SOURCES:
        _fail(f"{where}: unknown source {source!r} (expected one of {list(SOURCES)})")
    confidence = raw.get("confidence")
    if confidence not in CONFIDENCES:
        _fail(f"{where}: unknown confidence {confidence!r} (expected one of {list(CONFIDENCES)})")

    problem = validate_code(code, phase)
    if problem:
        _fail(f"{where}: {problem}")

    cause = raw.get("cause")
    if not isinstance(cause, str) or not cause:
        _fail(f"{where}: missing 'cause' i18n key")
    advice_raw = raw.get("advice")
    if not isinstance(advice_raw, list) or not advice_raw:
        _fail(f"{where}: 'advice' must be a non-empty list of i18n keys")
    for item in advice_raw:
        if not isinstance(item, str) or not item:
            _fail(f"{where}: 'advice' entries must be non-empty strings")

    match = raw.get("match")
    if not isinstance(match, dict):
        _fail(f"{where}: missing 'match' object")
    unknown = set(match) - MATCH_KEYS
    if unknown:
        _fail(f"{where}: unknown match keys {sorted(unknown)}")

    all_matchers = _build_matchers(match.get("all", []), f"{where}.match.all")
    any_matchers = _build_matchers(match.get("any", []), f"{where}.match.any")
    none_matchers = _build_matchers(match.get("none", []), f"{where}.match.none")
    if not all_matchers and not any_matchers:
        _fail(f"{where}: empty matcher (needs at least one entry in 'all' or 'any')")

    stop = raw.get("stop", False)
    if not isinstance(stop, bool):
        _fail(f"{where}: 'stop' must be true or false")

    return Rule(
        code=code,
        phase=phase,
        source=source,
        cause=cause,
        advice=tuple(advice_raw),
        confidence=confidence,
        stop=stop,
        order=order,
        all=all_matchers,
        any=any_matchers,
        none=none_matchers,
    )


def validate_rules(data: object) -> tuple[Rule, ...]:
    """Validate a parsed rule document; raise :class:`RulesError` when invalid."""
    if not isinstance(data, dict):
        _fail("the rule file must contain a JSON object")
    unknown = set(data) - TOP_KEYS
    if unknown:
        _fail(f"unknown top-level keys {sorted(unknown)}")
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        _fail("the rule file needs a 'rules' list")
    rules: list[Rule] = []
    seen: set[str] = set()
    for order, raw in enumerate(raw_rules):
        rule = _build_rule(raw, order)
        if rule.code in seen:
            _fail(f"duplicate code {rule.code}")
        seen.add(rule.code)
        rules.append(rule)
    if not rules:
        _fail("the rule file contains no rules")
    return tuple(rules)


def load_rules(path: Path | None = None) -> tuple[Rule, ...]:
    """Load and validate the knowledge base (default: the bundled ``rules.json``)."""
    rule_path = Path(path) if path is not None else RULE_FILE
    try:
        text = rule_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RulesError(f"cannot read the rule file {rule_path}: {exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RulesError(f"the rule file {rule_path} is not valid JSON: {exc}") from exc
    rules = validate_rules(data)
    _LOGGER.debug("diagnostics: loaded %d rule(s) from %s", len(rules), rule_path)
    return rules


def referenced_keys(rules: Sequence[Rule]) -> list[str]:
    """Every i18n key a rule file can produce (cause + advice, in file order)."""
    keys: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        for key in (rule.cause, *rule.advice):
            if key in seen or _PLACEHOLDER_RE.match(key):
                continue
            seen.add(key)
            keys.append(key)
    return keys


def split_advice(advice: Sequence[str]) -> list[tuple[str, tuple[str, ...]]]:
    """Group an advice list into (key, argument placeholders) pairs.

    ``["diagnosis.oom.advice", "{memory}"]`` becomes
    ``[("diagnosis.oom.advice", ("{memory}",))]`` — the design's way of passing
    facts into an advice sentence without putting prose in the core.
    """
    grouped: list[tuple[str, tuple[str, ...]]] = []
    for item in advice:
        if _PLACEHOLDER_RE.match(item):
            if not grouped:
                _fail(f"advice argument {item!r} has no preceding advice key")
            key, args = grouped[-1]
            grouped[-1] = (key, (*args, item))
            continue
        grouped.append((item, ()))
    return grouped
