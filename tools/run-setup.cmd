@echo off
setlocal
rem Runs inside the SFX extraction dir (deleted after this exits), so the
rem setup script installs to a persistent directory instead of this one.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-llama-server.ps1" -InstallDir "%USERPROFILE%\winslopper_RTX5090TI" -LlamaZip "%~dp0llama.zip"
