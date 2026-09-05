#Requires -Version 5.1
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
$tmplSha  = "55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c"
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
$presetText = @'
; ============================================================
; winslopper router-config.ini  (Windows host .123)
;
; Standardized on Qwen3.8-27B-OBLITERATED for BOTH hosts so the
; fallback is behaviorally identical: same weights, same template,
; same sampling profile. Only the ctx and offload depth differ.
;
; Windows boot profile is tuned to coexist with OBS replay buffer,
; EverQuest (P99) and Discord. Ctx 16k keeps the KV cache small
; (~2.3GB q8) so it lives in system RAM and offload depth is
; moderate so the game and DWM keep VRAM.
;
; NOTE: paths below are the /mnt/windows mount as seen from the
; Linux host. If this file runs natively on Windows, change them
; to the local drive (e.g. C:\LLM_Models\...\*.gguf) and point
; chat-template-file at the qwen-fixed.jinja copy on this host.
; ============================================================

; ------------------------------------------------------------
; Primary agent model: SAME qwen as Linux, Windows profile
; ------------------------------------------------------------
[omp-agent]
model = @@MODELS@@\Qwen3.8-27B-OBLITERATED-Q4_K_M.gguf
; smaller ctx so KV fits alongside running apps
ctx-size = 16384
; moderate offload (~87% of layers), leaves ~9GB VRAM for apps.
; raise to 99 only when not gaming.
ngl = 56
flash-attn = on
; Enable Jinja engine FIRST, then pass the template
jinja = on
chat-template-file = @@TEMPLATE@@
; disable reasoning traces so agent tool-call parsers don't choke
reasoning = off
; OBLITERAT-ed base is text-only; mmproj would load but can't be
; used and costs VRAM. Keep commented unless you switch to a
; genuinely multimodal checkpoint.
;mmproj = @@MODELS@@\mmproj-model-bf16.gguf

; ------------------------------------------------------------
; opencode-agent: same weights, same profile, same single model
; loaded. Two names but one file, so no load-swap cost.
; ------------------------------------------------------------
[opencode-agent]
model = @@MODELS@@\Qwen3.8-27B-OBLITERATED-Q4_K_M.gguf
ctx-size = 16384
ngl = 56
flash-attn = on
jinja = on
chat-template-file = @@TEMPLATE@@
reasoning = off

; ------------------------------------------------------------
; OPTIONAL extra flavors. Loaded on demand only, and each load
; swaps out the Qwen slot, so only use when you actually want
; that personality. Not part of the agent fallback path.
; ------------------------------------------------------------

[dolphin-heavy]
model = @@MODELS@@\Dolphin3.0-Mistral-24B-Q4_K_M.gguf
fit = on
ngl = 32
flash-attn = on
jinja = on

[dolphin-reasoning]
model = @@MODELS@@\Dolphin3.0-R1-Mistral-24B-Q4_K_M.gguf
fit = on
ngl = 99
flash-attn = on

[dolphin-light]
model = @@MODELS@@\dolphin-2.9-llama3-8b-Q5_K_M.gguf
fit = on
ngl = 99
flash-attn = on
jinja = on
'@
$presetText = $presetText.Replace('@@MODELS@@', $ModelsDir).Replace('@@TEMPLATE@@', $tmpl)
[IO.File]::WriteAllText($preset, $presetText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $preset"

$tmplText = @'
{%- set image_count = namespace(value=0) %}
{%- set video_count = namespace(value=0) %}
{%- macro render_content(content, do_vision_count, is_system_content=false) %}
    {%- if content is string %}
        {{- content }}
    {%- elif content is iterable and content is not mapping %}
        {%- for item in content %}
            {%- if 'image' in item or 'image_url' in item or item.type == 'image' %}
                {%- if is_system_content %}
                    {{- raise_exception('System message cannot contain images.') }}
                {%- endif %}
                {%- if do_vision_count %}
                    {%- set image_count.value = image_count.value + 1 %}
                {%- endif %}
                {%- if add_vision_id %}
                    {{- 'Picture ' ~ image_count.value ~ ': ' }}
                {%- endif %}
                {{- '<|vision_start|><|image_pad|><|vision_end|>' }}
            {%- elif 'video' in item or item.type == 'video' %}
                {%- if is_system_content %}
                    {{- raise_exception('System message cannot contain videos.') }}
                {%- endif %}
                {%- if do_vision_count %}
                    {%- set video_count.value = video_count.value + 1 %}
                {%- endif %}
                {%- if add_vision_id %}
                    {{- 'Video ' ~ video_count.value ~ ': ' }}
                {%- endif %}
                {{- '<|vision_start|><|video_pad|><|vision_end|>' }}
            {%- elif 'text' in item %}
                {{- item.text }}
            {%- else %}
                {{- raise_exception('Unexpected item type in content.') }}
            {%- endif %}
        {%- endfor %}
    {%- elif content is none or content is undefined %}
        {{- '' }}
    {%- else %}
        {{- raise_exception('Unexpected content type.') }}
    {%- endif %}
{%- endmacro %}
{%- if not messages %}
    {{- raise_exception('No messages provided.') }}
{%- endif %}
{%- set num_sys = 0 %}
{%- set merged_system = '' %}
{%- if messages[0].role == 'system' or messages[0].role == 'developer' %}
    {%- set first = render_content(messages[0].content, false, true)|trim %}
    {%- if messages|length > 1 and (messages[1].role == 'system' or messages[1].role == 'developer') %}
        {%- set second = render_content(messages[1].content, false, true)|trim %}
        {%- set merged_system = first + '\n' + second %}
        {%- set num_sys = 2 %}
    {%- else %}
        {%- set merged_system = first %}
        {%- set num_sys = 1 %}
    {%- endif %}
{%- endif %}
{%- if tools and tools is iterable and tools is not mapping %}
    {{- '<|im_start|>system\n' }}
    {{- "# Tools\n\nYou have access to the following functions:\n\n<tools>" }}
    {%- for tool in tools %}
        {{- "\n" }}
        {{- tool | tojson }}
    {%- endfor %}
    {{- "\n</tools>" }}
    {{- '\n\nIf you choose to call a function ONLY reply in the following format with NO suffix:\n\n<tool_call>\n<function=example_function_name>\n<parameter=example_parameter_1>\nvalue_1\n</parameter>\n<parameter=example_parameter_2>\nThis is the value for the second parameter\nthat can span\nmultiple lines\n</parameter>\n</function>\n</tool_call>\n\n<IMPORTANT>\nReminder:\n- Function calls MUST follow the specified format: an inner <function=...></function> block must be nested within <tool_call></tool_call> XML tags\n- Required parameters MUST be specified\n- You may provide optional reasoning for your function call in natural language BEFORE the function call, but NOT after\n- If there is no function call available, answer the question like normal with your current knowledge and do not tell the user about function calls\n</IMPORTANT>' }}
    {%- if merged_system %}
        {{- '\n\n' + merged_system }}
    {%- endif %}
    {{- '<|im_end|>\n' }}
{%- else %}
    {%- if merged_system %}
        {{- '<|im_start|>system\n' + merged_system + '<|im_end|>\n' }}
    {%- endif %}
{%- endif %}
{%- set ns = namespace(multi_step_tool=true, last_query_index=messages|length - 1) %}
{%- for message in messages[::-1] %}
    {%- set index = (messages|length - 1) - loop.index0 %}
    {%- if ns.multi_step_tool and message.role == "user" %}
        {%- set content = render_content(message.content, false)|trim %}
        {%- if not(content.startswith('<tool_response>') and content.endswith('</tool_response>')) %}
            {%- set ns.multi_step_tool = false %}
            {%- set ns.last_query_index = index %}
        {%- endif %}
    {%- endif %}
{%- endfor %}
{%- for message in messages %}
    {%- if loop.index0 >= num_sys and message.role != "system" and message.role != "developer" %}
    {%- set content = render_content(message.content, true)|trim %}
    {%- if message.role == "user" %}
        {{- '<|im_start|>' + message.role + '\n' + content + '<|im_end|>' + '\n' }}
    {%- elif message.role == "assistant" %}
        {%- set reasoning_content = '' %}
        {%- if message.reasoning_content is string %}
            {%- set reasoning_content = message.reasoning_content %}
        {%- else %}
            {%- if '</think>' in content %}
                {%- set reasoning_content = content.split('</think>')[0].rstrip('\n').split('<think>')[-1].lstrip('\n') %}
                {%- set content = content.split('</think>')[-1].lstrip('\n') %}
            {%- endif %}
        {%- endif %}
        {%- set reasoning_content = reasoning_content|trim %}
        {%- if (preserve_thinking is defined and preserve_thinking is true) or (loop.index0 > ns.last_query_index) %}
            {{- '<|im_start|>' + message.role + '\n<think>\n' + reasoning_content + '\n</think>\n\n' + content }}
        {%- else %}
            {{- '<|im_start|>' + message.role + '\n' + content }}
        {%- endif %}
        {%- if message.tool_calls and message.tool_calls is iterable and message.tool_calls is not mapping %}
            {%- for tool_call in message.tool_calls %}
                {%- if tool_call.function is defined %}
                    {%- set tool_call = tool_call.function %}
                {%- endif %}
                {%- if loop.first %}
                    {%- if content|trim %}
                        {{- '\n\n<tool_call>\n<function=' + tool_call.name + '>\n' }}
                    {%- else %}
                        {{- '<tool_call>\n<function=' + tool_call.name + '>\n' }}
                    {%- endif %}
                {%- else %}
                    {{- '\n<tool_call>\n<function=' + tool_call.name + '>\n' }}
                {%- endif %}
                {%- if tool_call.arguments is mapping %}
                    {%- for args_name in tool_call.arguments %}
                        {%- set args_value = tool_call.arguments[args_name] %}
                        {{- '<parameter=' + args_name + '>\n' }}
                        {%- set args_value = args_value | tojson | safe if args_value is mapping or (args_value is sequence and args_value is not string) else args_value | string %}
                        {{- args_value }}
                        {{- '\n</parameter>\n' }}
                    {%- endfor %}
                {%- endif %}
                {{- '</function>\n</tool_call>' }}
            {%- endfor %}
        {%- endif %}
        {{- '<|im_end|>\n' }}
    {%- elif message.role == "tool" %}
        {%- if loop.previtem and loop.previtem.role != "tool" %}
            {{- '<|im_start|>user' }}
        {%- endif %}
        {{- '\n<tool_response>\n' }}
        {{- content }}
        {{- '\n</tool_response>' }}
        {%- if not loop.last and loop.nextitem.role != "tool" %}
            {{- '<|im_end|>\n' }}
        {%- elif loop.last %}
            {{- '<|im_end|>\n' }}
        {%- endif %}
    {%- endif %}
    {%- endif %}
{%- endfor %}
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {%- if enable_thinking is defined and enable_thinking is false %}
        {{- '<think>\n\n</think>\n\n' }}
    {%- else %}
        {{- '<think>\n' }}
    {%- endif %}
{%- endif %}
{#- Unsloth fixes - developer role, tool calling #}
'@
[IO.File]::WriteAllText($tmpl, $tmplText.TrimEnd("`n"), (New-Object System.Text.UTF8Encoding($false)))
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
$batText = @'
@echo off
setlocal
title llama-server
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0llama-server.ps1" %*
'@
[IO.File]::WriteAllText($batFile, ($batText -replace "`r?`n", "`r`n"), (New-Object System.Text.ASCIIEncoding))
Write-Ok "wrote $batFile"
$menuText = @'
# llama.cpp router control menu (port 8081)
$ErrorActionPreference = "SilentlyContinue"
$root   = $PSScriptRoot
$exe    = Join-Path $root "llama\llama-server.exe"
$preset = Join-Path $root "llm\models\router-config.ini"
$port   = 8081
$health = "http://127.0.0.1:$port/health"

function Test-ServerRunning { return [bool](Get-Process -Name llama-server -ErrorAction SilentlyContinue) }
function Get-ServerHealth {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $health -TimeoutSec 3
        return ($r.StatusCode -eq 200 -and $r.Content -match '"status"\s*:\s*"ok"')
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
'@
[IO.File]::WriteAllText($menuFile, $menuText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $menuFile"

$webuiText = @'
# Optional Open WebUI setup/upgrade: browser chat UI with tools and web
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
'@
[IO.File]::WriteAllText($webuiFile, $webuiText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote $webuiFile (optional Open WebUI installer; run it for the browser chat with tools)"
$webuiMenuText = @'
# llama-chat (Open WebUI) control menu - 1=start, 2=stop, 3=status, 0=exit
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
'@
[IO.File]::WriteAllText((Join-Path $root "llama-chat.ps1"), $webuiMenuText, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "wrote llama-chat.ps1 (Open WebUI menu: 1=start, 2=stop, 3=status, 0=exit)"
$webuiBatText = @'
@echo off
setlocal
title llama-chat (Open WebUI)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0llama-chat.ps1" %*
'@
[IO.File]::WriteAllText((Join-Path $root "llama-chat.bat"), ($webuiBatText -replace "`r?`n", "`r`n"), (New-Object System.Text.ASCIIEncoding))
Write-Ok "wrote llama-chat.bat (opens the llama-chat menu)"

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
Write-Host "  Config  : $preset"
Write-Host "  Upgrade : delete $lockFile and re-run this script to update llama.cpp"
Write-Host "  Auto-start at logon: put a shortcut to $batFile in shell:startup"
