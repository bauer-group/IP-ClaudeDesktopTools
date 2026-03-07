<#
.SYNOPSIS
    One-Click Launcher fuer Config Backup & Restore.

.DESCRIPTION
    Kann lokal oder per PowerShell-Einzeiler gestartet werden:

    # Lokal (empfohlen):
    .\run.ps1

    # Remote:
    irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/config-sync/run.ps1 | iex

.NOTES
    Erfordert: Python 3.8+ (keine Admin-Rechte noetig)
#>

$ErrorActionPreference = "Stop"
$RepoBase = "https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main"
$ToolPath = "$RepoBase/tools/config-sync/config_sync.py"
$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "claude-config-sync"

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
Write-Host "  Claude Config Backup & Restore v1.0" -ForegroundColor Cyan
Write-Host "  =====================================" -ForegroundColor Cyan
Write-Host ""

$ScriptPath = $null

# 1. Neben dieser run.ps1 (lokale Ausfuehrung)
$LocalScript = Join-Path $PSScriptRoot "config_sync.py"
if ($PSScriptRoot -and (Test-Path $LocalScript)) {
    $ScriptPath = $LocalScript
    Write-Host "  [+] Lokales Skript gefunden" -ForegroundColor Green
}

# 2. GitHub-Download als Fallback
if (-not $ScriptPath) {
    $DownloadPath = Join-Path $TmpDir "config_sync.py"
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
Write-Host "    1. Backup erstellen" -ForegroundColor White
Write-Host "    2. Backup wiederherstellen" -ForegroundColor White
Write-Host "    3. Aenderungen anzeigen (diff)" -ForegroundColor White
Write-Host "    4. Backups auflisten" -ForegroundColor White
Write-Host "    5. Beenden" -ForegroundColor White
Write-Host ""
$choice = Read-Host "  Auswahl (1-5)"

switch ($choice) {
    "1" { & $Python $ScriptPath "backup" }
    "2" {
        & $Python $ScriptPath "list"
        $backup = Read-Host "  Backup-Name oder Pfad"
        if ($backup) { & $Python $ScriptPath "restore" $backup }
    }
    "3" {
        & $Python $ScriptPath "list"
        $backup = Read-Host "  Backup-Name oder Pfad"
        if ($backup) { & $Python $ScriptPath "diff" $backup }
    }
    "4" { & $Python $ScriptPath "list" }
    "5" { exit 0 }
    default {
        Write-Host "  Ungueltige Auswahl." -ForegroundColor Red
        pause
        exit 1
    }
}

Write-Host ""
Write-Host "  Enter zum Beenden..." -ForegroundColor Gray
pause
