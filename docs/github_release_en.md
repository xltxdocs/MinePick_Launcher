[简体中文](github_release.md) | English

# Publishing to GitHub (MinePick Launcher)

> This document is also available in [Simplified Chinese](github_release.md).

This repository is **MinePick Launcher**: remote `https://github.com/xltxdocs/MinePick_Launcher.git`, branch `main`, current version `0.3.0`.
This line ships a **GUI build only** — there is no CLI executable (no `MinePick_Launcher_cli.exe` is built, and `run_cli.py` is not packaged).
Every command below is run in **CMD** on Windows; the gh CLI is not installed, so the Release is created on the GitHub web page.

## 1. First release (the repository)

1. On the GitHub website → New repository (public or private, your choice), **do not** check the option that generates a README/LICENSE automatically;
2. Push from your local machine:

```cmd
git init
git add .
git commit -m "MinePick Launcher 首个版本"
git branch -M main
git remote add origin https://github.com/xltxdocs/MinePick_Launcher.git
git push -u origin main
```

> Note: build/, dist/, Releases/, .devdata/, tests/.work/ and the like are already excluded by .gitignore;
> the signing private key build/codesign.pfx is on the ignore list too, so **never** upload it.

## 2. Publishing a Release (with built artifacts)

The packaged artifacts are staged first in the repository's `Releases\` folder (that folder is covered by .gitignore, so it is never committed), and are also produced in `dist\`:

- `MinePick_Launcher.exe` (single-file GUI EXE, signed, roughly 65 MB)
- `Source_code.zip` (source code package, for GPL-3.0 compliant distribution, roughly 1 MB)

1. On the GitHub repository page → Releases → Draft a new release, and set the Tag to `v0.3.0` (the current version; the repository already has `v0.1.0`, `v0.1.1`, `v0.1.2`, `v0.1.4`, `v0.1.5`, `v0.2.0`, and the remote carries an extra `v0.1.3`);
2. Drag the two files above into the attachments area;
3. Write the release notes following the convention in section 4, and state:
   - A brief feature overview (see the feature list in the README);
   - A note about portable mode (a config/ folder is generated next to the EXE);
   - A note that the signature is a self-signed certificate (WDNDXLTX), so SmartScreen on other people's computers may warn about an "unknown publisher" — this is expected;
   - License: GPL-3.0.

## 3. Pushing commits and tags (CMD)

The version number lives in `launcher/__init__.py` and `pyproject.toml`; once the changes are committed, push from CMD:

```cmd
cd /d D:\dsh-workspace\Source_code_UI
git push
git push origin v0.3.0
```

> Note: a plain `git push` does **not** push tags, so you must run `git push origin vX.Y.Z` as well, otherwise the Release page cannot select that Tag.

## 4. Release notes convention

Write the English part first, then a single `---` line, then the same content in Chinese; both parts use the same three sections in this order:

```markdown
## ✨ New
## 🔧 Improvements
## 🐛 Fixes

**Omit a section entirely when it has nothing in it** (for example a release with only improvements and fixes carries no ✨ New heading); never invent entries to fill a section.

---

## ✨ 新增
## 🔧 改进
## 🐛 修复
```

Describe only what a user of the **previous released version** could observe; bugs that were introduced and fixed while developing the same version must **not** appear in the release notes.

## 5. GPL-3.0 compliance notes

- The repository root already contains LICENSE (the official full text of GNU GPL v3);
- Distributing the binaries (the EXE in the Release) should be accompanied by the source code; Source_code.zip exists for that purpose;
- If someone asks you for the source code, pointing them to the repository or to Source_code.zip is fine either way.

## 6. Self-check before a release (hard gate)

```powershell
python tools\ui_regression.py --quick        # every check must pass; the list lives in the script
python tools\ui_regression.py --list-checks  # print the current checks
```

- **A change that has not passed the self-check is not finished.** Fix failures until it is green.
- If the unit tests hit the known environment flake (an occasional native crash in a GUI worker
  thread that reproduces on a pristine checkout): **run them once more**; if still not green, run the
  two halves separately (`-k "not java and not locate and not detected"` and
  `-k "java or locate or detected"`). **Termination rule: both halves green → treat as a flake and
  proceed; one half crashes again on its own re-run → treat it as a real failure and do not commit.**
  A commit that only passed after a flake re-run carries the marker `(flake rerun passed)` at the end.
- When packaging, docs or screenshots changed, also **open the artifacts** in `Releases\` and verify
  them (version inside the package, all nine READMEs, screenshot count, no `tests/.work` leftovers,
  per-file sha256, and that this change is really inside).

### Version bump logic (short form)

| Change | Bump |
|---|---|
| Bug fix / polish / wording and i18n fixes / docs | PATCH `+1` |
| Ordinary additions: a small feature, one new option, a local removal | PATCH `+1` |
| **Major feature**: a whole new capability, or a clearly different way of working | MINOR `+1`, PATCH back to 0 |
| Breaking change (incompatible config layout) | allowed in MINOR while `0.x`; MAJOR once at `1.0.0` |
| UI declared final | `1.0.0` |

- **Bump only when a Release is actually cut** — never push the number ahead of time;
- Group a batch of changes into one bump; **tooling and documentation changes do not bump and are not tagged**;
- **When in doubt, choose PATCH**: a late bump can always be added, an early one cannot be taken back;
- Published artifacts are never rewritten: fix and cut the next PATCH;
- When bumping, update `launcher/__init__.py`, `pyproject.toml` and all nine READMEs, commit with the bare
  version as the message, tag it, and rebuild the EXE and the source package.

## 7. Build prerequisites (for packaging)

`python -m PyInstaller build_exe.spec --noconfirm` requires two local resources (neither goes into the repository; both are covered by `.gitignore`):

- `build/cf_key.txt` — the CurseForge API Key bundled into the package (when it is missing, packaging fails with `Unable to find 'build/cf_key.txt'`);
- The code signing certificate `CN=WDNDXLTX` — see `docs/code_signing.md`.

Packaging and signing: `python -m PyInstaller build_exe.spec --noconfirm` → `scripts\sign_exe.ps1`.

Rebuilding the source package: after any change to the READMEs or the docs you must rebuild `Source_code.zip` (it contains `docs/screenshots/` and all README translations):

```cmd
python tools/build_source_zip.py
```
