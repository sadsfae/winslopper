#!/usr/bin/env python3
"""Verify setup-llama-server.ps1 was generated deterministically from src/.
Run from the repository root: python tools/verify.py
"""

import hashlib
import importlib.util
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

spec = importlib.util.spec_from_file_location("gen", REPO / "gen.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

raw = (REPO / "setup-llama-server.ps1").read_bytes()
assert raw.startswith(b"\xef\xbb\xbf"), "missing BOM"
ps = raw.decode("utf-8-sig").replace("\r\n", "\n")
assert all(ord(c) < 128 for c in ps), "non-ASCII found"

for i, line in enumerate(ps.splitlines(), 1):
    assert not line.startswith('"@'), f"line {i}: stray double-quoted here-string"


def extract(label):
    m = re.search(rf"^\${label} = @'\n(.*?)\n'@$", ps, re.MULTILINE | re.DOTALL)
    assert m, label
    return m.group(1) + "\n"


tmpl = extract("tmplText")
src_tmpl = (REPO / "src" / "qwen-fixed.jinja").read_bytes()
assert tmpl.encode()[:-1] == src_tmpl, "template not byte-exact"
expected = hashlib.sha256(src_tmpl).hexdigest()
assert (
    f'$tmplSha  = "{expected}"' in ps
), "injected $tmplSha does not match src template"
print("template byte-exact, injected SHA:", expected)

ported = (
    (REPO / "src" / "router-config.ini")
    .read_text()
    .replace("/mnt/windows/LLM_Models/", "@@MODELS@@\\")
    .replace("/home/wfoster/llm/models/qwen-fixed.jinja", "@@TEMPLATE@@")
)
assert extract("presetText") == ported, "preset not exact"
print("preset exact")

assert extract("batText") == gen.BAT_LAUNCHER, "bat launcher not exact"
print("bat launcher exact")

assert extract("menuText") == gen.MENU_PS, "menu not exact"
print("menu exact")

print("ALL CHECKS PASS")
