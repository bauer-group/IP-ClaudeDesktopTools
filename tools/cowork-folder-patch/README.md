# Cowork Folder Bypass

Umgeht die Home-Directory-Einschraenkung im Claude Desktop Cowork Folder-Picker. Ermoeglicht Netzlaufwerke, externe Laufwerke und domaeneumgeleitete Ordner.

## Problem

Claude Desktop Cowork erlaubt im Folder-Picker nur Ordner innerhalb von `%USERPROFILE%`. In Domaenenumgebungen mit Ordnerumleitung, bei Netzlaufwerken oder externen Datentraegern schlaegt die Auswahl fehl.

## Technik (v5.0 – Config-basierter Bypass)

Die Ordner-Restriktion existiert **ausschliesslich** in der UI-Funktion `browseFolder` (Electron Main Process). Alle nachgelagerten Systeme akzeptieren beliebige Pfade ohne eigene Validierung:

| Komponente | Validierung |
|-----------|------------|
| `browseFolder` (UI) | Home-Dir-Check via `path.relative` + `startsWith("..")` |
| `addFolderToSpace` | Keine – fuegt Pfad direkt hinzu |
| `loadSpacesFromDisk` | Nur Schema-Validierung (Feldtypen) |
| `startSession` | Akzeptiert `userSelectedFolders` direkt |
| `SY` (Datei-Zugriff) | Prueft gegen `userSelectedFolders`, nicht gegen Home-Dir |

**Bypass-Strategie:** Ordnerpfade direkt in `spaces.json` und `localAgentModeTrustedFolders` schreiben. Die UI-Sperre (`browseFolder`) wird nie aufgerufen, da der Ordner bereits im Space vorhanden ist.

### Aeltere Versionen (v1–v4) – Nicht mehr verwendet

Die frueheren Versionen versuchten Binary-Patching (ASAR-Injection + Hash-Ersetzung in `claude.exe`). Dieser Ansatz scheitert, weil jede Aenderung an `claude.exe` die Authenticode-Signatur bricht und `cowork-svc.exe` den Start verweigert.

## Voraussetzungen

- Windows 10/11 mit Claude Desktop
- Python 3.8+
- **Keine** Administrator-Rechte noetig
- **Kein** Node.js noetig

## Schnellstart (One-Click)

PowerShell oeffnen und ausfuehren:

```powershell
irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/cowork-folder-patch/run.ps1 | iex
```

Der Launcher bietet ein interaktives Menue zum Hinzufuegen und Entfernen von Ordnern.

## Manuelle Verwendung

```bash
# Externe Ordner hinzufuegen
python patch_cowork_folders.py add "C:\Projects" "D:\Data"

# Netzlaufwerk hinzufuegen
python patch_cowork_folders.py add "\\server\share"

# Ordner entfernen
python patch_cowork_folders.py remove "C:\Projects"

# Aktuelle Ordner anzeigen
python patch_cowork_folders.py list

# System-Status pruefen
python patch_cowork_folders.py status
```

## Nach der Installation

1. **Claude Desktop neu starten**
2. In Cowork den Space **"External Folders"** auswaehlen
3. Die externen Ordner sind im Space verfuegbar

## Nach Claude-Updates

Der Bypass bleibt bestehen, da keine Binaries modifiziert werden. Die Konfiguration in `spaces.json` und `claude_desktop_config.json` ueberlebt Updates.

## Was wird geaendert?

| Datei | Aenderung |
|-------|----------|
| `%APPDATA%\Claude\claude_desktop_config.json` | Ordner in `preferences.localAgentModeTrustedFolders` eingetragen |
| `%APPDATA%\Claude\local-agent-mode-sessions\{accountId}\{userId}\spaces.json` | Space "External Folders" mit den Ordnern erstellt |

## Disclaimer

Dieses Tool modifiziert Claude Desktop Konfigurationsdateien auf nicht von Anthropic autorisierte Weise. Nutzung auf eigenes Risiko.

## Referenzen

- GitHub Issues [#20550](https://github.com/anthropics/claude-code/issues/20550), [#24964](https://github.com/anthropics/claude-code/issues/24964) – Dokumentation der Validierungsfunktion
