# IP-ClaudeDesktopTools

Interne Werkzeuge fuer Claude Desktop. Jedes Tool liegt in einem eigenen Unterordner unter `tools/`.

## Tools

| Tool                        | Beschreibung                                                                 | Pfad                                                        |
|-----------------------------|------------------------------------------------------------------------------|-------------------------------------------------------------|
| **Cowork Folder Bypass**    | Ermoeglicht externe Ordner im Cowork Folder-Picker per DevTools + JS-Snippet | [`tools/cowork-folder-patch/`](tools/cowork-folder-patch/)  |
| **MCP Server Manager**      | Legacy MCP Server verwalten (anzeigen, hinzufuegen, testen, exportieren)     | [`tools/mcp-manager/`](tools/mcp-manager/)                  |
| **Config Backup & Restore** | Backup/Restore von Claude Desktop & Code Konfigurationen                     | [`tools/config-sync/`](tools/config-sync/)                  |

## Schnellstart

Jedes Tool per PowerShell-Einzeiler oder lokal starten:

```powershell
# Cowork Folder Bypass
irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/cowork-folder-patch/run.ps1 | iex

# MCP Server Manager
irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/mcp-manager/run.ps1 | iex

# Config Backup & Restore
irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/config-sync/run.ps1 | iex
```

Oder lokal:

```bash
python tools/mcp-manager/mcp_manager.py list
python tools/config-sync/config_sync.py backup
python tools/cowork-folder-patch/patch_cowork_folders.py install
```

## Voraussetzungen

- Windows 10/11
- Python 3.8+

Einzelne Tools koennen weitere Abhaengigkeiten haben - siehe jeweilige README.

## Neues Tool hinzufuegen

1. Ordner unter `tools/<tool-name>/` anlegen
2. Tool-Code und eigene `README.md` dort ablegen
3. Tabelle oben in dieser README ergaenzen

## Disclaimer

Diese Tools modifizieren Claude Desktop Konfigurationsdateien auf nicht von Anthropic autorisierte Weise. Nutzung auf eigenes Risiko.
