<#
.SYNOPSIS
    One-Click Launcher fuer den Cowork Folder Patch.
    Nutzt das lokale Python-Skript oder laedt es von GitHub.

.DESCRIPTION
    Kann lokal oder per PowerShell-Einzeiler gestartet werden:

    # Lokal (empfohlen):
    .\run.ps1

    # Remote:
    irm https://raw.githubusercontent.com/bauer-group/IP-ClaudeDesktopTools/main/tools/cowork-folder-patch/run.ps1 | iex

.NOTES
    Erfordert: Python 3.8+, Node.js (npx), Administrator-Rechte
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

# ── Finde Patch-Skript ──
Write-Host ""
Write-Host "  Claude Cowork Folder Patch - One-Click Launcher" -ForegroundColor Cyan
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

# Strategie: Lokales Skript bevorzugen, GitHub als Fallback
$ScriptPath = $null

# 1. Neben dieser run.ps1 (lokale Ausfuehrung)
$LocalScript = Join-Path $PSScriptRoot "patch_cowork_folders.py"
if ($PSScriptRoot -and (Test-Path $LocalScript)) {
    $ScriptPath = $LocalScript
    Write-Host "  [+] Lokales Skript gefunden: $LocalScript" -ForegroundColor Green
}

# 2. GitHub-Download als Fallback (z.B. bei irm|iex)
if (-not $ScriptPath) {
    $DownloadPath = Join-Path $TmpDir "patch_cowork_folders.py"
    if (-not (Test-Path $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null }

    Write-Host "  [*] Kein lokales Skript, lade von GitHub..." -ForegroundColor Gray
    try {
        Invoke-RestMethod -Uri $ToolPath -OutFile $DownloadPath
        $ScriptPath = $DownloadPath
        Write-Host "  [+] Download erfolgreich" -ForegroundColor Green
    } catch {
        Write-Host "  [X] Download fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  [!] Tipp: run.ps1 im selben Ordner wie patch_cowork_folders.py ausfuehren" -ForegroundColor Yellow
        pause
        exit 1
    }
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
$pyArgs = @($ScriptPath) + $cmd.Split(" ")
Start-Process -FilePath $Python -ArgumentList $pyArgs -Verb RunAs -Wait

Write-Host ""
Write-Host "  Fertig. Enter zum Beenden..." -ForegroundColor Gray
pause
