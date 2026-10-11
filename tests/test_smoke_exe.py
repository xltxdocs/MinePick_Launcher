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

"""Smoke-rig tests: `tools/smoke_exe.py` must tell a good run from a bad one.

The rig under test exists to run a *packaged* EXE, which no unit test can do, so the tested command
is injectable (``--exe`` plus ``--arg``, or ``--command``) and these tests drive it with a stand-in
script that behaves like the packaged application from the outside: it writes the same startup
evidence into ``MCLAUNCHER_DATA_DIR``, unpacks a ``_MEI*`` folder into ``TEMP``, and then either
leaves on its own or does not.

That makes every verdict the rig publishes testable, and each test below pins one of them:

* a cooperative command -> PASS and exit code 0;
* a command that does not exist -> FAIL and exit code 1 (a rig that cannot report a missing EXE
  cannot be trusted to report a broken one);
* a command that comes up but never leaves -> FAIL, and the report must say the end was forced;
* a command that ignores the data directory override -> FAIL, because readiness is evidence-based
  and not a sleep;
* the negative control (``--expect-fail-demo``) inverts the verdict instead of passing anyway.

No test here starts a real window: the stand-in is a console interpreter launched with
``CREATE_NO_WINDOW``, and the offscreen platform variable is asserted by the rig itself.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import smoke_exe

# Outside the checkout and outside tests/.work: these runs launch processes and write scratch trees,
# and the user may be running the rest of the suite at the same time.
SCRATCH = ROOT.parent / "tmp"
TEMP_DIR = SCRATCH / "smoke_test_tmp"
DATA_DIR = SCRATCH / "smoke_test_data"

# Stands in for the packaged EXE: same observable behaviour, none of the 68 MB.
STAND_IN = '''
import json
import os
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else "cooperative"
data = Path(os.environ["MCLAUNCHER_DATA_DIR"])
if mode == "ignores-data-dir":
    data = Path(os.environ["TEMP"]) / "elsewhere"
(data / "logs").mkdir(parents=True, exist_ok=True)
(data / "logs" / "launcher.log").write_text("", encoding="utf-8")
(data / "config.json").write_text(json.dumps({"started": True}), encoding="utf-8")
# A real unpack fills its folder; an empty one is what a refused unpack leaves behind.
mei = Path(os.environ["TEMP"], "_MEI4242")
mei.mkdir(exist_ok=True)
(mei / "base_library.zip").write_bytes(b"stand-in payload")
if mode == "never-exits":
    time.sleep(300)
sys.exit(0)
'''


@pytest.fixture()
def stand_in():
    """The stand-in command as `smoke_exe.py` would receive it: interpreter plus script."""
    SCRATCH.mkdir(exist_ok=True)
    script = SCRATCH / "smoke_stand_in.py"
    script.write_text(STAND_IN, encoding="utf-8")
    return script


def run_rig(stand_in: Path, mode: str = "cooperative", *extra: str) -> int:
    return smoke_exe.main(
        [
            "--exe", sys.executable,
            "--arg", str(stand_in),
            "--arg", mode,
            "--temp-dir", str(TEMP_DIR),
            "--data-dir", str(DATA_DIR),
            "--poll", "0.1",
            "--timeout", "30",
            "--exit-timeout", "15",
            *extra,
        ]
    )


def test_a_cooperative_command_passes(stand_in, capsys):
    """Evidence appears, the process leaves by itself with code 0: PASS and exit code 0."""
    assert run_rig(stand_in) == 0
    out = capsys.readouterr().out
    assert "PASS: tools/smoke_exe.py" in out
    assert "clean_self_exit" in out
    assert "_MEI4242" in out, "the extraction evidence must name the folder that actually appeared"
    # The data directory holds both startup markers the real application writes.
    assert (DATA_DIR / "logs" / "launcher.log").is_file()
    assert (DATA_DIR / "config.json").is_file()


def test_a_missing_command_fails_with_exit_code_1(stand_in, capsys):
    """A rig that cannot report a missing EXE cannot be trusted to report a broken one."""
    assert smoke_exe.main(
        ["--exe", str(SCRATCH / "_no_such_command_.exe"), "--temp-dir", str(TEMP_DIR),
         "--data-dir", str(DATA_DIR)]
    ) == 1
    out = capsys.readouterr().out
    assert "FAIL: tools/smoke_exe.py" in out
    assert "does not exist" in out


def test_a_command_that_never_exits_fails_and_is_reported_as_forced(stand_in, capsys):
    """Readiness alone is not a pass: a process that has to be killed did not exit cleanly."""
    assert run_rig(stand_in, "never-exits", "--exit-timeout", "2") == 1
    out = capsys.readouterr().out
    assert "FAIL: tools/smoke_exe.py" in out
    assert "clean_self_exit" in out
    assert "forced termination - NOT a clean exit" in out
    # The startup half still worked, so only the exit half may be reported as a failure.
    assert "data_dir_startup_evidence" in out and "no_early_exit" in out
    assert "no _MEI* folder seen" not in out


def test_ignoring_the_data_dir_override_fails(stand_in, capsys):
    """Startup evidence is polled in MCLAUNCHER_DATA_DIR, so a wrong data dir cannot pass by luck."""
    assert run_rig(stand_in, "ignores-data-dir", "--timeout", "3", "--exit-timeout", "2") == 1
    out = capsys.readouterr().out
    assert "FAIL: tools/smoke_exe.py" in out
    assert "data_dir_startup_evidence" in out


def test_terminate_mode_reports_the_forced_end_as_not_applicable(stand_in, capsys):
    """--exit-mode terminate cannot claim a clean exit; it says so instead of guessing."""
    assert run_rig(stand_in, "never-exits", "--exit-mode", "terminate", "--timeout", "30") == 0
    out = capsys.readouterr().out
    assert "PASS: tools/smoke_exe.py" in out
    assert "not applicable: --exit-mode terminate forced the end" in out
    assert "forced termination - NOT a clean exit" in out


def test_the_negative_control_inverts_the_verdict(stand_in, capsys):
    """A defect that must break the smoke has to break it - and the command then reports success."""
    assert smoke_exe.main(
        ["--expect-fail-demo", "missing-exe", "--temp-dir", str(TEMP_DIR),
         "--data-dir", str(DATA_DIR)]
    ) == 0
    out = capsys.readouterr().out
    assert "NEGATIVE CONTROL PASSED" in out


def test_removing_the_offscreen_variable_is_refused_before_anything_starts(stand_in, capsys):
    """The no-window guarantee is enforced, not hoped for: no process may start without it."""
    assert smoke_exe.main(
        ["--expect-fail-demo", "no-offscreen-env", "--temp-dir", str(TEMP_DIR),
         "--data-dir", str(DATA_DIR)]
    ) == 0
    out = capsys.readouterr().out
    assert "refusing to launch" in out
    assert "NEGATIVE CONTROL PASSED" in out


def test_a_visible_window_ends_the_run_at_once(stand_in, monkeypatch, capsys):
    """Nothing may sit on the user's desktop for the length of a timeout: one window ends the run.

    The window is injected rather than created - the point under test is the abort, and a real
    message box would be exactly the thing this rig exists to keep off the screen.
    """
    monkeypatch.setattr(smoke_exe, "visible_windows", lambda pid: ["Error"])
    started = time.monotonic()
    assert run_rig(stand_in, "never-exits", "--timeout", "30") == 1
    elapsed = time.monotonic() - started
    out = capsys.readouterr().out
    assert "a visible window appeared" in out
    assert "'Error'" in out
    assert "visible_windows_zero" in out
    assert elapsed < 15, f"the run waited {elapsed:.1f}s instead of aborting at the first window"


def test_the_bad_data_dir_demo_fails(stand_in, capsys):
    """A data directory that cannot exist is a defect the rig must not be able to shrug off."""
    assert smoke_exe.main(
        ["--exe", sys.executable, "--arg", str(stand_in), "--arg", "cooperative",
         "--expect-fail-demo", "bad-data-dir",
         "--temp-dir", str(TEMP_DIR), "--data-dir", str(DATA_DIR),
         "--poll", "0.1", "--timeout", "20", "--exit-timeout", "5"]
    ) == 0
    out = capsys.readouterr().out
    assert "pointed under a regular file" in out
    assert "NEGATIVE CONTROL PASSED" in out


def _with_measured_facts(label, restricted):
    """Run a block with the two preflight inputs injected; restore them afterwards."""

    class _Patch:
        def __enter__(self):
            self.saved = (smoke_exe.mandatory_label, smoke_exe.restricted_sid_count)
            smoke_exe.mandatory_label = lambda path: label
            smoke_exe.restricted_sid_count = lambda: restricted

        def __exit__(self, *exc):
            smoke_exe.mandatory_label, smoke_exe.restricted_sid_count = self.saved
            return False

    return _Patch()


def test_the_preflight_refuses_a_low_integrity_exe_in_a_restricted_session(stand_in, capsys):
    """The combination that cannot unpack must be refused before anything is started.

    The two measured facts are injected rather than arranged: a real low-integrity EXE in a real
    restricted session is exactly the run this guard exists to prevent, and it is also the run that
    puts a native message box on screen.
    """
    with _with_measured_facts("low", 4):
        assert run_rig(stand_in, "cooperative") == 2
    out = capsys.readouterr().out
    assert "low-integrity EXE in a sandboxed session" in out
    assert "cannot write its own _MEI directory" in out
    assert "Releases\\ after the user copies it" in out
    assert "[REFUSED]" in out
    # Nothing started: the rig clears both scratch directories before it would have launched, so a
    # stand-in that had run would have left its extraction folder and its config behind.
    assert not list(TEMP_DIR.glob("_MEI*")), "the stand-in ran despite the refusal"
    assert not (DATA_DIR / "config.json").exists(), "the stand-in ran despite the refusal"


def test_the_preflight_opt_out_launches_anyway(stand_in, capsys):
    """--ignore-integrity-preflight is the deliberate way past the refusal, and it is not silent."""
    with _with_measured_facts("low", 4):
        assert run_rig(stand_in, "cooperative", "--ignore-integrity-preflight") == 0
    assert "PASS: tools/smoke_exe.py" in capsys.readouterr().out


def test_the_preflight_lets_a_medium_integrity_target_through(stand_in):
    """A medium copy - the Releases\\ case - must not be refused; that is the run this rig serves."""
    with _with_measured_facts("medium", 4):
        assert run_rig(stand_in, "cooperative") == 0


def test_the_preflight_rule_follows_from_what_this_machine_actually_reports():
    """Read the real facts, launch nothing, and require the rule to follow from them.

    On the machine this was written on that means ``dist\\MinePick_Launcher.exe`` is low and the
    token carries restricting SIDs - so the refusal is a measured outcome, not a hard-coded one. The
    assertion is an implication, so on an unconfined machine, where the same EXE is smokeable, it
    still holds.
    """
    exe = ROOT / "dist" / "MinePick_Launcher.exe"
    if not exe.exists():
        pytest.skip("no packaged EXE to inspect")
    # A reader that cannot answer is not a guard: on Windows this must produce a level, and the
    # refusal message would otherwise advertise "integrity=None" while claiming to have measured it.
    if os.name == "nt":
        assert smoke_exe.process_integrity() in {"untrusted", "low", "medium", "high", "system"}
        assert (smoke_exe.restricted_sid_count() or 0) >= 0
    assert smoke_exe.mandatory_label(exe) in {None, "untrusted", "low", "medium", "high", "system"}
    label = smoke_exe.mandatory_label(exe)
    restricted = smoke_exe.restricted_sid_count() or 0
    defects = smoke_exe.confinement_defects([str(exe)])
    if label == "low" and restricted > 0:
        assert defects, f"label={label}, restricting SIDs={restricted} must be refused"
        assert "low-integrity EXE in a sandboxed session" in defects[0]
        assert "process integrity=None" not in defects[0], "the refusal must report a measured level"
    else:
        assert not defects, f"label={label}, restricting SIDs={restricted} must not be refused"


def test_mandatory_label_never_guesses():
    """The label reader is the guard's only input, so both of its answers must be real ones."""
    assert smoke_exe.mandatory_label(SCRATCH / "_definitely_not_here_.exe") is None
    probe = SCRATCH / "smoke_label_probe.txt"
    probe.write_text("x", encoding="utf-8")
    try:
        assert smoke_exe.mandatory_label(probe) in {None, "low", "medium", "high", "system"}
    finally:
        probe.unlink(missing_ok=True)


# --------------------------------------------------------------------------------------
# units that need no process at all
# --------------------------------------------------------------------------------------
def test_split_command_keeps_windows_backslashes():
    """shlex in POSIX mode would eat them, silently turning a path into a different path."""
    assert smoke_exe.split_command(r'"C:\Program Files\app.exe" --flag') == [
        r"C:\Program Files\app.exe",
        "--flag",
    ]


def test_wipe_guards_refuse_roots_and_the_checkout():
    """A recursive delete must never be pointed at a drive root or at the repository itself."""
    with pytest.raises(smoke_exe.SmokeError):
        smoke_exe.assert_safe_to_wipe(Path(ROOT.anchor))
    with pytest.raises(smoke_exe.SmokeError):
        smoke_exe.assert_safe_to_wipe(ROOT)
    with pytest.raises(smoke_exe.SmokeError):
        smoke_exe.assert_safe_to_wipe(ROOT.parent)
    assert smoke_exe.assert_safe_to_wipe(TEMP_DIR) == TEMP_DIR.resolve()


def test_environment_defects_names_every_broken_guarantee():
    """Each defect is reported with the variable that carries it, so a refusal is actionable."""
    args = argparse.Namespace(exit_mode="autoquit", autoquit_ms=2500)
    good = smoke_exe.child_environment(args, TEMP_DIR, DATA_DIR)
    assert smoke_exe.environment_defects(good, TEMP_DIR, DATA_DIR, "autoquit") == []

    broken = dict(good)
    broken.pop(smoke_exe.ENV_PLATFORM)
    broken.pop("TMP")
    broken[smoke_exe.ENV_DATA_DIR] = str(DATA_DIR / "somewhere_else")
    broken[smoke_exe.ENV_AUTOQUIT] = "0"
    defects = smoke_exe.environment_defects(broken, TEMP_DIR, DATA_DIR, "autoquit")
    assert len(defects) == 4
    assert any(smoke_exe.ENV_PLATFORM in defect for defect in defects)
    assert any("TMP" in defect for defect in defects)
    assert any(smoke_exe.ENV_DATA_DIR in defect for defect in defects)
    assert any(smoke_exe.ENV_AUTOQUIT in defect for defect in defects)
