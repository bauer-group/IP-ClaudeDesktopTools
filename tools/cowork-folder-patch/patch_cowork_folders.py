#!/usr/bin/env python3
"""
Claude Desktop Cowork - Folder Restriction Bypass (v5.1)

Aktiviert DevTools in Claude Desktop und zeigt ein JS-Snippet,
das den Folder-Picker ohne Home-Dir-Restriktion oeffnet.

Hintergrund:
  browseFolder(title, restrictToHomeDir) ist der EINZIGE Validierungspunkt.
  Alle nachgelagerten Systeme akzeptieren beliebige Pfade.
  Ueber die DevTools-Console laesst sich browseFolder(title, false) aufrufen.

Usage:
  python patch_cowork_folders.py install     DevTools aktivieren + Anleitung
  python patch_cowork_folders.py restore     DevTools deaktivieren
  python patch_cowork_folders.py status      Status anzeigen

Requirements: Python 3.8+, Claude Desktop v1.1.x
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

VERSION = "5.1"


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

    def code(self, lines: List[str]):
        print()
        print(f"  {self._YELLOW}{'-' * 60}{self._RESET}")
        for line in lines:
            print(f"  {self._WHITE}{line}{self._RESET}")
        print(f"  {self._YELLOW}{'-' * 60}{self._RESET}")
        print()


log = Logger()


# ---------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------

def get_claude_appdata() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not set")
    claude_dir = Path(appdata) / "Claude"
    if not claude_dir.is_dir():
        raise RuntimeError(f"Claude Desktop nicht gefunden: {claude_dir}")
    return claude_dir


def read_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------
# JavaScript Snippet
# ---------------------------------------------------------

JS_SNIPPET = r"""(async()=>{const w=window["claude.web"];if(!w||!w.FileSystem){console.error("Bridge nicht gefunden");return}const p=await w.FileSystem.browseFolder("Externen Ordner waehlen",false);if(!p){console.log("Abgebrochen");return}console.log("Ordner:",p);if(w.LocalAgentModeSessions&&w.LocalAgentModeSessions.addTrustedFolder){await w.LocalAgentModeSessions.addTrustedFolder(p);console.log("Als trusted markiert")}if(w.LocalAgentModeSessions&&w.LocalAgentModeSessions.setDraftSessionFolders){await w.LocalAgentModeSessions.setDraftSessionFolders([p]);console.log("Als Draft-Folder gesetzt - jetzt Nachricht senden!")}})()"""

JS_SNIPPET_PRETTY = [
    '(async () => {',
    '  const w = window["claude.web"];',
    '  if (!w || !w.FileSystem) { console.error("Bridge nicht gefunden"); return; }',
    '  // Ordner-Picker OHNE Home-Dir-Restriktion oeffnen',
    '  const p = await w.FileSystem.browseFolder("Externen Ordner waehlen", false);',
    '  if (!p) { console.log("Abgebrochen"); return; }',
    '  console.log("Ordner:", p);',
    '  // Als trusted markieren',
    '  if (w.LocalAgentModeSessions?.addTrustedFolder)',
    '    await w.LocalAgentModeSessions.addTrustedFolder(p);',
    '  // Als Draft-Folder fuer naechste Session setzen',
    '  if (w.LocalAgentModeSessions?.setDraftSessionFolders) {',
    '    await w.LocalAgentModeSessions.setDraftSessionFolders([p]);',
    '    console.log("Draft-Folder gesetzt! Jetzt Nachricht senden.");',
    '  }',
    '})()',
]


# ---------------------------------------------------------
# Commands
# ---------------------------------------------------------

def cmd_install():
    """Enable DevTools and show bypass instructions."""
    log.header(f"Claude Cowork Folder Bypass v{VERSION} - Installieren")

    claude_dir = get_claude_appdata()

    dev_settings_path = claude_dir / "developer_settings.json"
    dev_settings = read_json(dev_settings_path)
    dev_settings["allowDevTools"] = True
    write_json(dev_settings_path, dev_settings)
    log.info(f"DevTools aktiviert: {dev_settings_path}")

    print()
    log.warn("Claude Desktop neu starten!")
    print()
    log.step("Danach so vorgehen:")
    print()
    print(f"  {log._WHITE}1. Claude Desktop oeffnen{log._RESET}")
    print(f"  {log._WHITE}2. DevTools oeffnen:{log._RESET}")
    print(f"     {log._CYAN}Ctrl+Shift+I{log._RESET} oder {log._CYAN}Hilfe > Show Dev Tools{log._RESET}")
    print(f"  {log._WHITE}3. Reiter 'Console' waehlen{log._RESET}")
    print(f"  {log._WHITE}4. Folgenden Code einfuegen und Enter druecken:{log._RESET}")
    log.code(JS_SNIPPET_PRETTY)
    print(f"  {log._WHITE}5. Externen Ordner im Picker waehlen{log._RESET}")
    print(f"  {log._WHITE}6. In Cowork eine Nachricht senden{log._RESET}")
    print(f"     {log._GRAY}Der gewaehlte Ordner ist dann fuer diese Session verfuegbar{log._RESET}")
    print()
    log.detail("Einzeiler zum Kopieren:")
    print()
    print(f"  {log._YELLOW}{JS_SNIPPET}{log._RESET}")
    print()


def cmd_restore():
    """Disable DevTools and clean up trusted folders."""
    log.header(f"Claude Cowork Folder Bypass v{VERSION} - Deinstallieren")

    claude_dir = get_claude_appdata()

    # DevTools deaktivieren
    dev_settings_path = claude_dir / "developer_settings.json"
    if dev_settings_path.exists():
        dev_settings = read_json(dev_settings_path)
        dev_settings.pop("allowDevTools", None)
        if dev_settings:
            write_json(dev_settings_path, dev_settings)
        else:
            dev_settings_path.unlink()
        log.info("DevTools deaktiviert.")
    else:
        log.detail("DevTools waren nicht aktiviert.")

    # Trusted Folders entfernen (vom JS-Snippet geschrieben)
    config_path = claude_dir / "claude_desktop_config.json"
    config = read_json(config_path)
    prefs = config.get("preferences", {})
    if "localAgentModeTrustedFolders" in prefs:
        del prefs["localAgentModeTrustedFolders"]
        write_json(config_path, config)
        log.info("Trusted Folders entfernt.")

    print()
    log.warn("Claude Desktop neu starten!")
    print()


def cmd_status():
    """Show system status."""
    log.header(f"Claude Cowork Folder Bypass v{VERSION} - Status")

    claude_dir = get_claude_appdata()
    log.info(f"Claude AppData: {claude_dir}")

    # DevTools
    dev_settings_path = claude_dir / "developer_settings.json"
    dev_settings = read_json(dev_settings_path)
    if dev_settings.get("allowDevTools", False):
        log.info("DevTools: aktiviert")
    else:
        log.warn("DevTools: nicht aktiviert")
        log.detail("Ausfuehren: python patch_cowork_folders.py install")

    # Trusted Folders
    config_path = claude_dir / "claude_desktop_config.json"
    config = read_json(config_path)
    trusted = config.get("preferences", {}).get("localAgentModeTrustedFolders", [])
    if trusted:
        log.info(f"Trusted Folders: {len(trusted)}")
        for f in trusted:
            log.detail(f)
    else:
        log.detail("Keine Trusted Folders konfiguriert.")

    print()


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=f"Claude Desktop Cowork - Folder Restriction Bypass v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ablauf:
  1. 'install' ausfuehren
  2. Claude Desktop neu starten
  3. DevTools oeffnen (Ctrl+Shift+I)
  4. JavaScript-Snippet in Console einfuegen
  5. Externen Ordner waehlen
  6. In Cowork Nachricht senden
        """,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s v{VERSION}")

    sub = parser.add_subparsers(dest="command", help="Verfuegbare Befehle")
    sub.add_parser("install", help="DevTools aktivieren + Anleitung")
    sub.add_parser("restore", help="DevTools deaktivieren, aufraumen")
    sub.add_parser("status", help="Status anzeigen")

    args = parser.parse_args()

    if args.command == "install":
        cmd_install()
    elif args.command == "restore":
        cmd_restore()
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
