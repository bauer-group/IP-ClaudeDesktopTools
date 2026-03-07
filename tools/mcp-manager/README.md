# MCP Server Manager

Verwaltet Legacy MCP Server in Claude Desktop (`claude_desktop_config.json`). Die neueren "Claude Extensions" haben bereits eine eigene UI in Claude Desktop - dieses Tool ist fuer die manuell konfigurierten MCP Server unter `mcpServers`.

## Was es tut

- MCP Server anzeigen, hinzufuegen, entfernen
- Server testen (MCP Protokoll-Initialisierung pruefen)
- Server-Konfigurationen exportieren und importieren (Team-Sharing)
- Secrets werden automatisch maskiert

## Voraussetzungen

- Windows 10/11 mit Claude Desktop
- Python 3.8+
- Keine Administrator-Rechte noetig

## Benutzung

```bash
python mcp_manager.py list                          # Alle Server anzeigen
python mcp_manager.py add MyServer                  # Neuen Server hinzufuegen (Wizard)
python mcp_manager.py remove MyServer               # Server entfernen
python mcp_manager.py test MyServer                 # Server testen
python mcp_manager.py export MyServer               # Config exportieren
python mcp_manager.py export MyServer --include-secrets  # Mit Secrets
python mcp_manager.py import mcp-server_MyServer.json    # Config importieren
```

## Export/Import

Ermoeglicht das Teilen von MCP Server-Konfigurationen im Team:

- `export` erstellt eine JSON-Datei mit der Server-Konfiguration
- Secrets (Tokens, Keys) werden per Default als `<REDACTED>` maskiert
- `--include-secrets` exportiert die echten Werte
- `import` liest die JSON-Datei und fuegt den Server zur Config hinzu
- Bei maskierten Secrets wird gewarnt, dass diese manuell ergaenzt werden muessen

## Server testen

`test` startet den MCP Server-Prozess und sendet einen JSON-RPC Initialize-Request. Geprueft wird:

1. Befehl im PATH vorhanden
2. Prozess startet erfolgreich
3. MCP Protokoll-Antwort erhalten (innerhalb 10 Sekunden)

## Was wird geaendert

| Datei | Aenderung |
| --- | --- |
| `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers`-Eintraege hinzufuegen/entfernen |

Alle anderen Config-Keys (Preferences, Extensions, etc.) bleiben unberuehrt.

## Disclaimer

Dieses Tool modifiziert Claude Desktop Konfigurationsdateien auf nicht von Anthropic autorisierte Weise. Nutzung auf eigenes Risiko.
