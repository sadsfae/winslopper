# Fetching Civitai models on Windows

How to download Stable Diffusion checkpoints and LoRAs from Civitai onto this Windows host.

## Use `curl.exe`, not PowerShell `Invoke-WebRequest`

PowerShell 5.1's `Invoke-WebRequest` (used by `Download-Model.ps1`) is unreliable for
multi-GB files: it can stall and appear to do nothing (no partial file, idle Task Manager).
Use the real `curl.exe` that ships with Windows 10/11.

### Download a checkpoint
```powershell
curl.exe -L -J -O --ssl-no-revoke "https://civitai.com/api/download/models/<modelVersionId>"
```
- `-L` follows Civitai's redirect to its CDN.
- `-J -O` takes the remote filename from the `content-disposition` header (so you don't
  have to guess the `.safetensors` name).
- The command streams to the current directory. From `winslopper\`, that lands in
  `sd\stable-diffusion-webui\models\Stable-diffusion\`.

### Download a LoRA
Same command; move the resulting file to `sd\stable-diffusion-webui\models\Lora\`.

### If a filename/extension drops, name it explicitly
```powershell
curl.exe -L -o "MyModel.safetensors" --ssl-no-revoke "https://civitai.com/api/download/models/<modelVersionId>"
```

## The `--ssl-no-revoke` flag

Windows curl (schannel) can fail the TLS handshake with:
> `curl: (35) schannel: next InitializeSecurityContext failed: Unknown error (0x80092013) - ... revocation server was offline.`

This is a certificate-revocation-lookup failure (revocation endpoint unreachable), not a
valid-cert problem. Add `--ssl-no-revoke` to skip the lookup. Minor trust trade-off —
fine for large public downloads, avoid it for sensitive sites. Retry if it stays flaky;
revocation endpoints intermittently drop.

## Selecting a model

AUTOMATIC1111 exposes `POST /sdapi/v1/txt2img`. The checkpoint is chosen per-request via
`override_settings.sd_model_checkpoint` in the JSON body (set to the exact filename, e.g.
the version filename from the `modelVersions[].files[].name` field). So you only need the
file present in `models\Stable-diffusion` — a batch/generator names it via the API rather
than you hard-pinning a safetensors in the WebUI config.

## Getting the `modelVersionId`

Civitai model pages use `civitai.com/models/<modelId>`. The direct-download URL uses the
**modelVersionId**, found via the API:
```powershell
curl.exe "https://civitai.com/api/v1/models/<modelId>"
```
Look at `modelVersions[].id` (and `files[0].name` / `sizeKB`) to pick the version, then
download `https://civitai.com/api/download/models/<that id>`.
