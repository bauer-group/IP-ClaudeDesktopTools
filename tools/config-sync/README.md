# Config Backup & Restore

Sichert und stellt Konfigurationen von Claude Desktop und Claude Code wieder her. Ermoeglicht schnelle Wiederherstellung nach Updates, Neuinstallationen oder Maschinenwechsel.

## Was es tut

- Backup aller relevanten Config-Dateien als ZIP
- Restore mit automatischem Pre-Restore-Backup
- Diff: zeigt Aenderungen seit einem Backup (Key-by-Key)
- Unterstuetzt Claude Desktop UND Claude Code

## Was gesichert wird

**Claude Desktop** (`%APPDATA%\Claude\`):
- `claude_desktop_config.json` (MCP Server, Preferences)
- `developer_settings.json` (DevTools)
- `config.json` (Locale, Theme - ohne OAuth-Tokens)
- `Claude Extensions Settings\*.json` (Extension-Configs)
- `cowork_settings.json` (Cowork-Plugin-Settings)

**Claude Code** (`~/.claude/`):
- `settings.json` (Permissions, Plugins, Effort Level)
- `settings.local.json` (falls vorhanden)
- `plugins/installed_plugins.json` (Plugin-Liste)
- `plugins/known_marketplaces.json` (Marketplace-Config)
- `projects/*/memory/MEMORY.md` (Projekt-Memories)

**NICHT gesichert**: Credentials, OAuth-Tokens, Logs, Caches, Session Storage, Transcripts.

## Voraussetzungen

- Windows 10/11
- Python 3.8+
- Keine Administrator-Rechte noetig

## Benutzung

```bash
python config_sync.py backup                   # Alles sichern
python config_sync.py backup --desktop-only    # Nur Claude Desktop
python config_sync.py backup --code-only       # Nur Claude Code
python config_sync.py backup --include-secrets # MCP-Secrets nicht maskieren

python config_sync.py list                     # Backups auflisten
python config_sync.py diff <backup>            # Aenderungen anzeigen
python config_sync.py restore <backup>         # Wiederherstellen
python config_sync.py restore <backup> --force # Ohne Bestaetigung
```

## Backup-Details

- **Speicherort**: `%APPDATA%\Claude\config-backups\`
- **Format**: ZIP mit `manifest.json` + Config-Dateien
- **Secrets**: MCP-Server Env-Werte werden per Default als `<REDACTED>` maskiert
- **Restore**: Erstellt automatisch ein Pre-Restore-Backup vor dem Ueberschreiben
- **Diff**: Rekursiver Key-by-Key Vergleich, zeigt hinzugefuegte/entfernte/geaenderte Werte

## Disclaimer

Dieses Tool modifiziert Claude Desktop und Claude Code Konfigurationsdateien. Nutzung auf eigenes Risiko.
