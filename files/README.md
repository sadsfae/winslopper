# Bundled installers

These are the last well-known official **Windows 64-bit installers** that their
upstream projects shipped, vendored here so a Stable Diffusion / Open WebUI
install never depends on an upstream file still being online.

Always install Python only from python.org and Git only from git-scm.com (the
official GitHub releases), never from a third-party repackaged build. Verify the
SHA-256 below matches before running.

| File | Version | Source | SHA-256 |
| ---- | ------- | ------ | ------- |
| `python-3.10.11-amd64.exe` | 3.10.11 (last 3.10 installer) | https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe | `d8dede5005564b408ba50317108b765ed9c3c510342a598f9fd42681cbe0648b` |
| `python-3.12.9-amd64.exe` | 3.12.9 (last 3.12 installer) | https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe | `2a52993092a19cfdffe126e2eeac46a4265e25705614546604ad44988e040c0f` |
| `Git-for-Windows-64bit.exe` | Git 2.55.0.5 | https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/Git-2.55.0.5-64-bit.exe | `d065a4e23c3d9a6b5073d609b5be0830227ec3ca053c083ba385061ddfaf94c6` |

Notes:

- **Stable Diffusion WebUI** needs Python 3.10 (AUTOMATIC1111 is tested on 3.10, and its pinned CUDA torch 2.1.2 has no 3.12+ wheels); use `python-3.10.11-amd64.exe`. Python 3.11/3.12/3.13 will be rejected by the setup.
- **Open WebUI** accepts Python 3.11 or 3.12; the bundled installer is `python-3.12.9-amd64.exe`.
- Git for Windows is only required by the **Stable Diffusion** component (it clones the WebUI repo), not the router or Open WebUI.
- The Python files are about 29 MB each; Git for Windows is about 63 MB.
- These are the installer files, not the software itself. Run the installer, then re-run the relevant `setup-*.ps1`.

Recompute with:

```sh
sha256sum python-3.10.11-amd64.exe python-3.12.9-amd64.exe Git-for-Windows-64bit.exe
```
