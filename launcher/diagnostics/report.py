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

"""Assemble the human-readable diagnosis and export it (sanitized).

The core never writes prose: it hands out **i18n keys plus arguments** and the
caller supplies a ``translate`` callable (``gui.i18n.tr`` in the app). That is
what keeps the nine language tables the single source of wording.

``sanitize()`` runs over **everything written to disk** — access tokens, JWT-ish
strings and ``C:\\Users\\<name>`` style home paths, plus the launcher's own data
directory, are masked before a log leaves this machine. Analysis itself is
local-only: nothing here opens a socket.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from launcher import paths
from launcher.diagnostics.engine import Diagnosis, Finding
from launcher.diagnostics.facts import EnvironmentFacts
from launcher.diagnostics.prepare import KIND_EXTRA, PreparedLog

_LOGGER = logging.getLogger(__name__)

Translate = Callable[..., str]

TOKEN_MASK = "***"
USER_MASK = "<user>"
LAUNCHER_DIR_MASK = "<launcher dir>"

ENV_FILENAME = "环境与启动信息.txt"
MODS_FILENAME = "模组清单.txt"

_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "Authorization: Bearer eyJ..." first: the scheme word must not be eaten as a token
    re.compile(r"(?i)\b(Bearer\s+)([A-Za-z0-9._~+/=-]{8,})"),
    # A JWT-shaped string anywhere in a log
    re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{2,}\b"),
    # "mc_access_token": "eyJ..." / accessToken=... / refresh_token: ...
    re.compile(
        r"(?i)(\"?[a-z_]*(?:access|refresh|session|auth|identity)[a-z_]*\"?\s*[:=]\s*\"?)"
        r"(?!Bearer\b)([^\s\",}]{4,})"
    ),
)

_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)([A-Za-z]:\\Users\\)([^\\\s\"']+)"),
    re.compile(r"(?i)(/home/)([^/\s\"']+)"),
    re.compile(r"(?i)(/Users/)([^/\s\"']+)"),
)


def default_translate(key: str, *args) -> str:
    """Fallback translate: renders the key itself (used by tests and core-only callers)."""
    return key.format(*args) if args else key


def sanitize(text: str, *, extra_paths: Iterable[Path | str] = ()) -> str:
    """Mask tokens, home-directory user names and local launcher paths.

    Applied to every file written by :func:`export_report`; the raw log never
    leaves the machine without passing through here.
    """
    if not text:
        return text
    out = str(text)
    for pattern in _TOKEN_PATTERNS:
        if pattern.groups == 2:
            out = pattern.sub(lambda match: match.group(1) + TOKEN_MASK, out)
        else:
            out = pattern.sub(TOKEN_MASK, out)
    for pattern in _PATH_PATTERNS:
        out = pattern.sub(lambda match: match.group(1) + USER_MASK, out)

    local: list[str] = [str(paths.launcher_dir()), str(Path.home())]
    for value in extra_paths:
        local.append(str(value))
    for literal in local:
        if literal and len(literal) > 3:
            out = re.sub(re.escape(literal), LAUNCHER_DIR_MASK, out, flags=re.IGNORECASE)
    return out


def _phase_label(finding: Finding, translate: Translate) -> str:
    return translate(f"diagnosis.phase.{finding.phase}")


def _confidence_label(finding: Finding, translate: Translate) -> str:
    return translate(f"diagnosis.confidence.{finding.confidence}")


def _kind_label(kind: str, translate: Translate) -> str:
    return translate(f"diagnosis.kind.{kind}")


def render_lines(diagnosis: Diagnosis, translate: Translate | None = None) -> list[str]:
    """The user-facing summary as a list of lines (keys + arguments only)."""
    tr = translate or default_translate
    primary = diagnosis.primary
    lines: list[str] = [
        tr("diagnosis.title"),
        tr("diagnosis.code", diagnosis.code),
        tr("diagnosis.phase", _phase_label(primary, tr)),
        tr("diagnosis.confidence", _confidence_label(primary, tr)),
    ]
    if primary.rules_merged:
        lines.append(tr("diagnosis.merged.codes", ", ".join(primary.codes)))
    lines.append("")
    lines.append(tr("diagnosis.section.cause"))
    lines.append(tr(primary.cause))
    lines.append("")
    lines.append(tr("diagnosis.section.advice"))
    for key, args in primary.advice:
        lines.append("· " + tr(key, *args))

    alternatives = diagnosis.alternatives
    if alternatives:
        lines.append("")
        lines.append(tr("diagnosis.section.candidates") + " — " + tr("diagnosis.multi.hint"))
        for finding in alternatives:
            lines.append(
                f"· [{finding.code}] {tr(finding.cause)}"
                f" — {_phase_label(finding, tr)}/{_confidence_label(finding, tr)}"
            )

    if primary.evidence:
        lines.append("")
        lines.append(tr("diagnosis.section.evidence"))
        for item in primary.evidence:
            lines.append(
                "· " + tr("diagnosis.evidence.item", _kind_label(item.log_kind, tr), item.line)
            )

    lines.append("")
    lines.append(tr("diagnosis.local_only"))
    return lines


def environment_lines(facts: EnvironmentFacts, translate: Translate | None = None) -> list[str]:
    """The synthesized ``环境与启动信息.txt`` body (sanitized by the caller)."""
    tr = translate or default_translate
    unknown = tr("diagnosis.fact.unknown")

    def value(text: str) -> str:
        return text if text and text != "-" else unknown

    if facts.isolated is None:
        isolation = unknown
    else:
        isolation = tr(
            "diagnosis.fact.isolation.on" if facts.isolated else "diagnosis.fact.isolation.off"
        )
    exit_code = value(str(facts.exit_code) if facts.exit_code is not None else "")
    rows = [
        ("diagnosis.fact.instance", value(facts.instance_id)),
        ("diagnosis.fact.game_version", value(facts.mc_version)),
        ("diagnosis.fact.loader", value(facts.loader_name)),
        ("diagnosis.fact.java", value(facts.java_text)),
        ("diagnosis.fact.memory", value(facts.memory_text)),
        ("diagnosis.fact.isolation", isolation),
        ("diagnosis.fact.exit_code", exit_code),
        ("diagnosis.fact.os", facts.os_name),
        ("diagnosis.fact.game_dir", facts.game_dir),
        ("diagnosis.fact.launch_dir", facts.launch_dir),
        ("diagnosis.fact.mods_count", facts.mods_text),
    ]
    return [tr("diagnosis.export.env.title"), ""] + [
        tr("diagnosis.export.env.row", tr(key), text) for key, text in rows
    ]


def mods_lines(facts: EnvironmentFacts, translate: Translate | None = None) -> list[str]:
    """The synthesized ``模组清单.txt`` body."""
    tr = translate or default_translate
    lines = [tr("diagnosis.export.mods.title"), ""]
    if not facts.mods:
        lines.append(tr("diagnosis.export.mods.empty"))
        return lines
    for mod in facts.mods:
        state_key = (
            "diagnosis.export.mod.enabled" if mod.enabled else "diagnosis.export.mod.disabled"
        )
        state = tr(state_key)
        lines.append(
            tr(
                "diagnosis.export.mods.row",
                mod.file,
                mod.name,
                mod.mod_id,
                mod.version or "-",
                state,
            )
        )
    return lines


def _log_body(log: PreparedLog, translate: Translate | None = None) -> str:
    tr = translate or default_translate
    header = tr("diagnosis.export.log.header", log.name, _kind_label(log.kind, tr))
    note = tr("diagnosis.export.windowed", len(log.lines)) if log.truncated else ""
    body = "\n".join(log.lines)
    return "\n".join(part for part in (header, note, body) if part)


def _safe_entry_name(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", sanitize(name)).strip() or "log.txt"
    candidate = cleaned
    index = 2
    while candidate.lower() in used:
        stem = Path(cleaned).stem
        suffix = Path(cleaned).suffix
        candidate = f"{stem}({index}){suffix}"
        index += 1
    used.add(candidate.lower())
    return candidate


def export_report(
    dest_zip: Path,
    diagnosis: Diagnosis,
    *,
    translate: Translate | None = None,
    logs: Sequence[PreparedLog] | None = None,
    include_extra: bool = True,
) -> Path:
    """Write a sanitized zip: selected logs + environment + mod list.

    Everything is passed through :func:`sanitize` before it is written, and the
    archive is built as a temp file plus an atomic replace.
    """
    tr = translate or default_translate
    selected = list(diagnosis.logs if logs is None else logs)
    if not include_extra:
        selected = [log for log in selected if log.kind != KIND_EXTRA]

    dest_zip = Path(dest_zip)
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_zip.with_name(dest_zip.name + ".tmp")
    used: set[str] = {ENV_FILENAME.lower(), MODS_FILENAME.lower()}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(ENV_FILENAME, sanitize("\n".join(environment_lines(diagnosis.facts, tr))))
        archive.writestr(MODS_FILENAME, sanitize("\n".join(mods_lines(diagnosis.facts, tr))))
        for log in selected:
            archive.writestr(_safe_entry_name(log.name, used), sanitize(_log_body(log, tr)))
    tmp.replace(dest_zip)
    _LOGGER.info("diagnostics: exported the report of %s to %s", diagnosis.code, dest_zip)
    return dest_zip
