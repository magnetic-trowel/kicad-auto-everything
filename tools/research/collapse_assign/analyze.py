# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline conflict-graph statistics on extracted boards (no KiCad needed).

    python analyze.py EXTRACT_DIR [id ...] [--realize] [--out stats.jsonl]

EXTRACT_DIR holds <id>.json files written by `kicad_io.py extract` from
kae-work/tasks/<id>/route/input/board.kicad_pcb. With --realize the prior-biased
PathFinder runs too (engine numbers only; KiCad DRC is the judge, use the harness).
"""
import os
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pnr"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import collapse  # noqa: E402
from router import Router  # noqa: E402
from world import World  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--realize", action="store_true")
    ap.add_argument("--baseline", action="store_true", help="also run the plain PathFinder")
    ap.add_argument("--opt", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    opts = {}
    for kv in a.opt:
        k, v = kv.split("=", 1)
        opts[k] = json.loads(v) if v[:1].isdigit() or v in ("true", "false") else v
    ids = a.ids or sorted(p.stem for p in Path(a.dir).glob("*.json"))
    outf = open(a.out, "a") if a.out else None
    for i in ids:
        data = json.loads((Path(a.dir) / f"{i}.json").read_text())
        t0 = time.time()
        w = World(data, g=0.1)
        quiet = lambda *_: None  # noqa: E731
        if a.realize:
            r = collapse.collapse(w, log=quiet, **opts)
            st = None
        else:
            for pi in range(len(w.parts)):
                w.place_original(pi)
            _, _, _, st = collapse.lift_and_assign(w, log=quiet)
        if a.baseline:
            w2 = World(data, g=0.1)
            for pi in range(len(w2.parts)):
                w2.place_original(pi)
            rb = Router(w2)
            rb.pathfinder(iters=40)
            print("BASE", i, rb.stats(), flush=True)
        if st is not None:
            st["id"] = i
            st["secs"] = round(time.time() - t0, 1)
            print(json.dumps(st, default=str), flush=True)
            if outf:
                outf.write(json.dumps(st, default=str) + "\n")
                outf.flush()


if __name__ == "__main__":
    main()
