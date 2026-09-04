# winslopper

[![Build](https://github.com/sadsfae/winslopper/actions/workflows/release-sfx.yml/badge.svg)](https://github.com/sadsfae/winslopper/actions/workflows/release-sfx.yml)
[![Release](https://img.shields.io/github/v/release/sadsfae/winslopper)](https://github.com/sadsfae/winslopper/releases/latest)
[![Windows](https://img.shields.io/badge/Windows-10%2B-0078D6?logo=windows&logoColor=white)](https://learn.microsoft.com/en-us/powershell/)

> Targets an NVIDIA RTX 3090 TI only llama.cpp setup on Linux.

Windows port of natureboy's llama.cpp router setup (systemd unit + router preset + Qwen chat template). Runs the llama.cpp router on port 8081 with the same `router-config.ini` and `qwen-fixed.jinja`, controlled from a small PowerShell menu in a normal console window. No service, no auto-start: you run it on demand, and closing the window stops the server.

## Table of Contents

- [Requirements](#requirements)
- [Repository layout](#repository-layout)
- [Setup](#setup)
- [One-click release EXE](#one-click-release-exe)
- [Running the server on demand](#running-the-server-on-demand)
- [Menu](#menu)
- [CLI subcommands](#cli-subcommands)
- [Open WebUI chat (optional)](#open-webui-chat-optional)
- [Interface preview](#interface-preview)
- [Upgrading llama.cpp](#upgrading-llama-cpp)
- [Firewall](#firewall)
- [systemd mapping](#systemd-mapping)
- [Troubleshooting](#troubleshooting)
- [Source files and making changes](#source-files-and-making-changes)
- [License](#license)

## Requirements

- Windows 10 (target 21H2), PowerShell 5.1 (built in). No Python, no nssm, no extra tools for the router itself; the optional Open WebUI chat needs Python 3.11/3.12 (see below).
- An NVIDIA RTX 3090 TI with a driver that supports CUDA 13.3.
- The GGUF models on the Windows disk at `C:\LLM_Models`. These are the same files Linux sees at `/mnt/windows/LLM_Models` (same physical disk, mounted by Linux for inference).
- No internet needed for the release EXE: the llama.cpp CUDA 13.3 binaries and the CUDA runtime are embedded in it (~540 MB). The folder-based setup downloads both on first run (about 540 MB together) unless you supply them with `-LlamaZip` / `-LlamaCudartZip`.

## Repository layout

```
setup-llama-server.ps1      main installer, idempotent, run on Windows
gen.py                      regenerates setup-llama-server.ps1 from src/ (build-time only)
docs/                       interface mockup image + generator
src/                        exact originals from natureboy
tools/                      run-setup.cmd (release EXE entry point), verify.py (CI gate)
```

What the setup script creates inside the folder you copy:

```
llama/                      llama-server.exe + CUDA 13.3 DLLs
llm/models/router-config.ini
llm/models/qwen-fixed.jinja
llama-server.bat            launcher
llama-server.ps1            control menu
REMOVE_ME_TO_UPGRADE        upgrade lock
llama-server.lnk            desktop shortcut (created by setup)
setup-webui.ps1             optional Open WebUI installer (run it once)
llama-chat.bat / .ps1       optional llama-chat menu (Open WebUI on 8080)
llama-chat.lnk              desktop shortcut for the llama-chat menu
```

## Setup

1. Copy this folder to Windows as one folder (it is relocatable; paths regenerate on re-run).
2. Confirm the models are present at `C:\LLM_Models`.
3. Open PowerShell in the folder and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup-llama-server.ps1
   ```

   Optional flags:

   - `-LlamaZip C:\path\llama-bXXXXXn-bin-win-cuda-13.3-x64.zip` reuses a zip you already downloaded instead of downloading.
   - `-LlamaCudartZip C:\path\cudart-llama-bin-win-cuda-13.3-x64.zip` supplies the CUDA runtime DLLs (cudart/cublas/cublasLt) when installing from a folder; the release EXE bundles them. Setup downloads them automatically on the folder path if not provided. They are required for GPU inference (without them llama-server silently runs on CPU).
   - `-ModelsDir D:\LLM_Models` if the models live elsewhere.
   - `-Build bXXXXX` to pick a specific nightly for the first install.
   - `-SkipFirewall` / `-NoShortcut` to skip the firewall rule / desktop shortcut.
   - Run from an elevated PowerShell if you want the inbound firewall rule created.

   Re-running is safe (idempotent): the build is skipped when unchanged, and the config, template, launcher and menu are rewritten deterministically.

## One-click release EXE

Pushing a tag (`v*`) triggers the `release-sfx.yml` GitHub Actions workflow: it regenerates and verifies the setup script, downloads the pinned llama.cpp CUDA 13.3 zip, verifies its SHA-256 against the GitHub API, and packs the binaries zip, the CUDA runtime DLLs zip, and the setup script into a self-extracting EXE (~540 MB) with IExpress (built into Windows, no third-party extractor). Running the EXE extracts to a temporary folder, opens a console window that streams the setup log, installs to `%USERPROFILE%\winslopper` (unelevated), then cleans up temporary files. When the inbound firewall rule is missing, setup asks once via UAC whether to open TCP 8081 for LAN access (`-SkipFirewall` or declining skips it). The result behaves exactly like the folder install. Downloads and the plain `.ps1` remain the manual alternative.

SmartScreen: the EXE is unsigned, so Windows shows "Windows protected your PC" once (More info > Run anyway). This is expected for personal builds; a paid code-signing certificate is the only way to suppress it. Always compare the published SHA-256 before running, and prefer running the `.ps1` path if you distrust the artifact.

## Running the server on demand

No service and no auto-start. Run it when you need it:

- Double-click the `llama-server` shortcut on your desktop (created by setup; uses the PowerShell system icon), or
- Double-click `llama-server.bat`, or
- Run `.\llama-server.bat` from a terminal.

A console window opens with the menu. Option 1 starts the router in that same window and its logs stream there. Close the window or press Ctrl+C and the server stops.

Chat from any device on the LAN (phone, etc.): while the router is running, open `http://<host-ip>:8081/` in a browser and pick `qwen-chat` in the model dropdown. Same address works on the host as `http://127.0.0.1:8081/`.

Point OpenAI-compatible clients (omp, opencode, etc.) at `http://127.0.0.1:8081/v1` with model `omp-agent`, `opencode-agent` or `qwen-chat`.

## Menu

```
llama.cpp router on 0.0.0.0:8081
  1) Start server - logs stream in this window; closing it stops
  2) Stop server
  3) Status
  0) Exit / close window
choose [0-3]: 1
```

- `1` starts the router in this window. The first request to a model loads it (10 to 40 seconds).
- `2` stops it immediately (the router and any child model servers).
- `3` shows `running ({"status":"ok"})` or `stopped`.
- `0` closes the window.

## CLI subcommands

```powershell
.\llama-server.ps1 start | stop | restart | status
```

## Open WebUI chat (optional)

ChatGPT-like browser chat with tools (web search) for the LAN, backed by the router's Qwen3 preset. Open WebUI is the UI; llama.cpp stays the engine.

One-time setup (does not affect the router; skip it entirely to stay Python-free):

1. Install **Python 3.11 or 3.12** on the Windows host (`winget install Python.Python.3.12`, or from [python.org](https://www.python.org/downloads/)). Newer Pythons (3.13/3.14) are not supported by open-webui.
2. Make sure `setup-webui.ps1` is in the install folder (it is generated by every setup run; an EXE from v1.0.5 onward installs it).
3. Run `.\setup-webui.ps1` once. It creates `webui\venv`, installs open-webui, and asks once via UAC to open inbound TCP 8080 for LAN access (`-SkipFirewall` skips the rule). Re-running is safe; a venv built with the wrong Python is rebuilt automatically. All Python and pip activity stays strictly inside `webui\venv` (`webui\venv\Scripts\python.exe -m pip`), so your system Python is never touched.

Daily use:

- Double-click the `llama-chat` desktop icon. Its own persistent terminal window shows a menu: 1 start the chat server (logs stream in the window), 2 stop, 3 status, 0 exit; closing the window also stops it. Nothing runs until you start it.
- With the router running, open `http://<host-ip>:8080` from any device; first run creates a local account. The UI talks to the router at `http://127.0.0.1:8081/v1` with model `qwen-chat`; enable Web Search under Settings > Web Search for tool calls.
- Updating Open WebUI: run `.\setup-webui.ps1 -Upgrade` (upgrades it inside `webui\venv`; pip never touches your system Python), then restart the chat from the menu (2 then 1). A plain re-run of `setup-webui.ps1` does not update anything - use `-Upgrade`. The manual equivalent, if you prefer (or your install predates the `-Upgrade` switch):
- Open WebUI must come from the official wheel (it embeds the web frontend). A source install shows `v0.0.0` and runs in API-only mode; fix it with:
  ```
  %USERPROFILE%\winslopper\webui\venv\Scripts\python.exe -m pip install --force-reinstall --only-binary :all: open-webui
  ```
  ```
  %USERPROFILE%\winslopper\webui\venv\Scripts\python.exe -m pip install -U open-webui
  ```
- Stopped = ~0 CPU and memory; running it costs about 300 MB RAM plus the router's GPU load when chatting.
- Without this, the simpler fallback is the router's own web page at `http://<host-ip>:8081/` (no Python, no tools).

## Interface preview

![llama-server control menu mockup](docs/interface-mockup.png)

## Upgrading llama.cpp

- While `REMOVE_ME_TO_UPGRADE` exists, setup never checks for a newer nightly and makes no network calls.
- To upgrade, delete `REMOVE_ME_TO_UPGRADE` and re-run setup. It resolves the latest nightly from the GitHub API (or use `-Build bXXXXX` to pin one), replaces `llama\`, and re-creates the lock.
- `-Force` reinstalls the current build.

## Firewall

- The server binds `0.0.0.0:8081`. For localhost use no rule is needed.
- Setup creates the inbound rule itself: it asks once via UAC when it is not already running elevated (`-SkipFirewall` skips this). If the prompt is declined, or you prefer a rule scoped to your LAN only, run this in an elevated PowerShell (right-click > Run as administrator):
  ```powershell
  New-NetFirewallRule -DisplayName "llama-server TCP 8081" -Direction Inbound -Protocol TCP -LocalPort 8081 -Action Allow -Profile Private
  ```
  Then test from another machine with `Test-NetConnection <host-ip> -Port 8081`. If it still fails, check your router's AP/client isolation.
- No authentication and no API key: any client that can reach port 8081 can use the router. Keep the rule scoped to a trusted network (the Private profile above).

## systemd mapping

| systemd (Linux unit)               | Windows equivalent                        |
| ---------------------------------- | ----------------------------------------- |
| `Type=simple` + `ExecStart`        | menu option 1 (foreground console)        |
| `Restart=always` / `RestartSec=10` | none; closing the window stops it         |
| `LimitMEMLOCK=infinity`            | none (router mode does not use `--mlock`) |
| `WantedBy=default.target`          | none; run on demand via the shortcut      |

## Troubleshooting

- Models reported missing: setup prints the missing paths; check `-ModelsDir`.
- Windows Firewall prompt on first start: click Allow, or run setup elevated for the rule.
- Port 8081 already in use: the router fails to bind; find and stop the other process.
- "llama-server is already running": a leftover process; use menu option 2, close the window, or `taskkill /IM llama-server.exe /F`.
- Health check: `http://127.0.0.1:8081/health`.

## Source files and making changes

- `src/router-config.ini` and `src/qwen-fixed.jinja` are the Linux originals from natureboy and the source of truth. Edit them, run `python3 gen.py`, then commit both the edited `src/` file and the regenerated `setup-llama-server.ps1`.
- `gen.py` translates `/mnt/windows/LLM_Models/...` to the Windows models dir and `/home/wfoster/llm/models/qwen-fixed.jinja` to the local template path, embeds both byte-for-byte, and stamps the template SHA into the script. The Windows setup writes them out and verifies the written template against that SHA, so edits in `src/` flow through automatically.
- `src/llama-server.service`: the original systemd unit, reference only (not consumed by `gen.py`).

## License

This repository is MIT licensed (see `LICENSE`), matching the license of the llama.cpp binaries it redistributes. Third-party components used by the release EXE (the llama.cpp binaries and the Qwen chat template) are covered in `THIRD_PARTY_NOTICES.md`. The EXE itself is assembled with the IExpress self-extractor that ships with Windows.
