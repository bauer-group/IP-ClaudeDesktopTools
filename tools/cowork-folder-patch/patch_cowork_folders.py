#!/usr/bin/env python3
"""
Claude Desktop Cowork – Folder Restriction Patch

Removes the home-directory validation from the Cowork folder picker,
enabling network drives, external drives, and redirected folders.

Based on the 3-phase technique from shraga100/claude-desktop-rtl-patch:
  Phase 1: ASAR Injection  (neutralize JS validation)
  Phase 2: Hash Replacement (update integrity hash in claude.exe)
  Phase 3: Certificate Swap (replace embedded cert in cowork-svc.exe)

Requirements: Python 3.8+, Node.js (npx), PowerShell 5.1+, Administrator
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import glob
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

PATCH_MARKER = "/*cowork-folder-patched*/"
CERT_FRIENDLY_NAME = "Claude_FolderPatch_SelfSigned"
LOG_PATH = os.path.join(tempfile.gettempdir(), "claude-cowork-folder-patch.log")
TMP_DIR = os.path.join(tempfile.gettempdir(), "claude_folder_patch_tmp")
VERSION = "3.0"


# ─────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────

class Logger:
    """Colored console output with file logging."""

    # ANSI codes (Windows 10+ Terminal supports them)
    _RESET = "\033[0m"
    _CYAN = "\033[36m"
    _GREEN = "\033[32m"
    _YELLOW = "\033[33m"
    _RED = "\033[31m"
    _MAGENTA = "\033[35m"
    _GRAY = "\033[90m"
    _WHITE = "\033[97m"

    def __init__(self, log_path: str):
        self._log_path = log_path
        self._log_file = open(log_path, "a", encoding="utf-8")
        # Enable ANSI on Windows
        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    def _ts(self) -> str:
        return time.strftime("%H:%M:%S")

    def _write_log(self, tag: str, msg: str):
        self._log_file.write(f"[{self._ts()}] [{tag}] {msg}\n")
        self._log_file.flush()

    def info(self, msg: str):
        self._write_log("INFO", msg)
        print(f"  {self._CYAN}[*]{self._RESET} {msg}")

    def success(self, msg: str):
        self._write_log("OK", msg)
        print(f"  {self._GREEN}[+]{self._RESET} {msg}")

    def warn(self, msg: str):
        self._write_log("WARN", msg)
        print(f"  {self._YELLOW}[!]{self._RESET} {msg}")

    def error(self, msg: str):
        self._write_log("ERROR", msg)
        print(f"  {self._RED}[X]{self._RESET} {msg}")

    def step(self, msg: str):
        self._write_log("STEP", msg)
        print(f"\n{self._MAGENTA}\u25ba {msg}{self._RESET}")

    def detail(self, msg: str):
        print(f"  {self._GRAY}    {msg}{self._RESET}")

    def close(self):
        self._log_file.close()


# ─────────────────────────────────────────────────────────────
# Installation paths
# ─────────────────────────────────────────────────────────────

@dataclass
class InstallPaths:
    base_dir: str
    app_dir: str
    resources_dir: str
    asar_path: str
    exe_path: str
    svc_path: str
    layout: str  # "msix" or "classic"


class ClaudeFinder:
    """Locate Claude Desktop installation on Windows."""

    def find(self) -> InstallPaths:
        # Try MSIX first
        paths = self._find_msix()
        if paths:
            return paths

        # Classic install
        paths = self._find_classic()
        if paths:
            return paths

        raise FileNotFoundError(
            "Claude Desktop nicht gefunden. Unterstuetzt: MSIX (Store) und klassische Installation."
        )

    def _find_msix(self) -> Optional[InstallPaths]:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-AppxPackage *Claude* | Where-Object { $_.InstallLocation -like '*WindowsApps*' } "
                 "| Select-Object -First 1).InstallLocation"],
                capture_output=True, text=True, timeout=15
            )
            base = result.stdout.strip()
            if not base or not os.path.isdir(base):
                return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        app_dir = os.path.join(base, "app")
        resources_dir = os.path.join(app_dir, "resources")
        asar = os.path.join(resources_dir, "app.asar")

        if not os.path.isfile(asar):
            return None

        exe = os.path.join(app_dir, "claude.exe")
        if not os.path.isfile(exe):
            exe = os.path.join(app_dir, "Claude.exe")

        svc = os.path.join(resources_dir, "cowork-svc.exe")

        return InstallPaths(
            base_dir=base, app_dir=app_dir, resources_dir=resources_dir,
            asar_path=asar, exe_path=exe, svc_path=svc, layout="msix"
        )

    def _find_classic(self) -> Optional[InstallPaths]:
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local, "Programs", "claude-desktop"),
            os.path.join(local, "Programs", "Claude"),
        ]
        for base in candidates:
            asar = os.path.join(base, "resources", "app.asar")
            if os.path.isfile(asar):
                exe = os.path.join(base, "claude.exe")
                if not os.path.isfile(exe):
                    exe = os.path.join(base, "Claude.exe")
                svc = os.path.join(base, "resources", "cowork-svc.exe")
                return InstallPaths(
                    base_dir=base, app_dir=base,
                    resources_dir=os.path.join(base, "resources"),
                    asar_path=asar, exe_path=exe, svc_path=svc,
                    layout="classic"
                )
        return None


# ─────────────────────────────────────────────────────────────
# Phase 1: ASAR Patcher
# ─────────────────────────────────────────────────────────────

class AsarPatcher:
    """Extract ASAR, patch JS validation functions, repack."""

    def __init__(self, asar_path: str, tmp_dir: str, logger: Logger):
        self.asar_path = asar_path
        self.tmp_dir = tmp_dir
        self.log = logger

    # ── Hash computation ──────────────────────────────────────

    @staticmethod
    def compute_hash(asar_path: str) -> str:
        """
        Compute SHA-256 hex digest of the ASAR JSON header.
        Format: skip 12 bytes, read uint32 LE (JSON size),
        read that many bytes, decode UTF-8, hash the string.
        """
        with open(asar_path, "rb") as f:
            f.seek(12)
            raw = f.read(4)
            if len(raw) < 4:
                raise ValueError("ASAR file too small")
            json_size = struct.unpack("<I", raw)[0]
            if json_size <= 0 or json_size > 10 * 1024 * 1024:
                raise ValueError(f"Abnormal ASAR header size: {json_size}")
            json_bytes = f.read(json_size)

        json_str = json_bytes.decode("utf-8")
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    # ── Extract / Pack via npx ────────────────────────────────

    def extract(self, dst: str):
        self.log.info("Extrahiere ASAR-Archiv...")
        r = subprocess.run(
            ["npx", "--yes", "@electron/asar", "extract", self.asar_path, dst],
            capture_output=True, text=True, timeout=120, shell=True
        )
        if not os.path.isdir(dst) or not os.listdir(dst):
            raise RuntimeError(f"ASAR-Extraktion fehlgeschlagen: {r.stderr.strip()}")

    def pack(self, src: str, dst: str):
        self.log.info("Packe ASAR-Archiv neu...")
        r = subprocess.run(
            ["npx", "--yes", "@electron/asar", "pack", src, dst],
            capture_output=True, text=True, timeout=120, shell=True
        )
        if not os.path.isfile(dst):
            raise RuntimeError(f"ASAR-Packing fehlgeschlagen: {r.stderr.strip()}")

    # ── JS patching (structural detection) ────────────────────

    def patch_js_files(self, extract_dir: str) -> List[str]:
        """Find and patch all home-directory validation functions."""
        results: List[str] = []
        build_dir = os.path.join(extract_dir, ".vite", "build")
        search_dir = build_dir if os.path.isdir(build_dir) else extract_dir

        js_files = glob.glob(os.path.join(search_dir, "**", "*.js"), recursive=True)
        self.log.info(f"Durchsuche {len(js_files)} JS-Dateien...")

        for js_path in js_files:
            try:
                with open(js_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            if not content or PATCH_MARKER in content:
                continue

            original = content
            basename = os.path.basename(js_path)

            # Strategy A: Sync validators (path.relative + isAbsolute + startsWith)
            content, a = self._patch_sync_validators(content, basename)
            results.extend(a)

            # Strategy B: Async wrappers (fs.realpath calls)
            content, b = self._patch_async_wrappers(content, basename)
            results.extend(b)

            # Strategy C: Inline upload/permission checks
            content, c = self._patch_inline_checks(content, basename)
            results.extend(c)

            # Strategy D: Fallback if nothing matched via structural detection
            if not a and not b and not c:
                content, count = self._fallback_patch(content, basename)
                if count > 0:
                    results.append(f"Fallback: {count} Expression(en) in {basename}")

            if content != original:
                with open(js_path, "w", encoding="utf-8") as f:
                    f.write(PATCH_MARKER + content)

        return results

    def _patch_sync_validators(self, content: str, basename: str) -> Tuple[str, List[str]]:
        """
        Find functions matching:
          function XX(t,e){const r=YY.relative(e,t);return!YY.isAbsolute(r)&&!r.startsWith("..")}

        Key: search for the structural pattern .relative( + .isAbsolute( + .startsWith("..")
        regardless of which variable name the path module is assigned to.
        """
        results: List[str] = []
        anchor_re = re.compile(
            r'\.relative\(\w+,\s*\w+\)\s*;'      # .relative(e,t);
            r'\s*return\s*!'                       # return!
            r'\w+\.isAbsolute\(\w+\)'              # XX.isAbsolute(r)
            r'\s*&&\s*!\w+\.startsWith\("\.\."'    # &&!r.startsWith(".."
        )

        # Collect matches first, then patch in reverse order to preserve positions
        matches = list(anchor_re.finditer(content))
        for match in reversed(matches):
            anchor_pos = match.start()

            # Skip TAR/archive library functions
            context_start = max(0, anchor_pos - 500)
            context_end = min(len(content), anchor_pos + 500)
            context = content[context_start:context_end]
            if "TAR_ENTRY" in context or "tar_entry" in context.lower():
                continue

            func_start = self._find_function_start(content, anchor_pos)
            if func_start is None:
                continue

            func_end = self._find_matching_brace(content, func_start)
            if func_end is None:
                continue

            func_text = content[func_start:func_end]
            name_match = re.match(r"(?:async\s+)?function\s+(\w+)", func_text)
            if not name_match:
                continue
            func_name = name_match.group(1)

            is_async = func_text.startswith("async")
            if is_async:
                replacement = f"async function {func_name}(t,e){{return true}}"
            else:
                replacement = f"function {func_name}(t,e){{return true}}"

            content = content[:func_start] + replacement + content[func_end:]

            results.append(f"Sync-Validator '{func_name}' gepatcht in {basename}")
            self.log.success(f"Sync-Validator '{func_name}' gepatcht in {basename}")

        return content, results

    def _patch_async_wrappers(self, content: str, basename: str) -> Tuple[str, List[str]]:
        """
        Find async wrappers that call a sync validator via fs.realpath:
          async function EP(t,e){return ZI(await ir.realpath(t),await ir.realpath(e))}
        """
        results: List[str] = []
        anchor_re = re.compile(
            r'\.realpath\(\w+\)\s*,\s*await\s+\w+\.realpath\(\w+\)\)'
        )

        # Collect matches first, then patch in reverse order to preserve positions
        matches = list(anchor_re.finditer(content))
        for match in reversed(matches):
            anchor_pos = match.start()

            func_start = self._find_function_start(content, anchor_pos)
            if func_start is None:
                continue

            func_end = self._find_matching_brace(content, func_start)
            if func_end is None:
                continue

            func_text = content[func_start:func_end]

            # Must be async and short (wrapper, not a complex function)
            if not func_text.startswith("async") or len(func_text) > 300:
                continue

            name_match = re.match(r"async\s+function\s+(\w+)", func_text)
            if not name_match:
                continue
            func_name = name_match.group(1)

            replacement = f"async function {func_name}(t,e){{return true}}"
            content = content[:func_start] + replacement + content[func_end:]

            results.append(f"Async-Wrapper '{func_name}' gepatcht in {basename}")
            self.log.success(f"Async-Wrapper '{func_name}' gepatcht in {basename}")

        return content, results

    def _patch_inline_checks(self, content: str, basename: str) -> Tuple[str, List[str]]:
        """
        Patch inline home-dir checks like the upload validator (b6t pattern):
          XX.isAbsolute(n)||n.startsWith("..") before a warn/error call
        """
        results: List[str] = []

        # Pattern: isAbsolute(X)||X.startsWith("..") followed by error/warn context
        # Note: \)+ handles the closing parens of both startsWith() and the if()
        inline_re = re.compile(
            r'(\w+\.isAbsolute\(\w+\)\|\|\w+\.startsWith\("\.\.")'
            r'(?=\)+\s*(?:return|&&|\|\|)\s*\w+\.(?:warn|error)\()'
        )

        for match in inline_re.finditer(content):
            # Skip TAR library contexts
            ctx_start = max(0, match.start() - 500)
            if "TAR_ENTRY" in content[ctx_start:match.end() + 200]:
                continue

            content = content[:match.start(1)] + "false" + content[match.end(1):]
            results.append(f"Inline-Check gepatcht in {basename}")
            self.log.success(f"Inline-Check gepatcht in {basename}")
            break  # Only replace once per file to avoid offset issues

        return content, results

    def _fallback_patch(self, content: str, basename: str) -> Tuple[str, int]:
        """
        Last resort: replace the boolean expression
          !XX.isAbsolute(r)&&!r.startsWith("..")
        with 'true' when .relative( appears within 200 chars before.
        """
        pattern = re.compile(
            r'!\w+\.isAbsolute\(\w+\)\s*&&\s*!\w+\.startsWith\("\.\."'
            r'(?:\))?'
        )
        count = 0
        new_content = content

        for match in pattern.finditer(content):
            region_before = content[max(0, match.start() - 200):match.start()]
            if ".relative(" not in region_before:
                continue
            # Skip TAR library
            ctx = content[max(0, match.start() - 500):match.start() + 200]
            if "TAR_ENTRY" in ctx:
                continue

            # Find the full expression including the closing paren
            full_match = match.group(0)
            if full_match.endswith(")"):
                replacement = "true)"
            else:
                replacement = "true"

            new_content = new_content[:match.start()] + replacement + new_content[match.end():]
            count += 1
            self.log.success(f"Fallback-Patch in {basename}")
            break  # One replacement per file

        return new_content, count

    # ── Brace-counting helpers ────────────────────────────────

    @staticmethod
    def _find_function_start(content: str, anchor_pos: int) -> Optional[int]:
        """Scan backwards from anchor_pos to find 'function <name>(' or 'async function <name>('."""
        search_start = max(0, anchor_pos - 500)
        region = content[search_start:anchor_pos]

        func_re = re.compile(r"(?:async\s+)?function\s+\w+\s*\(")
        last_match = None
        for m in func_re.finditer(region):
            last_match = m

        if last_match:
            return search_start + last_match.start()
        return None

    @staticmethod
    def _find_matching_brace(content: str, start: int) -> Optional[int]:
        """
        From 'start', find the first '{' and count braces to find the matching '}'.
        Handles string literals to avoid counting braces inside strings.
        Returns position AFTER the closing '}'.
        """
        brace_pos = content.find("{", start)
        if brace_pos == -1:
            return None

        depth = 0
        i = brace_pos
        # Minified JS functions can be very long; use generous limit
        limit = min(len(content), brace_pos + 100000)

        while i < limit:
            ch = content[i]

            # Skip string literals
            if ch in ('"', "'", "`"):
                i = AsarPatcher._skip_string(content, i)
                continue

            # Skip line comments
            if ch == "/" and i + 1 < limit:
                next_ch = content[i + 1]
                if next_ch == "/":
                    nl = content.find("\n", i + 2)
                    i = nl + 1 if nl != -1 else limit
                    continue
                elif next_ch == "*":
                    end = content.find("*/", i + 2)
                    i = end + 2 if end != -1 else limit
                    continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i + 1

            i += 1

        return None

    @staticmethod
    def _skip_string(content: str, pos: int) -> int:
        """Skip past a string literal. Returns position after closing quote."""
        quote = content[pos]
        i = pos + 1
        while i < len(content):
            ch = content[i]
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                return i + 1
            # Template literals can have ${...} expressions
            if quote == "`" and ch == "$" and i + 1 < len(content) and content[i + 1] == "{":
                i += 2
                depth = 1
                while i < len(content) and depth > 0:
                    if content[i] == "{":
                        depth += 1
                    elif content[i] == "}":
                        depth -= 1
                    elif content[i] == "\\":
                        i += 1
                    i += 1
                continue
            i += 1
        return i

    # ── Orchestration ─────────────────────────────────────────

    def run(self, dry_run: bool = False) -> Tuple[str, str]:
        """
        Execute Phase 1: extract, patch, repack.
        Returns (old_hash, new_hash).
        """
        old_hash = self.compute_hash(self.asar_path)
        self.log.info(f"Original-Hash: {old_hash}")

        # Clean tmp dir
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

        self.extract(self.tmp_dir)
        self.log.success("ASAR extrahiert")

        patch_results = self.patch_js_files(self.tmp_dir)

        if not patch_results:
            raise RuntimeError(
                "Keine Validierungsfunktion gefunden! "
                "Code-Muster evtl. geaendert. Bitte '--dry-run' verwenden."
            )

        self.log.success(f"{len(patch_results)} Patch(es) angewendet")

        if dry_run:
            self.log.info("Dry-Run: Keine Dateien geschrieben.")
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            return old_hash, "(dry-run)"

        tmp_asar = self.asar_path + ".new"
        self.pack(self.tmp_dir, tmp_asar)

        new_hash = self.compute_hash(tmp_asar)
        self.log.info(f"Neuer Hash: {new_hash}")

        # Replace original
        shutil.move(tmp_asar, self.asar_path)
        self.log.success("Phase 1 abgeschlossen")

        return old_hash, new_hash


# ─────────────────────────────────────────────────────────────
# Phase 2: EXE Patcher
# ─────────────────────────────────────────────────────────────

class ExePatcher:
    """Replace ASAR integrity hash in claude.exe."""

    def __init__(self, exe_path: str, logger: Logger):
        self.exe_path = exe_path
        self.log = logger

    def replace_hash(self, old_hash: str, new_hash: str) -> int:
        """
        Find all occurrences of old_hash (ASCII) in claude.exe and replace
        with new_hash. Reads from .bak for idempotency.
        Returns number of replacements.
        """
        bak = self.exe_path + ".bak"
        source = bak if os.path.isfile(bak) else self.exe_path
        self.log.info(f"Lese {os.path.basename(source)} ({os.path.getsize(source) // (1024*1024)} MB)...")

        data = bytearray(Path(source).read_bytes())
        old_bytes = old_hash.encode("ascii")
        new_bytes = new_hash.encode("ascii")

        if len(old_bytes) != len(new_bytes):
            raise RuntimeError(
                f"Hash-Laengen stimmen nicht ueberein: {len(old_bytes)} vs {len(new_bytes)}"
            )

        count = 0
        offset = 0
        while True:
            idx = data.find(old_bytes, offset)
            if idx == -1:
                break
            data[idx:idx + len(new_bytes)] = new_bytes
            offset = idx + len(new_bytes)
            count += 1
            self.log.detail(f"Hash ersetzt bei Offset 0x{idx:x}")

        if count > 0:
            self._wait_unlock(self.exe_path)
            Path(self.exe_path).write_bytes(bytes(data))
            self.log.success(f"{count} ASAR-Hash(es) in claude.exe ersetzt")
        else:
            self.log.warn("Alter Hash nicht in claude.exe gefunden!")

        return count

    @staticmethod
    def _wait_unlock(path: str, timeout: int = 20):
        for _ in range(timeout):
            try:
                with open(path, "r+b"):
                    return
            except OSError:
                time.sleep(1)
        raise RuntimeError(f"Datei '{os.path.basename(path)}' nach {timeout}s noch gesperrt.")


# ─────────────────────────────────────────────────────────────
# Phase 3: Certificate Patcher
# ─────────────────────────────────────────────────────────────

class CertPatcher:
    """Locate, replace, and re-sign certificates via PowerShell."""

    def __init__(self, svc_path: str, exe_path: str, logger: Logger):
        self.svc_path = svc_path
        self.exe_path = exe_path
        self.log = logger
        self._thumbprint: Optional[str] = None

    def _ps(self, script: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a PowerShell command and return the result."""
        return subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=timeout
        )

    # ── Find embedded certificates ────────────────────────────

    def find_embedded_certs(self, data: bytes) -> List[Tuple[int, int]]:
        """
        Find all copies of the Anthropic DER certificate in cowork-svc.exe.
        Searches for 'Anthropic, PBC' anchor, scans backwards for DER header.
        Deduplicates overlapping/nested entries, keeping only the innermost cert.
        Returns list of (offset, size) tuples.
        """
        anchor = b"Anthropic, PBC"
        raw_certs: list[tuple[int, int]] = []

        search_offset = 0
        while True:
            anchor_pos = data.find(anchor, search_offset)
            if anchor_pos == -1:
                break

            # Find ALL DER headers near this anchor (there may be nested structures)
            limit = max(0, anchor_pos - 2000)
            candidates: list[tuple[int, int]] = []
            for i in range(anchor_pos, limit, -1):
                if i + 3 >= len(data):
                    continue
                if data[i] == 0x30 and data[i + 1] == 0x82:
                    total_size = 4 + (data[i + 2] << 8 | data[i + 3])
                    if (500 < total_size < 4000
                            and i < anchor_pos
                            and (i + total_size) > anchor_pos):
                        candidates.append((i, total_size))

            # Keep only the smallest (innermost) cert for this anchor
            if candidates:
                smallest = min(candidates, key=lambda c: c[1])
                raw_certs.append(smallest)

            search_offset = anchor_pos + 1

        # Deduplicate by offset
        seen: dict[int, int] = {}
        for offset, size in raw_certs:
            if offset not in seen:
                seen[offset] = size

        return sorted(seen.items())

    # ── Get original certificate subject ──────────────────────

    def get_original_subject(self) -> str:
        bak = self.exe_path + ".bak"
        source = bak if os.path.isfile(bak) else self.exe_path
        r = self._ps(
            f'(Get-AuthenticodeSignature -FilePath "{source}").SignerCertificate.Subject'
        )
        subject = r.stdout.strip()
        if subject:
            self.log.info(f"Original-Subject: {subject}")
            return subject
        self.log.warn("Original-Subject nicht lesbar, verwende Fallback.")
        return "CN=Claude-FolderPatch"

    # ── Generate self-signed certificate ──────────────────────

    def generate_cert(self, subject: str, max_size: int, max_attempts: int = 10):
        """Generate a code-signing cert that fits within the old cert slot."""
        # Cleanup old patch certs
        self._ps(f'''
            Get-ChildItem Cert:\\LocalMachine\\My |
                Where-Object {{ $_.FriendlyName -eq "{CERT_FRIENDLY_NAME}" }} |
                Remove-Item -ErrorAction SilentlyContinue
            Get-ChildItem Cert:\\LocalMachine\\Root |
                Where-Object {{ $_.FriendlyName -eq "{CERT_FRIENDLY_NAME}" }} |
                Remove-Item -ErrorAction SilentlyContinue
        ''')

        # Escape single quotes in subject for PowerShell
        ps_subject = subject.replace("'", "''")

        for attempt in range(1, max_attempts + 1):
            self.log.info(f"Generiere Zertifikat (Versuch {attempt}/{max_attempts})...")

            r = self._ps(f'''
                $cert = New-SelfSignedCertificate `
                    -Subject '{ps_subject}' `
                    -Type CodeSigningCert `
                    -CertStoreLocation "Cert:\\LocalMachine\\My" `
                    -FriendlyName "{CERT_FRIENDLY_NAME}" `
                    -KeyAlgorithm RSA -KeyLength 2048
                "$($cert.RawData.Length)|$($cert.Thumbprint)"
            ''')

            # Parse the last line containing "|" (skip any PS warnings/progress)
            output_lines = r.stdout.strip().splitlines()
            data_line = next(
                (line for line in reversed(output_lines) if "|" in line), ""
            )
            if not data_line:
                self.log.warn(f"Zertifikat-Erstellung fehlgeschlagen: {r.stderr.strip()}")
                continue

            try:
                parts = data_line.split("|", 1)
                cert_size = int(parts[0].strip())
                thumbprint = parts[1].strip()
            except (ValueError, IndexError):
                self.log.warn(f"Unerwartete Ausgabe: {data_line}")
                continue

            if cert_size <= max_size:
                # Add to trusted root store
                self._ps(f'''
                    $cert = Get-ChildItem "Cert:\\LocalMachine\\My\\{thumbprint}"
                    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root","LocalMachine")
                    $store.Open("ReadWrite")
                    $store.Add($cert)
                    $store.Close()
                ''')
                self._thumbprint = thumbprint
                self.log.success(f"Zertifikat passt ({cert_size} <= {max_size} Bytes)")
                return
            else:
                self.log.warn(f"Zertifikat zu gross ({cert_size} > {max_size}). Neuer Versuch...")
                self._ps(f'Remove-Item "Cert:\\LocalMachine\\My\\{thumbprint}" -ErrorAction SilentlyContinue')

        raise RuntimeError(
            f"Konnte nach {max_attempts} Versuchen kein passendes Zertifikat generieren."
        )

    # ── Get cert raw bytes ────────────────────────────────────

    def get_cert_raw_bytes(self) -> bytes:
        r = self._ps(f'''
            $cert = Get-ChildItem "Cert:\\LocalMachine\\My\\{self._thumbprint}"
            [Convert]::ToBase64String($cert.RawData)
        ''')
        b64 = r.stdout.strip()
        if not b64:
            raise RuntimeError("Konnte Zertifikat-Bytes nicht lesen.")
        return base64.b64decode(b64)

    # ── Sign executable ───────────────────────────────────────

    def sign_exe(self, exe_path: str):
        self.log.info(f"Signiere {os.path.basename(exe_path)}...")
        r = self._ps(f'''
            $cert = Get-ChildItem "Cert:\\LocalMachine\\My\\{self._thumbprint}"
            $result = Set-AuthenticodeSignature -FilePath "{exe_path}" `
                -Certificate $cert -HashAlgorithm SHA256
            $result.Status
        ''')
        status = r.stdout.strip()
        if status != "Valid":
            raise RuntimeError(
                f"Signierung {os.path.basename(exe_path)} fehlgeschlagen: {status}. "
                f"Stderr: {r.stderr.strip()}"
            )
        self.log.success(f"{os.path.basename(exe_path)} signiert")

    # ── Orchestration ─────────────────────────────────────────

    def run(self):
        """Execute Phase 3: locate cert, generate replacement, swap, sign."""
        if not os.path.isfile(self.svc_path):
            self.log.warn("cowork-svc.exe nicht gefunden. Phase 3 uebersprungen.")
            return
        if not os.path.isfile(self.exe_path):
            self.log.warn("claude.exe nicht gefunden. Phase 3 uebersprungen.")
            return

        # Read from backup for idempotency
        svc_bak = self.svc_path + ".bak"
        svc_source = svc_bak if os.path.isfile(svc_bak) else self.svc_path
        svc_data = bytearray(Path(svc_source).read_bytes())

        # 1. Find all embedded certificate copies
        cert_positions = self.find_embedded_certs(bytes(svc_data))
        if not cert_positions:
            raise RuntimeError(
                "Anthropic-Zertifikat nicht in cowork-svc.exe gefunden!"
            )
        for offset, size in cert_positions:
            self.log.info(f"Zertifikat bei 0x{offset:x} ({size} Bytes)")

        # Use the smallest slot size as constraint
        min_slot = min(size for _, size in cert_positions)

        # 2. Get original subject and generate fitting cert
        subject = self.get_original_subject()
        self.generate_cert(subject, min_slot)

        # 3. Sign claude.exe first (before touching cowork-svc)
        ExePatcher._wait_unlock(self.exe_path)
        self.sign_exe(self.exe_path)

        # 4. Replace all cert copies in cowork-svc.exe
        new_cert = self.get_cert_raw_bytes()
        if len(new_cert) > min_slot:
            raise RuntimeError(
                f"Neues Zertifikat ({len(new_cert)}B) groesser als Slot ({min_slot}B). "
                f"Dies sollte nicht passieren — bitte erneut versuchen."
            )
        self.log.info(
            f"Ersetze {len(cert_positions)} Zertifikat-Kopie(n) in cowork-svc.exe "
            f"(Cert: {len(new_cert)} Bytes)..."
        )

        for offset, old_size in cert_positions:
            padded = new_cert + b"\x00" * (old_size - len(new_cert))
            svc_data[offset:offset + old_size] = padded
            self.log.detail(f"Ersetzt bei 0x{offset:x} (Padding: {old_size - len(new_cert)} Bytes)")

        ExePatcher._wait_unlock(self.svc_path)
        Path(self.svc_path).write_bytes(bytes(svc_data))
        self.log.success("Zertifikat(e) in cowork-svc.exe ersetzt")

        # 5. Sign cowork-svc.exe
        self.sign_exe(self.svc_path)

        self.log.success("Phase 3 abgeschlossen")


# ─────────────────────────────────────────────────────────────
# Patch Manager (Orchestration)
# ─────────────────────────────────────────────────────────────

class PatchManager:
    """Orchestrates all patch phases with atomic rollback."""

    def __init__(self, logger: Logger):
        self.log = logger
        self._paths: Optional[InstallPaths] = None

    # ── Admin check ───────────────────────────────────────────

    @staticmethod
    def _is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _ensure_admin(self):
        if self._is_admin():
            return

        self.log.warn("Fordere Administrator-Rechte an...")
        script = os.path.abspath(sys.argv[0])
        # Build argument list for PowerShell Start-Process
        # Quote args containing spaces, leave simple args unquoted
        parts = [f'`"{script}`"']
        for a in sys.argv[1:]:
            parts.append(f'`"{a}`"' if " " in a else a)
        args_str = " ".join(parts)
        ps_cmd = (
            f'Start-Process -FilePath "{sys.executable}" -Verb RunAs '
            f'-ArgumentList "{args_str}" -Wait'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd])
        sys.exit(0)

    # ── Prerequisites ─────────────────────────────────────────

    def _check_npx(self):
        try:
            r = subprocess.run(
                ["npx", "--version"], capture_output=True, text=True,
                timeout=15, shell=True
            )
            if r.returncode == 0:
                self.log.info(f"npx Version: {r.stdout.strip()}")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        raise RuntimeError(
            "Node.js (npx) wird benoetigt. Bitte installieren: https://nodejs.org"
        )

    # ── Service management ────────────────────────────────────

    def _stop_services(self):
        self.log.step("Stoppe Claude-Prozesse und -Dienste...")
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", '''
                $svc = Get-WmiObject Win32_Service |
                    Where-Object { $_.PathName -match "cowork-svc" }
                if ($svc) {
                    Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
                    for ($w = 0; $w -lt 10; $w++) {
                        $state = (Get-Service -Name $svc.Name -EA SilentlyContinue).Status
                        if ($state -eq 'Stopped' -or -not $state) { break }
                        Start-Sleep -Seconds 1
                    }
                }
                Stop-Process -Name "claude" -Force -ErrorAction SilentlyContinue
                Stop-Process -Name "cowork-svc" -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
                $rem = Get-Process -Name "cowork-svc" -ErrorAction SilentlyContinue
                if ($rem) {
                    Start-Sleep -Seconds 5
                    Stop-Process -Name "cowork-svc" -Force -ErrorAction SilentlyContinue
                }
            '''],
            capture_output=True, timeout=60
        )
        self.log.success("Prozesse und Dienste gestoppt")

    def _start_services(self):
        self.log.step("Starte Claude-Dienste...")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", '''
                $svc = Get-WmiObject Win32_Service |
                    Where-Object { $_.PathName -match "cowork-svc" }
                if ($svc) {
                    # Force-stop any remnants
                    Stop-Process -Name "cowork-svc" -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 2
                    Start-Service -Name $svc.Name -ErrorAction SilentlyContinue
                    for ($w = 0; $w -lt 15; $w++) {
                        $state = (Get-Service -Name $svc.Name -EA SilentlyContinue).Status
                        if ($state -eq 'Running') { break }
                        Start-Sleep -Seconds 1
                    }
                }
                try {
                    Start-Process "shell:AppsFolder\\Claude_pzs8sxrjxfjjc!Claude" -ErrorAction SilentlyContinue
                } catch {}
            '''],
            capture_output=True, timeout=60
        )
        self.log.success("Dienste gestartet")

    # ── Filesystem helpers ────────────────────────────────────

    def _take_ownership(self, path: str):
        self.log.info(f"Setze Rechte: {path}")
        subprocess.run(
            f'takeown /F "{path}" /R /D Y >nul 2>&1',
            shell=True, capture_output=True, timeout=60
        )
        subprocess.run(
            f'icacls "{path}" /grant Administrators:F /T /Q >nul 2>&1',
            shell=True, capture_output=True, timeout=60
        )

    def _create_backups(self, paths: List[str]):
        self.log.step("Erstelle Backups...")
        for p in paths:
            if not os.path.isfile(p):
                continue
            bak = p + ".bak"
            if not os.path.isfile(bak):
                shutil.copy2(p, bak)
                self.log.success(f"{os.path.basename(bak)} erstellt")
            else:
                self.log.info(f"{os.path.basename(bak)} existiert bereits")

    def _cleanup_certs(self):
        """Remove all patch certificates from the Windows certificate store."""
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f'''
                Get-ChildItem Cert:\\LocalMachine\\My |
                    Where-Object {{ $_.FriendlyName -eq "{CERT_FRIENDLY_NAME}" }} |
                    Remove-Item -ErrorAction SilentlyContinue
                Get-ChildItem Cert:\\LocalMachine\\Root |
                    Where-Object {{ $_.FriendlyName -eq "{CERT_FRIENDLY_NAME}" }} |
                    Remove-Item -ErrorAction SilentlyContinue
            '''],
            capture_output=True, timeout=30
        )

    # ── Install ───────────────────────────────────────────────

    def install(self, dry_run: bool = False):
        print(f"\n{'=' * 55}")
        print("     CLAUDE COWORK ORDNER-PATCH INSTALLIEREN")
        print(f"{'=' * 55}\n")

        self._ensure_admin()
        self._check_npx()

        self._paths = ClaudeFinder().find()
        p = self._paths
        self.log.success(f"Claude gefunden: {p.base_dir} ({p.layout})")
        self.log.info(f"ASAR: {p.asar_path}")
        self.log.info(f"EXE:  {p.exe_path}")
        self.log.info(f"SVC:  {p.svc_path}")

        if not dry_run:
            self._stop_services()

            if p.layout == "msix":
                self.log.step("Rechte setzen (MSIX)...")
                self._take_ownership(p.app_dir)
                self._take_ownership(p.resources_dir)

            self._create_backups([p.asar_path, p.exe_path, p.svc_path])

        try:
            # Phase 1: ASAR Injection
            self.log.step("Phase 1: ASAR-Injection")
            asar = AsarPatcher(p.asar_path, TMP_DIR, self.log)
            old_hash, new_hash = asar.run(dry_run=dry_run)

            if dry_run:
                print(f"\n{'=' * 55}")
                print("  DRY-RUN ABGESCHLOSSEN (keine Dateien geaendert)")
                print(f"{'=' * 55}\n")
                return

            # Phase 2: Hash Replacement
            self.log.step("Phase 2: Hash-Ersetzung in claude.exe")
            exe = ExePatcher(p.exe_path, self.log)
            exe.replace_hash(old_hash, new_hash)

            # Phase 3: Certificate Swap
            self.log.step("Phase 3: Zertifikat-Tausch")
            cert = CertPatcher(p.svc_path, p.exe_path, self.log)
            cert.run()

            # Cleanup and start
            self.log.step("Aufraeumen und Starten")
            if os.path.exists(TMP_DIR):
                shutil.rmtree(TMP_DIR, ignore_errors=True)
            self._start_services()

            print(f"\n{'=' * 55}")
            print("  PATCH ERFOLGREICH INSTALLIERT!")
            print(f"{'=' * 55}")
            print()
            print("  Netzlaufwerke und externe Ordner sind jetzt")
            print("  im Cowork Folder-Picker verfuegbar.")
            print()
            print("  HINWEIS: Nach Claude-Updates erneut ausfuehren!")
            print(f"  Log: {LOG_PATH}")
            print()

        except Exception as e:
            self.log.error(f"KRITISCHER FEHLER: {e}")
            self.log.warn("Starte automatischen Rollback...")
            self.restore(is_rollback=True)
            raise SystemExit(
                f"\nInstallation fehlgeschlagen. System auf Originalzustand zurueckgesetzt.\n"
                f"Ursache: {e}"
            )

    # ── Restore ───────────────────────────────────────────────

    def restore(self, is_rollback: bool = False):
        if not is_rollback:
            print(f"\n{'=' * 55}")
            print("     AUF ORIGINALZUSTAND ZURUECKSETZEN")
            print(f"{'=' * 55}\n")
            self._ensure_admin()

        try:
            paths = ClaudeFinder().find()
        except FileNotFoundError:
            if is_rollback:
                self.log.warn("Claude-Verzeichnis nicht gefunden.")
                return
            raise

        if not is_rollback:
            self._stop_services()

        if paths.layout == "msix":
            self._take_ownership(paths.app_dir)
            self._take_ownership(paths.resources_dir)

        self.log.info("Stelle Originaldateien wieder her...")
        restored = False
        for orig in [paths.asar_path, paths.exe_path, paths.svc_path]:
            bak = orig + ".bak"
            if os.path.isfile(bak):
                try:
                    shutil.copy2(bak, orig)
                    self.log.success(f"Wiederhergestellt: {os.path.basename(orig)}")
                    restored = True
                except OSError as e:
                    self.log.warn(f"Fehler bei {os.path.basename(orig)}: {e}")
            else:
                self.log.warn(f"Kein Backup fuer {os.path.basename(orig)}")

        self.log.info("Entferne Patch-Zertifikate...")
        self._cleanup_certs()
        self.log.success("Patch-Zertifikate entfernt")

        # Cleanup temp dir
        if os.path.exists(TMP_DIR):
            shutil.rmtree(TMP_DIR, ignore_errors=True)

        if not is_rollback:
            self._start_services()
            if restored:
                self.log.success("Wiederherstellung abgeschlossen.")
            else:
                self.log.warn("Keine Backup-Dateien gefunden.")

        if is_rollback:
            self.log.success("Rollback abgeschlossen.")

    # ── Status ────────────────────────────────────────────────

    def status(self):
        print("\n  Status-Pruefung...\n")

        try:
            paths = ClaudeFinder().find()
        except FileNotFoundError as e:
            self.log.warn(str(e))
            return

        # Extract ASAR to check for marker
        chk_dir = os.path.join(tempfile.gettempdir(), "claude_folder_patch_chk")
        if os.path.exists(chk_dir):
            shutil.rmtree(chk_dir)

        try:
            subprocess.run(
                ["npx", "--yes", "@electron/asar", "extract", paths.asar_path, chk_dir],
                capture_output=True, timeout=120, shell=True
            )

            patched = False
            for js_path in glob.glob(os.path.join(chk_dir, "**", "*.js"), recursive=True):
                try:
                    with open(js_path, "r", encoding="utf-8") as f:
                        head = f.read(len(PATCH_MARKER) + 10)
                    if PATCH_MARKER in head:
                        patched = True
                        break
                except (OSError, UnicodeDecodeError):
                    continue

            bak_exists = os.path.isfile(paths.asar_path + ".bak")

            if patched:
                print("  Status: \033[32mGEPATCHT\033[0m")
                print("  Ordner-Einschraenkung: \033[32mDEAKTIVIERT\033[0m")
            else:
                print("  Status: \033[33mORIGINAL\033[0m")
                print("  Ordner-Einschraenkung: \033[33mAKTIV\033[0m")

            print(f"  Backup vorhanden: {'Ja' if bak_exists else 'Nein'}")
            print(f"  Installation: {paths.base_dir}")
            print(f"  Layout: {paths.layout}")
            print()

        except Exception as e:
            self.log.warn(f"Status-Pruefung fehlgeschlagen: {e}")
        finally:
            if os.path.exists(chk_dir):
                shutil.rmtree(chk_dir, ignore_errors=True)


# ─────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Claude Desktop Cowork - Ordner-Patch v" + VERSION,
        epilog=(
            "Entfernt die Home-Directory-Einschraenkung im Cowork Folder-Picker.\n"
            "Erfordert: Administrator-Rechte, Node.js (npx), PowerShell 5.1+"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    install_p = sub.add_parser("install", help="Patch installieren")
    install_p.add_argument(
        "--dry-run", action="store_true",
        help="Nur analysieren, keine Dateien aendern"
    )

    sub.add_parser("restore", help="Originalzustand wiederherstellen")
    sub.add_parser("status", help="Patch-Status pruefen")

    args = parser.parse_args()
    logger = Logger(LOG_PATH)

    try:
        mgr = PatchManager(logger)

        if args.command == "install":
            mgr.install(dry_run=args.dry_run)
        elif args.command == "restore":
            mgr.restore()
        elif args.command == "status":
            mgr.status()

    except SystemExit:
        raise
    except KeyboardInterrupt:
        logger.warn("Abgebrochen durch Benutzer.")
        sys.exit(130)
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)
    finally:
        logger.close()


if __name__ == "__main__":
    main()
