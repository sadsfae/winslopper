#!/usr/bin/env python3
"""Generate setup-llama-server.ps1 embedding natureboy's router config and
chat template (with Linux -> Windows path translation), plus a PowerShell
control menu (start/stop/status) and a small .bat launcher. Deterministic."""

import hashlib
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
SRC = BASE / "src"

ini_text = (SRC / "router-config.ini").read_bytes().decode("utf-8")
jinja = (SRC / "qwen-fixed.jinja").read_bytes().decode("utf-8")

ORIGINAL_TMPL_SHA = "55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c"
tmpl_sha = hashlib.sha256(jinja.encode("utf-8")).hexdigest()
if tmpl_sha != ORIGINAL_TMPL_SHA:
    print(
        f"note: src/qwen-fixed.jinja differs from the original natureboy file (sha {tmpl_sha})"
    )

# source template has NO trailing newline; the writer trims the here-string's
# terminator newline to stay byte-exact
tmpl_has_trailing_nl = jinja.endswith("\n")
tmpl_write_rhs = '$tmplText.TrimEnd("`n")' if not tmpl_has_trailing_nl else "$tmplText"

# ported preset: translate Linux paths, keep everything else byte-identical
ported_ini = ini_text.replace("/mnt/windows/LLM_Models/", "@@MODELS@@\\")
assert "@@MODELS@@" in ported_ini
ported_ini = ported_ini.replace(
    "/home/wfoster/llm/models/qwen-fixed.jinja", "@@TEMPLATE@@"
)
assert "@@TEMPLATE@@" in ported_ini

BAT_LAUNCHER = """@echo off
setlocal
title llama-server
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0llama-server.ps1" %*
"""

MENU_PS = """# llama.cpp router control menu (port 8081)
$ErrorActionPreference = "SilentlyContinue"
$root   = $PSScriptRoot
$exe    = Join-Path $root "llama\\llama-server.exe"
$preset = Join-Path $root "llm\\models\\router-config.ini"
$port   = 8081
$health = "http://127.0.0.1:$port/health"

function Test-ServerRunning { return [bool](Get-Process -Name llama-server -ErrorAction SilentlyContinue) }
function Get-ServerHealth {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $health -TimeoutSec 3
        return ($r.StatusCode -eq 200 -and $r.Content -match '"status"\\s*:\\s*"ok"')
    } catch {
        return $false
    }
}
function Start-Server {
    if (Test-ServerRunning) { Write-Host "llama-server is already running"; return }
    if (-not (Test-Path $exe)) { Write-Host "llama-server.exe not found - run setup-llama-server.ps1 first"; return }
    Write-Host ""
    Write-Host "Starting llama-server on 0.0.0.0:$port (logs below; close this window or Ctrl+C to stop)..."
    & $exe --port $port --host 0.0.0.0 --models-preset "$preset" --models-max 1 --cache-type-k q8_0 --cache-type-v q8_0
    Write-Host ""
    Write-Host "server stopped; cleaning up any leftover model servers..."
    taskkill /IM llama-server.exe /F 2>$null | Out-Null
}
function Stop-Server {
    taskkill /IM llama-server.exe /F 2>$null | Out-Null
    Start-Sleep -Milliseconds 300
    if (Test-ServerRunning) { Write-Host "failed to stop" } else { Write-Host "stopped" }
}
function Show-Status {
    if (-not (Test-ServerRunning)) { Write-Host "stopped"; return }
    if (Get-ServerHealth) { Write-Host "running and healthy" } else { Write-Host "running (starting? health not ok yet)" }
}
if ($args.Count -gt 0) {
    switch ($args[0]) {
        "start"   { Start-Server }
        "stop"    { Stop-Server }
        "restart" { Stop-Server; Start-Server }
        "status"  { Show-Status }
        default   { Write-Host "usage: llama-server.ps1 [start|stop|restart|status]  (no args = menu)" }
    }
    exit 0
}

while ($true) {
    Write-Host ""
    Write-Host "llama.cpp router on 0.0.0.0:$port"
    Write-Host "  1) Start server - logs stream in this window; closing it stops"
    Write-Host "  2) Stop server"
    Write-Host "  3) Status"
    Write-Host "  0) Exit / close window"
    $k = Read-Host "choose [0-3]"
    switch ($k) {
        "1" { Start-Server }
        "2" { Stop-Server }
        "3" { Show-Status }
        "0" { exit 0 }
        default { Write-Host "unknown choice" }
    }
}
"""


WEBUI_SETUP_PS = r"""# Optional Open WebUI setup/upgrade: browser chat UI with tools and web
# search for the llama.cpp router (http://127.0.0.1:8081/v1). Python 3.11/3.12
# is a prerequisite (not installed by this script); everything else stays
# inside the webui\venv below. Re-running without -Upgrade is a no-op re-check.
param(
    [switch]$SkipFirewall,
    [switch]$Upgrade
)
# 'Continue' (not 'Stop'): on PowerShell 5.1 a failing native command's stderr
# becomes a terminating error under Stop and would kill this script mid-run
# (e.g. pip or a python probe). Real failures are handled via $LASTEXITCODE/throw.
$ErrorActionPreference = "Continue"
$root  = $PSScriptRoot
$webui = Join-Path $root "webui"
$venv  = Join-Path $webui "venv"
$bat   = Join-Path $root "llama-chat.bat"
$port  = 8080

function Write-Ok  ([string]$m) { Write-Host "    $m" -ForegroundColor Green }
function Write-Warn([string]$m) { Write-Host "    WARN: $m" -ForegroundColor Yellow }

# ---------------------------------------------------------------- python
# Python 3.11 or 3.12 is required for Open WebUI (its metadata refuses 3.13+).
# We do not install it here; prefer the py launcher (3.12), skip the Store stub.
$pyPath = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    $null = py -3.12 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pyPath = (py -3.12 -c "import sys; print(sys.executable)").Trim()
    } else {
        $null = py -3 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $pyPath = (py -3 -c "import sys; print(sys.executable)").Trim()
        }
    }
}
if (-not $pyPath -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $p = (python -c "import sys; print(sys.executable)").Trim()
    if ($p -and ($p -notmatch "WindowsApps")) { $pyPath = $p }
}
if (-not $pyPath) {
    Write-Warn "Python 3.11 or 3.12 is required for Open WebUI and was not found."
    Write-Warn "Install Python 3.12 (winget install Python.Python.3.12, or from python.org) and re-run."
    exit 1
}
$ver = (& $pyPath -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if ($ver -notmatch "^3\.1[12]$") {
    Write-Warn "found python $ver, but open-webui supports only Python 3.11/3.12."
    Write-Warn "Install Python 3.12, delete webui\venv if it exists, then re-run this script."
    exit 1
}
$pyPath = (Resolve-Path $pyPath).Path
Write-Ok "python: $pyPath ($ver)"

# ---------------------------------------------------------------- venv + open-webui
New-Item -ItemType Directory -Force -Path $webui | Out-Null
$venvPy = Join-Path $venv "Scripts\python.exe"
if (Test-Path $venvPy) {
    $vver = (& $venvPy -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
    if ($vver -ne $ver) {
        Write-Warn "existing webui\venv uses python $vver; removing it to rebuild with $ver..."
        Remove-Item $venv -Recurse -Force
    }
}
if (-not (Test-Path $venvPy)) {
    & $pyPath -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}
$vp = Join-Path $venv "Scripts\python.exe"
& $vp -m pip install --upgrade pip --quiet
# open-webui ships a py3-none-any wheel with the prebuilt frontend AND a
# source tarball (backend only: version 0.0.0, no UI). Always install from the
# wheel (--only-binary) and auto-repair: every run checks the current install
# and force-reinstalls from the wheel when it is missing, broken (0.0.0 / no
# frontend), or when -Upgrade is requested. The global pip cache is left alone.
$owSite = Join-Path $venv "Lib\site-packages\open_webui"
# the official wheel embeds the real UI under open_webui\frontend
# (open_webui\static only holds favicons/swagger and is always present, so it
# is not a reliable health signal).
$owSiteFrontend = Join-Path $owSite "frontend\index.html"
# Health is checked from the filesystem only - no python subprocess here: a
# missing package makes python print a traceback to stderr, which PowerShell
# 5.1 can turn into a terminating error even with 2>$null (seen on the box).
$owVer = ""
$owDist = Get-ChildItem (Join-Path $owSite "*.dist-info") -ErrorAction SilentlyContinue | Select-Object -First 1
if ($owDist) {
    $owMeta = Get-Content (Join-Path $owDist.FullName "METADATA") -ErrorAction SilentlyContinue -TotalCount 30
    $vLine = $owMeta | Where-Object { $_ -match "^Version:\s*" } | Select-Object -First 1
    if ($vLine) { $owVer = ($vLine -replace "^Version:\s*", "").Trim() }
}
$needRepair = $Upgrade -or (-not $owVer) -or ($owVer -eq "0.0.0") -or (-not (Test-Path $owSiteFrontend))
if ($needRepair) {
    $reason = "not installed or unreadable install"
    if (-not (Test-Path $owSiteFrontend)) { $reason = "missing or broken install (no frontend) - cleaning it up" }
    elseif ($owVer -eq "0.0.0") { $reason = "broken install (version 0.0.0) - cleaning it up" }
    elseif ($Upgrade) { $reason = "-Upgrade requested" }
    Write-Host "open-webui: $reason; reinstalling from the official wheel..."
    & $vp -m pip install --force-reinstall --only-binary :all: open-webui
    if ($LASTEXITCODE -ne 0) { throw "pip install open-webui failed (no wheel for this platform?)" }
} else {
    Write-Ok "open-webui already installed and healthy (v$owVer); nothing to do (use -Upgrade to update)"
}
# final sanity: the official wheel embeds the frontend and the real version.
$owVerNew = ""
$owDistNew = Get-ChildItem (Join-Path $owSite "*.dist-info") -ErrorAction SilentlyContinue | Select-Object -First 1
if ($owDistNew) {
    $owMetaNew = Get-Content (Join-Path $owDistNew.FullName "METADATA") -ErrorAction SilentlyContinue -TotalCount 30
    $vLineNew = $owMetaNew | Where-Object { $_ -match "^Version:\s*" } | Select-Object -First 1
    if ($vLineNew) { $owVerNew = ($vLineNew -replace "^Version:\s*", "").Trim() }
}
if ($owVerNew -eq "0.0.0" -or -not (Test-Path $owSiteFrontend)) {
    Write-Warn "still no healthy open-webui install (version $owVerNew); try:"
    Write-Warn "  $vp -m pip install --force-reinstall --only-binary :all: open-webui"
    exit 1
}
Write-Ok "open-webui $owVerNew with frontend OK"

# llama-chat.ps1, llama-chat.bat and the llama-chat desktop shortcut are
# already created by setup-llama-server.ps1; this script only installs the
# Python service, so nothing else is written here.

# ---------------------------------------------------------------- firewall (8080)
if (-not $SkipFirewall) {
    $ruleName = "llama-chat-$port"
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Ok "firewall rule '$ruleName' already present"
    } elseif ($isAdmin) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
        Write-Ok "added inbound firewall rule for TCP $port"
    } else {
        $helper = Join-Path $env:TEMP "winslopper-webui-firewall.ps1"
        Set-Content -Path $helper -Value "New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null" -Encoding ASCII
        Write-Host "asking for permission to open inbound TCP $port on the Windows firewall (UAC)..."
        $elv = Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$helper`"" -Wait -PassThru
        Remove-Item -Path $helper -Force -ErrorAction SilentlyContinue
        if ($elv.ExitCode -eq 0) {
            Write-Ok "added inbound firewall rule for TCP $port"
        } else {
            Write-Warn "firewall rule not added (UAC declined); add manually in an elevated PowerShell:"
            Write-Warn "New-NetFirewallRule -DisplayName llama-chat-$port -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any"
        }
    }
}

Write-Host ""
Write-Ok "Open WebUI ready. Start it any time with the llama-chat desktop icon (or llama-chat.bat)."
Write-Ok "Open http://<host-ip>:$port from any device; first run creates a local account."
Write-Ok "It talks to the router at http://127.0.0.1:8081/v1; pick an available preset as the model."
Write-Ok "Web search tools are enabled in the UI: Settings > Web Search. Close llama-chat when unused to free its ~300 MB RAM."
Write-Ok "Updating later: run .\setup-webui.ps1 -Upgrade (stays inside the venv), then in the llama-chat menu press 2 then 1."
"""

WEBUI_MENU_PS = r"""# llama-chat (Open WebUI) control menu - 1=start, 2=stop, 3=status, 0=exit
$ErrorActionPreference = "SilentlyContinue"
$root   = $PSScriptRoot
$vp     = Join-Path $root "webui\venv\Scripts\python.exe"
$port   = 8080

function Test-ChatRunning { return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
function Get-ChatProcId {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.OwningProcess }
    return $null
}
function Start-Chat {
    # 'open-webui serve' is the supported entry point: it points the frontend at
    # the wheel-shipped open_webui/frontend (invoking the module directly uses a
    # dev-only build path and serves API without UI).
    $owCli = Join-Path $root "webui\venv\Scripts\open-webui.exe"
    if (-not (Test-Path $owCli)) { Write-Host "Open WebUI is not installed yet - run setup-webui.ps1 first"; return }
    if (Test-ChatRunning) { Write-Host "llama-chat is already running"; return }
    $env:OPENAI_API_BASE_URL = "http://127.0.0.1:8081/v1"
    $env:OPENAI_API_KEY = "noop"
    # open-webui refuses to start without WEBUI_SECRET_KEY; generate it once and
    # persist it so the same session key is reused across restarts.
    if (-not $env:WEBUI_SECRET_KEY) {
        $keyFile = Join-Path $root "webui\.secret_key"
        if (Test-Path $keyFile) {
            $env:WEBUI_SECRET_KEY = (Get-Content $keyFile -Raw).Trim()
        } else {
            $env:WEBUI_SECRET_KEY = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
            Set-Content -Path $keyFile -Value $env:WEBUI_SECRET_KEY -Encoding Ascii
        }
    }
    Write-Host ""
    Write-Host "Starting Open WebUI on 0.0.0.0:$port (logs below; close this window or Ctrl+C to stop)..."
    # surface the failure stream so a crash is visible instead of silently returning
    $ErrorActionPreference = "Continue"
    & $owCli serve --host 0.0.0.0 --port $port
    $ErrorActionPreference = "SilentlyContinue"
    Write-Host "open-webui exited; cleaning up leftover process..."
    $proc = Get-ChatProcId
    if ($proc) { Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue }
}
function Stop-Chat {
    $proc = Get-ChatProcId
    if ($proc) { Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
    if (Test-ChatRunning) { Write-Host "failed to stop" } else { Write-Host "stopped" }
}
function Show-Status {
    if (Test-ChatRunning) {
        Write-Host "running (open http://127.0.0.1:$port here, or http://<host-ip>:$port from the LAN)"
    } else {
        Write-Host "stopped"
    }
}
if ($args.Count -gt 0) {
    switch ($args[0]) {
        "start"   { Start-Chat }
        "stop"    { Stop-Chat }
        "status"  { Show-Status }
        default   { Write-Host "usage: llama-chat.ps1 [start|stop|status]  (no args = menu)" }
    }
    exit 0
}
while ($true) {
    Write-Host ""
    Write-Host "llama-chat (Open WebUI) on 0.0.0.0:$port"
    Write-Host "  1) Start chat server - logs stream in this window; closing it stops"
    Write-Host "  2) Stop chat server"
    Write-Host "  3) Status"
    Write-Host "  0) Exit / close window"
    $k = Read-Host "choose [0-3]"
    switch ($k) {
        "1" { Start-Chat }
        "2" { Stop-Chat }
        "3" { Show-Status }
        "0" { exit 0 }
        default { Write-Host "unknown choice" }
    }
}
"""

WEBUI_BAT = r"""@echo off
setlocal
title llama-chat (Open WebUI)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0llama-chat.ps1" %*
"""

SD_SETUP_PS = r"""# Optional Stable Diffusion WebUI setup/upgrade: local AUTOMATIC1111
# stable-diffusion-webui service exposing a simple image generation API
# (/sdapi/v1/txt2img). Python 3.10 is a prerequisite (not installed by
# this script); everything else stays inside the sd\venv below. Re-running
# without -Upgrade is a no-op re-check.
param(
    [switch]$SkipFirewall,
    [switch]$Upgrade
)
# 'Continue' (not 'Stop'): on PowerShell 5.1 a failing native command's stderr
# becomes a terminating error under Stop and would kill this script mid-run.
$ErrorActionPreference = "Continue"
$root   = $PSScriptRoot
$sd     = Join-Path $root "sd"
$repo   = Join-Path $sd "stable-diffusion-webui"
$venv   = Join-Path $sd "venv"
$models = Join-Path $repo "models\Stable-diffusion"
$port   = 7860

function Write-Ok  ([string]$m) { Write-Host "    $m" -ForegroundColor Green }
function Write-Warn([string]$m) { Write-Host "    WARN: $m" -ForegroundColor Yellow }

# ---------------------------------------------------------------- python
# Python 3.10 is supported: AUTOMATIC1111 is tested on 3.10 and its pinned
# CUDA torch (2.1.2) ships no 3.12+ wheels. Prefer the py launcher, skip the
# Store stub.
$pyPath = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    $null = py -3.10 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pyPath = (py -3.10 -c "import sys; print(sys.executable)").Trim()
    } else {
        $null = py -3 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $pyPath = (py -3 -c "import sys; print(sys.executable)").Trim()
        }
    }
}
if (-not $pyPath -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $p = (python -c "import sys; print(sys.executable)").Trim()
    if ($p -and ($p -notmatch "WindowsApps")) { $pyPath = $p }
}
if (-not $pyPath) {
    Write-Warn "Python 3.10 is required for Stable Diffusion WebUI and was not found."
    Write-Warn "Install Python 3.10 (winget install Python.Python.3.10, or from python.org) and re-run."
    exit 1
}
$ver = (& $pyPath -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if ($ver -notmatch "^3\.10$") {
    Write-Warn "found python $ver; Stable Diffusion WebUI requires Python 3.10."
    Write-Warn "Its pinned CUDA torch (2.1.2) has no 3.12+ wheels; install Python 3.10, delete sd\venv if it exists, then re-run this script."
    exit 1
}
$pyPath = (Resolve-Path $pyPath).Path
Write-Ok "python: $pyPath ($ver)"

# ---------------------------------------------------------------- git clone
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Warn "git is required to fetch stable-diffusion-webui and was not found."
    Write-Warn "Install Git for Windows (winget install Git.Git, or git-scm.com/download/win) and re-run."
    exit 1
}
New-Item -ItemType Directory -Force -Path $sd | Out-Null
if (Test-Path (Join-Path $repo ".git")) {
    Write-Ok "stable-diffusion-webui already cloned"
    if ($Upgrade) {
        Write-Host "    pulling latest..."
        Push-Location $repo
        try { git pull --ff-only | Out-Null } finally { Pop-Location }
    }
} else {
    Write-Host "    cloning stable-diffusion-webui (a few hundred MB)..."
    git clone --depth 1 https://github.com/AUTOMATIC1111/stable-diffusion-webui.git $repo
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
}
if (-not (Test-Path (Join-Path $repo "launch.py"))) { throw "launch.py not found in $repo" }

# ---------------------------------------------------------------- venv + deps
$venvPy = Join-Path $venv "Scripts\python.exe"
if (Test-Path $venvPy) {
    $vver = (& $venvPy -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
    if ($vver -ne $ver) {
        Write-Warn "existing sd\venv uses python $vver; removing it to rebuild with $ver..."
        Remove-Item $venv -Recurse -Force
    }
}
if (-not (Test-Path $venvPy)) {
    & $pyPath -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}
$vp = Join-Path $venv "Scripts\python.exe"
& $vp -m pip install --upgrade pip wheel --quiet
# setuptools<82 still bundles pkg_resources; newer versions drop it, and the
# WebUI builds openai/CLIP and open_clip from source with pip build isolation,
# which then fails with: No module named 'pkg_resources'.
& $vp -m pip install --quiet "setuptools<82"
# Pre-build those two source packages (with --no-build-isolation) so they are
# importable and the WebUI skips its own (failing) builds of them at first launch.
& $vp -m pip install --no-build-isolation --quiet "https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip"
if ($LASTEXITCODE -ne 0) { Write-Warn "CLIP pre-build failed; the WebUI will retry it." }
& $vp -m pip install --no-build-isolation --quiet "https://github.com/mlfoundations/open_clip/archive/bb6e834e9c70d9c27d0dc3ecedeebeaeb1ffad6b.zip"
if ($LASTEXITCODE -ne 0) { Write-Warn "open_clip pre-build failed; the WebUI will retry it." }
$reqFile = Join-Path $repo "requirements.txt"
if (-not (Test-Path $reqFile)) {
    Write-Warn "no requirements.txt in $repo; the WebUI install is incomplete."
} else {
    # ready only when torch imports (and on an NVIDIA GPU) CUDA is usable; a
    # CPU-only venv left by earlier releases is repaired by this reinstall path.
    $gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -match 'NVIDIA' }
    if ($gpu) {
        $null = & $vp -c "import torch; assert torch.cuda.is_available()" 2>$null
    } else {
        $null = & $vp -c "import torch" 2>$null
    }
    $ready = ($LASTEXITCODE -eq 0)
    if ($ready -and -not $Upgrade) {
        Write-Ok "dependencies already installed"
    } else {
        Write-Host "    installing requirements (torch is large; this can take a while)..."
        # AUTOMATIC1111's requirements.txt leaves torch unpinned, so pip would
        # otherwise pull the CPU wheel from PyPI and fail the GPU check. On an
        # NVIDIA GPU install the matching CUDA build first (stock for v1.10.x).
        if ($gpu) {
            Write-Host "    NVIDIA GPU detected; installing CUDA torch..."
            & $vp -m pip install torch==2.1.2+cu121 torchvision==0.16.2+cu121 --index-url https://download.pytorch.org/whl/cu121
            if ($LASTEXITCODE -ne 0) { throw "CUDA torch install failed; re-run with internet access (download.pytorch.org) or install torch manually into sd\venv." }
        } else {
            Write-Warn "no NVIDIA GPU detected; installing CPU torch (image generation will be slow)."
        }
        & $vp -m pip install -r $reqFile
        if ($LASTEXITCODE -ne 0) { Write-Warn "pip install failed; ensure a CUDA-capable torch is available (see the README)." }
    }
}
New-Item -ItemType Directory -Force -Path $models | Out-Null

# stablediffusion.ps1, stablediffusion.bat and the desktop shortcut are
# already created by setup-llama-server.ps1; this script only installs the
# Python service, so nothing else is written here.

# ---------------------------------------------------------------- firewall (7860)
if (-not $SkipFirewall) {
    $ruleName = "stablediffusion-$port"
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Ok "firewall rule '$ruleName' already present"
    } elseif ($isAdmin) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
        Write-Ok "added inbound firewall rule for TCP $port"
    } else {
        $helper = Join-Path $env:TEMP "winslopper-sd-firewall.ps1"
        Set-Content -Path $helper -Value "New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null" -Encoding ASCII
        Write-Host "asking for permission to open inbound TCP $port on the Windows firewall (UAC)..."
        $elv = Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$helper`"" -Wait -PassThru
        Remove-Item -Path $helper -Force -ErrorAction SilentlyContinue
        if ($elv.ExitCode -eq 0) {
            Write-Ok "added inbound firewall rule for TCP $port"
        } else {
            Write-Warn "firewall rule not added (UAC declined); add it manually in an elevated PowerShell:"
            Write-Warn "New-NetFirewallRule -DisplayName stablediffusion-$port -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any"
        }
    }
}

# ---------------------------------------------------------------- checkpoint
$ckpt  = Join-Path $models "RealVisXL_V5.0_fp16.safetensors"
if (-not (Test-Path $ckpt)) {
    Write-Host "    downloading RealVisXL V5.0 (SDXL photorealism, ~7 GB, baked VAE)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -UseBasicParsing -Uri "https://huggingface.co/SG161222/RealVisXL_V5.0/resolve/main/RealVisXL_V5.0_fp16.safetensors" -OutFile $ckpt
    Write-Ok "downloaded checkpoint: $(Split-Path $ckpt -Leaf)"
} else {
    Write-Ok "checkpoint already present: $(Split-Path $ckpt -Leaf)"
}

Write-Host ""
Write-Ok "Stable Diffusion WebUI ready. Start it any time with the stablediffusion desktop icon (or stablediffusion.bat)."
Write-Ok "Default checkpoint: RealVisXL V5.0 (SDXL). Drop any other .safetensors/.ckpt into sd\stable-diffusion-webui\models\Stable-diffusion."
Write-Ok "It serves a simple image API at http://<host-ip>:$port (POST /sdapi/v1/txt2img); the browser UI is there too."
Write-Ok "Close stablediffusion when unused to free its GPU memory."
Write-Ok "Updating later: run .\\setup-stablediffusion.ps1 -Upgrade, then restart from the menu (2 then 1)."
"""

SD_MENU_PS = r"""# stablediffusion (Stable Diffusion WebUI) control menu - 1=start, 2=stop, 3=status, 0=exit
$ErrorActionPreference = "SilentlyContinue"
$root   = $PSScriptRoot
$vp     = Join-Path $root "sd\venv\Scripts\python.exe"
$repo   = Join-Path $root "sd\stable-diffusion-webui"
$port   = 7860

function Test-SdRunning { return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
function Get-SdProcId {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.OwningProcess }
    return $null
}
function Start-Sd {
    if (-not (Test-Path $vp)) { Write-Host "Stable Diffusion WebUI is not installed yet - run setup-stablediffusion.ps1 first"; return }
    if (Test-SdRunning) { Write-Host "stablediffusion is already running"; return }
    $launch = Join-Path $repo "launch.py"
    if (-not (Test-Path $launch)) { Write-Host "launch.py not found - run setup-stablediffusion.ps1 first"; return }
    Write-Host ""
    Write-Host "Starting Stable Diffusion WebUI on 0.0.0.0:$port (logs below; close this window or Ctrl+C to stop)..."
    # surface the failure stream so a crash is visible instead of silently returning
    $ErrorActionPreference = "Continue"
    & $vp $launch --api --listen --port $port
    $ErrorActionPreference = "SilentlyContinue"
    Write-Host "stablediffusion exited; cleaning up leftover process..."
    $proc = Get-SdProcId
    if ($proc) { Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue }
}
function Stop-Sd {
    $proc = Get-SdProcId
    if ($proc) { Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
    if (Test-SdRunning) { Write-Host "failed to stop" } else { Write-Host "stopped" }
}
function Show-Status {
    if (Test-SdRunning) {
        Write-Host "running (open http://127.0.0.1:$port here, or http://<host-ip>:$port from the LAN)"
    } else {
        Write-Host "stopped"
    }
}
if ($args.Count -gt 0) {
    switch ($args[0]) {
        "start"   { Start-Sd }
        "stop"    { Stop-Sd }
        "status"  { Show-Status }
        default   { Write-Host "usage: stablediffusion.ps1 [start|stop|status]  (no args = menu)" }
    }
    exit 0
}
while ($true) {
    Write-Host ""
    Write-Host "stablediffusion (Stable Diffusion WebUI) on 0.0.0.0:$port"
    Write-Host "  1) Start - logs stream in this window; closing it stops"
    Write-Host "  2) Stop"
    Write-Host "  3) Status"
    Write-Host "  0) Exit / close window"
    $k = Read-Host "choose [0-3]"
    switch ($k) {
        "1" { Start-Sd }
        "2" { Stop-Sd }
        "3" { Show-Status }
        "0" { exit 0 }
        default { Write-Host "unknown choice" }
    }
}
"""

SD_BAT = r"""@echo off
setlocal
title stablediffusion (Stable Diffusion WebUI)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stablediffusion.ps1" %*
"""

SD_DOWNLOAD_PS = r"""# Fetch a Stable Diffusion checkpoint into the models folder used by the
# stablediffusion component. Run this after setup-stablediffusion.ps1 so the
# stable-diffusion-webui repo exists. Defaults to RealVisXL V5.0 (SDXL,
# photorealism, ~7 GB, baked VAE). Idempotent: an existing file is kept unless -Force.
param(
    [string]$Url = "https://huggingface.co/SG161222/RealVisXL_V5.0/resolve/main/RealVisXL_V5.0_fp16.safetensors",
    [switch]$Force
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$root   = $PSScriptRoot
$repo   = Join-Path $root "sd\stable-diffusion-webui"
$launch = Join-Path $repo "launch.py"
$models = Join-Path $repo "models\Stable-diffusion"
if (-not (Test-Path $launch)) {
    Write-Host "    WARN: stable-diffusion-webui not found. Run .\setup-stablediffusion.ps1 first, then re-run this." -ForegroundColor Yellow
    exit 1
}
New-Item -ItemType Directory -Force -Path $models | Out-Null

$name = Split-Path $Url -Leaf
$dest = Join-Path $models $name
if (-not $Force -and (Test-Path $dest)) {
    Write-Host "    $name already present; skipping. Use -Force to re-download." -ForegroundColor Green
    exit 0
}
Write-Host "    downloading $name (a few GB) from $Url ..."
Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $dest
Write-Host "    saved $dest" -ForegroundColor Green
Write-Host "    start stablediffusion and it will use this model."
"""

assert "'@" not in BAT_LAUNCHER and "'@" not in MENU_PS and "'@" not in WEBUI_SETUP_PS
assert "'@" not in WEBUI_MENU_PS and "'@" not in WEBUI_BAT
assert "'@" not in SD_SETUP_PS and "'@" not in SD_MENU_PS and "'@" not in SD_BAT
assert "'@" not in SD_DOWNLOAD_PS
assert "'@" not in jinja and "'@" not in ported_ini, "here-string terminator collision"
assert all(
    ord(c) < 128
    for c in (BAT_LAUNCHER + MENU_PS + WEBUI_SETUP_PS + WEBUI_MENU_PS + WEBUI_BAT
              + SD_SETUP_PS + SD_MENU_PS + SD_BAT + SD_DOWNLOAD_PS)
), "menu/launcher/webui/sd must be pure ASCII"


def ps_here_string(label, body):
    # single-quoted here-string; terminator '@ at column 0.
    # A PS here-string's value is the text between the delimiters plus one
    # trailing newline, so strip exactly one newline to round-trip verbatim.
    body = body.rstrip("\n") + "\n"
    return f"${label} = @'\n{body[:-1]}\n'@"


launcher_var = ps_here_string("batText", BAT_LAUNCHER)
menu_var = ps_here_string("menuText", MENU_PS)
webui_var = ps_here_string("webuiText", WEBUI_SETUP_PS)
webui_menu_var = ps_here_string("webuiMenuText", WEBUI_MENU_PS)
webui_bat_var = ps_here_string("webuiBatText", WEBUI_BAT)
sd_var = ps_here_string("sdText", SD_SETUP_PS)
sd_menu_var = ps_here_string("sdMenuText", SD_MENU_PS)
sd_bat_var = ps_here_string("sdBatText", SD_BAT)
sd_download_var = ps_here_string("sdDlText", SD_DOWNLOAD_PS)
tmpl_var = ps_here_string("tmplText", jinja)
preset_var = ps_here_string("presetText", ported_ini)

PS = r"""#Requires -Version 5.1
<#
.SYNOPSIS
    Idempotent Windows setup for the llama.cpp router server (port 8081) --
    a port of natureboy's systemd unit + router preset + Qwen chat template.

.DESCRIPTION
    Creates, inside this script's own folder:

      .\llama\                       llama-server.exe + CUDA 13.3 DLLs (pulled
                                     from the llama.cpp GitHub CUDA 13.3 Windows
                                     nightly build; or copied from -LlamaZip)
      .\llm\models\router-config.ini router preset, same as natureboy's file,
                                     with Windows paths
      .\llm\models\qwen-fixed.jinja  chat template, byte-identical to natureboy
      .\llama-server.bat             launcher -> opens the control menu
      .\llama-server.ps1             control menu: 1=start, 2=stop, 3=status,
                                     0=exit (also subcommands)
      .\REMOVE_ME_TO_UPGRADE         upgrade lock (created after first install)
      desktop shortcut               llama-server.lnk -> llama-server.bat
      .\setup-webui.ps1              optional: installs Open WebUI (needs
                                     Python 3.x, used only in webui\venv)
      .\llama-chat.bat / .ps1        optional llama-chat menu (Open WebUI on
                                     port 8080) + desktop icon llama-chat.lnk
      .\setup-stablediffusion.ps1    optional: installs Stable Diffusion WebUI
                                     (needs Python 3.x, used only in sd\venv)
      .\stablediffusion.bat / .ps1   optional stablediffusion menu (Stable
                                     Diffusion WebUI on port 7860, exposes a
                                     simple /sdapi/v1/txt2img API) + desktop
                                     icon stablediffusion.lnk
      .\Download-Model.ps1           optional: downloads a Stable Diffusion
                                     checkpoint into sd\...\models\Stable-diffusion

    Menu behaviour:
      Option 1 runs llama-server in this same console window: its logs stream
      to the window, and closing the window or Ctrl+C stops the server (any
      child model servers are cleaned up afterwards). So a permanently open
      window = a running server, exactly like a foreground systemd service.

    Nightly / upgrade lock:
      The first successful install downloads a llama.cpp nightly zip, extracts
      it into .\llama\ and creates .\REMOVE_ME_TO_UPGRADE. While that file
      exists, the script does NOT check for or download any newer nightly and
      makes no network calls. Delete REMOVE_ME_TO_UPGRADE and re-run the
      script to upgrade in place: the latest nightly is resolved from the
      GitHub API (or use -Build to pin a specific build), binaries are
      replaced, and the lock file is re-created.

    systemd -> Windows mapping:
      Type=simple, ExecStart ...        menu option 1 (foreground console)
      Restart=always / RestartSec=10    no equivalent; close window / option 2
      LimitMEMLOCK=infinity             N/A (no memory lock; router mode does
                                        not use --mlock)
      WantedBy=default.target          put llama-server.bat (or a shortcut to
                                       "llama-server.ps1 start") in
                                       shell:startup to auto-start at logon

    Idempotent: safe to re-run. Download/extract is skipped when the same build
    marker is present (-Force to redo); config/template/launcher/menu are
    regenerated deterministically on every run.

.PARAMETER Build
    llama.cpp nightly build tag. Default b10786, used for the first install.
    When REMOVE_ME_TO_UPGRADE is missing and no -Build is passed, the latest
    nightly is resolved automatically. Pass -Build explicitly to pin a
    specific build for an upgrade. Download URL becomes
    https://github.com/ggml-org/llama.cpp/releases/download/<Build>/llama-<Build>-bin-win-cuda-13.3-x64.zip

.PARAMETER LlamaZip
    Path to a locally downloaded llama-*-bin-win-cuda-13.3-x64.zip. When set,
    that zip is used instead of downloading. Pair it with -LlamaCudartZip:
    the CUDA runtime DLLs (cudart/cublas) ship in a separate llama.cpp asset,
    and without them llama-server silently runs on CPU.

.PARAMETER ModelsDir
    Directory containing the GGUF models (natureboy's /mnt/windows/LLM_Models).
    Default: C:\LLM_Models

.PARAMETER InstallDir
    Persistent install directory. Defaults to the script's own folder. The
    self-extracting release EXE passes %USERPROFILE%\winslopper,
    because the installer extracts to a temp directory that is deleted afterwards.

.PARAMETER Force
    Re-download / re-extract the llama.cpp build even if already installed.

.PARAMETER SkipFirewall
    Do not create the inbound firewall rule for TCP 8081.

.PARAMETER NoShortcut
    Do not create the desktop shortcut.

.EXAMPLE
    .\setup-llama-server.ps1
    .\setup-llama-server.ps1 -Build b10786
    .\setup-llama-server.ps1 -LlamaZip C:\Downloads\llama-b10786-bin-win-cuda-13.3-x64.zip
    .\setup-llama-server.ps1 -ModelsDir D:\LLM_Models
#>
param(
    [string]$Build      = "b10786",
    [string]$LlamaZip   = "",
    [string]$LlamaCudartZip = "",
    [string]$ModelsDir  = "C:\LLM_Models",
    [string]$InstallDir = "",
    [switch]$Force,
    [switch]$SkipFirewall,
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$root     = $(if ($InstallDir) { $InstallDir } else { $PSScriptRoot })
$llamaDir = Join-Path $root "llama"
$llmDir   = Join-Path $root "llm\models"
$dlDir    = Join-Path $root "downloads"
$exe      = Join-Path $llamaDir "llama-server.exe"
$preset   = Join-Path $llmDir "router-config.ini"
$tmpl     = Join-Path $llmDir "qwen-fixed.jinja"
$marker   = Join-Path $llamaDir ".llama-version"
$lockFile = Join-Path $root "REMOVE_ME_TO_UPGRADE"
$batFile  = Join-Path $root "llama-server.bat"
$menuFile = Join-Path $root "llama-server.ps1"
$webuiFile = Join-Path $root "setup-webui.ps1"
$sdFile = Join-Path $root "setup-stablediffusion.ps1"
$sdDlFile = Join-Path $root "Download-Model.ps1"
$tmplSha  = "__TM_PLSHA__"
$svcPort  = 8081
$ModelsDir = $ModelsDir.TrimEnd("\")

function Write-Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok  ([string]$m) { Write-Host "    $m" -ForegroundColor Green }
function Write-Warn([string]$m) { Write-Host "    WARN: $m" -ForegroundColor Yellow }

New-Item -ItemType Directory -Force -Path $llamaDir, $llmDir, $dlDir | Out-Null

# ---------------------------------------------------------------- llama.cpp
$lockExists = (Test-Path $lockFile)
$haveExe    = (Test-Path $exe)
$installed  = ""
if (Test-Path $marker) { $installed = (Get-Content $marker -Raw).Trim() }

$target = $Build
$reason = ""
if ($haveExe -and $lockExists) {
    $reason = "locked by REMOVE_ME_TO_UPGRADE; keeping installed build"
} elseif ($haveExe -and -not $lockExists -and -not $Force) {
    $reason = "upgrade requested (REMOVE_ME_TO_UPGRADE removed)"
    if ($PSBoundParameters.ContainsKey("Build")) {
        Write-Host "    explicit -Build given: upgrading to $target"
    } else {
        Write-Host "    resolving latest nightly from GitHub..."
        try {
            $relHeaders = @{ "User-Agent" = "llama-server-setup" }
            if ($env:GITHUB_TOKEN) { $relHeaders["Authorization"] = "token $($env:GITHUB_TOKEN)" }
            $rel = @(Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10" -Headers $relHeaders -TimeoutSec 20)
            $latest = $rel | Where-Object { $_.tag_name -match "^b\d+$" } | Select-Object -First 1 -ExpandProperty tag_name
            if ($latest) {
                $target = $latest
                Write-Host "    latest nightly: $target"
            } else {
                Write-Warn "could not resolve latest nightly tag; using $Build"
            }
        } catch {
            Write-Warn "GitHub lookup failed ($($_.Exception.Message)); using $Build"
        }
    }
} else {
    $reason = $(if ($Force) { "forced reinstall" } else { "first install" })
}

Write-Step "llama.cpp target: $target (CUDA 13.3, Windows x64) [$reason]"
$needInstall = $Force -or (-not $haveExe) -or ($installed -ne $target)
if (-not $needInstall) {
    Write-Ok "already installed ($target); skipping download/extract"
} else {
    $zipName = "llama-$target-bin-win-cuda-13.3-x64.zip"
    $zipUrl  = "https://github.com/ggml-org/llama.cpp/releases/download/$target/$zipName"
    $zipPath = ""
    if ($LlamaZip) {
        if (-not (Test-Path $LlamaZip)) { throw "Provided -LlamaZip not found: $LlamaZip" }
        $zipPath = $LlamaZip
        Write-Host "    using provided zip: $zipPath"
    } else {
        $zipPath = Join-Path $dlDir $zipName
        if ((Test-Path $zipPath) -and -not $Force) {
            Write-Host "    using cached zip: $zipPath"
        } else {
            Write-Host "    downloading $zipUrl"
            Invoke-WebRequest -UseBasicParsing -Uri $zipUrl -OutFile $zipPath
            Write-Ok "downloaded $((Get-Item $zipPath).Length) bytes"
        }
    }

    $staging = Join-Path $dlDir "staging-$target"
    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $staging -Force

    $serverExe = Get-ChildItem -Path $staging -Recurse -Filter llama-server.exe | Select-Object -First 1
    if (-not $serverExe) { throw "llama-server.exe not found inside $zipPath" }
    $payload = $serverExe.DirectoryName

    # The CUDA runtime DLLs (cudart/cublas/cublasLt) ship in a separate asset.
    # Without them ggml-cuda.dll cannot load and the server silently runs on
    # CPU. They must sit next to llama-server.exe (DLL loader search path).
    $cudartName = "cudart-llama-bin-win-cuda-13.3-x64.zip"
    $cudartZip = ""
    if ($LlamaCudartZip) {
        if (-not (Test-Path $LlamaCudartZip)) { throw "Provided -LlamaCudartZip not found: $LlamaCudartZip" }
        $cudartZip = $LlamaCudartZip
        Write-Host "    using provided cudart zip: $cudartZip"
    } else {
        $cudartZip = Join-Path $dlDir $cudartName
        if ((Test-Path $cudartZip) -and -not $Force) {
            Write-Host "    using cached cudart zip: $cudartZip"
        } else {
            $cudartUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$target/$cudartName"
            Write-Host "    downloading $cudartUrl"
            Invoke-WebRequest -UseBasicParsing -Uri $cudartUrl -OutFile $cudartZip
            Write-Ok "downloaded $((Get-Item $cudartZip).Length) bytes"
        }
    }
    if ($cudartZip) {
        $cudartDir = Join-Path $dlDir "cudart-$target"
        if (Test-Path $cudartDir) { Remove-Item $cudartDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $cudartDir | Out-Null
        Expand-Archive -Path $cudartZip -DestinationPath $cudartDir -Force
        $runtimeDlls = Get-ChildItem -Path $cudartDir -Recurse | Where-Object { $_.Name -match "^(cudart64_|cublas64_|cublasLt64_).*\.dll$" }
        if (-not $runtimeDlls) { Write-Warn "no cudart/cublas DLLs found in $cudartZip" }
        $runtimeDlls | Copy-Item -Destination $payload -Force
        Remove-Item $cudartDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Ok "CUDA runtime DLLs placed next to llama-server.exe"
    }

    if (Test-Path $llamaDir) { Remove-Item $llamaDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $llamaDir | Out-Null
    Copy-Item -Path (Join-Path $payload "*") -Destination $llamaDir -Recurse -Force
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue

    if (-not (Test-Path $exe)) { throw "llama-server.exe missing after extraction" }
    Set-Content -Path $marker -Value $target -Encoding Ascii -NoNewline
    Write-Ok "installed $target to $llamaDir"

    if (-not $lockExists) {
        New-Item -ItemType File -Path $lockFile -Force | Out-Null
        Set-Content -Path $lockFile -Value "Delete this file to let setup-llama-server.ps1 download the latest llama.cpp nightly and replace the binaries." -Encoding Ascii
        Write-Ok "created $lockFile (delete it to enable nightly upgrades)"
    }
}

# ------------------------------------------------------- router preset + template
Write-Step "Writing router preset and chat template"
__PRESET_PS__
$presetText = $presetText.Replace('@@MODELS@@', $ModelsDir).Replace('@@TEMPLATE@@', $tmpl)
[IO.File]::WriteAllText($preset, $presetText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $preset"

__TMPL_PS__
[IO.File]::WriteAllText($tmpl, __TMPL_WRITE__, (New-Object System.Text.UTF8Encoding($false)))
$sha = (Get-FileHash -Algorithm SHA256 -Path $tmpl).Hash.ToLower()
if ($sha -ne $tmplSha) { Write-Warn "template hash $sha != expected $tmplSha" }
else { Write-Ok "template verified (SHA256 $tmplSha)" }

# ---------------------------------------------------------------- models
Write-Step "Checking models under $ModelsDir"
$missing = @()
foreach ($line in ($presetText -split "`r?`n")) {
    $t = $line.TrimStart()
    if ($t.StartsWith("#") -or $t.StartsWith(";") -or $t -notmatch '^(model|mmproj)\s*=') { continue }
    $p = ($t -split "=", 2)[1].Trim()
    if ($p -and -not (Test-Path -LiteralPath $p)) { $missing += $p }
}
if ($missing.Count -eq 0) { Write-Ok "all models present" }
else { foreach ($m in $missing) { Write-Warn "missing: $m" } }

# ---------------------------------------------------------------- launcher + menu
Write-Step "Generating llama-server.bat launcher and control menu"
__BAT_LAUNCHER_PS__
[IO.File]::WriteAllText($batFile, ($batText -replace "`r?`n", "`r`n"), (New-Object System.Text.ASCIIEncoding))
Write-Ok "wrote $batFile"
__MENU_PS__
[IO.File]::WriteAllText($menuFile, $menuText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $menuFile"

__WEBUI_SETUP_PS__
[IO.File]::WriteAllText($webuiFile, $webuiText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $webuiFile (optional Open WebUI installer; run it for the browser chat with tools)"
__WEBUI_MENU_PS__
[IO.File]::WriteAllText((Join-Path $root "llama-chat.ps1"), $webuiMenuText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote llama-chat.ps1 (Open WebUI menu: 1=start, 2=stop, 3=status, 0=exit)"
__WEBUI_BAT_PS__
[IO.File]::WriteAllText((Join-Path $root "llama-chat.bat"), ($webuiBatText -replace "`r?`n", "`r`n"), (New-Object System.Text.ASCIIEncoding))
Write-Ok "wrote llama-chat.bat (opens the llama-chat menu)"

__SD_SETUP_PS__
[IO.File]::WriteAllText($sdFile, $sdText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $sdFile (optional Stable Diffusion WebUI installer; run it for the simple image API)"
__SD_MENU_PS__
[IO.File]::WriteAllText((Join-Path $root "stablediffusion.ps1"), $sdMenuText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote stablediffusion.ps1 (Stable Diffusion WebUI menu: 1=start, 2=stop, 3=status, 0=exit)"
__SD_BAT_PS__
[IO.File]::WriteAllText((Join-Path $root "stablediffusion.bat"), ($sdBatText -replace "`r?`n", "`r`n"), (New-Object System.Text.ASCIIEncoding))
Write-Ok "wrote stablediffusion.bat (opens the stablediffusion menu)"
__SD_DOWNLOAD_PS__
[IO.File]::WriteAllText($sdDlFile, $sdDlText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $sdDlFile (optional: downloads a Stable Diffusion checkpoint; run .\Download-Model.ps1)"

if (-not $NoShortcut) {
    $lnkPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "llama-server.lnk"
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($lnkPath)
    $lnk.TargetPath = $batFile
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
    $lnk.Description = "llama.cpp router server on port $svcPort"
    $lnk.Save()
    Write-Ok "desktop shortcut: $lnkPath"

    $chatLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "llama-chat.lnk"
    $cl = $ws.CreateShortcut($chatLnk)
    $cl.TargetPath = Join-Path $root "llama-chat.bat"
    $cl.WorkingDirectory = $root
    $cl.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
    $cl.Description = "Open WebUI chat for the llama.cpp router (port 8080)"
    $cl.Save()
    Write-Ok "desktop shortcut: $chatLnk"

    $sdLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "stablediffusion.lnk"
    $sl = $ws.CreateShortcut($sdLnk)
    $sl.TargetPath = Join-Path $root "stablediffusion.bat"
    $sl.WorkingDirectory = $root
    $sl.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
    $sl.Description = "Stable Diffusion WebUI simple image API (port 7860)"
    $sl.Save()
    Write-Ok "desktop shortcut: $sdLnk"
}

# ---------------------------------------------------------------- firewall
# Add the inbound rule for LAN access. Requires elevation, so when setup is
# not running as admin it launches a tiny elevated helper (one UAC prompt)
# that creates only this rule; -SkipFirewall skips this stage entirely.
if (-not $SkipFirewall) {
    $ruleName = "llama-server-$svcPort"
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Ok "firewall rule '$ruleName' already present"
    } elseif ($isAdmin) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $svcPort -Action Allow -Profile Any | Out-Null
        Write-Ok "added inbound firewall rule for TCP $svcPort"
    } else {
        $helper = Join-Path $env:TEMP "winslopper-firewall-$([guid]::NewGuid().ToString('N')).ps1"
        Set-Content -Path $helper -Value "New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Protocol TCP -LocalPort $svcPort -Action Allow -Profile Any | Out-Null" -Encoding ASCII
        Write-Host "asking for permission to open inbound TCP $svcPort on the Windows firewall (UAC)..."
        $elv = Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$helper`"" -Wait -PassThru
        Remove-Item -Path $helper -Force -ErrorAction SilentlyContinue
        if ($elv.ExitCode -eq 0) {
            Write-Ok "added inbound firewall rule for TCP $svcPort"
        } else {
            Write-Warn "firewall rule not added (UAC declined); add it manually in an elevated PowerShell:"
            Write-Warn "New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $svcPort -Action Allow -Profile Any"
        }
    }
}

# ---------------------------------------------------------------- summary
Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  Run     : .\llama-server.bat  (opens the control menu)"
Write-Host "  Menu    : 1 = start server (logs stream in the window), 2 = stop, 3 = status, 0 = exit"
Write-Host "  Close   : closing the window or Ctrl+C stops the server"
Write-Host "  Direct  : .\llama-server.ps1 start|stop|restart|status"
Write-Host "  Health  : http://127.0.0.1:$svcPort/health"
Write-Host "  WebUI   : optional browser chat with tools - install Python 3.x, run .\setup-webui.ps1, then use the llama-chat icon"
Write-Host "  SD      : optional simple image API - install Python 3.10, run .\setup-stablediffusion.ps1 (downloads RealVisXL V5.0), use the stablediffusion icon"
Write-Host "  Config  : $preset"
Write-Host "  Upgrade : delete $lockFile and re-run this script to update llama.cpp"
Write-Host "  Auto-start at logon: put a shortcut to $batFile in shell:startup"
"""

PS = (
    PS.replace("__PRESET_PS__", preset_var, 1)
    .replace("__TMPL_PS__", tmpl_var, 1)
    .replace("__TMPL_WRITE__", tmpl_write_rhs, 1)
    .replace("__BAT_LAUNCHER_PS__", launcher_var, 1)
    .replace("__MENU_PS__", menu_var, 1)
    .replace("__WEBUI_SETUP_PS__", webui_var, 1)
    .replace("__WEBUI_MENU_PS__", webui_menu_var, 1)
    .replace("__WEBUI_BAT_PS__", webui_bat_var, 1)
    .replace("__SD_SETUP_PS__", sd_var, 1)
    .replace("__SD_MENU_PS__", sd_menu_var, 1)
    .replace("__SD_BAT_PS__", sd_bat_var, 1)
    .replace("__SD_DOWNLOAD_PS__", sd_download_var, 1)
    .replace("__TM_PLSHA__", tmpl_sha, 1)
)

out = BASE / "setup-llama-server.ps1"
# BOM + LF bytes, identical on every platform (write_text would
# translate \n to CRLF on Windows and break byte-exact verification)
out.write_bytes(b"\xef\xbb\xbf" + PS.encode("utf-8"))
if any(ord(c) > 127 for c in PS):
    raise SystemExit("generated script is not pure ASCII; check embedded content")
print(f"wrote {out} ({out.stat().st_size} bytes)")
