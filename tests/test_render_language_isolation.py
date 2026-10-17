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

"""A render must use the language it was asked for, not the one the previous render left behind.

The defect this pins (2026-10-17): ``tools/shot_pages.py`` set the preview data dir, game dir, theme,
accent, font and radius, but never ``ui_language``. ``create_app()`` reads that key from the shared
preview config at startup, so with one ``--preview`` tree a German render left German in
``_preview/data/config.json`` and the next render came out German too, whatever it was supposed to
render. The fix writes the language (and ``wizard_done``, which would otherwise let ``create_app()``
replace it with the system language) before the application is created, and the tool now refuses to
save pictures when the started language is not the requested one.

The test walks one tree through de_de -> zh_cn -> de_de: the second render is the regression (before
the fix it started in de_de), the third is the same check in the other direction. The language is read
from the tool's own ``language <code>`` line, which is printed from ``i18n.current_language()`` inside
the process after ``create_app()`` - not from the config file, because a late write would still leave
the file correct while the window had already been built in the old language.

Cost: three offscreen renders of one page, about 15-20s.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
TIMEOUT_S = 300
LANGUAGE_LINE = re.compile(r"^language ([a-z]{2}_[a-z]{2})$", re.MULTILINE)


def _render(preview: Path, out: Path, language: str) -> tuple[str, dict]:
    """Render one launch page; return the started language and the config the render left behind."""
    proc = subprocess.run(
        [
            PYTHON,
            str(ROOT / "tools" / "shot_pages.py"),
            "--root",
            str(ROOT),
            "--preview",
            str(preview),
            "--out",
            str(out),
            "--label",
            language,
            "--pages",
            "launch",
            "--language",
            language,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_S,
        check=False,
    )
    detail = f"stdout tail:\n{proc.stdout[-2000:]}\nstderr tail:\n{proc.stderr[-2000:]}"
    assert proc.returncode == 0, f"render {language} failed with exit {proc.returncode}\n{detail}"
    match = LANGUAGE_LINE.search(proc.stdout)
    assert match is not None, f"render {language} did not report its language\n{detail}"
    config = json.loads((preview / "_preview" / "data" / "config.json").read_text(encoding="utf-8"))
    return match.group(1), config


def test_consecutive_renders_on_one_tree_use_the_requested_language(ws_tmp):
    """de_de -> zh_cn -> de_de on a shared preview tree: each render reports its own language."""
    preview = ws_tmp / "preview"
    out = ws_tmp / "out"
    renders = [_render(preview, out, language) for language in ("de_de", "zh_cn", "de_de")]
    actual = [language for language, _config in renders]
    second_config = renders[1][1]
    assert actual == ["de_de", "zh_cn", "de_de"], (
        "a render used the previous render's language instead of the one it was given "
        f"(got {actual}, preview config says ui_language={second_config.get('ui_language')!r}, "
        f"wizard_done={second_config.get('wizard_done')!r})"
    )
    # The settings page displays game_language too: the first render must not pin it for the others.
    assert second_config["game_language"] == "zh_cn"
    assert second_config["ui_language"] == "zh_cn"
    # The last render's own language is what the shared preview config must end on. A config value
    # that disagrees would mean the next process starts somewhere else again.
    final_config = renders[2][1]
    assert final_config["ui_language"] == "de_de"
    assert final_config["game_language"] == "de_de"
