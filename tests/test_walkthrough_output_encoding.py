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

"""The walkthrough must survive printing an interface language that is not ASCII.

The defect this pins (2026-10-17): ``tools/keyboard_walkthrough.py`` printed its per-stop lines - the
interface's own text - to a Python stdout that defaults to the OEM code page when it is redirected
(GBK on the Chinese Windows this was found on). The run had *already written the complete report* when
``print("  UNMEASURED ... Instanzen suchen ...")`` raised ``UnicodeEncodeError: 'gbk' codec can't
encode character '\\xf6'``, so the tool exited 1 with a valid report on disk. ``tests/test_keyboard_focus.py``
runs it as a subprocess and asserts on the exit code, which is how one non-ASCII language in the shared
preview profile turned into three ERRORs on an otherwise green suite.

Why a second walkthrough instead of a cheaper probe: the failing line only exists once the real window
has been built and walked in a non-ASCII language, so there is nothing smaller to assert on without
mocking the very thing under test. One extra run costs about 20s of the suite.

The umlaut is the assertion, not decoration: ``subprocess`` decodes this tool's output as UTF-8, so a
byte that arrives in the OEM code page still fails here even on a machine whose console happens to be
UTF-8 (where the crash itself would stay hidden). ``öffnen`` is the German label of two of the stops
(``Link öffnen`` on the about page, ``Datenverzeichnis öffnen`` in the settings) and is printed only
after the German ``Instanzen suchen`` line that used to kill the run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
# A fixed ordinary directory, not a random-suffix one: the workspace sandbox locks writes inside
# mkdtemp-style paths, which is why the suite's conftest offers ws_tmp and why tests/test_keyboard_focus.py
# writes its report under tmp/ as well.
OUT_DIR = ROOT.parent / "tmp" / "kb_guard"
TIMEOUT_S = 900  # the guard in tests/test_keyboard_focus.py uses the same ceiling


def _german_preview(preview: Path) -> Path:
    """An isolated preview tree whose launcher profile is set to German.

    ``--preview`` is what makes this isolated: the tool calls ``shot_pages.ensure_preview`` with it and
    keeps the app's data dir there, so the repository's own ``_preview`` profile is never read (and the
    gate cannot depend on whichever language a previous render job left in it).
    """
    data_dir = preview / "_preview" / "data"  # ensure_preview's layout inside the --preview root
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "config.json").write_text(
        json.dumps({"ui_language": "de_de", "wizard_done": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return data_dir


def test_a_non_ascii_interface_language_prints_and_exits_zero(ws_tmp):
    """German interface text must reach stdout as UTF-8 and exit 0 (it was exit 1 before the fix)."""
    _german_preview(ws_tmp)
    report = OUT_DIR / "kb_encoding_de.md"
    proc = subprocess.run(
        [
            PYTHON,
            str(ROOT / "tools" / "keyboard_walkthrough.py"),
            "--root",
            str(ROOT),
            "--out",
            str(report),
            "--preview",
            str(ws_tmp),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=TIMEOUT_S,
        check=False,
    )
    stdout = proc.stdout
    assert proc.returncode == 0, f"{stdout[-2000:]}\n{proc.stderr[-2000:]}"
    # The run really was German: without this the umlaut assertion below could pass on an English run.
    assert "Instanzen suchen" in stdout, f"the German profile was not used:\n{stdout[-2000:]}"
    assert "öffnen" in stdout, (
        "the umlaut did not survive the tool's stdout - its output is still in the console code page, "
        f"which the caller decodes as UTF-8:\n{stdout[-2000:]}"
    )
