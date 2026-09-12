# Bundled Python Windows installers

These are the last official **Windows 64-bit installers** that python.org shipped
for Python 3.11 and 3.12. After these, both series moved to source-only
security releases (no binary installer is built anymore). They are vendored here
so a Stable Diffusion / Open WebUI install never depends on a python.org file
being online.

Always install Python from python.org, never from a third-party repackaged
build. Verify the SHA-256 below matches before running.

| File | Version | Source | SHA-256 |
| ---- | ------- | ------ | ------- |
| `python-3.11.9-amd64.exe` | 3.11.9 (last 3.11 installer) | https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe | `5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde` |
| `python-3.12.9-amd64.exe` | 3.12.9 (last 3.12 installer) | https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe | `2a52993092a19cfdffe126e2eeac46a4265e25705614546604ad44988e040c0f` |

Notes:

- The WebUI components accept Python 3.11 or 3.12. Prefer **3.12** (`python-3.12.9-amd64.exe`); Python 3.13+ is not supported by the WebUI.
- Both files are about 26 MB each.
- These are the installer files, not Python itself. Run the installer (check "Add python.exe to PATH" and "Use the Python launcher for Windows") to install, then re-run the relevant `setup-*.ps1`.

Recompute with:

```sh
sha256sum python-3.11.9-amd64.exe python-3.12.9-amd64.exe
```
