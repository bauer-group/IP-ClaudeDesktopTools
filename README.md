# IP-ClaudeDesktopTools

Interne Werkzeuge fuer Claude Desktop auf Windows. Jedes Tool liegt in einem eigenen Unterordner unter `tools/`.

## Tools

| Tool | Beschreibung | Pfad |
|------|-------------|------|
| **Cowork Folder Patch** | Entfernt die Home-Directory-Einschraenkung im Cowork Folder-Picker | [`tools/cowork-folder-patch/`](tools/cowork-folder-patch/) |

## Schnellstart

Jedes Tool kann direkt aus dem GitHub-Repository per PowerShell-Einzeiler gestartet werden (Administrator-Rechte erforderlich):

**Cowork Folder Patch:**

```powershell
irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/cowork-folder-patch/run.ps1 | iex
```

## Voraussetzungen (allgemein)

- Windows 10/11
- Python 3.8+
- Administrator-Rechte

Einzelne Tools koennen weitere Abhaengigkeiten haben — siehe jeweilige README.

## Neues Tool hinzufuegen

1. Ordner unter `tools/<tool-name>/` anlegen
2. Tool-Code und eigene `README.md` dort ablegen
3. Tabelle oben in dieser README ergaenzen

## Disclaimer

Diese Tools modifizieren Claude Desktop Binaries auf nicht von Anthropic autorisierte Weise. Nutzung auf eigenes Risiko.
