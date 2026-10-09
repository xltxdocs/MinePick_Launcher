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

"""Release gate: no locally held secret may appear in anything we publish.

`build/cf_key.txt` is gitignored and only ever bundled into the EXE, yet "gitignored" is not a proof:
a key can leak through an earlier commit, through the source zip, or through a README. This audits
four surfaces and exits non-zero on any hit, so the packaging checklist can gate on it.

The secret is read **inside this process** and never passed on a command line, printed, or written
anywhere: the report only ever contains counts and `file:line`.

Usage:
    python tools/audit_secret_leak.py [--file build/cf_key.txt] [--zip dist/Source_code.zip]
"""

from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_PATTERNS = ("README*.md", "docs/*.md", "THIRD_PARTY_NOTICES.md")
MAX_ZIP_ENTRY_BYTES = 4_000_000


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def _lines_containing(blob: bytes, needle: bytes) -> list[int]:
    if not needle:
        return []
    return [n for n, line in enumerate(blob.splitlines(), 1) if needle in line]


def audit(secret_file: Path, zip_path: Path) -> list[str]:
    findings: list[str] = []
    if not secret_file.is_file():
        print(f"secret file not found: {secret_file} (nothing to audit)")
        return findings
    needle = secret_file.read_text(encoding="utf-8", errors="replace").strip().encode("utf-8")
    print(f"secret file: {secret_file.name} ({len(needle)} bytes; value never printed)")

    print("\n1) tracked files")
    tracked = [line for line in _git("ls-files").splitlines() if line.strip()]
    hits = 0
    for name in tracked:
        path = ROOT / name
        if not path.is_file():
            continue
        for line in _lines_containing(path.read_bytes(), needle):
            hits += 1
            findings.append(f"working tree hit: {name}:{line}")
            print(f"   HIT {name}:{line}")
    print(f"   {len(tracked)} files checked, {hits} hit(s)")

    print("\n2) git history (pickaxe -S: commits that added or removed the value)")
    history = _git("log", "--all", "--oneline", "-S", needle.decode("utf-8", "replace"))
    commits = [line for line in history.splitlines() if line.strip()]
    for line in commits:
        findings.append(f"git history hit: {line}")
        print(f"   HIT {line}")
    print(f"   {len(commits)} commit(s)")

    print("\n3) source zip")
    if zip_path.is_file():
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            name_hits = [n for n in names if "cf_key" in n.lower()]
            content_hits: list[str] = []
            for info in archive.infolist():
                if info.is_dir() or info.file_size > MAX_ZIP_ENTRY_BYTES:
                    continue
                if needle and needle in archive.read(info):
                    content_hits.append(info.filename)
        for name in name_hits:
            findings.append(f"source zip entry name: {name}")
            print(f"   HIT name {name}")
        for name in content_hits:
            findings.append(f"source zip content: {name}")
            print(f"   HIT content {name}")
        print(f"   {len(names)} entries, {len(name_hits)} name hit(s), {len(content_hits)} content hit(s)")
    else:
        print(f"   no zip at {zip_path} (skipped)")

    print("\n4) shipped documents")
    docs: list[Path] = []
    for pattern in DOC_PATTERNS:
        docs.extend(sorted(ROOT.glob(pattern)))
    doc_hits = [str(p.relative_to(ROOT)) for p in docs if needle and needle in p.read_bytes()]
    for name in doc_hits:
        findings.append(f"document hit: {name}")
        print(f"   HIT {name}")
    print(f"   {len(docs)} files checked, {len(doc_hits)} hit(s)")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", default="build/cf_key.txt", help="secret file to look for")
    parser.add_argument("--zip", default="dist/Source_code.zip", help="published source archive")
    args = parser.parse_args()

    findings = audit(ROOT / args.file, ROOT / args.zip)
    print()
    if findings:
        print(f"FAIL: {len(findings)} leak finding(s) - rotate the key and re-issue the secret file")
        return 1
    print("OK: the secret appears on none of the four surfaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
