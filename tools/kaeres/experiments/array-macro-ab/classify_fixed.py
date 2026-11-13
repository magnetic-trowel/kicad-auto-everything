# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixed parts of boards with no task record yet: the prepare step's own classify-mech (no overrides).
    classify_fixed.py OUT.json BOARD... (harness venv, KAE_KICAD_WRAP set)"""
import sys, json, os
from concurrent.futures import ThreadPoolExecutor
from kaebench import tools
from kaebench.kicad_scripts.mech_rules import apply_overrides
boards = sys.argv[2:]
def one(b):
    try:
        rows = tools.run_ops("classify-mech", os.path.expanduser(f"~/kae-boards/boards/{b}/board.kicad_pcb"))["footprints"]
        apply_overrides(rows, None)
        return b, sorted(r["ref"] for r in rows if r["fixed"])
    except Exception as e:
        return b, f"error {type(e).__name__}: {e}"[:300]
out = {}
with ThreadPoolExecutor(4) as ex:
    for b, v in ex.map(one, boards):
        out[b] = v
        print(b, v if isinstance(v, str) else len(v), flush=True)
json.dump(out, open(sys.argv[1], "w"), indent=0)
