#!/usr/bin/env python3
"""
Claude Config Backup & Restore v1.0

Sichert und stellt Konfigurationen von Claude Desktop und Claude Code
wieder her. Unterstuetzt Backup, Restore, Diff und Auflistung.

Gesichert werden:
  Claude Desktop: claude_desktop_config.json, developer_settings.json,
    config.json, Extension-Settings, Cowork-Settings
  Claude Code: settings.json, Plugin-Config, Projekt-Memories

NICHT gesichert: Credentials, OAuth-Tokens, Logs, Caches, Transcripts.

Usage:
  python config_sync.py backup [--desktop-only] [--code-only] [--include-secrets]
  python config_sync.py restore <backup> [--force]
  python config_sync.py diff <backup>
  python config_sync.py list

Requirements: Python 3.8+
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VERSION = "1.0"

SECRET_KEY_PATTERNS = ["TOKEN", "KEY", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL"]
CONFIG_SENSITIVE_KEYS = {"oauth:tokenCache"}
CONFIG_SENSITIVE_PREFIXES = ["dxt:allowlistCache:"]


# ---------------------------------------------------------
# Logger
# ---------------------------------------------------------

class Logger:
    _RESET  = "\033[0m"
    _RED    = "\033[91m"
    _GREEN  = "\033[92m"
    _YELLOW = "\033[93m"
    _CYAN   = "\033[96m"
    _GRAY   = "\033[90m"
    _BOLD   = "\033[1m"
    _WHITE  = "\033[97m"

    @staticmethod
    def _enable_ansi():
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                pass

    def __init__(self):
        self._enable_ansi()

    def info(self, msg: str):
        print(f"  {self._GREEN}[+]{self._RESET} {msg}")

    def warn(self, msg: str):
        print(f"  {self._YELLOW}[!]{self._RESET} {msg}")

    def error(self, msg: str):
        print(f"  {self._RED}[X]{self._RESET} {msg}")

    def step(self, msg: str):
        print(f"  {self._CYAN}[*]{self._RESET} {msg}")

    def detail(self, msg: str):
        print(f"      {self._GRAY}{msg}{self._RESET}")

    def header(self, msg: str):
        print()
        print(f"  {self._BOLD}{self._CYAN}{msg}{self._RESET}")
        print(f"  {self._CYAN}{'=' * len(msg)}{self._RESET}")
        print()


log = Logger()


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def get_claude_appdata() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not set")
    claude_dir = Path(appdata) / "Claude"
    if not claude_dir.is_dir():
        raise RuntimeError(f"Claude Desktop nicht gefunden: {claude_dir}")
    return claude_dir


def get_claude_code_home() -> Path:
    claude_dir = Path.home() / ".claude"
    if not claude_dir.is_dir():
        raise RuntimeError(f"Claude Code nicht gefunden: {claude_dir}")
    return claude_dir


def get_backup_dir() -> Path:
    backup_dir = get_claude_appdata() / "config-backups"
    backup_dir.mkdir(exist_ok=True)
    return backup_dir


def read_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_text(path: Path) -> str:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def format_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def is_secret_key(key: str) -> bool:
    return any(p in key.upper() for p in SECRET_KEY_PATTERNS)


def mask_secret(value: str) -> str:
    if not isinstance(value, str) or len(value) <= 4:
        return "****"
    return value[:4] + "****"


def confirm(prompt: str) -> bool:
    answer = input(f"  {prompt} [j/N] ").strip().lower()
    return answer in ("j", "ja", "y", "yes")


# ---------------------------------------------------------
# Sensitive data stripping
# ---------------------------------------------------------

def strip_config_secrets(data: dict) -> dict:
    """Strip oauth tokens and encrypted blobs from config.json."""
    cleaned = {}
    for key, value in data.items():
        if key in CONFIG_SENSITIVE_KEYS:
            continue
        if any(key.startswith(prefix) for prefix in CONFIG_SENSITIVE_PREFIXES):
            continue
        cleaned[key] = value
    return cleaned


def strip_mcp_secrets(data: dict, include_secrets: bool = False) -> dict:
    """Optionally mask env secrets in claude_desktop_config.json."""
    if include_secrets:
        return data
    result = json.loads(json.dumps(data))  # deep copy
    servers = result.get("mcpServers", {})
    for srv in servers.values():
        env = srv.get("env", {})
        for key in env:
            if is_secret_key(key) or (isinstance(env[key], str) and len(env[key]) > 16
                                       and not env[key].startswith("http")):
                env[key] = "<REDACTED>"
    return result


# ---------------------------------------------------------
# File collection
# ---------------------------------------------------------

def collect_desktop_files(claude_dir: Path, include_secrets: bool) -> List[Tuple[str, str]]:
    """Collect Claude Desktop config files. Returns (zip_path, content) tuples."""
    files: List[Tuple[str, str]] = []

    # claude_desktop_config.json
    path = claude_dir / "claude_desktop_config.json"
    if path.exists():
        data = strip_mcp_secrets(read_json(path), include_secrets)
        files.append(("desktop/claude_desktop_config.json", json.dumps(data, indent=2, ensure_ascii=False)))

    # developer_settings.json
    path = claude_dir / "developer_settings.json"
    if path.exists():
        files.append(("desktop/developer_settings.json", path.read_text(encoding="utf-8")))

    # config.json (strip sensitive keys)
    path = claude_dir / "config.json"
    if path.exists():
        data = strip_config_secrets(read_json(path))
        files.append(("desktop/config.json", json.dumps(data, indent=2, ensure_ascii=False)))

    # extensions-blocklist.json
    path = claude_dir / "extensions-blocklist.json"
    if path.exists():
        files.append(("desktop/extensions-blocklist.json", path.read_text(encoding="utf-8")))

    # Claude Extensions Settings
    ext_settings_dir = claude_dir / "Claude Extensions Settings"
    if ext_settings_dir.is_dir():
        for f in sorted(ext_settings_dir.glob("*.json")):
            files.append((f"desktop/extensions-settings/{f.name}", f.read_text(encoding="utf-8")))

    # Cowork settings (dynamic path)
    sessions_dir = claude_dir / "local-agent-mode-sessions"
    if sessions_dir.is_dir():
        for settings_file in sessions_dir.glob("*/*/cowork_settings.json"):
            rel = settings_file.relative_to(sessions_dir)
            files.append((f"desktop/cowork-settings/{rel.as_posix()}", settings_file.read_text(encoding="utf-8")))

    return files


def collect_code_files(code_dir: Path) -> List[Tuple[str, str]]:
    """Collect Claude Code config files. Returns (zip_path, content) tuples."""
    files: List[Tuple[str, str]] = []

    # settings.json
    path = code_dir / "settings.json"
    if path.exists():
        files.append(("code/settings.json", path.read_text(encoding="utf-8")))

    # settings.local.json
    path = code_dir / "settings.local.json"
    if path.exists():
        files.append(("code/settings.local.json", path.read_text(encoding="utf-8")))

    # plugins/installed_plugins.json
    path = code_dir / "plugins" / "installed_plugins.json"
    if path.exists():
        files.append(("code/plugins/installed_plugins.json", path.read_text(encoding="utf-8")))

    # plugins/known_marketplaces.json
    path = code_dir / "plugins" / "known_marketplaces.json"
    if path.exists():
        files.append(("code/plugins/known_marketplaces.json", path.read_text(encoding="utf-8")))

    # Project memories
    projects_dir = code_dir / "projects"
    if projects_dir.is_dir():
        for mem_file in sorted(projects_dir.glob("*/memory/MEMORY.md")):
            project_name = mem_file.parent.parent.name
            files.append((f"code/memory/{project_name}/MEMORY.md", mem_file.read_text(encoding="utf-8")))

    return files


# ---------------------------------------------------------
# Diff logic
# ---------------------------------------------------------

def diff_dicts(old: Any, new: Any, path: str = "") -> List[Tuple[str, str, Any, Any]]:
    """Recursive dict comparison. Returns (path, change_type, old_val, new_val)."""
    changes: List[Tuple[str, str, Any, Any]] = []

    if isinstance(old, dict) and isinstance(new, dict):
        all_keys = sorted(set(list(old.keys()) + list(new.keys())))
        for key in all_keys:
            full_path = f"{path}.{key}" if path else key
            if key not in old:
                changes.append((full_path, "added", None, new[key]))
            elif key not in new:
                changes.append((full_path, "removed", old[key], None))
            else:
                changes.extend(diff_dicts(old[key], new[key], full_path))
    elif old != new:
        changes.append((path, "changed", old, new))

    return changes


def format_value(val: Any) -> str:
    if isinstance(val, str):
        if len(val) > 60:
            return f'"{val[:57]}..."'
        return f'"{val}"'
    if isinstance(val, dict):
        return f"{{{len(val)} keys}}"
    if isinstance(val, list):
        return f"[{len(val)} items]"
    return str(val)


# ---------------------------------------------------------
# Commands
# ---------------------------------------------------------

def cmd_backup(desktop_only: bool, code_only: bool, include_secrets: bool):
    log.header(f"Config Backup v{VERSION} - Backup erstellen")

    files: List[Tuple[str, str]] = []
    scope = "all"

    if not code_only:
        try:
            claude_dir = get_claude_appdata()
            desktop_files = collect_desktop_files(claude_dir, include_secrets)
            files.extend(desktop_files)
            log.info(f"Claude Desktop: {len(desktop_files)} Dateien")
        except RuntimeError as e:
            if desktop_only:
                raise
            log.warn(f"Claude Desktop: {e}")

    if not desktop_only:
        try:
            code_dir = get_claude_code_home()
            code_files = collect_code_files(code_dir)
            files.extend(code_files)
            log.info(f"Claude Code: {len(code_files)} Dateien")
        except RuntimeError as e:
            if code_only:
                raise
            log.warn(f"Claude Code: {e}")

    if not files:
        log.error("Keine Dateien zum Sichern gefunden.")
        return

    if desktop_only:
        scope = "desktop"
    elif code_only:
        scope = "code"

    # Manifest
    manifest = {
        "version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_version": VERSION,
        "scope": scope,
        "hostname": platform.node(),
        "secrets_included": include_secrets,
        "files": [f[0] for f in files],
    }

    # ZIP erstellen
    backup_dir = get_backup_dir()
    backup_name = f"claude-config-backup_{format_timestamp()}.zip"
    backup_path = backup_dir / backup_name

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for zip_path, content in files:
            zf.writestr(zip_path, content)

    size = backup_path.stat().st_size
    log.info(f"Backup erstellt: {backup_path}")
    log.detail(f"{len(files)} Dateien, {format_size(size)}")
    if not include_secrets:
        log.detail("MCP-Server Secrets als <REDACTED> maskiert")
    print()


def _create_pre_restore_backup():
    """Create automatic backup before restore."""
    files: List[Tuple[str, str]] = []
    try:
        files.extend(collect_desktop_files(get_claude_appdata(), include_secrets=True))
    except RuntimeError:
        pass
    try:
        files.extend(collect_code_files(get_claude_code_home()))
    except RuntimeError:
        pass

    if not files:
        return None

    manifest = {
        "version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_version": VERSION,
        "scope": "all",
        "hostname": platform.node(),
        "secrets_included": True,
        "files": [f[0] for f in files],
        "type": "pre-restore",
    }

    backup_dir = get_backup_dir()
    backup_name = f"claude-config-pre-restore_{format_timestamp()}.zip"
    backup_path = backup_dir / backup_name

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for zip_path, content in files:
            zf.writestr(zip_path, content)

    return backup_path


def _resolve_backup_path(backup_ref: str) -> Path:
    """Resolve backup reference to actual path."""
    path = Path(backup_ref)
    if path.exists():
        return path
    # Suche im Backup-Verzeichnis
    backup_dir = get_backup_dir()
    candidate = backup_dir / backup_ref
    if candidate.exists():
        return candidate
    # Ohne .zip Extension
    candidate = backup_dir / f"{backup_ref}.zip"
    if candidate.exists():
        return candidate
    raise RuntimeError(f"Backup nicht gefunden: {backup_ref}")


def _get_restore_target(zip_path: str) -> Optional[Path]:
    """Map a ZIP-internal path to the filesystem target."""
    try:
        claude_dir = get_claude_appdata()
    except RuntimeError:
        claude_dir = None
    try:
        code_dir = get_claude_code_home()
    except RuntimeError:
        code_dir = None

    if zip_path.startswith("desktop/") and claude_dir:
        rel = zip_path[len("desktop/"):]
        if rel.startswith("extensions-settings/"):
            return claude_dir / "Claude Extensions Settings" / rel[len("extensions-settings/"):]
        elif rel.startswith("cowork-settings/"):
            return claude_dir / "local-agent-mode-sessions" / rel[len("cowork-settings/"):]
        else:
            return claude_dir / rel
    elif zip_path.startswith("code/") and code_dir:
        rel = zip_path[len("code/"):]
        if rel.startswith("memory/"):
            project_and_file = rel[len("memory/"):]
            return code_dir / "projects" / project_and_file.replace("/MEMORY.md", "/memory/MEMORY.md")
        else:
            return code_dir / rel
    return None


def cmd_restore(backup_ref: str, desktop_only: bool, code_only: bool, force: bool):
    log.header(f"Config Backup v{VERSION} - Backup wiederherstellen")

    backup_path = _resolve_backup_path(backup_ref)
    log.info(f"Backup: {backup_path}")

    with zipfile.ZipFile(backup_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))

        # Scope pruefen
        backup_scope = manifest.get("scope", "all")
        if desktop_only and backup_scope == "code":
            log.error("Backup enthaelt nur Claude Code, --desktop-only nicht moeglich.")
            return
        if code_only and backup_scope == "desktop":
            log.error("Backup enthaelt nur Claude Desktop, --code-only nicht moeglich.")
            return

        # Dateien filtern
        files_to_restore: List[Tuple[str, Path]] = []
        for zip_path in manifest.get("files", []):
            if desktop_only and not zip_path.startswith("desktop/"):
                continue
            if code_only and not zip_path.startswith("code/"):
                continue
            target = _get_restore_target(zip_path)
            if target:
                files_to_restore.append((zip_path, target))

        if not files_to_restore:
            log.error("Keine Dateien zum Wiederherstellen.")
            return

        # Vorschau
        log.step(f"{len(files_to_restore)} Dateien werden wiederhergestellt:")
        for zip_path, target in files_to_restore:
            exists = "existiert" if target.exists() else "neu"
            log.detail(f"{zip_path} -> ({exists})")

        # Redacted-Warnung
        if not manifest.get("secrets_included", True):
            print()
            log.warn("Backup enthaelt maskierte Secrets (<REDACTED>).")
            log.detail("MCP-Server Env-Werte werden NICHT ueberschrieben.")

        print()

        # Pre-Restore Backup
        log.step("Erstelle Pre-Restore Backup...")
        pre_backup = _create_pre_restore_backup()
        if pre_backup:
            log.info(f"Pre-Restore Backup: {pre_backup}")

        if not force:
            if not confirm(f"{len(files_to_restore)} Dateien wiederherstellen?"):
                log.detail("Abgebrochen.")
                return

        # Restore
        secrets_redacted = not manifest.get("secrets_included", True)

        for zip_path, target in files_to_restore:
            content = zf.read(zip_path).decode("utf-8")

            # Bei maskierten Secrets: bestehende Werte beibehalten
            if secrets_redacted and zip_path == "desktop/claude_desktop_config.json" and target.exists():
                new_config = json.loads(content)
                old_config = read_json(target)
                # MCP Server env Werte wiederherstellen
                new_servers = new_config.get("mcpServers", {})
                old_servers = old_config.get("mcpServers", {})
                for srv_name, srv_config in new_servers.items():
                    old_srv = old_servers.get(srv_name, {})
                    for env_key, env_val in srv_config.get("env", {}).items():
                        if env_val == "<REDACTED>" and env_key in old_srv.get("env", {}):
                            srv_config["env"][env_key] = old_srv["env"][env_key]
                content = json.dumps(new_config, indent=2, ensure_ascii=False)

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        log.info(f"{len(files_to_restore)} Dateien wiederhergestellt.")
        log.warn("Claude Desktop und/oder Claude Code neu starten!")
        print()


def cmd_diff(backup_ref: str):
    log.header(f"Config Backup v{VERSION} - Aenderungen anzeigen")

    backup_path = _resolve_backup_path(backup_ref)
    log.info(f"Vergleiche mit: {backup_path}")
    print()

    with zipfile.ZipFile(backup_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        has_changes = False

        for zip_path in manifest.get("files", []):
            target = _get_restore_target(zip_path)
            if not target:
                continue

            backup_content = zf.read(zip_path).decode("utf-8")

            # JSON diff
            if zip_path.endswith(".json"):
                try:
                    backup_data = json.loads(backup_content)
                except json.JSONDecodeError:
                    continue

                if not target.exists():
                    print(f"  {log._RED}{zip_path}: Datei geloescht{log._RESET}")
                    has_changes = True
                    continue

                current_data = read_json(target)
                changes = diff_dicts(backup_data, current_data)

                if changes:
                    has_changes = True
                    print(f"  {log._WHITE}{zip_path}:{log._RESET}")
                    for path, change_type, old_val, new_val in changes:
                        if change_type == "added":
                            print(f"    {log._GREEN}[+] {path}{log._RESET}  {format_value(new_val)}")
                        elif change_type == "removed":
                            print(f"    {log._RED}[-] {path}{log._RESET}  {format_value(old_val)}")
                        elif change_type == "changed":
                            print(f"    {log._YELLOW}[~] {path}{log._RESET}  {format_value(old_val)} -> {format_value(new_val)}")
                    print()

            # Markdown diff
            elif zip_path.endswith(".md"):
                if not target.exists():
                    print(f"  {log._RED}{zip_path}: Datei geloescht{log._RESET}")
                    has_changes = True
                elif target.read_text(encoding="utf-8") != backup_content:
                    backup_lines = backup_content.count("\n")
                    current_lines = target.read_text(encoding="utf-8").count("\n")
                    print(f"  {log._YELLOW}{zip_path}: geaendert ({backup_lines} -> {current_lines} Zeilen){log._RESET}")
                    has_changes = True

        if not has_changes:
            log.info("Keine Aenderungen seit dem Backup.")

    print()


def cmd_list():
    log.header(f"Config Backup v{VERSION} - Backups anzeigen")

    backup_dir = get_backup_dir()
    backups = sorted(backup_dir.glob("claude-config-*.zip"), reverse=True)

    if not backups:
        log.detail("Keine Backups gefunden.")
        log.detail(f"Verzeichnis: {backup_dir}")
        print()
        return

    log.info(f"{len(backups)} Backups in {backup_dir}:")
    print()
    print(f"  {'Nr':>3}  {'Datum':20}  {'Typ':12}  {'Umfang':8}  {'Dateien':>7}  {'Groesse':>8}")
    print(f"  {'---':>3}  {'----':20}  {'---':12}  {'------':8}  {'-------':>7}  {'-------':>8}")

    for i, backup_path in enumerate(backups, 1):
        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                manifest = json.loads(zf.read("manifest.json"))

            timestamp = manifest.get("timestamp", "?")
            if "T" in timestamp:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                date_str = timestamp

            backup_type = "Pre-Restore" if manifest.get("type") == "pre-restore" else "Backup"
            scope = manifest.get("scope", "?")
            file_count = len(manifest.get("files", []))
            size = format_size(backup_path.stat().st_size)

            print(f"  {i:>3}  {date_str:20}  {backup_type:12}  {scope:8}  {file_count:>7}  {size:>8}")
        except Exception:
            print(f"  {i:>3}  {backup_path.name}  (Fehler beim Lesen)")

    print()
    log.detail(f"Backup-Verzeichnis: {backup_dir}")
    print()


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=f"Claude Config Backup & Restore v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s backup                     Alles sichern
  %(prog)s backup --desktop-only      Nur Claude Desktop
  %(prog)s backup --code-only         Nur Claude Code
  %(prog)s restore <backup>           Wiederherstellen
  %(prog)s diff <backup>              Aenderungen anzeigen
  %(prog)s list                       Backups auflisten
        """,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s v{VERSION}")

    sub = parser.add_subparsers(dest="command", help="Verfuegbare Befehle")

    p_backup = sub.add_parser("backup", help="Backup erstellen")
    p_backup.add_argument("--desktop-only", action="store_true", help="Nur Claude Desktop")
    p_backup.add_argument("--code-only", action="store_true", help="Nur Claude Code")
    p_backup.add_argument("--include-secrets", action="store_true", help="Secrets nicht maskieren")

    p_restore = sub.add_parser("restore", help="Backup wiederherstellen")
    p_restore.add_argument("backup", help="Backup-Datei (Pfad oder Name)")
    p_restore.add_argument("--desktop-only", action="store_true", help="Nur Claude Desktop")
    p_restore.add_argument("--code-only", action="store_true", help="Nur Claude Code")
    p_restore.add_argument("--force", action="store_true", help="Ohne Bestaetigung")

    p_diff = sub.add_parser("diff", help="Aenderungen seit Backup anzeigen")
    p_diff.add_argument("backup", help="Backup-Datei (Pfad oder Name)")

    sub.add_parser("list", help="Backups auflisten")

    args = parser.parse_args()

    try:
        if args.command == "backup":
            cmd_backup(args.desktop_only, args.code_only, args.include_secrets)
        elif args.command == "restore":
            cmd_restore(args.backup, args.desktop_only, args.code_only, args.force)
        elif args.command == "diff":
            cmd_diff(args.backup)
        elif args.command == "list":
            cmd_list()
        else:
            parser.print_help()
            sys.exit(1)
    except RuntimeError as e:
        log.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
