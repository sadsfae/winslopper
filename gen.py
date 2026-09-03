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
$webui  = "http://127.0.0.1:$port"

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
    if (Get-ServerHealth) { Write-Host "running and healthy ($webui)" } else { Write-Host "running (starting? health not ok yet)" }
}
function Show-WebChat {
    if (-not (Test-ServerRunning)) { Write-Host "llama-server is not running - start it first (option 1)"; return }
    if (-not (Get-ServerHealth)) { Write-Host "server is up but not healthy yet (still loading); wait a moment and retry"; return }
    Write-Host ""
    Write-Host "Opening web chat: $webui" -ForegroundColor Green
    Write-Host "  pick model 'qwen-chat' in the dropdown; the UI is served by llama-server itself"
    Start-Process $webui
}

if ($args.Count -gt 0) {
    switch ($args[0]) {
        "start"   { Start-Server }
        "stop"    { Stop-Server }
        "restart" { Stop-Server; Start-Server }
        "status"  { Show-Status }
        "web"     { Show-WebChat }
        default   { Write-Host "usage: llama-server.ps1 [start|stop|restart|status|web]  (no args = menu)" }
    }
    exit 0
}

while ($true) {
    Write-Host ""
    Write-Host "llama.cpp router on 0.0.0.0:$port"
    Write-Host "  1) Start server - logs stream in this window; closing it stops"
    Write-Host "  2) Stop server"
    Write-Host "  3) Status"
    Write-Host "  4) Open web chat: $webui (needs the server running)"
    Write-Host "  0) Exit / close window"
    $k = Read-Host "choose [0-4]"
    switch ($k) {
        "1" { Start-Server }
        "2" { Stop-Server }
        "3" { Show-Status }
        "4" { Show-WebChat }
        "0" { exit 0 }
        default { Write-Host "unknown choice" }
    }
}
"""


assert "'@" not in BAT_LAUNCHER and "'@" not in MENU_PS
assert "'@" not in jinja and "'@" not in ported_ini, "here-string terminator collision"
assert all(
    ord(c) < 128 for c in (BAT_LAUNCHER + MENU_PS)
), "menu/launcher must be pure ASCII"


def ps_here_string(label, body):
    # single-quoted here-string; terminator '@ at column 0.
    # A PS here-string's value is the text between the delimiters plus one
    # trailing newline, so strip exactly one newline to round-trip verbatim.
    body = body.rstrip("\n") + "\n"
    return f"${label} = @'\n{body[:-1]}\n'@"


launcher_var = ps_here_string("batText", BAT_LAUNCHER)
menu_var = ps_here_string("menuText", MENU_PS)
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
                                     4=web chat, 0=exit (also subcommands)
      .\REMOVE_ME_TO_UPGRADE         upgrade lock (created after first install)
      desktop shortcut               llama-server.lnk -> llama-server.bat

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
    } elseif (-not $LlamaZip) {
        $cudartZip = Join-Path $dlDir $cudartName
        if ((Test-Path $cudartZip) -and -not $Force) {
            Write-Host "    using cached cudart zip: $cudartZip"
        } else {
            $cudartUrl = "https://github.com/ggml-org/llama.cpp/releases/download/$target/$cudartName"
            Write-Host "    downloading $cudartUrl"
            Invoke-WebRequest -UseBasicParsing -Uri $cudartUrl -OutFile $cudartZip
            Write-Ok "downloaded $((Get-Item $cudartZip).Length) bytes"
        }
    } else {
        Write-Warn "no cudart runtime zip available; the server will run on CPU unless the CUDA runtime DLLs are already present"
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
Write-Host "  Menu    : 1 = start server (logs stream in the window), 2 = stop, 3 = status, 4 = web chat, 0 = exit"
Write-Host "  Close   : closing the window or Ctrl+C stops the server"
Write-Host "  Direct  : .\llama-server.ps1 start|stop|restart|status|web"
Write-Host "  Health  : http://127.0.0.1:$svcPort/health"
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
    .replace("__TM_PLSHA__", tmpl_sha, 1)
)

out = BASE / "setup-llama-server.ps1"
# BOM + LF bytes, identical on every platform (write_text would
# translate \n to CRLF on Windows and break byte-exact verification)
out.write_bytes(b"\xef\xbb\xbf" + PS.encode("utf-8"))
if any(ord(c) > 127 for c in PS):
    raise SystemExit("generated script is not pure ASCII; check embedded content")
print(f"wrote {out} ({out.stat().st_size} bytes)")
