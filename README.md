[English](README.md) | [简体中文](README_zh.md)

# MinePick Launcher

An open-source Minecraft launcher built with Python + PySide6: online/offline login, version management, Modrinth mods & modpacks, Fabric/Forge/NeoForge loaders, and instance management — packaged as a portable single-file EXE.

> License: **GPL-3.0** (see LICENSE). Release guide: docs/github_release.md.

## Features

### Accounts
- Microsoft login via device code flow (authorization page auto-opens and the code is copied to your clipboard)
- Multi-account management with one-click switching, skin avatars, automatic token refresh
- Optional encrypted token storage (password-protected)

### Versions & Java
- Version list / details / one-click install & uninstall
- Automatic Java matching and download (Adoptium JRE with SHA256 verification), built-in Java manager
- Version isolation: separate saves/mods/config per version

### Launching
- Memory, game language, custom JVM arguments, direct server connect, demo mode
- Live game log tail and a crash-report viewer
- Auto-hide the launcher after the game starts (the game keeps running independently)

### Resources (Modrinth)
- Mod search & install (keyword search, download counts, version/loader selection)
- One-click modpack install (auto loader setup → instance creation → all files + overrides merged)
- Resource packs / shaders, installed-content manager (list / size / delete)

### Loaders & Instances
- Silent Fabric / Forge / NeoForge official installer support
- Instances: create / launch / delete / rename / notes / sorting / import & export

### UI & UX
- Bilingual UI (English / 简体中文, instant switch), dark / light themes
- First-run wizard (language / game directory / memory)
- Download speed limit, resumable downloads, live speed & ETA

## Download & Usage

Get the binaries from the Releases page:
- `MinePick_Launcher.exe` — GUI (double-click to run, no console window)
- `MinePick_Launcher_cli.exe` — CLI (run all commands from a terminal)

Portable mode: a `config/` folder is created next to the EXE on first run; both builds can share it.

CLI examples:
```powershell
MinePick_Launcher_cli.exe login            # Microsoft login
MinePick_Launcher_cli.exe install 1.20.1   # install a version
MinePick_Launcher_cli.exe launch 1.20.1    # launch the game
MinePick_Launcher_cli.exe --help           # list all commands
```

> Note: the EXEs are signed with a self-signed certificate (WDNDXLTX), so SmartScreen on other machines may show "Unknown publisher" — click "More info → Run anyway".

## Development

```powershell
pip install -r requirements-dev.txt
python -m gui                # run the GUI
python -m launcher --help    # run the CLI
pytest -q                    # tests (160+)
ruff check launcher gui tests
```

Build & sign: `pyinstaller build_exe.spec` → `scripts/sign_exe.ps1` (see docs/code_signing.md).

## License

GPL-3.0, see LICENSE.
