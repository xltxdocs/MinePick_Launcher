[简体中文](github_release.md) | English

# Publishing to GitHub (MinePick Launcher)

> This document is also available in [Simplified Chinese](github_release.md).

git/gh CLI is not installed on this machine (the current development environment); the procedure below can be run on any machine that has git installed.

## 1. First release (the repository)

1. On the GitHub website → New repository (public or private, your choice), **do not** check the option that generates a README/LICENSE automatically;
2. Push from your local machine:

```powershell
git init
git add .
git commit -m "MinePick Launcher 首个版本"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

> Note: build/, dist/, .devdata/, tests/.work/ and the like are already excluded by .gitignore;
> the signing private key build/codesign.pfx is on the ignore list too, so **never** upload it.

## 2. Publishing a Release (with built artifacts)

The packaged artifacts:
- `dist/MinePick_Launcher.exe` (GUI, signed)
- `dist/MinePick_Launcher_cli.exe` (CLI, signed)
- `Source_code.zip` (source code package, for GPL-3.0 compliant distribution)

1. On the GitHub repository page → Releases → Draft a new release, and set the Tag to `v0.1.0`;
2. Drag the three files above into the attachments area;
3. Suggested release notes:
   - A brief feature overview (see the feature list in the README);
   - A note about portable mode (a config/ folder is generated next to the EXE);
   - A note that the signature is a self-signed certificate (WDNDXLTX), so SmartScreen on other people's computers may warn about an "unknown publisher" — this is expected;
   - License: GPL-3.0.

## 3. GPL-3.0 compliance notes

- The repository root already contains LICENSE (the official full text of GNU GPL v3);
- Distributing the binaries (the EXEs in the Release) should be accompanied by the source code; Source_code.zip exists for that purpose;
- If someone asks you for the source code, pointing them to the repository or to Source_code.zip is fine either way.

## 4. Build prerequisites (for packaging)

`pyinstaller build_exe.spec` requires two local resources (neither goes into the repository; both are covered by `.gitignore`):

- `build/cf_key.txt` — the CurseForge API Key bundled into the package (when it is missing, packaging fails with `Unable to find 'build/cf_key.txt'`);
- The code signing certificate `CN=WDNDXLTX` — see `docs/code_signing.md`.

Packaging and signing: `python -m PyInstaller build_exe.spec --noconfirm` → `scripts\sign_exe.ps1`.
