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

"""The diagnosis engine: phase ladder -> merge by cause -> ranking -> fallback.

The ladder is the cheap, explainable priority order of the design
(``launcher`` -> ``fatal`` -> ``primary`` -> ``secondary``): every phase runs in
order and a phase that produced a hit which says ``stop`` ends the walk.

Within a phase the candidates are ranked by (confidence, rule order); findings
that share a cause are merged into one entry with the union of their evidence.
A diagnosis is **always** produced: ``MPL-Crash-0000`` when nothing matched and
``MPL-Crash-0001`` when there was nothing analysable — the dialog never opens
empty and never has to invent wording of its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from launcher.diagnostics.codes import NOTHING_TO_ANALYSE_CODE, UNKNOWN_CODE
from launcher.diagnostics.context import DiagnosisContext
from launcher.diagnostics.facts import EnvironmentFacts, collect_facts
from launcher.diagnostics.prepare import PreparedLog, prepare_logs
from launcher.diagnostics.rules import Rule, RulesError, load_rules, split_advice

_LOGGER = logging.getLogger(__name__)

#: Ordered phase ladder (the launcher side always runs first).
PHASES = ("launcher", "fatal", "primary", "secondary")
CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}

MAX_EVIDENCE_LINES = 3

# Fallback keys (also used by the report; always present in the i18n tables).
UNKNOWN_CAUSE_KEY = "diagnosis.unknown.cause"
UNKNOWN_ADVICE_KEY = "diagnosis.unknown.advice"
NOTHING_CAUSE_KEY = "diagnosis.nothing.cause"
NOTHING_ADVICE_KEY = "diagnosis.nothing.advice"

#: (i18n key, resolved placeholder arguments)
AdviceItem = tuple[str, tuple[str, ...]]


@dataclass(frozen=True)
class Evidence:
    """One matched line and the log kind it came from."""

    log_name: str
    log_kind: str
    line: str
    matched: str  # the substring / regex that hit this line


@dataclass(frozen=True)
class Finding:
    """One possible cause, ready for the report (keys + arguments only)."""

    code: str
    phase: str
    confidence: str
    cause: str
    advice: tuple[AdviceItem, ...]
    evidence: tuple[Evidence, ...]
    codes: tuple[str, ...]  # every merged rule code (first one is `code`)
    order: int  # best rule order inside the phase, for stable sorting
    fallback: bool = False

    @property
    def rules_merged(self) -> bool:
        return len(self.codes) > 1


@dataclass(frozen=True)
class Diagnosis:
    """The result of one diagnosis request."""

    code: str
    phase: str
    confidence: str
    findings: tuple[Finding, ...]
    logs: tuple[PreparedLog, ...]
    facts: EnvironmentFacts
    exit_code: int | None
    analysable: bool

    @property
    def primary(self) -> Finding:
        """The best candidate (always present)."""
        return self.findings[0]

    @property
    def alternatives(self) -> tuple[Finding, ...]:
        """Every other candidate, in ranked order."""
        return self.findings[1:]

    @property
    def log_kinds(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(log.kind for log in self.logs))


@dataclass(frozen=True)
class _Hit:
    rule: Rule
    log: PreparedLog
    lines: tuple[str, ...]


def _sort_key(hit: _Hit) -> tuple[int, int, int]:
    return (PHASES.index(hit.rule.phase), CONFIDENCE_RANK[hit.rule.confidence], hit.rule.order)


def _evidence_of(hit: _Hit) -> list[Evidence]:
    matchers = (*hit.rule.all, *hit.rule.any)
    out: list[Evidence] = []
    for line in hit.lines:
        matched = ""
        for matcher in matchers:
            if matcher.hits(line):
                matched = matcher.pattern
                break
        out.append(
            Evidence(log_name=hit.log.name, log_kind=hit.log.kind, line=line, matched=matched)
        )
    return out


def _run_ladder(rules: tuple[Rule, ...], logs: list[PreparedLog]) -> list[_Hit]:
    """Walk the phase ladder; stop after a phase whose hit asked to stop."""
    hits: list[_Hit] = []
    for phase in PHASES:
        phase_hits: list[_Hit] = []
        for rule in rules:
            if rule.phase != phase:
                continue
            for log in logs:
                if log.kind != rule.source:
                    continue
                lines = rule.match_lines(log.lines)
                if lines is None:
                    continue
                phase_hits.append(_Hit(rule=rule, log=log, lines=tuple(lines[:MAX_EVIDENCE_LINES])))
        hits.extend(phase_hits)
        if phase_hits and any(hit.rule.stop for hit in phase_hits):
            _LOGGER.debug(
                "diagnostics: phase %s asked to stop after %d hit(s)", phase, len(phase_hits)
            )
            break
    return hits


def _merge(hits: list[_Hit], facts: EnvironmentFacts) -> tuple[Finding, ...]:
    """Merge hits that share a cause (union of evidence) and rank the candidates."""
    groups: dict[str, list[_Hit]] = {}
    for hit in hits:
        groups.setdefault(hit.rule.cause, []).append(hit)

    findings: list[Finding] = []
    for cause, group in groups.items():
        best = min(group, key=_sort_key)
        codes: dict[str, None] = {}
        evidence: list[Evidence] = []
        seen_evidence: set[tuple[str, str]] = set()
        for hit in sorted(group, key=_sort_key):
            codes.setdefault(hit.rule.code, None)
            for item in _evidence_of(hit):
                key = (item.log_name, item.line)
                if key in seen_evidence:
                    continue
                seen_evidence.add(key)
                evidence.append(item)
        advice: list[AdviceItem] = []
        for key, args in split_advice(best.rule.advice):
            resolved = tuple(facts.placeholder(arg[1:-1]) for arg in args)
            advice.append((key, resolved))
        findings.append(
            Finding(
                code=best.rule.code,
                phase=best.rule.phase,
                confidence=best.rule.confidence,
                cause=cause,
                advice=tuple(advice),
                evidence=tuple(evidence),
                codes=tuple(codes),
                order=best.rule.order,
            )
        )
    findings.sort(
        key=lambda item: (
            PHASES.index(item.phase),
            CONFIDENCE_RANK[item.confidence],
            item.order,
        )
    )
    return tuple(findings)


def _fallback(*, analysable: bool) -> Finding:
    if analysable:
        return Finding(
            code=UNKNOWN_CODE,
            phase="fatal",
            confidence="low",
            cause=UNKNOWN_CAUSE_KEY,
            advice=((UNKNOWN_ADVICE_KEY, ()),),
            evidence=(),
            codes=(UNKNOWN_CODE,),
            order=-1,
            fallback=True,
        )
    return Finding(
        code=NOTHING_TO_ANALYSE_CODE,
        phase="fatal",
        confidence="low",
        cause=NOTHING_CAUSE_KEY,
        advice=((NOTHING_ADVICE_KEY, ()),),
        evidence=(),
        codes=(NOTHING_TO_ANALYSE_CODE,),
        order=-1,
        fallback=True,
    )


def _log_findings(findings: tuple[Finding, ...], logs: list[PreparedLog]) -> None:
    """Every finding goes to the launcher log with its evidence (never silently swallowed)."""
    _LOGGER.info(
        "diagnosis: %d analysable log(s): %s",
        len(logs),
        ", ".join(f"{log.name}[{log.kind}]={len(log.lines)}" for log in logs) or "none",
    )
    for index, finding in enumerate(findings, start=1):
        evidence = "; ".join(
            f"{item.log_kind}/{item.log_name}: {item.line[:160]}" for item in finding.evidence
        )
        _LOGGER.info(
            "diagnosis candidate %d: code=%s phase=%s confidence=%s cause=%s codes=%s evidence=%s",
            index,
            finding.code,
            finding.phase,
            finding.confidence,
            finding.cause,
            ",".join(finding.codes),
            evidence or "none",
        )


def diagnose(
    context: DiagnosisContext,
    *,
    rules: tuple[Rule, ...] | None = None,
    facts: EnvironmentFacts | None = None,
    logs: list[PreparedLog] | None = None,
) -> Diagnosis:
    """Diagnose one launch (pure, local, no Qt and no network).

    `rules` / `facts` / `logs` are injection points for tests; production callers
    pass only the context.
    """
    resolved_rules: tuple[Rule, ...]
    if rules is not None:
        resolved_rules = rules
    else:
        try:
            resolved_rules = load_rules(context.rules_path)
        except RulesError as exc:
            # A broken or missing knowledge base must never break the crash dialog:
            # log it loudly and degrade to "no rules" (the fallback still answers).
            _LOGGER.error("diagnostics: the rule file could not be loaded: %s", exc)
            resolved_rules = ()
    resolved_facts = facts if facts is not None else collect_facts(context)
    resolved_logs = logs if logs is not None else prepare_logs(context)

    matchable = [log for log in resolved_logs if log.is_matchable]
    hits = _run_ladder(resolved_rules, matchable)
    findings = _merge(hits, resolved_facts)
    analysable = bool(matchable)
    if not findings:
        findings = (_fallback(analysable=analysable),)

    _log_findings(findings, matchable)
    return Diagnosis(
        code=findings[0].code,
        phase=findings[0].phase,
        confidence=findings[0].confidence,
        findings=findings,
        logs=tuple(resolved_logs),
        facts=resolved_facts,
        exit_code=context.exit_code,
        analysable=analysable,
    )
