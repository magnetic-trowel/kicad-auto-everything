# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-process dev loop (no KiCad): run methods on extracted boards, print engine cost.

    python dev.py EXTRACT_DIR METHOD[,METHOD...] ID[,ID...] [--budget S] [--opt k=v]

METHOD is a name in methods.py (seq, grow, ...) or in mcts.py (beam, mcts, grow_wide).
Prints routed length, vias, unrouted connections, engine cost and placement legality.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")

import methods  # noqa: E402
import mcts  # noqa: E402
from placekit import Kit  # noqa: E402
from world import World  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ext")
    ap.add_argument("methods")
    ap.add_argument("ids")
    ap.add_argument("--budget", type=float, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--opt", action="append", default=[])
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    a.ext = str(Path(a.ext).resolve())
    os.chdir("/home/user/kicad-auto-everything")  # extracts carry repo-relative board paths
    opts = {}
    for kv in a.opt:
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except ValueError:
            pass
        opts[k] = v
    ids = a.ids.split(",")
    if a.ids.startswith("@"):
        ids = Path(a.ids[1:]).read_text().split()
    for bid in ids:
        data = json.loads((Path(a.ext) / f"{bid}.json").read_text())
        for m in a.methods.split(","):
            fn = getattr(mcts, m, None) or getattr(methods, m)
            world = World(data, g=0.1)
            t0 = time.process_time()
            logs = []
            r = fn(world, seed=a.seed, budget=a.budget, log=(print if a.v else logs.append), **opts)
            dt = time.process_time() - t0
            kit = Kit(world, r)
            viol = [world.part_violation(pi) for pi in world.pose]
            unpl = sum(1 for p in world.parts if p.idx not in world.pose)
            bad = sum(1 for v in viol if v != (0, 0)) + unpl
            st = r.stats()
            extra = [s for s in logs if "stats" in s]
            print(f"{bid[:34]:34s} {m:10s} len={st['length_mm']:7.1f} vias={st['vias']:3d} "
                  f"unr={st['unrouted']:2d}/{st['connections']:3d} cost={kit.total_cost():8.1f} "
                  f"illegal={bad} t={dt:5.1f}s"
                  + (f" phys={world.phys.total():.2f}" if getattr(world, "phys", None) else ""), flush=True)
            for s in extra:
                print("   ", s.strip()[:400], flush=True)


if __name__ == "__main__":
    main()
