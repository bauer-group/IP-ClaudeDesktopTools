#!/usr/bin/env python3
"""
Claude Desktop Cowork – Folder Restriction Bypass

Bypasses the home-directory restriction in the Cowork folder picker
by directly injecting folder paths into Claude's spaces.json and
trusted-folders config. No binary patching, no admin rights needed.

How it works:
  The folder picker (browseFolder) is the ONLY validation point that
  checks if a folder is inside %USERPROFILE%. All downstream systems
  (SpacesManager, SessionManager, file access control) work with
  whatever paths they receive. By writing directly to spaces.json
  and localAgentModeTrustedFolders, we bypass browseFolder entirely.

Usage:
  python patch_cowork_folders.py add "C:\\Projects" "D:\\Data"
  python patch_cowork_folders.py remove "C:\\Projects"
  python patch_cowork_folders.py list
  python patch_cowork_folders.py status

Requirements: Python 3.8+, Claude Desktop must be restarted after changes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import time
from pathlib import Path
from typing import List, Optional

VERSION = "5.0"

# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────

class Logger:
    _RESET  = "\033[0m"
    _RED    = "\033[91m"
    _GREEN  = "\033[92m"
    _YELLOW = "\033[93m"
    _CYAN   = "\033[96m"
    _GRAY   = "\033[90m"
    _BOLD   = "\033[1m"

    @staticmethod
    def _enable_ansi():
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

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


# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────

def get_claude_appdata() -> Path:
    """Get Claude Desktop's %APPDATA% directory."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not set")
    claude_dir = Path(appdata) / "Claude"
    if not claude_dir.is_dir():
        raise RuntimeError(f"Claude Desktop data directory not found: {claude_dir}")
    return claude_dir


def get_config_path(claude_dir: Path) -> Path:
    return claude_dir / "claude_desktop_config.json"


def find_session_dir(claude_dir: Path) -> Optional[Path]:
    """Find the local-agent-mode-sessions/{accountId}/{userId}/ directory."""
    sessions_base = claude_dir / "local-agent-mode-sessions"
    if not sessions_base.is_dir():
        return None

    for account_dir in sessions_base.iterdir():
        if not account_dir.is_dir() or account_dir.name == "skills-plugin":
            continue
        for user_dir in account_dir.iterdir():
            if user_dir.is_dir():
                return user_dir
    return None


def get_spaces_path(session_dir: Path) -> Path:
    return session_dir / "spaces.json"


# ─────────────────────────────────────────────────────────────
# Config Operations
# ─────────────────────────────────────────────────────────────

def read_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_config(config_path: Path, config: dict):
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def normalize_path(folder: str) -> str:
    """Normalize a folder path (resolve, remove trailing separators)."""
    p = Path(folder).resolve()
    return str(p)


def get_trusted_folders(config: dict) -> List[str]:
    prefs = config.get("preferences", {})
    return prefs.get("localAgentModeTrustedFolders", [])


def set_trusted_folders(config: dict, folders: List[str]) -> dict:
    if "preferences" not in config:
        config["preferences"] = {}
    config["preferences"]["localAgentModeTrustedFolders"] = folders
    return config


def add_trusted_folder(config: dict, folder: str) -> dict:
    """Add a folder to the trusted folders list if not already present."""
    norm = normalize_path(folder)
    trusted = get_trusted_folders(config)
    # Check if already present (case-insensitive on Windows)
    existing = {f.lower().rstrip("\\/") for f in trusted}
    if norm.lower().rstrip("\\/") not in existing:
        trusted.append(norm)
    return set_trusted_folders(config, trusted)


def remove_trusted_folder(config: dict, folder: str) -> dict:
    """Remove a folder from the trusted folders list."""
    norm = normalize_path(folder).lower().rstrip("\\/")
    trusted = get_trusted_folders(config)
    filtered = [f for f in trusted if f.lower().rstrip("\\/") != norm]
    return set_trusted_folders(config, filtered)


# ─────────────────────────────────────────────────────────────
# Spaces Operations
# ─────────────────────────────────────────────────────────────

BYPASS_SPACE_NAME = "External Folders"

def read_spaces(spaces_path: Path) -> dict:
    if spaces_path.exists():
        with open(spaces_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"spaces": []}


def write_spaces(spaces_path: Path, data: dict):
    spaces_path.parent.mkdir(parents=True, exist_ok=True)
    with open(spaces_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_bypass_space(spaces_data: dict) -> Optional[dict]:
    """Find the bypass space in the spaces data."""
    for space in spaces_data.get("spaces", []):
        if space.get("name") == BYPASS_SPACE_NAME:
            return space
    return None


def create_bypass_space(folders: List[str]) -> dict:
    """Create a new space with the given folders."""
    now = int(time.time() * 1000)
    return {
        "id": str(uuid.uuid4()),
        "name": BYPASS_SPACE_NAME,
        "folders": [{"path": normalize_path(f)} for f in folders],
        "projects": [],
        "instructions": "Auto-generated space for folders outside the home directory.",
        "createdAt": now,
        "updatedAt": now,
    }


def add_folders_to_space(spaces_data: dict, folders: List[str]) -> dict:
    """Add folders to the bypass space, creating it if needed."""
    space = find_bypass_space(spaces_data)
    normalized = [normalize_path(f) for f in folders]

    if space is None:
        space = create_bypass_space(folders)
        spaces_data["spaces"].append(space)
        return spaces_data

    existing = {f["path"].lower().rstrip("\\/") for f in space.get("folders", [])}
    for norm in normalized:
        if norm.lower().rstrip("\\/") not in existing:
            space["folders"].append({"path": norm})
            existing.add(norm.lower().rstrip("\\/"))
    space["updatedAt"] = int(time.time() * 1000)
    return spaces_data


def remove_folders_from_space(spaces_data: dict, folders: List[str]) -> dict:
    """Remove folders from the bypass space."""
    space = find_bypass_space(spaces_data)
    if space is None:
        return spaces_data

    to_remove = {normalize_path(f).lower().rstrip("\\/") for f in folders}
    space["folders"] = [
        f for f in space.get("folders", [])
        if f["path"].lower().rstrip("\\/") not in to_remove
    ]
    space["updatedAt"] = int(time.time() * 1000)

    # Remove empty space
    if not space["folders"]:
        spaces_data["spaces"] = [
            s for s in spaces_data["spaces"]
            if s.get("name") != BYPASS_SPACE_NAME
        ]
    return spaces_data


# ─────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────

def cmd_add(folders: List[str]):
    """Add external folders to Claude Desktop Cowork."""
    log.header(f"Claude Cowork Folder Bypass v{VERSION} – Ordner hinzufuegen")

    if not folders:
        log.error("Keine Ordner angegeben.")
        sys.exit(1)

    # Validate folders exist
    for f in folders:
        p = Path(f)
        if not p.is_dir():
            log.error(f"Ordner existiert nicht: {f}")
            sys.exit(1)

    # Determine home directory for info
    home = Path.home()
    external = []
    for f in folders:
        norm = normalize_path(f)
        try:
            Path(norm).relative_to(home)
            log.warn(f"'{norm}' ist bereits im Home-Verzeichnis – Bypass nicht noetig")
        except ValueError:
            external.append(f)
            log.step(f"Externer Ordner: {norm}")

    if not external:
        log.info("Alle Ordner sind im Home-Verzeichnis. Kein Bypass noetig.")
        return

    claude_dir = get_claude_appdata()
    config_path = get_config_path(claude_dir)
    session_dir = find_session_dir(claude_dir)

    if not session_dir:
        log.error("Keine Cowork-Session gefunden. Bitte zuerst Claude Desktop starten")
        log.detail("und mindestens einmal Cowork verwenden.")
        sys.exit(1)

    # Step 1: Add to trusted folders in config
    log.step("Schritt 1: Trusted Folders in Config aktualisieren...")
    config = read_config(config_path)
    for f in external:
        config = add_trusted_folder(config, f)
    write_config(config_path, config)
    log.info(f"Config aktualisiert: {config_path}")

    # Step 2: Add to spaces.json
    log.step("Schritt 2: Space mit externen Ordnern erstellen...")
    spaces_path = get_spaces_path(session_dir)
    spaces_data = read_spaces(spaces_path)
    spaces_data = add_folders_to_space(spaces_data, external)
    write_spaces(spaces_path, spaces_data)
    log.info(f"Spaces aktualisiert: {spaces_path}")

    # Summary
    space = find_bypass_space(spaces_data)
    if space:
        print()
        log.info(f"Space '{BYPASS_SPACE_NAME}' enthaelt {len(space['folders'])} Ordner:")
        for f in space["folders"]:
            log.detail(f["path"])

    print()
    log.warn("Claude Desktop muss neu gestartet werden!")
    log.detail("Danach den Space 'External Folders' in Cowork auswaehlen.")
    print()


def cmd_remove(folders: List[str]):
    """Remove folders from the bypass."""
    log.header(f"Claude Cowork Folder Bypass v{VERSION} – Ordner entfernen")

    if not folders:
        log.error("Keine Ordner angegeben.")
        sys.exit(1)

    claude_dir = get_claude_appdata()
    config_path = get_config_path(claude_dir)
    session_dir = find_session_dir(claude_dir)

    # Remove from config
    log.step("Trusted Folders aus Config entfernen...")
    config = read_config(config_path)
    for f in folders:
        config = remove_trusted_folder(config, f)
    write_config(config_path, config)
    log.info("Config aktualisiert.")

    # Remove from spaces
    if session_dir:
        log.step("Ordner aus Space entfernen...")
        spaces_path = get_spaces_path(session_dir)
        spaces_data = read_spaces(spaces_path)
        spaces_data = remove_folders_from_space(spaces_data, folders)
        write_spaces(spaces_path, spaces_data)
        log.info("Spaces aktualisiert.")

    print()
    log.warn("Claude Desktop muss neu gestartet werden!")
    print()


def cmd_list():
    """List currently bypassed folders."""
    log.header(f"Claude Cowork Folder Bypass v{VERSION} – Status")

    claude_dir = get_claude_appdata()
    config_path = get_config_path(claude_dir)
    session_dir = find_session_dir(claude_dir)

    # Trusted folders from config
    config = read_config(config_path)
    trusted = get_trusted_folders(config)
    print(f"  Trusted Folders (Config): {len(trusted)}")
    for f in trusted:
        log.detail(f)

    # Spaces
    if session_dir:
        spaces_path = get_spaces_path(session_dir)
        spaces_data = read_spaces(spaces_path)
        space = find_bypass_space(spaces_data)
        if space:
            folders = space.get("folders", [])
            print(f"\n  Space '{BYPASS_SPACE_NAME}': {len(folders)} Ordner")
            for f in folders:
                log.detail(f["path"])
        else:
            print(f"\n  Space '{BYPASS_SPACE_NAME}': nicht vorhanden")
    else:
        log.warn("Keine Cowork-Session gefunden.")

    print()


def cmd_status():
    """Show system status."""
    log.header(f"Claude Cowork Folder Bypass v{VERSION} – System-Status")

    claude_dir = get_claude_appdata()
    log.info(f"Claude AppData: {claude_dir}")

    config_path = get_config_path(claude_dir)
    log.info(f"Config: {config_path} {'(existiert)' if config_path.exists() else '(fehlt)'}")

    session_dir = find_session_dir(claude_dir)
    if session_dir:
        log.info(f"Session-Dir: {session_dir}")
        spaces_path = get_spaces_path(session_dir)
        exists_str = "(existiert)" if spaces_path.exists() else "(neu)"
        log.info(f"Spaces: {spaces_path} {exists_str}")
    else:
        log.warn("Keine Cowork-Session gefunden.")

    # Show config
    config = read_config(config_path)
    trusted = get_trusted_folders(config)
    if trusted:
        log.info(f"Trusted Folders: {len(trusted)}")
        for f in trusted:
            log.detail(f)
    else:
        log.detail("Keine Trusted Folders konfiguriert.")

    # Show spaces
    if session_dir:
        spaces_data = read_spaces(get_spaces_path(session_dir))
        total_spaces = len(spaces_data.get("spaces", []))
        log.info(f"Spaces gesamt: {total_spaces}")
        bypass = find_bypass_space(spaces_data)
        if bypass:
            log.info(f"Bypass-Space: {len(bypass.get('folders', []))} Ordner")
        else:
            log.detail("Kein Bypass-Space vorhanden.")

    print()


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Claude Desktop Cowork – Folder Restriction Bypass",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  %(prog)s add "C:\\Projects" "D:\\Data"     Ordner hinzufuegen
  %(prog)s add "\\\\server\\share"             Netzlaufwerk hinzufuegen
  %(prog)s remove "C:\\Projects"             Ordner entfernen
  %(prog)s list                              Aktuelle Ordner anzeigen
  %(prog)s status                            System-Status pruefen

Hinweis: Claude Desktop muss nach Aenderungen neu gestartet werden.
         Danach den Space 'External Folders' in Cowork auswaehlen.
        """,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s v{VERSION}")

    sub = parser.add_subparsers(dest="command", help="Verfuegbare Befehle")

    p_add = sub.add_parser("add", help="Externe Ordner hinzufuegen")
    p_add.add_argument("folders", nargs="+", help="Ordnerpfade")

    p_rm = sub.add_parser("remove", help="Ordner entfernen")
    p_rm.add_argument("folders", nargs="+", help="Ordnerpfade")

    sub.add_parser("list", help="Aktuelle Ordner anzeigen")
    sub.add_parser("status", help="System-Status pruefen")

    # Legacy compatibility: accept 'install', 'restore' as aliases
    sub.add_parser("install", help=argparse.SUPPRESS)
    sub.add_parser("restore", help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args.folders)
    elif args.command == "remove":
        cmd_remove(args.folders)
    elif args.command == "list":
        cmd_list()
    elif args.command in ("status", "install", "restore"):
        if args.command == "install":
            log.warn("'install' ist veraltet. Nutze: add <ordner>")
            log.detail("Beispiel: python patch_cowork_folders.py add \"C:\\Projects\"")
            print()
        elif args.command == "restore":
            log.warn("'restore' ist veraltet. Nutze: remove <ordner>")
            log.detail("Beispiel: python patch_cowork_folders.py remove \"C:\\Projects\"")
            print()
        cmd_status()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
