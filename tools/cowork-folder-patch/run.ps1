<#
.SYNOPSIS
    One-Click Launcher fuer den Cowork Folder Bypass.

.DESCRIPTION
    Kann lokal oder per PowerShell-Einzeiler gestartet werden:

    # Lokal (empfohlen):
    .\run.ps1

    # Remote:
    irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/cowork-folder-patch/run.ps1 | iex

.NOTES
    Erfordert: Python 3.8+ (keine Admin-Rechte noetig)
#>

$ErrorActionPreference = "Stop"
$RepoBase = "https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main"
$ToolPath = "$RepoBase/tools/cowork-folder-patch/patch_cowork_folders.py"
$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "claude-folder-patch"

# ── Pruefe Python ──
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

# ── Finde Bypass-Skript ──
Write-Host ""
Write-Host "  Claude Cowork Folder Bypass v5.1" -ForegroundColor Cyan
Write-Host "  =================================" -ForegroundColor Cyan
Write-Host ""

$ScriptPath = $null

# 1. Neben dieser run.ps1 (lokale Ausfuehrung)
$LocalScript = Join-Path $PSScriptRoot "patch_cowork_folders.py"
if ($PSScriptRoot -and (Test-Path $LocalScript)) {
    $ScriptPath = $LocalScript
    Write-Host "  [+] Lokales Skript gefunden" -ForegroundColor Green
}

# 2. GitHub-Download als Fallback
if (-not $ScriptPath) {
    $DownloadPath = Join-Path $TmpDir "patch_cowork_folders.py"
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

# ── Auswahl ──
Write-Host ""
Write-Host "  Aktion waehlen:" -ForegroundColor White
Write-Host "    1. Bypass installieren (DevTools + Anleitung)" -ForegroundColor White
Write-Host "    2. Bypass entfernen" -ForegroundColor White
Write-Host "    3. Status pruefen" -ForegroundColor White
Write-Host "    4. Beenden" -ForegroundColor White
Write-Host ""
$choice = Read-Host "  Auswahl (1-4)"

switch ($choice) {
    "1" { & $Python $ScriptPath "install" }
    "2" { & $Python $ScriptPath "restore" }
    "3" { & $Python $ScriptPath "status" }
    "4" { exit 0 }
    default {
        Write-Host "  Ungueltige Auswahl." -ForegroundColor Red
        pause
        exit 1
    }
}

Write-Host ""
Write-Host "  Enter zum Beenden..." -ForegroundColor Gray
pause
