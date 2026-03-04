<#
.SYNOPSIS
    One-Click Launcher fuer den Cowork Folder Patch.
    Laedt das Python-Skript aus dem GitHub-Repository und fuehrt es aus.

.DESCRIPTION
    Kann direkt aus dem Browser oder per PowerShell-Einzeiler gestartet werden:

    irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/cowork-folder-patch/run.ps1 | iex

.NOTES
    Erfordert: Python 3.8+, Node.js (npx), Administrator-Rechte
#>

$ErrorActionPreference = "Stop"
$RepoBase = "https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main"
$ToolPath = "$RepoBase/tools/cowork-folder-patch/patch_cowork_folders.py"
$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "claude-folder-patch"
$ScriptPath = Join-Path $TmpDir "patch_cowork_folders.py"

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

# ── Pruefe Node.js ──
try {
    $npxVer = npx --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "npx fehlt" }
} catch {
    Write-Host ""
    Write-Host "  [X] Node.js (npx) nicht gefunden!" -ForegroundColor Red
    Write-Host "      Bitte installieren: https://nodejs.org" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

# ── Lade Skript ──
Write-Host ""
Write-Host "  Claude Cowork Folder Patch - One-Click Launcher" -ForegroundColor Cyan
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null }

Write-Host "  [*] Lade Patch-Skript von GitHub..." -ForegroundColor Gray
try {
    Invoke-RestMethod -Uri $ToolPath -OutFile $ScriptPath
} catch {
    Write-Host "  [X] Download fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    pause
    exit 1
}

# ── Auswahl ──
Write-Host ""
Write-Host "  Aktion waehlen:" -ForegroundColor White
Write-Host "    1. Patch installieren" -ForegroundColor White
Write-Host "    2. Patch entfernen (Originalzustand)" -ForegroundColor White
Write-Host "    3. Status pruefen" -ForegroundColor White
Write-Host "    4. Nur analysieren (Dry-Run)" -ForegroundColor White
Write-Host "    5. Beenden" -ForegroundColor White
Write-Host ""
$choice = Read-Host "  Auswahl (1-5)"

$cmd = switch ($choice) {
    "1" { "install" }
    "2" { "restore" }
    "3" { "status" }
    "4" { "install --dry-run" }
    "5" { exit 0 }
    default { Write-Host "  Ungueltige Auswahl." -ForegroundColor Red; pause; exit 1 }
}

# ── Ausfuehren (mit Elevation) ──
Write-Host ""
$args = @($ScriptPath) + $cmd.Split(" ")
Start-Process -FilePath $Python -ArgumentList $args -Verb RunAs -Wait

Write-Host ""
Write-Host "  Fertig. Enter zum Beenden..." -ForegroundColor Gray
pause
