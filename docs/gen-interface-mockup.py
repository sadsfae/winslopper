#!/usr/bin/env python3
"""Render a terminal-style mockup of the llama-server control menu/console.

Output: interface-mockup.png (next to this script).
Deterministic; no network access.
"""

import glob
import pathlib

from PIL import Image, ImageDraw, ImageFont

BASE = pathlib.Path(__file__).resolve().parent

# palette (Windows Terminal dark)
BG = (12, 12, 12)
TITLE_BG = (31, 31, 31)
TITLE_TEXT = (200, 200, 200)
BORDER = (63, 63, 63)
WHITE = (235, 235, 235)
GRAY = (170, 170, 170)
DIM = (110, 122, 130)
CYAN = (96, 195, 208)
GREEN = (158, 200, 128)
YELLOW = (231, 195, 125)
DESKTOP = (37, 53, 74)

TITLE = "llama-server - llama.cpp router  (PowerShell)"
FONT_SZ = 24
ADV = FONT_SZ + 6  # line advance
PAD = 22
TITLE_H = 44


def find_font(spec):
    hits = glob.glob(spec, recursive=True)
    return hits[0] if hits else None


def load_font(size, bold=False):
    candidates = [
        (
            "/usr/share/fonts/google-noto/NotoSansMono-Bold.ttf"
            if bold
            else "/usr/share/fonts/google-noto/NotoSansMono-SemiBold.ttf"
        ),
        "/usr/share/fonts/google-noto/NotoSansMono-Regular.ttf",
        (
            "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Bold.ttf"
            if bold
            else "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Regular.ttf"
        ),
    ]
    for spec in candidates:
        path = find_font(spec)
        if path:
            return ImageFont.truetype(path, size)
    raise SystemExit("no monospace TTF found")


FONT = load_font(FONT_SZ)
FONT_BOLD = load_font(FONT_SZ, bold=True)
FONT_TITLE = load_font(15, bold=True)

# (text, color) segments; None = default WHITE
LINES = [
    [("llama.cpp router on 0.0.0.0:8081", WHITE)],
    [
        ("  1) ", CYAN),
        ("Start server - logs stream in this window; closing it stops", GRAY),
    ],
    [("  2) ", CYAN), ("Stop server", GRAY)],
    [("  3) ", CYAN), ("Status", GRAY)],
    [("  4) ", CYAN), ("Open web chat (http://127.0.0.1:8081)", GRAY)],
    [("  0) ", CYAN), ("Exit / close window", GRAY)],
    [("choose [0-4]: ", CYAN), ("1", WHITE)],
    [],
    [("Starting llama-server (logs below; close window or Ctrl+C to stop)...", GREEN)],
    [("srv  | reading preset 'llm\\models\\router-config.ini' (6 models)", DIM)],
    [("srv  | model 'omp-agent' is not loaded, loading...", DIM)],
    [("srv  | spawning instance name=omp-agent on port 48223", DIM)],
    [("srv  |", DIM), ("   llama-server.exe --port 48223 --alias omp-agent", GRAY)],
    [("     |", DIM), ("     --ctx-size 166656 --ngl 99 --flash-attn --jinja", GRAY)],
    [
        ("     |", DIM),
        (
            "     --chat-template-file llm\\models\\qwen-fixed.jinja --reasoning off",
            GRAY,
        ),
    ],
    [("model| loaded Qwen3.8-27B-OBLITERATED-Q4_K_M.gguf + mmproj (21.3s)", GREEN)],
    [("srv  | proxying request to model 'omp-agent' on port 48223", DIM)],
    [("slot | id 3 | task 0 | prompt n_tokens=1842 | 1296 t/s", DIM)],
    [("tool | ", YELLOW), ('get_weather({"city": "Paris"})', YELLOW)],
    [],
    [("closing this window stops the server", DIM)],
    [],
]


def line_width(segs):
    return sum(FONT.getlength(t) for t, _ in segs)


W = max(line_width(s) for s in LINES)
content_w = int(W) + 2 * PAD
body_h = len(LINES) * ADV + 2 * PAD
W = content_w + 2
H = TITLE_H + body_h + 2

scale = 2
img = Image.new("RGB", (W * scale + 3 * PAD, H * scale + 3 * PAD), DESKTOP)
d = ImageDraw.Draw(img)

d.rectangle(
    [2 * PAD + 4, 2 * PAD + 4, 2 * PAD + W * scale + 4, 2 * PAD + H * scale + 4],
    fill=(0, 0, 0),
)

ox, oy = PAD, PAD
d.rounded_rectangle(
    [ox, oy, ox + W * scale, oy + H * scale],
    radius=10 * scale,
    fill=BG,
    outline=BORDER,
    width=2 * scale,
)

# title bar
d.rectangle(
    [ox + 2 * scale, oy + 2 * scale, ox + W * scale - 2 * scale, oy + TITLE_H * scale],
    fill=TITLE_BG,
)
for pos, col in zip(
    [(ox + 24, oy + 22), (ox + 42, oy + 22), (ox + 60, oy + 22)],
    [(255, 95, 86), (255, 189, 46), (40, 200, 64)],
):
    r = 5 * scale
    d.ellipse([pos[0] - r, pos[1] - r, pos[0] + r, pos[1] + r], fill=col)
d.text(
    (ox + 84 * scale, oy + (TITLE_H / 2 - 8) * scale),
    TITLE,
    font=FONT_TITLE,
    fill=TITLE_TEXT,
)

# body
ty = oy + TITLE_H * scale + PAD * scale
for segs in LINES:
    tx = ox + PAD * scale
    if segs:
        for text, color in segs:
            d.text((tx, ty), text, font=FONT, fill=color)
            tx += FONT.getlength(text) * scale
    ty += ADV * scale

# cursor block on the final blank line
cursor_x = ox + PAD * scale
cursor_y = oy + (TITLE_H + PAD) * scale + (len(LINES) - 1) * ADV * scale + 1 * scale
d.rectangle(
    [
        cursor_x,
        cursor_y,
        cursor_x + max(9 * scale, int(FONT.getlength("M") * scale)),
        cursor_y + (FONT_SZ + 2) * scale,
    ],
    fill=WHITE,
)

out = BASE / "interface-mockup.png"
img = img.resize((img.width // scale, img.height // scale), Image.LANCZOS)
img.save(out)
print(f"wrote {out} ({out.stat().st_size} bytes, {img.size[0]}x{img.size[1]})")
