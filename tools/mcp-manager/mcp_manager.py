#!/usr/bin/env python3
"""
Claude Desktop MCP Server Manager v1.0

Verwaltet Legacy MCP Server in claude_desktop_config.json.
(Die neueren "Claude Extensions" haben bereits eine eigene UI.)

Usage:
  python mcp_manager.py list                     Alle Server anzeigen
  python mcp_manager.py add <name>               Server hinzufuegen (Wizard)
  python mcp_manager.py remove <name>            Server entfernen
  python mcp_manager.py test <name>              Server testen (MCP Init)
  python mcp_manager.py export <name>            Config exportieren
  python mcp_manager.py import <datei>           Config importieren

Requirements: Python 3.8+, Claude Desktop
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

VERSION = "1.0"

SECRET_KEY_PATTERNS = ["TOKEN", "KEY", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL"]


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


def get_config_path() -> Path:
    return get_claude_appdata() / "claude_desktop_config.json"


def read_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def write_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_mcp_servers(config: dict) -> Dict[str, Any]:
    return config.get("mcpServers", {})


def is_secret_key(key: str) -> bool:
    return any(p in key.upper() for p in SECRET_KEY_PATTERNS)


def is_secret_value(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return len(value) > 16 and not value.startswith("http")


def mask_secret(value: str) -> str:
    if not isinstance(value, str) or len(value) <= 4:
        return "****"
    return value[:4] + "****"


def should_mask(key: str, value: str) -> bool:
    return is_secret_key(key) or is_secret_value(value)


def confirm(prompt: str) -> bool:
    answer = input(f"  {prompt} [j/N] ").strip().lower()
    return answer in ("j", "ja", "y", "yes")


# ---------------------------------------------------------
# Commands
# ---------------------------------------------------------

def cmd_list():
    log.header(f"MCP Server Manager v{VERSION} - Server anzeigen")

    config = read_json(get_config_path())
    servers = get_mcp_servers(config)

    if not servers:
        log.detail("Keine MCP Server konfiguriert.")
        print()
        return

    log.info(f"{len(servers)} MCP Server konfiguriert:")
    print()

    for name, srv in servers.items():
        print(f"  {log._BOLD}{log._WHITE}{name}{log._RESET}")
        cmd = srv.get("command", "?")
        args = srv.get("args", [])
        env = srv.get("env", {})

        print(f"    Befehl:  {cmd}")
        if args:
            print(f"    Args:    {' '.join(str(a) for a in args)}")
        if env:
            print(f"    Env:")
            for k, v in env.items():
                display_v = mask_secret(v) if should_mask(k, v) else v
                print(f"             {k} = {display_v}")
        print()


def cmd_add(name: str):
    log.header(f"MCP Server Manager v{VERSION} - Server hinzufuegen")

    config_path = get_config_path()
    config = read_json(config_path)
    servers = get_mcp_servers(config)

    if name in servers:
        log.error(f"Server '{name}' existiert bereits.")
        log.detail("Verwenden Sie 'remove' zuerst.")
        return

    log.step(f"Neuen MCP Server hinzufuegen: {name}")
    print()

    command = input("  Befehl (z.B. npx, uvx, node, python): ").strip()
    if not command:
        log.error("Befehl darf nicht leer sein.")
        return

    args_str = input("  Argumente (Leerzeichen-getrennt, leer fuer keine): ").strip()
    args = args_str.split() if args_str else []

    print("  Umgebungsvariablen (leer zum Beenden):")
    env: Dict[str, str] = {}
    while True:
        env_name = input("    Name: ").strip()
        if not env_name:
            break
        env_value = input("    Wert: ").strip()
        env[env_name] = env_value

    server_config: Dict[str, Any] = {"command": command}
    if args:
        server_config["args"] = args
    if env:
        server_config["env"] = env

    print()
    log.step("Vorschau:")
    print(f"  {json.dumps({name: server_config}, indent=2, ensure_ascii=False)}")
    print()

    if not confirm("Server hinzufuegen?"):
        log.detail("Abgebrochen.")
        return

    if "mcpServers" not in config:
        config["mcpServers"] = {}
    config["mcpServers"][name] = server_config
    write_json(config_path, config)

    log.info(f"Server '{name}' hinzugefuegt.")
    log.warn("Claude Desktop muss neu gestartet werden!")
    print()


def cmd_remove(name: str, force: bool = False):
    log.header(f"MCP Server Manager v{VERSION} - Server entfernen")

    config_path = get_config_path()
    config = read_json(config_path)
    servers = get_mcp_servers(config)

    if name not in servers:
        log.error(f"Server '{name}' nicht gefunden.")
        if servers:
            log.detail(f"Verfuegbar: {', '.join(servers.keys())}")
        return

    log.step(f"Server '{name}':")
    srv = servers[name]
    print(f"  {json.dumps({name: srv}, indent=2, ensure_ascii=False)}")
    print()

    if not force and not confirm(f"Server '{name}' entfernen?"):
        log.detail("Abgebrochen.")
        return

    del config["mcpServers"][name]
    write_json(config_path, config)

    log.info(f"Server '{name}' entfernt.")
    log.warn("Claude Desktop muss neu gestartet werden!")
    print()


def cmd_test(name: str):
    log.header(f"MCP Server Manager v{VERSION} - Server testen")

    config = read_json(get_config_path())
    servers = get_mcp_servers(config)

    if name not in servers:
        log.error(f"Server '{name}' nicht gefunden.")
        if servers:
            log.detail(f"Verfuegbar: {', '.join(servers.keys())}")
        return

    srv = servers[name]
    command = srv.get("command", "")
    args = srv.get("args", [])
    srv_env = srv.get("env", {})

    log.step(f"Server '{name}' testen...")

    # Pruefen ob Befehl existiert
    cmd_path = shutil.which(command)
    if not cmd_path:
        # Windows: auch .cmd-Variante pruefen
        cmd_path = shutil.which(command + ".cmd")
    if not cmd_path:
        log.error(f"Befehl nicht gefunden: {command}")
        log.detail(f"Ist '{command}' installiert und im PATH?")
        return

    log.info(f"Befehl gefunden: {cmd_path}")

    # Umgebung vorbereiten
    env = os.environ.copy()
    env.update(srv_env)

    # MCP Initialize Request
    init_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-manager-test", "version": VERSION}
        }
    })

    try:
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            [cmd_path] + [str(a) for a in args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=creation_flags,
        )
        log.info(f"Prozess gestartet (PID {proc.pid})")

        # Timeout nach 10 Sekunden
        timer = threading.Timer(10.0, proc.kill)
        timer.start()

        try:
            # Sende Initialize Request (mit Content-Length Header)
            message = f"Content-Length: {len(init_request)}\r\n\r\n{init_request}"
            stdout_data, stderr_data = proc.communicate(
                input=message.encode("utf-8"),
                timeout=10,
            )
            timer.cancel()

            stdout_text = stdout_data.decode("utf-8", errors="replace")
            stderr_text = stderr_data.decode("utf-8", errors="replace")

            # Suche nach JSON-RPC Response
            if '"jsonrpc"' in stdout_text and '"result"' in stdout_text:
                log.info("MCP Protokoll-Initialisierung erkannt")
                log.info("Server antwortet korrekt")
            elif '"jsonrpc"' in stdout_text:
                log.warn("JSON-RPC Antwort erhalten, aber kein 'result'")
                log.detail("Server antwortet, aber moeglicherweise mit Fehler")
            elif stdout_text.strip():
                log.warn("Ausgabe erhalten, aber kein MCP Protokoll erkannt")
                log.detail(f"Ausgabe: {stdout_text[:200]}")
            else:
                log.warn("Keine Ausgabe vom Server")
                if stderr_text.strip():
                    log.detail(f"Fehler: {stderr_text[:200]}")

        except subprocess.TimeoutExpired:
            timer.cancel()
            proc.kill()
            log.warn("Timeout (10s) - Server antwortet nicht")
            log.detail("Server laeuft moeglicherweise, antwortet aber nicht auf Initialize")

    except FileNotFoundError:
        log.error(f"Befehl konnte nicht ausgefuehrt werden: {cmd_path}")
    except Exception as e:
        log.error(f"Fehler beim Testen: {e}")

    print()


def cmd_export(name: str, include_secrets: bool = False, output: Optional[str] = None):
    log.header(f"MCP Server Manager v{VERSION} - Server exportieren")

    config = read_json(get_config_path())
    servers = get_mcp_servers(config)

    if name not in servers:
        log.error(f"Server '{name}' nicht gefunden.")
        if servers:
            log.detail(f"Verfuegbar: {', '.join(servers.keys())}")
        return

    srv = dict(servers[name])

    # Secrets maskieren
    if not include_secrets and "env" in srv:
        masked_env = {}
        for k, v in srv["env"].items():
            if should_mask(k, v):
                masked_env[k] = "<REDACTED>"
            else:
                masked_env[k] = v
        srv["env"] = masked_env

    export_data = {
        "name": name,
        "config": srv,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": f"mcp-manager v{VERSION}",
    }

    out_path = Path(output) if output else Path(f"mcp-server_{name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    log.info(f"Exportiert: {out_path}")
    if not include_secrets:
        log.detail("Secrets wurden als <REDACTED> maskiert.")
        log.detail("--include-secrets fuer vollstaendigen Export verwenden.")
    print()


def cmd_import(file_path: str, name_override: Optional[str] = None, force: bool = False):
    log.header(f"MCP Server Manager v{VERSION} - Server importieren")

    import_path = Path(file_path)
    if not import_path.exists():
        log.error(f"Datei nicht gefunden: {import_path}")
        return

    try:
        with open(import_path, "r", encoding="utf-8") as f:
            import_data = json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"Ungueltige JSON-Datei: {e}")
        return

    if "name" not in import_data or "config" not in import_data:
        log.error("Ungueltiges Export-Format (name und config erforderlich).")
        return

    name = name_override or import_data["name"]
    srv_config = import_data["config"]

    if "command" not in srv_config:
        log.error("Server-Config hat keinen 'command'.")
        return

    # Pruefen auf <REDACTED>
    redacted_keys = []
    for k, v in srv_config.get("env", {}).items():
        if v == "<REDACTED>":
            redacted_keys.append(k)

    if redacted_keys:
        log.warn("Folgende Env-Variablen sind maskiert:")
        for k in redacted_keys:
            log.detail(f"{k} = <REDACTED>")
        print()
        log.warn("Diese Werte muessen manuell in der Config ergaenzt werden!")
        print()

    config_path = get_config_path()
    config = read_json(config_path)
    servers = get_mcp_servers(config)

    if name in servers and not force:
        log.error(f"Server '{name}' existiert bereits.")
        log.detail("--force zum Ueberschreiben oder --name zum Umbenennen verwenden.")
        return

    log.step("Vorschau:")
    print(f"  {json.dumps({name: srv_config}, indent=2, ensure_ascii=False)}")
    print()

    if not confirm(f"Server '{name}' importieren?"):
        log.detail("Abgebrochen.")
        return

    if "mcpServers" not in config:
        config["mcpServers"] = {}
    config["mcpServers"][name] = srv_config
    write_json(config_path, config)

    log.info(f"Server '{name}' importiert.")
    if redacted_keys:
        log.warn(f"Env-Werte ergaenzen: {', '.join(redacted_keys)}")
    log.warn("Claude Desktop muss neu gestartet werden!")
    print()


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=f"Claude Desktop MCP Server Manager v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s v{VERSION}")

    sub = parser.add_subparsers(dest="command", help="Verfuegbare Befehle")

    sub.add_parser("list", help="MCP Server anzeigen")

    p_add = sub.add_parser("add", help="MCP Server hinzufuegen")
    p_add.add_argument("name", help="Name des Servers")

    p_remove = sub.add_parser("remove", help="MCP Server entfernen")
    p_remove.add_argument("name", help="Name des Servers")
    p_remove.add_argument("--force", action="store_true", help="Ohne Bestaetigung")

    p_test = sub.add_parser("test", help="MCP Server testen")
    p_test.add_argument("name", help="Name des Servers")

    p_export = sub.add_parser("export", help="Server-Konfiguration exportieren")
    p_export.add_argument("name", help="Name des Servers")
    p_export.add_argument("--include-secrets", action="store_true", help="Secrets nicht maskieren")
    p_export.add_argument("--output", "-o", help="Ausgabe-Datei")

    p_import = sub.add_parser("import", help="Server-Konfiguration importieren")
    p_import.add_argument("file", help="Import-Datei")
    p_import.add_argument("--name", help="Server umbenennen")
    p_import.add_argument("--force", action="store_true", help="Ueberschreiben erlauben")

    args = parser.parse_args()

    try:
        if args.command == "list":
            cmd_list()
        elif args.command == "add":
            cmd_add(args.name)
        elif args.command == "remove":
            cmd_remove(args.name, args.force)
        elif args.command == "test":
            cmd_test(args.name)
        elif args.command == "export":
            cmd_export(args.name, args.include_secrets, args.output)
        elif args.command == "import":
            cmd_import(args.file, args.name, args.force)
        else:
            parser.print_help()
            sys.exit(1)
    except RuntimeError as e:
        log.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
