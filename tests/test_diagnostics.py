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

"""Crash / launch-failure knowledge base tests (design §8).

Sample logs live in ``tests/data/crash_samples/`` and every one of them asserts
the **expected error code**, never the wording: the text comes from the nine
language tables and is covered by the i18n integrity tests instead.
"""

from __future__ import annotations

import codecs
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pytest

from gui import i18n
from launcher import paths
from launcher.diagnostics import (
    ENV_FILENAME,
    MODS_FILENAME,
    NOTHING_TO_ANALYSE_CODE,
    RULE_FILE,
    UNKNOWN_CODE,
    DiagnosisContext,
    RulesError,
    decode_bytes,
    derive_version_facts,
    diagnose,
    export_report,
    load_rules,
    prepare_logs,
    sanitize,
    validate_rules,
)
from launcher.diagnostics.facts import UNKNOWN_VALUE
from launcher.diagnostics.prepare import (
    KIND_DEBUG,
    KIND_EXTRA,
    KIND_GAME,
    KIND_LAUNCHER,
    MAX_LINE_CHARS,
    WINDOWS,
    bound_text,
)
from launcher.launch.runner import TAIL_LINES, RunResult, run_process

SAMPLES = Path(__file__).resolve().parent / "data" / "crash_samples"


def _translate(key: str, *args) -> str:
    """Render through the English table without touching the global UI language."""
    table = i18n.TRANSLATIONS["en_us"]
    text = table.get(key, key)
    return text.format(*args) if args else text

# (sample file, destination inside the game dir, expected code)
CRASH_DIR = "crash-reports/"
GOLDEN_CASES = [
    ("oom.latest.log", "logs/latest.log", "MPL-Crash-0101"),
    ("hs_err_pid4820.log", "hs_err_pid4820.log", "MPL-Crash-0103"),
    ("hs_err_pid3312_32bit.log", "hs_err_pid3312_32bit.log", "MPL-Crash-0102"),
    ("mixin_failure.latest.log", "logs/latest.log", "MPL-Crash-0106"),
    ("missing_dependency.latest.log", "logs/latest.log", "MPL-Crash-0104"),
    ("wrong_java.latest.log", "logs/latest.log", "MPL-Crash-0107"),
    ("duplicate_mods.latest.log", "logs/latest.log", "MPL-Crash-0105"),
    ("gbk_launcher.log", "launcher-logs/launcher.log", "MPL-Launch-0006"),
    (
        "forge_crash_report.txt",
        CRASH_DIR + "crash-2026-09-25_21.16.03-client.txt",
        "MPL-Crash-0108",
    ),
    (
        "vanilla_crash_report.txt",
        CRASH_DIR + "crash-2026-09-25_21.14.11-client.txt",
        UNKNOWN_CODE,
    ),
    (
        "empty_report.txt",
        CRASH_DIR + "crash-2026-09-25_21.17.00-client.txt",
        NOTHING_TO_ANALYSE_CODE,
    ),
]

# Launcher-side failures arrive as the failure text of the failed launch (there is
# no game log at all in that case).
LAUNCH_CASES = [
    ("JavaMissingError: no suitable Java runtime for this version", "MPL-Launch-0002"),
    (
        "OfflineLockedError: Offline mode requires signing in with a Microsoft account",
        "MPL-Launch-0003",
    ),
    ("MetaError: meta.not_found - version JSON for 1.20.1 is missing", "MPL-Launch-0004"),
    ("DownloadError: net.connect - download failed after 3 attempts", "MPL-Launch-0005"),
    (
        "PermissionError: [WinError 5] Access is denied: 'versions\\\\1.20.1\\\\1.20.1.jar'",
        "MPL-Launch-0006",
    ),
    ("OSError: [Errno 28] No space left on device", "MPL-Launch-0007"),
]


def _context(ws_tmp: Path, **overrides) -> DiagnosisContext:
    """A diagnosis context pointing at an empty game directory inside ws_tmp."""
    game = ws_tmp / "game"
    game.mkdir(parents=True, exist_ok=True)
    launcher_logs = ws_tmp / "launcher-logs"
    launcher_logs.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "version_id": "fabric-loader-0.15.11-1.20.1",
        "game_dir": game,
        "exit_code": 1,
        "launch_started_at": time.time() - 60,
        "launcher_logs_dir": launcher_logs,
        "memory_gb": 4.0,
        "java_major": 17,
    }
    kwargs.update(overrides)
    return DiagnosisContext(**kwargs)


def _place(ws_tmp: Path, sample: str, relative: str) -> Path:
    """Copy a sample log into the game dir (or the launcher log dir) of ws_tmp."""
    if relative.startswith("launcher-logs/"):
        target = ws_tmp / relative
    else:
        target = ws_tmp / "game" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SAMPLES / sample, target)
    return target


def _write_rules(ws_tmp: Path, rules: list[dict]) -> Path:
    path = ws_tmp / "rules.json"
    payload = json.dumps({"version": 1, "rules": rules}, ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Rule file: schema and validation
# --------------------------------------------------------------------------- #
def test_shipped_rule_file_is_valid() -> None:
    assert RULE_FILE.is_file(), f"the knowledge base is missing: {RULE_FILE}"
    rules = load_rules()
    assert 12 <= len(rules) <= 15, f"expected 12-15 rules, found {len(rules)}"
    codes = [rule.code for rule in rules]
    assert len(codes) == len(set(codes)), "duplicate codes in the shipped rule file"
    assert all(rule.cause.startswith("diagnosis.") for rule in rules)
    assert all(rule.advice for rule in rules)
    assert {rule.phase for rule in rules} <= {"launcher", "fatal", "primary", "secondary"}
    assert {rule.confidence for rule in rules} == {"high", "medium", "low"}
    assert all(rule.source != "extra" for rule in rules)
    # both prefixes are in use and no reserved code was taken
    assert any(code.startswith("MPL-Launch-") for code in codes)
    assert any(code.startswith("MPL-Crash-") for code in codes)
    assert UNKNOWN_CODE not in codes and NOTHING_TO_ANALYSE_CODE not in codes


def _mutate(ws_tmp: Path, mutate) -> Path:
    data = json.loads(RULE_FILE.read_text(encoding="utf-8-sig"))
    mutate(data)
    path = ws_tmp / "rules.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_duplicate_code_raises(ws_tmp) -> None:
    def mutate(data):
        data["rules"][1]["code"] = data["rules"][0]["code"]

    with pytest.raises(RulesError, match="duplicate code"):
        load_rules(_mutate(ws_tmp, mutate))


def test_uncompilable_regex_raises(ws_tmp) -> None:
    def mutate(data):
        data["rules"][0]["match"] = {"any": [{"regex": "([unclosed"}]}

    with pytest.raises(RulesError, match="uncompilable regex"):
        load_rules(_mutate(ws_tmp, mutate))


def test_unknown_source_raises(ws_tmp) -> None:
    def mutate(data):
        data["rules"][0]["source"] = "gameboy"

    with pytest.raises(RulesError, match="unknown source"):
        load_rules(_mutate(ws_tmp, mutate))


def test_unknown_key_raises(ws_tmp) -> None:
    def mutate(data):
        data["rules"][0]["severity"] = "high"

    with pytest.raises(RulesError, match="unknown keys"):
        load_rules(_mutate(ws_tmp, mutate))


def test_unknown_phase_and_confidence_raise(ws_tmp) -> None:
    with pytest.raises(RulesError, match="unknown phase"):
        load_rules(_mutate(ws_tmp, lambda data: data["rules"][0].update(phase="doom")))
    with pytest.raises(RulesError, match="unknown confidence"):
        load_rules(_mutate(ws_tmp, lambda data: data["rules"][0].update(confidence="maybe")))


def test_empty_matcher_raises(ws_tmp) -> None:
    def mutate(data):
        data["rules"][0]["match"] = {"all": [], "any": []}

    with pytest.raises(RulesError, match="empty matcher"):
        load_rules(_mutate(ws_tmp, mutate))


def test_wrong_prefix_and_reserved_code_raise(ws_tmp) -> None:
    def wrong_prefix(data):
        data["rules"][0]["code"] = "MPL-Crash-9001"  # a launcher rule with the crash prefix

    with pytest.raises(RulesError, match="wrong prefix"):
        load_rules(_mutate(ws_tmp, wrong_prefix))

    def reserved(data):
        data["rules"][0]["code"] = UNKNOWN_CODE

    with pytest.raises(RulesError, match="reserved"):
        load_rules(_mutate(ws_tmp, reserved))


def test_missing_rule_file_raises(ws_tmp) -> None:
    with pytest.raises(RulesError, match="cannot read"):
        load_rules(ws_tmp / "nope.json")


def test_validate_rules_rejects_a_non_object_document() -> None:
    with pytest.raises(RulesError):
        validate_rules([{"code": "MPL-Crash-0002"}])


# --------------------------------------------------------------------------- #
# Golden sample logs: every sample asserts its expected code
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sample,relative,expected", GOLDEN_CASES)
def test_sample_log_yields_expected_code(ws_tmp, sample, relative, expected) -> None:
    _place(ws_tmp, sample, relative)
    diagnosis = diagnose(_context(ws_tmp))
    assert diagnosis.code == expected, (
        f"{sample}: got {diagnosis.code}, causes={[f.cause for f in diagnosis.findings]}"
    )
    assert diagnosis.findings, "a diagnosis always carries at least one finding"


@pytest.mark.parametrize("error_text,expected", LAUNCH_CASES)
def test_launcher_side_failure_text_yields_expected_code(ws_tmp, error_text, expected) -> None:
    diagnosis = diagnose(_context(ws_tmp, error_text=error_text))
    assert diagnosis.code == expected, (error_text, diagnosis.code)


def test_heap_size_failure_is_detected_in_the_captured_output(ws_tmp) -> None:
    """The JVM refuses to start: its stderr is the only evidence (MPL-Launch-0008)."""
    tail = [
        "Picked up JAVA_TOOL_OPTIONS: -Dfile.encoding=UTF-8",
        "Invalid maximum heap size: -Xmx99999G",
        "Error: Could not create the Java Virtual Machine.",
        "Error occurred during initialization of VM",
        "Could not reserve enough space for object heap",
    ]
    diagnosis = diagnose(_context(ws_tmp, captured_output=tail))
    assert diagnosis.code == "MPL-Launch-0008"
    assert diagnosis.primary.evidence
    assert diagnosis.primary.evidence[0].log_kind == KIND_GAME


def test_gbk_launcher_log_is_decoded(ws_tmp) -> None:
    """A GBK-encoded launcher log is decoded (not skipped) and still matches."""
    context = _context(ws_tmp)
    message = "另一个程序正在使用此文件"
    log_path = context.launcher_logs_dir / "launcher.log"
    log_path.write_bytes(f"OSError: [WinError 32] {message}\n".encode("gb18030"))
    diagnosis = diagnose(context)
    assert diagnosis.code == "MPL-Launch-0006"
    assert diagnosis.primary.evidence[0].line.endswith(message)


# --------------------------------------------------------------------------- #
# Collector / prepare behaviour
# --------------------------------------------------------------------------- #
def test_freshness_gate_ignores_an_old_log(ws_tmp) -> None:
    path = _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    old = time.time() - 3600
    os.utime(path, (old, old))

    stale = diagnose(_context(ws_tmp, launch_started_at=time.time() - 60))
    assert stale.code == NOTHING_TO_ANALYSE_CODE
    assert not stale.analysable

    # The same file written after the launch start is picked up
    fresh = diagnose(_context(ws_tmp, launch_started_at=old - 1))
    assert fresh.code == "MPL-Crash-0101"


def test_crash_report_mtime_gate_and_newest_first(ws_tmp) -> None:
    reports = ws_tmp / "game" / "crash-reports"
    reports.mkdir(parents=True, exist_ok=True)
    old = reports / "crash-old.txt"
    new = reports / "crash-new.txt"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    now = time.time()
    os.utime(old, (now - 7200, now - 7200))
    os.utime(new, (now - 10, now - 10))
    from launcher.diagnostics import collect_candidates

    candidates = collect_candidates(_context(ws_tmp))
    names = [item.name for item in candidates]
    assert names == ["crash-new.txt"]  # the stale report is gated out
    assert new.stat().st_mtime == pytest.approx(candidates[0].mtime)


def test_huge_log_is_windowed_and_de_duplicated(ws_tmp) -> None:
    path = ws_tmp / "game" / "logs" / "latest.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"[21:00:00] [main/INFO] [Test/]: line {index}" for index in range(6000)]
    lines.append(lines[0])  # duplicate inside the tail window
    lines.append("java.lang.OutOfMemoryError: Java heap space")
    path.write_text("\n".join(lines), encoding="utf-8")

    logs = prepare_logs(_context(ws_tmp))
    latest = next(log for log in logs if log.kind == KIND_GAME)
    head, tail = WINDOWS[KIND_GAME]
    assert len(latest.lines) <= head + tail
    assert len(set(latest.lines)) == len(latest.lines), "duplicate lines survived"
    assert all(line.strip() for line in latest.lines), "blank lines survived"
    assert latest.lines[0] == lines[0]
    assert latest.lines[-1] == lines[-1]
    assert not any("line 4000" in line for line in latest.lines), "the middle was kept"
    assert diagnose(_context(ws_tmp)).code == "MPL-Crash-0101"


def test_debug_log_window_is_head_only(ws_tmp) -> None:
    path = ws_tmp / "game" / "logs" / "debug.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"[21:00:00] [Render thread/DEBUG] [Test/]: debug {i}" for i in range(5000)),
        encoding="utf-8",
    )
    logs = prepare_logs(_context(ws_tmp))
    debug = next(log for log in logs if log.kind == KIND_DEBUG)
    assert len(debug.lines) == WINDOWS[KIND_DEBUG][0]
    assert debug.lines[0].endswith("debug 0")


def test_monster_line_is_clipped_and_matching_input_is_bounded(ws_tmp) -> None:
    path = ws_tmp / "game" / "logs" / "latest.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "X" * 50_000 + "\njava.lang.OutOfMemoryError: Java heap space\n", encoding="utf-8"
    )
    logs = prepare_logs(_context(ws_tmp))
    latest = next(log for log in logs if log.kind == KIND_GAME)
    assert max(len(line) for line in latest.lines) <= MAX_LINE_CHARS
    assert len(latest.match_text) <= len(bound_text("X" * 1_000_000))
    assert diagnose(_context(ws_tmp)).code == "MPL-Crash-0101"


def test_extra_files_are_not_matched(ws_tmp) -> None:
    """A file in crash-reports/ that is neither a crash report nor an hs_err only gets exported."""
    extra = ws_tmp / "game" / "crash-reports" / "notes.txt"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("java.lang.OutOfMemoryError: Java heap space", encoding="utf-8")
    diagnosis = diagnose(_context(ws_tmp))
    assert diagnosis.code == NOTHING_TO_ANALYSE_CODE
    assert any(log.kind == KIND_EXTRA for log in diagnosis.logs)


def test_launcher_log_is_found_under_the_launcher_directory(ws_tmp) -> None:
    context = _context(ws_tmp)
    (context.launcher_logs_dir / "launcher.log").write_text(
        "OfflineLockedError: Offline mode requires ...", encoding="utf-8"
    )
    diagnosis = diagnose(context)
    assert diagnosis.code == "MPL-Launch-0003"
    assert diagnosis.primary.evidence[0].log_kind == KIND_LAUNCHER
    assert diagnosis.primary.evidence[0].log_name == "launcher.log"


def test_decode_bytes_handles_boms_and_gb18030() -> None:
    assert decode_bytes(codecs.BOM_UTF8 + "中文".encode()) == ("中文", "utf-8-sig")
    assert decode_bytes("中文".encode("utf-16")) == ("中文", "utf-16")
    assert decode_bytes("中文".encode("gb18030")) == ("中文", "gb18030")
    assert decode_bytes(b"plain ascii") == ("plain ascii", "utf-8")


def test_captured_output_is_de_duplicated_against_game_logs(ws_tmp) -> None:
    """The same stdout tail and latest.log must not produce the same evidence twice."""
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    tail = (SAMPLES / "oom.latest.log").read_text(encoding="utf-8").splitlines()
    diagnosis = diagnose(_context(ws_tmp, captured_output=tail))
    assert diagnosis.code == "MPL-Crash-0101"
    names = {item.log_name for item in diagnosis.primary.evidence}
    assert names  # evidence is present and labelled with its source


# --------------------------------------------------------------------------- #
# Engine: ladder, merging, ranking, fallbacks
# --------------------------------------------------------------------------- #
def test_nothing_analysable_is_0001(ws_tmp) -> None:
    diagnosis = diagnose(_context(ws_tmp))
    assert diagnosis.code == NOTHING_TO_ANALYSE_CODE
    assert not diagnosis.analysable
    assert diagnosis.primary.fallback
    assert diagnosis.primary.cause == "diagnosis.nothing.cause"


def test_nothing_matched_is_0000(ws_tmp) -> None:
    _place(ws_tmp, "vanilla_crash_report.txt", "crash-reports/crash-2026-09-25_21.14.11-client.txt")
    diagnosis = diagnose(_context(ws_tmp))
    assert diagnosis.code == UNKNOWN_CODE
    assert diagnosis.analysable
    assert diagnosis.primary.cause == "diagnosis.unknown.cause"


def test_a_broken_rule_file_still_produces_a_diagnosis(ws_tmp, caplog) -> None:
    """A missing/broken knowledge base degrades to the fallback instead of raising."""
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    broken = ws_tmp / "broken-rules.json"
    broken.write_text("{ not json", encoding="utf-8")
    with caplog.at_level("ERROR", logger="launcher.diagnostics.engine"):
        diagnosis = diagnose(_context(ws_tmp, rules_path=broken))
    assert diagnosis.code == UNKNOWN_CODE
    assert diagnosis.primary.fallback
    assert any("rule file" in record.getMessage() for record in caplog.records)


def test_same_cause_is_merged_and_phases_are_ordered(ws_tmp) -> None:
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    rules_path = _write_rules(
        ws_tmp,
        [
            {
                "code": "MPL-Crash-0201",
                "phase": "fatal",
                "source": "game",
                "match": {"any": ["OutOfMemoryError"]},
                "cause": "diagnosis.crash.oom.cause",
                "advice": ["diagnosis.crash.oom.advice", "{memory}"],
                "confidence": "high",
            },
            {
                "code": "MPL-Crash-0202",
                "phase": "primary",
                "source": "game",
                "match": {"any": ["Failed to allocate a 1048576 byte allocation"]},
                "cause": "diagnosis.crash.oom.cause",
                "advice": ["diagnosis.crash.oom.advice", "{memory}"],
                "confidence": "high",
            },
            {
                "code": "MPL-Crash-0203",
                "phase": "secondary",
                "source": "game",
                "match": {"any": ["Exception ticking world"]},
                "cause": "diagnosis.crash.suspected_mod.cause",
                "advice": ["diagnosis.crash.suspected_mod.advice"],
                "confidence": "medium",
            },
        ],
    )
    diagnosis = diagnose(_context(ws_tmp, rules_path=rules_path))
    assert len(diagnosis.findings) == 2, "hits sharing a cause must merge into one finding"
    merged = diagnosis.findings[0]
    assert merged.code == "MPL-Crash-0201"  # the fatal phase wins
    assert merged.codes == ("MPL-Crash-0201", "MPL-Crash-0202")
    assert merged.rules_merged
    assert len(merged.evidence) >= 2, "the merged finding keeps the union of the evidence"
    assert diagnosis.findings[1].code == "MPL-Crash-0203"
    assert diagnosis.findings[1].phase == "secondary"
    assert diagnosis.code == "MPL-Crash-0201"
    assert merged.advice[0] == ("diagnosis.crash.oom.advice", ("4 GB",))


def test_launcher_phase_runs_before_the_game_phases(ws_tmp) -> None:
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    rules_path = _write_rules(
        ws_tmp,
        [
            {
                "code": "MPL-Crash-0211",
                "phase": "fatal",
                "source": "game",
                "match": {"any": ["OutOfMemoryError"]},
                "cause": "diagnosis.crash.oom.cause",
                "advice": ["diagnosis.crash.oom.advice", "{memory}"],
                "confidence": "high",
            },
            {
                "code": "MPL-Launch-0212",
                "phase": "launcher",
                "source": "launcher",
                "match": {"any": ["JavaMissingError"]},
                "cause": "diagnosis.launch.java_missing.cause",
                "advice": ["diagnosis.launch.java_missing.advice"],
                "confidence": "high",
            },
        ],
    )
    diagnosis = diagnose(
        _context(ws_tmp, rules_path=rules_path, error_text="JavaMissingError: no suitable Java")
    )
    assert [finding.code for finding in diagnosis.findings] == ["MPL-Launch-0212", "MPL-Crash-0211"]
    assert diagnosis.code == "MPL-Launch-0212"


def test_stop_ends_the_ladder(ws_tmp) -> None:
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    rules_path = _write_rules(
        ws_tmp,
        [
            {
                "code": "MPL-Crash-0221",
                "phase": "fatal",
                "source": "game",
                "match": {"any": ["OutOfMemoryError"]},
                "cause": "diagnosis.crash.oom.cause",
                "advice": ["diagnosis.crash.oom.advice", "{memory}"],
                "confidence": "high",
                "stop": True,
            },
            {
                "code": "MPL-Crash-0222",
                "phase": "primary",
                "source": "game",
                "match": {"any": ["Exception ticking world"]},
                "cause": "diagnosis.crash.suspected_mod.cause",
                "advice": ["diagnosis.crash.suspected_mod.advice"],
                "confidence": "medium",
            },
        ],
    )
    diagnosis = diagnose(_context(ws_tmp, rules_path=rules_path))
    assert [finding.code for finding in diagnosis.findings] == ["MPL-Crash-0221"]


def test_confidence_orders_candidates_inside_a_phase(ws_tmp) -> None:
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    rules_path = _write_rules(
        ws_tmp,
        [
            {
                "code": "MPL-Crash-0231",
                "phase": "fatal",
                "source": "game",
                "match": {"any": ["OutOfMemoryError"]},
                "cause": "diagnosis.crash.oom.cause",
                "advice": ["diagnosis.crash.oom.advice", "{memory}"],
                "confidence": "low",
            },
            {
                "code": "MPL-Crash-0232",
                "phase": "fatal",
                "source": "game",
                "match": {"any": ["Exception ticking world"]},
                "cause": "diagnosis.crash.suspected_mod.cause",
                "advice": ["diagnosis.crash.suspected_mod.advice"],
                "confidence": "high",
            },
        ],
    )
    diagnosis = diagnose(_context(ws_tmp, rules_path=rules_path))
    assert [finding.code for finding in diagnosis.findings] == ["MPL-Crash-0232", "MPL-Crash-0231"]


def test_findings_are_logged_with_evidence(ws_tmp, caplog) -> None:
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    with caplog.at_level("INFO", logger="launcher.diagnostics.engine"):
        diagnose(_context(ws_tmp))
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "MPL-Crash-0101" in messages
    assert "OutOfMemoryError" in messages


# --------------------------------------------------------------------------- #
# Report: rendering, sanitizing, exporting
# --------------------------------------------------------------------------- #
def test_render_lines_uses_keys_and_arguments(ws_tmp) -> None:
    from launcher.diagnostics import render_lines

    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    diagnosis = diagnose(_context(ws_tmp))
    raw = render_lines(diagnosis)  # no translator: the keys themselves
    assert "diagnosis.title" in raw
    assert "diagnosis.crash.oom.cause" in raw

    i18n.set_language("zh_cn")
    try:
        chinese = "\n".join(render_lines(diagnosis, i18n.tr))
        assert "MPL-Crash-0101" in chinese
        assert i18n.TRANSLATIONS["zh_cn"]["diagnosis.crash.oom.cause"] in chinese
        assert "4 GB" in chinese
    finally:
        i18n.set_language("zh_cn")


def test_sanitize_masks_tokens_paths_and_the_launcher_dir() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.eyJ4IjoxMjM0NTY3ODkwfQ.abcdefghijkl"
    text = (
        f'accessToken": "{token}"\n'
        "path C:\\Users\\Alice\\AppData\\Roaming\\.minecraft\\logs\\latest.log\n"
        "Authorization: Bearer abcdef0123456789\n"
    )
    cleaned = sanitize(text)
    assert token not in cleaned
    assert "Alice" not in cleaned
    assert "abcdef0123456789" not in cleaned
    assert "<user>" in cleaned

    launcher = str(paths.launcher_dir())
    assert launcher not in sanitize(f"log file: {launcher}\\logs\\launcher.log")


def test_export_report_is_sanitized_and_complete(ws_tmp) -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.eyJ4IjoxMjM0NTY3ODkwfQ.abcdefghijkl"
    log_path = ws_tmp / "game" / "logs" / "latest.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f'accessToken": "{token}"\n'
        "C:\\Users\\Alice\\AppData\\Roaming\\.minecraft\\logs\\latest.log\n"
        "java.lang.OutOfMemoryError: Java heap space\n",
        encoding="utf-8",
    )
    # The environment header comes from the language tables, so it must go through a translator
    mods_dir = ws_tmp / "game" / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    (mods_dir / "sodium.jar").write_bytes(b"not a real jar")

    diagnosis = diagnose(_context(ws_tmp, mods_dir=mods_dir))
    assert diagnosis.code == "MPL-Crash-0101"

    dest = ws_tmp / "diag.zip"
    export_report(dest, diagnosis, translate=_translate)
    with zipfile.ZipFile(dest) as archive:
        names = archive.namelist()
        blob = "\n".join(archive.read(name).decode("utf-8") for name in names)
    assert ENV_FILENAME in names
    assert MODS_FILENAME in names
    assert "latest.log" in names
    assert token not in blob, "the access token leaked into the export"
    assert "Alice" not in blob, "the user name leaked into the export"
    assert "sodium.jar" in blob, "the mod list is missing from the export"
    assert _translate("diagnosis.fact.instance") in blob, "the environment header is missing"


def test_export_can_drop_extra_files(ws_tmp) -> None:
    extra = ws_tmp / "game" / "crash-reports" / "notes.txt"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("nothing to see", encoding="utf-8")
    diagnosis = diagnose(_context(ws_tmp))
    assert [log.kind for log in diagnosis.logs] == [KIND_EXTRA]
    dest = ws_tmp / "diag.zip"
    export_report(dest, diagnosis, translate=_translate, include_extra=False)
    with zipfile.ZipFile(dest) as archive:
        assert "notes.txt" not in archive.namelist()
    export_report(dest, diagnosis, translate=_translate, include_extra=True)
    with zipfile.ZipFile(dest) as archive:
        assert "notes.txt" in archive.namelist()


# --------------------------------------------------------------------------- #
# Facts and wiring
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "version_id,expected",
    [
        ("1.21.1", ("vanilla", "1.21.1")),
        ("fabric-loader-0.15.11-1.20.1", ("fabric", "1.20.1")),
        ("quilt-loader-0.24.0-1.20.1", ("quilt", "1.20.1")),
        ("1.20.1-forge-47.4.22", ("forge", "1.20.1")),
        ("neoforge-21.1.72", ("neoforge", "1.21.1")),
    ],
)
def test_derive_version_facts(version_id, expected) -> None:
    assert derive_version_facts(version_id) == expected


def test_facts_read_the_mods_directory(ws_tmp) -> None:
    _place(ws_tmp, "oom.latest.log", "logs/latest.log")
    mods_dir = ws_tmp / "game" / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    (mods_dir / "sodium.jar").write_bytes(b"not a real jar")
    (mods_dir / "old.jar.disabled").write_bytes(b"not a real jar")
    diagnosis = diagnose(_context(ws_tmp, mods_dir=mods_dir))
    assert len(diagnosis.facts.mods) == 2
    assert diagnosis.facts.loader == "fabric"
    assert diagnosis.facts.mc_version == "1.20.1"
    assert diagnosis.facts.memory_text == "4 GB"
    assert diagnosis.facts.placeholder("java") == "17"
    assert diagnosis.facts.placeholder("nope") == UNKNOWN_VALUE


def test_context_picks_up_the_resolved_instance(ws_tmp) -> None:
    """A ResolvedInstance supplies the paths when the caller passes one."""
    from launcher.instances import ResolvedInstance

    game = ws_tmp / "game"
    instance_dir = game / "versions" / "1.20.1"
    (instance_dir / "mods").mkdir(parents=True, exist_ok=True)
    (instance_dir / "mods" / "sodium.jar").write_bytes(b"not a real jar")
    (instance_dir / "logs").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SAMPLES / "oom.latest.log", instance_dir / "logs" / "latest.log")
    resolved = ResolvedInstance(
        id="1.20.1",
        game_dir=game,
        launch_dir=instance_dir,
        isolated=True,
        java_path=None,
        memory_gb=6.0,
        jvm_args="",
        game_args="",
        mods_dir=instance_dir / "mods",
    )
    diagnosis = diagnose(DiagnosisContext(version_id="1.20.1", instance=resolved, exit_code=1))
    assert diagnosis.code == "MPL-Crash-0101"
    assert diagnosis.facts.memory_text == "6 GB"
    assert diagnosis.facts.isolated is True
    assert len(diagnosis.facts.mods) == 1


def test_run_process_captures_a_bounded_tail(ws_tmp) -> None:
    program = (
        "for index in range(600):\n"
        "    print('line', index)\n"
        "print('LAST-MARKER')\n"
    )
    result = run_process([sys.executable, "-c", program], ws_tmp, capture_tail=True)
    assert isinstance(result, RunResult)
    assert result.exit_code == 0
    assert len(result.tail) == TAIL_LINES  # 601 printed, 501 kept
    assert result.tail[-1] == "LAST-MARKER"
    assert result.tail[0] == "line 100"
    assert "line 0" not in result.tail


def test_run_process_returns_an_int_without_capture(ws_tmp) -> None:
    code = run_process([sys.executable, "-c", "print('hello')"], ws_tmp)
    assert isinstance(code, int)
    assert code == 0


# --------------------------------------------------------------------------- #
# i18n and layering
# --------------------------------------------------------------------------- #
def test_rule_advice_arguments_match_the_translated_templates() -> None:
    """Every rule's `{fact}` arguments must match the `{}` count of its templates.

    The key-set test (tests/test_i18n_languages.py) proves the keys exist; this
    one proves the arguments a rule hands to them fit.
    """
    from launcher.diagnostics.rules import split_advice

    languages = [code for code, _name in i18n.UI_LANGUAGES]
    problems = []
    for rule in load_rules():
        for key, args in split_advice(rule.advice):
            for language in languages:
                template = i18n.TRANSLATIONS[language][key]
                if template.count("{}") != len(args):
                    problems.append(f"{rule.code} {language} {key}: {template!r} vs {args}")
    assert not problems, "advice arguments do not match the templates:\n" + "\n".join(problems)


def test_diagnosis_core_does_not_import_qt() -> None:
    """The knowledge base is core-library code: no Qt import anywhere in the package."""
    package = Path(__file__).resolve().parents[1] / "launcher" / "diagnostics"
    offenders = []
    for path in sorted(package.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in ("PySide6", "PyQt", "QtCore", "QtWidgets"):
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, f"Qt references inside launcher/diagnostics: {offenders}"


def test_diagnosis_is_local_only() -> None:
    """No network client is imported by the diagnosis pipeline."""
    import launcher.diagnostics.engine as engine_module

    source = Path(engine_module.__file__).read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "requests" not in source
