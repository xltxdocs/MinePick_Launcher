[English](README.md) | [简体中文](README_zh.md) | [繁體中文](README_zh_TW.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Русский](README_ru.md) | [Français](README_fr.md) | [Español](README_es.md) | [Deutsch](README_de.md)

# MinePick Launcher — UI Trial

Ein portabler Minecraft-Launcher auf Basis von Python + PySide6: Microsoft-/Offline-Konten, Versionsinstallation,
Modrinth- & CurseForge-Ressourcen, Fabric/Forge/NeoForge/Quilt-Loader, isolierte Instanzen — verpackt als
einzelne portable EXE.

**Dieses Repository ist die Oberflächen-Testlinie (Version 0.1.2).** Sie bietet denselben Funktionsumfang wie das
Hauptprojekt plus die unten beschriebene Oberflächen-Überarbeitung und liefert **nur einen GUI-Build** — eine
Befehlszeilen-EXE gibt es hier nicht.

> Haupt-Launcher: [xltxdocs/MinePick_Launcher](https://github.com/xltxdocs/MinePick_Launcher)

## Screenshots

<table>
  <tr>
    <td><img src="docs/screenshots/launch_en.png" width="480" alt="Startseite"/></td>
    <td><img src="docs/screenshots/versions_en.png" width="480" alt="Versionsseite"/></td>
  </tr>
  <tr>
    <td align="center"><sub>Start</sub></td>
    <td align="center"><sub>Versionen</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/instances_mods_en.png" width="480" alt="Instanzen und lokaler Mod-Manager"/></td>
    <td><img src="docs/screenshots/settings_en.png" width="480" alt="Einstellungen"/></td>
  </tr>
  <tr>
    <td align="center"><sub>Instanzen &amp; lokaler Mod-Manager</sub></td>
    <td align="center"><sub>Einstellungen (Anpassung der Oberfläche)</sub></td>
  </tr>
</table>

## Oberfläche (was diese Testlinie ändert)

- **Assistent beim ersten Start, im Fenster** — der Willkommensablauf ist ein Overlay im Hauptfenster
  (Schrittleiste links, Inhalt rechts, Aktionsleiste unten) statt eines separaten Dialogs und
  blendet sich beim Abschluss aus
- **Eigener Fensterrahmen** — die Titelleiste wird vom Launcher selbst gezeichnet, sodass die
  Fensterdekoration zum Design passt; das Fenstericon ist überall und in jeder Größe das Spitzhacken-Design
- **Anpassbares Aussehen** — Akzentfarbe (beliebiger Hex-Wert, acht Voreinstellungen oder die
  System-Farbauswahl), Schriftart der Oberfläche (alle installierten Familien, die häufigsten oben angeheftet, Tippen
  zum Filtern), Eckenradius (Kompakt / Standard / Rund), Design (Dunkel / Hell / Systemeinstellung folgen)
- **Klareres Layout** — ein Seitenkopf mit einzeiliger Beschreibung auf jeder Seite, ein Markenblock über
  der Seitenleiste, eine gemeinsame Abstandsskala auf allen Seiten, Lupensymbole in Suchfeldern
- **Ruhigeres Verhalten** — Scrollbalken erscheinen nur, solange der Zeiger in einer Liste ist; eine
  Fokusumrandung wird nur bei Tastaturnavigation angezeigt; kurzes Einblenden beim Seitenwechsel;
  Spaltenbreiten von Tabellen werden gemerkt; Kopfzeilen lassen sich per Klick sortieren
- **Klar lesbare Zustände** — Schaltflächen sind abgestuft (primär / sekundär / gefährlich umrandet),
  Statusmeldungen sind nach Schweregrad eingefärbt, leere Listen erklären die nächsten Schritte
- **Standardmäßig barrierefrei** — jedes Text-/Hintergrund-Paar erfüllt den WCAG-AA-Kontrast (Akzentflächen
  mit weißer Schrift werden automatisch abgedunkelt), und die Oberfläche ist in 9 Sprachen verfügbar

## Launcher-Funktionen

### Konten
- Microsoft-Anmeldung per Gerätecode-Ablauf (die Autorisierungsseite öffnet sich automatisch und der Code
  wird in die Zwischenablage kopiert), mit Live-Status der Abfrage
- Offline-Modus, Liste mehrerer Konten mit Ein-Klick-Wechsel, Skin-Avatare, automatische Token-Aktualisierung
- Optionale Token-Verschlüsselung (cryptography Fernet + Passwort, `MCLAUNCHER_TOKEN_PASSWORD` wird unterstützt)

### Versionen & Java
- Offizielles Versions-Manifest mit Kategorie-Tabs (Release / Snapshot / Aprilscherz / Legacy), Karten „Neueste
  Version“ und „Neuester Snapshot“, Namenssuche, Ein-Klick-Installation & -Deinstallation, Versionsdetails
- Versionsisolierung: Jede Version behält ihre eigenen Spielstände / Mods / Konfiguration
- Java-Anforderungszuordnung (1.16.5→8, 1.17–1.20.4→17, 1.20.5–1.21.11→21, 26.1+→25) mit automatischem
  Adoptium-Download und Runtime-Manager

### Start & Instanzen
- Speicherempfehlung anhand Mod-Anzahl und verfügbarem RAM, eigene JVM-Argumente, Server-Direktverbindung,
  Spielsprache, Live-Spielprotokoll, Verhalten „Nach dem Spielstart“, Freigabe des Launcher-Speichers
- Isolierte Instanzen mit Notizen, Umbenennen, Import/Export und einem lokalen Mod-Manager pro Instanz (liest
  Jar-Metadaten für Fabric / Quilt / NeoForge / Forge / mcmod.info, Aktivieren/Deaktivieren, Suchen & Filtern, Drag-and-Drop)

### Ressourcen
- Mods, Ressourcenpakete, Shader und Modpacks von **Modrinth** und **CurseForge**, pro Tab die Top 30 nach
  Downloads, Stichwortsuche (inklusive chinesischer Community-Namen), Ein-Klick-Installation, `.mrpack`-Modpack-Installation

## Download & Verwendung

Laden Sie `MinePick_UI_Trial.exe` von der Releases-Seite herunter und doppelklicken Sie sie — kein Installer,
kein Konsolenfenster. Beim ersten Start wird neben der EXE ein Ordner `config/` angelegt, sodass Einstellungen,
Konten und Instanzen in einem einzigen Ordner bleiben.

Alles wird in der App konfiguriert: **Änderungen wirken sofort, es gibt keinen Speichern-Button.**

> Der Build ist mit einem selbstsignierten Zertifikat (WDNDXLTX) signiert, daher kann SmartScreen auf anderen
> Rechnern vor einem unbekannten Herausgeber warnen — wählen Sie „Weitere Informationen → Trotzdem ausführen“.

## Entwicklung

```powershell
pip install -r requirements-dev.txt
python -m gui                # run the GUI
pytest -q                    # tests (240+)
ruff check launcher gui tests
```

Build & Signieren: `pyinstaller build_exe.spec` → `scripts/sign_exe.ps1` (siehe `docs/code_signing.md`, auf Chinesisch).
Die Spec-Datei erzeugt eine einzelne GUI-EXE (die Build-Voraussetzungen stehen in `docs/github_release.md`, auf Chinesisch).

Oberflächenprüfung mit einem Befehl (Tests + Lint + Kontrast/Überlauf/Hoch-DPI + Eckenradius-Audit + Screenshots):

```powershell
python tools/ui_regression.py            # add --quick to skip the screenshots
```

Design-Interna (Platzhalter, Anpassungs-Hooks, neue Option hinzufügen): `docs/theming.md` (auf Chinesisch).

## Lizenz

GPL-3.0-only — siehe [LICENSE](LICENSE). Das mit jeder Veröffentlichung ausgelieferte Quellcode-Paket (`Source_code.zip`)
erfüllt die Anforderung der GPL zur Quellcode-Verteilung.

## Verwandte Projekte

- [MinePick Launcher](https://github.com/xltxdocs/MinePick_Launcher) — der Haupt-Launcher (GUI + CLI)
- [MinePick Launcher Revision](https://github.com/TheDarkLord234/MinePick_Launcher_Revision) — eine überarbeitete Edition von einem Mitglied der Community
