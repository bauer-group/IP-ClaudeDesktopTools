# Cowork Folder Bypass

Ermoeglicht die Nutzung von Ordnern ausserhalb von `%USERPROFILE%` im Claude Desktop Cowork Folder-Picker (Netzlaufwerke, externe Laufwerke, domaeneumgeleitete Ordner).

## Was es tut

1. Aktiviert DevTools in Claude Desktop (`developer_settings.json`)
2. Zeigt ein JavaScript-Snippet, das den Folder-Picker **ohne** Home-Dir-Restriktion oeffnet

## Einschraenkungen

- **Kein permanenter Patch** - das Snippet muss pro Session in der DevTools-Console ausgefuehrt werden
- Binary-Patching ist nicht moeglich (bricht Authenticode-Signatur)
- Config-Injection via `spaces.json` funktioniert nicht (SpacesManager wird in v1.1.x nie initialisiert)

## Warum dieser Ansatz

Die Ordner-Restriktion existiert **nur** in `browseFolder(title, restrictToHomeDir)` im Electron Main Process. Alle nachgelagerten Systeme (`startSession`, Datei-Zugriff) akzeptieren beliebige Pfade. Ueber die DevTools-Console laesst sich `browseFolder("title", false)` direkt aufrufen.

## Voraussetzungen

- Windows 10/11 mit Claude Desktop
- Python 3.8+
- Keine Administrator-Rechte noetig

## Benutzung

```bash
python patch_cowork_folders.py install     # DevTools aktivieren + Anleitung
python patch_cowork_folders.py restore     # DevTools deaktivieren, aufraumen
python patch_cowork_folders.py status      # Status anzeigen
```

### Ablauf

1. `install` ausfuehren
2. Claude Desktop neu starten
3. DevTools oeffnen (`Ctrl+Shift+I`)
4. Console-Tab waehlen
5. Snippet einfuegen (wird von `install` angezeigt) + Enter
6. Ordner waehlen, in Cowork Nachricht senden

## Was wird geaendert

| Datei | Aenderung |
| --- | --- |
| `%APPDATA%\Claude\developer_settings.json` | `allowDevTools: true` |

Das JS-Snippet schreibt zur Laufzeit `localAgentModeTrustedFolders` in `claude_desktop_config.json` (wird von `restore` aufgeraeumt).

## Disclaimer

Dieses Tool modifiziert Claude Desktop Konfigurationsdateien auf nicht von Anthropic autorisierte Weise. Nutzung auf eigenes Risiko.
