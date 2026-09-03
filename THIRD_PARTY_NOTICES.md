# Third-party notices

This repository and the release EXEs it produces redistribute third-party
software. Sources and licenses:

## llama.cpp (MIT)

The Windows release EXE embeds prebuilt llama.cpp binaries (llama-server.exe
and the CUDA 13.3 runtime DLLs) from the official llama.cpp nightly releases.

- Project: https://github.com/ggml-org/llama.cpp
- License: MIT (see `LICENSE`; the same license text applies to these binaries)
- Copyright (c) 2023-2026 The ggml authors

No modifications are made to the binaries; they are extracted as distributed
and verified by SHA-256 during the release build.

## Qwen chat template (Apache-2.0)

`src/qwen-fixed.jinja` and the copy installed by setup are the chat template
shipped with the Qwen3 model family.

- Project: https://github.com/QwenLM/Qwen3
- License: Apache License 2.0

## Model weights

The GGUF model files are not shipped by this repository. They live on the
local disk at `C:\LLM_Models` and are covered by their own licenses (for
example, the Qwen models are Apache-2.0 / Qwen license).
