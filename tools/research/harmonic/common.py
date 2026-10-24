# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Load a task board into a pnr World (extract cached in kae-work/harm-cache)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")

ROOT = Path("/home/user/kicad-auto-everything")
CACHE = ROOT / "kae-work" / "harm-cache"


def load_world(board, kind="route", g=0.1):
    from run import kicad
    from world import World
    inp = ROOT / "kae-work" / "tasks" / board / kind / "input" / "board.kicad_pcb"
    ext = CACHE / f"{board}.{kind}.json"
    if not ext.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        kicad("extract", inp, ext)
    data = json.loads(ext.read_text())
    return World(data, g=g)
