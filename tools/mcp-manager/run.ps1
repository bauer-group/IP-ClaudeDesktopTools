<#
.SYNOPSIS
    One-Click Launcher fuer den MCP Server Manager.

.DESCRIPTION
    Kann lokal oder per PowerShell-Einzeiler gestartet werden:

    # Lokal (empfohlen):
    .\run.ps1

    # Remote:
    irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/mcp-manager/run.ps1 | iex

.NOTES
    Erfordert: Python 3.8+ (keine Admin-Rechte noetig)
#>

$ErrorActionPreference = "Stop"
$RepoBase = "https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main"
$ToolPath = "$RepoBase/tools/mcp-manager/mcp_manager.py"
$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "claude-mcp-manager"

# -- Pruefe Python --
$Python = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python\s+3\.") {
            $Python = $cmd
            break
        }
    } catch {}
}

if (-not $Python) {
    Write-Host ""
    Write-Host "  [X] Python 3.8+ nicht gefunden!" -ForegroundColor Red
    Write-Host "      Bitte installieren: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

# -- Finde Skript --
Write-Host ""
Write-Host "  Claude Desktop MCP Server Manager v1.0" -ForegroundColor Cyan
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""

$ScriptPath = $null

# 1. Neben dieser run.ps1 (lokale Ausfuehrung)
$LocalScript = Join-Path $PSScriptRoot "mcp_manager.py"
if ($PSScriptRoot -and (Test-Path $LocalScript)) {
    $ScriptPath = $LocalScript
    Write-Host "  [+] Lokales Skript gefunden" -ForegroundColor Green
}

# 2. GitHub-Download als Fallback
if (-not $ScriptPath) {
    $DownloadPath = Join-Path $TmpDir "mcp_manager.py"
    if (-not (Test-Path $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null }

    Write-Host "  [*] Lade von GitHub..." -ForegroundColor Gray
    try {
        Invoke-RestMethod -Uri $ToolPath -OutFile $DownloadPath
        $ScriptPath = $DownloadPath
        Write-Host "  [+] Download erfolgreich" -ForegroundColor Green
    } catch {
        Write-Host "  [X] Download fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
        pause
        exit 1
    }
}

# -- Auswahl --
Write-Host ""
Write-Host "  Aktion waehlen:" -ForegroundColor White
Write-Host "    1. MCP Server anzeigen" -ForegroundColor White
Write-Host "    2. MCP Server hinzufuegen" -ForegroundColor White
Write-Host "    3. MCP Server entfernen" -ForegroundColor White
Write-Host "    4. MCP Server testen" -ForegroundColor White
Write-Host "    5. Server exportieren" -ForegroundColor White
Write-Host "    6. Server importieren" -ForegroundColor White
Write-Host "    7. Beenden" -ForegroundColor White
Write-Host ""
$choice = Read-Host "  Auswahl (1-7)"

switch ($choice) {
    "1" { & $Python $ScriptPath "list" }
    "2" {
        $name = Read-Host "  Server-Name"
        if ($name) { & $Python $ScriptPath "add" $name }
    }
    "3" {
        & $Python $ScriptPath "list"
        $name = Read-Host "  Server-Name zum Entfernen"
        if ($name) { & $Python $ScriptPath "remove" $name }
    }
    "4" {
        & $Python $ScriptPath "list"
        $name = Read-Host "  Server-Name zum Testen"
        if ($name) { & $Python $ScriptPath "test" $name }
    }
    "5" {
        & $Python $ScriptPath "list"
        $name = Read-Host "  Server-Name zum Exportieren"
        if ($name) { & $Python $ScriptPath "export" $name }
    }
    "6" {
        $file = Read-Host "  Import-Datei (Pfad)"
        if ($file) { & $Python $ScriptPath "import" $file }
    }
    "7" { exit 0 }
    default {
        Write-Host "  Ungueltige Auswahl." -ForegroundColor Red
        pause
        exit 1
    }
}

Write-Host ""
Write-Host "  Enter zum Beenden..." -ForegroundColor Gray
pause
