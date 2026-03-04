# Cowork Folder Patch

Entfernt die Home-Directory-Einschraenkung im Claude Desktop Cowork Folder-Picker. Ermoeglicht Netzlaufwerke, externe Laufwerke und domaeneumgeleitete Ordner.

## Problem

Claude Desktop Cowork erlaubt im Folder-Picker nur Ordner innerhalb von `%USERPROFILE%`. In Domaenenumgebungen mit Ordnerumleitung, bei Netzlaufwerken oder externen Datentraegern schlaegt die Auswahl fehl.

## Technik

3-Phasen-Patch basierend auf [shraga100/claude-desktop-rtl-patch](https://github.com/shraga100/claude-desktop-rtl-patch):

| Phase | Aktion | Grund |
|-------|--------|-------|
| 1 - ASAR-Injection | JS-Validierungsfunktion deaktivieren | `path.relative` + `startsWith("..")` blockiert externe Pfade |
| 2 - Hash-Ersetzung | ASAR-Integritaetshash in `claude.exe` aktualisieren | `claude.exe` prueft SHA-256 des ASAR-Headers |
| 3 - Zertifikat-Tausch | Anthropic-Zertifikat in `cowork-svc.exe` ersetzen, beide EXEs neu signieren | `cowork-svc.exe` verifiziert `claude.exe` per eingebettetem X.509-Zertifikat |

## Voraussetzungen

- Windows 10/11 mit Claude Desktop (MSIX oder klassisch)
- Python 3.8+
- Node.js mit npx (fuer `@electron/asar`)
- Administrator-Rechte

## Schnellstart (One-Click)

PowerShell als Administrator oeffnen und ausfuehren:

```powershell
irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/cowork-folder-patch/run.ps1 | iex
```

Der Launcher prueft automatisch Python und Node.js, laedt das Patch-Skript herunter und bietet ein interaktives Menue.

## Manuelle Verwendung

```bash
# Patch installieren
python patch_cowork_folders.py install

# Nur analysieren (keine Aenderungen)
python patch_cowork_folders.py install --dry-run

# Originalzustand wiederherstellen
python patch_cowork_folders.py restore

# Status pruefen
python patch_cowork_folders.py status
```

## Nach Claude-Updates

Jedes Update ueberschreibt die gepatchten Dateien. Einfach erneut `install` ausfuehren.

## Disclaimer

Dieses Tool modifiziert Claude Desktop Binaries auf nicht von Anthropic autorisierte Weise. Nutzung auf eigenes Risiko.

## Referenzen

- [shraga100/claude-desktop-rtl-patch](https://github.com/shraga100/claude-desktop-rtl-patch) - Validierte 3-Phasen-Architektur
- GitHub Issues [#20550](https://github.com/anthropics/claude-code/issues/20550), [#24964](https://github.com/anthropics/claude-code/issues/24964) - Dokumentation der Validierungsfunktion
