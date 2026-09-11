[English](README.md) | [简体中文](README_zh.md)

# MinePick Launcher — UI Trial

A portable Minecraft launcher built with Python + PySide6: Microsoft/offline accounts, version installation,
Modrinth & CurseForge resources, Fabric/Forge/NeoForge/Quilt loaders, isolated instances — packaged as a
single portable EXE.

**This repository is the interface trial line (version 0.1.0).** It carries the same launcher feature set as the
main project plus the interface rework described below, and it ships a **GUI build only** — there is no CLI
executable here.

> Main launcher: [xltxdocs/MinePick_Launcher](https://github.com/xltxdocs/MinePick_Launcher)

## Screenshots

<table>
  <tr>
    <td><img src="docs/screenshots/launch_en.png" width="480" alt="Launch page"/></td>
    <td><img src="docs/screenshots/versions_en.png" width="480" alt="Versions page"/></td>
  </tr>
  <tr>
    <td align="center"><sub>Launch</sub></td>
    <td align="center"><sub>Versions</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/instances_mods_en.png" width="480" alt="Instances and local mod manager"/></td>
    <td><img src="docs/screenshots/settings_en.png" width="480" alt="Settings"/></td>
  </tr>
  <tr>
    <td align="center"><sub>Instances &amp; local mod manager</sub></td>
    <td align="center"><sub>Settings (interface customisation)</sub></td>
  </tr>
</table>

## Interface (what this line changes)

- **Customisable look** — accent colour (any hex value, eight presets, or the system colour picker),
  UI font (every installed family, common ones pinned, type to filter), corner radius (compact / default /
  round), theme (dark / light / follow the system)
- **Clearer layout** — a page header with a one-line description on every page, a brand block above the
  sidebar, one spacing scale across all pages, magnifier icons in search fields
- **Calmer interaction** — scrollbars appear only while the pointer is inside a list, a focus outline is shown
  for keyboard navigation only, a short fade when switching pages, table column widths are remembered,
  headers are click-to-sort
- **Readable states** — buttons are ranked (primary / secondary / outlined danger), status messages are
  coloured by severity, empty lists explain what to do next
- **Accessible by default** — every text/background pair meets WCAG AA contrast (white-on-accent fills are
  darkened automatically), and the interface is available in 9 languages

## Launcher features

### Accounts
- Microsoft login via device code flow (the authorization page opens automatically and the code is copied to
  the clipboard), with live polling status
- Offline mode, multi-account list with one-click switching, skin avatars, automatic token refresh
- Optional token encryption (cryptography Fernet + password, `MCLAUNCHER_TOKEN_PASSWORD` supported)

### Versions & Java
- Official version manifest with category tabs (release / snapshot / April Fools / legacy), "Latest release"
  and "Latest snapshot" cards, name search, one-click install & uninstall, version details
- Version isolation: each version keeps its own saves / mods / configuration
- Java requirement mapping (1.16.5→8, 1.17–1.20.4→17, 1.20.5–1.21.11→21, 26.1+→25) with automatic Adoptium
  download and a runtime manager

### Launching & instances
- Memory suggestion from mod count and free RAM, custom JVM arguments, server direct-connect, game language,
  live log tail, "after the game starts" behaviour, working-set trimming
- Isolated instances with notes, rename, import/export, and a per-instance local mod manager (reads jar
  metadata for Fabric / Quilt / NeoForge / Forge / mcmod.info, enable/disable, search & filter, drag-and-drop)

### Resources
- Mods, resource packs, shaders and modpacks from **Modrinth** and **CurseForge**, popular top 30 per tab,
  keyword search (Chinese community names included), one-click install, `.mrpack` modpack install

## Download & usage

Grab `MinePick_UI_Trial.exe` from the Releases page and double-click it — no installer, no console window.
On first run a `config/` folder is created next to the EXE, so settings, accounts and instances stay inside
one folder.

Everything is configured inside the app: **settings apply immediately, there is no Save button.**

> The build is signed with a self-signed certificate (WDNDXLTX), so SmartScreen on other machines may warn
> about an unknown publisher — choose "More info → Run anyway".

## Development

```powershell
pip install -r requirements-dev.txt
python -m gui                # run the GUI
pytest -q                    # tests (240+)
ruff check launcher gui tests
```

Build & sign: `pyinstaller build_exe.spec` → `scripts/sign_exe.ps1` (see `docs/code_signing.md`).
The spec expects the bundled CurseForge key at `build/cf_key.txt` (git-ignored) and produces a single GUI EXE.

One-command interface check (tests + lint + contrast/overflow/high-DPI + corner audit + screenshots):

```powershell
python tools/ui_regression.py            # add --quick to skip the screenshots
```

Theme internals (placeholders, customisation hooks, how to add a new option): `docs/theming.md`.

## License

GPL-3.0-only — see [LICENSE](LICENSE). The source package shipped with each release (`Source_code.zip`)
satisfies the GPL source-distribution requirement.

## Related projects

- [MinePick Launcher](https://github.com/xltxdocs/MinePick_Launcher) — the main launcher (GUI + CLI)
- [MinePick Launcher Revision](https://github.com/TheDarkLord234/MinePick_Launcher_Revision) — a revised edition by a fellow community member
