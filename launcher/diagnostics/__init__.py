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

"""Crash / launch-failure knowledge base — the Qt-free core (design §2).

Layering::

    launcher/diagnostics/
      collector.py  find the candidate logs of one launch (freshness gate)
      prepare.py    classify + window + de-duplicate + decode (BOM/UTF-8/GB18030)
      rules.py      load and validate data/rules.json (plain data, strict schema)
      facts.py      environment facts (exit code, Java, memory, loader, mods)
      engine.py     phase ladder -> merge by cause -> rank -> fallback
      report.py     keys + arguments only, sanitize(), export zip
      data/rules.json  the knowledge base (MPL-Launch-#### / MPL-Crash-####)

**The GUI's entry point.** A later phase calls :func:`diagnose` with what it
knows about the launch it just ran::

    from launcher.diagnostics import DiagnosisContext, diagnose, render_lines

    context = DiagnosisContext(
        version_id=prepared.version.id,
        game_dir=game_dir,                    # shared game directory
        launch_dir=prepared.command.cwd,       # effective working directory
        exit_code=exit_code,                   # process exit code (None = never started)
        launch_started_at=started,             # freshness gate: mtime >= started
        captured_output=tail,                  # run_process(..., capture_tail=True).tail
        instance=resolved,                     # launcher.instances.ResolvedInstance
        error_text=message,                    # launcher-side failure text, when any
        memory_gb=resolved.memory_gb,
        java_major=prepared.java.major,
        java_path=prepared.java.path,
    )
    diagnosis = diagnose(context)
    lines = render_lines(diagnosis, gui.i18n.tr)      # fully localized text
    export_report(dest_zip, diagnosis, translate=gui.i18n.tr)

Everything is local: no network, no upload, no telemetry. `diagnose()` always
returns a diagnosis — ``MPL-Crash-0000`` (nothing matched) or
``MPL-Crash-0001`` (nothing analysable) when the knowledge base has no answer.
"""

from __future__ import annotations

from launcher.diagnostics.codes import (
    CRASH_PREFIX,
    LAUNCH_PREFIX,
    NOTHING_TO_ANALYSE_CODE,
    RESERVED_CODES,
    UNKNOWN_CODE,
)
from launcher.diagnostics.collector import (
    LogCandidate,
    collect_candidates,
)
from launcher.diagnostics.context import DiagnosisContext
from launcher.diagnostics.engine import (
    PHASES,
    Diagnosis,
    Evidence,
    Finding,
    diagnose,
)
from launcher.diagnostics.facts import (
    EnvironmentFacts,
    ModFact,
    collect_facts,
    derive_version_facts,
)
from launcher.diagnostics.prepare import (
    KIND_CRASH_REPORT,
    KIND_DEBUG,
    KIND_EXTRA,
    KIND_GAME,
    KIND_HS_ERR,
    KIND_LAUNCHER,
    KINDS,
    MATCHABLE_KINDS,
    WINDOWS,
    PreparedLog,
    decode_bytes,
    prepare_logs,
)
from launcher.diagnostics.report import (
    ENV_FILENAME,
    MODS_FILENAME,
    environment_lines,
    export_report,
    mods_lines,
    render_lines,
    sanitize,
)
from launcher.diagnostics.rules import (
    RULE_FILE,
    Matcher,
    Rule,
    RulesError,
    load_rules,
    referenced_keys,
    validate_rules,
)

__all__ = [
    "CRASH_PREFIX",
    "ENV_FILENAME",
    "KINDS",
    "KIND_CRASH_REPORT",
    "KIND_DEBUG",
    "KIND_EXTRA",
    "KIND_GAME",
    "KIND_HS_ERR",
    "KIND_LAUNCHER",
    "LAUNCH_PREFIX",
    "MATCHABLE_KINDS",
    "MODS_FILENAME",
    "NOTHING_TO_ANALYSE_CODE",
    "PHASES",
    "RESERVED_CODES",
    "RULE_FILE",
    "UNKNOWN_CODE",
    "WINDOWS",
    "Diagnosis",
    "DiagnosisContext",
    "EnvironmentFacts",
    "Evidence",
    "Finding",
    "LogCandidate",
    "Matcher",
    "ModFact",
    "PreparedLog",
    "Rule",
    "RulesError",
    "collect_candidates",
    "collect_facts",
    "decode_bytes",
    "derive_version_facts",
    "diagnose",
    "environment_lines",
    "export_report",
    "load_rules",
    "mods_lines",
    "prepare_logs",
    "referenced_keys",
    "render_lines",
    "sanitize",
    "validate_rules",
]
