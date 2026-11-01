# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cost of one router refresh (kae.em.pnr.solve_fields) on one board state: the 10 MHz solve of every pattern
against the whole-spectrum model of kae.em.spectral, built greedily (the first refresh) and recycled (later
refreshes: the same snapshot frequencies, solved one after another or concurrently).

    python em_r4_cost.py BOARD.kicad_pcb [--pitch 0.25] [--workers 1 4]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "kae" / "src"))

from kae.em.pnr import PhysRouter  # noqa: E402
from kae.em.spectral import Spectral  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--pitch", type=float, default=0.25)
    ap.add_argument("--workers", type=int, nargs="*", default=[2])
    ap.add_argument("--work")
    a = ap.parse_args(argv)
    r = PhysRouter(a.board, Path(a.work or ".") / "cost_out.kicad_pcb", pitch=a.pitch, work=a.work, verify=True,
                   log=lambda s: print(s, flush=True))
    t = time.time()
    r.solve_fields()
    print(f"COST 10 MHz refresh: {time.time() - t:.1f}s", flush=True)
    r.spec = Spectral(r, log=lambda s: print(s, flush=True))
    for label, w in [("greedy", 1)] + [(f"recycled, {w} at once", w) for w in a.workers]:
        r.spec.workers = w
        r._sig = None
        t = time.time()
        r.solve_fields()
        c = r.spec.costs[-1]
        print(f"COST spectral refresh ({label}): {time.time() - t:.1f}s; " +
              ", ".join(f"{k} {v:.1f}" if isinstance(v, float) else f"{k} {v}" for k, v in c.items()), flush=True)


if __name__ == "__main__":
    main()
