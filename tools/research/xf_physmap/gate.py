# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validation gate: ExactPhys.exact_map vs Terms.delta_by_kind at random cells.

    python gate.py EXTRACT_DIR [--boards FILE] [--n 500] [--stride 0.4] [--out JSON]

EXTRACT_DIR/<board>/extract.json from pnr/kicad_io.py extract. Two configurations per
board: the human placement and a random one (every part at a random in-board cell and
rotation). For every active part and rotation, n random in-board cells; error per kind
e = |map - delta| / max(|delta|, floor), floor = 1e-3 cost units.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "pnr"))

from physmap import ExactPhys  # noqa: E402
from world import World  # noqa: E402

FLOOR = 1e-3


def run_board(path, n, stride, rng, log, rtol=0.01, atol=1e-3, budget=None):
    data = json.loads(Path(path).read_text())
    res = {}
    timing = []
    for cfg in ("human", "random"):
        w = World(data, g=0.1)
        cells = np.argwhere(w.inside)
        for p in w.parts:
            if cfg == "human":
                try:
                    w.place_original(p.idx, exact=False)
                except Exception:
                    pass
            else:
                y, x = cells[rng.randrange(len(cells))]
                w.place(p.idx, int(x), int(y), rng.randrange(4))
        ph = ExactPhys(w, data["path"], stride_mm=stride, rtol=rtol, atol=atol, map_budget=budget)
        ph.sync()
        T = ph.T
        for pi in sorted(ph.active):
            u = ph.key[pi]
            for ri in range(4):
                t0 = time.process_time()
                maps = ph.exact_map(pi, ri, by_kind=True)
                timing.append(time.process_time() - t0)
                pts = [cells[rng.randrange(len(cells))] for _ in range(n)]
                for y, x in pts:
                    pose = (int(x), int(y), ri)
                    if w.pose.get(pi) == pose:
                        continue
                    d = T.delta_by_kind(ph.poses, [u], {u: ph.pose(pi, pose)})
                    for kind in set(d) | set(maps):
                        dv = d.get(kind, 0.0)
                        mv = float(maps[kind][y, x]) if kind in maps else 0.0
                        r = res.setdefault(kind, dict(err=[], abs=[], mag=[]))
                        r["err"].append(abs(mv - dv) / max(abs(dv), FLOOR))
                        r["abs"].append(abs(mv - dv))
                        r["mag"].append(abs(dv))
        log(f"  {cfg}: active={len(ph.active)} maps={len(timing)}")
    return res, timing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extract_dir")
    ap.add_argument("--boards")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--stride", type=float, default=0.4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rtol", type=float, default=0.01)
    ap.add_argument("--atol", type=float, default=1e-3)
    ap.add_argument("--map-budget", type=float, default=None)
    ap.add_argument("--out")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    boards = Path(a.boards).read_text().split() if a.boards else sorted(p.name for p in Path(a.extract_dir).iterdir())
    allres = {}
    times = []
    per_board = {}
    for b in boards:
        print(b, flush=True)
        res, tm = run_board(Path(a.extract_dir) / b / "extract.json", a.n, a.stride, rng, print, a.rtol, a.atol, a.map_budget)
        times += tm
        per_board[b] = {}
        for k, r in res.items():
            e = np.array(r["err"])
            per_board[b][k] = dict(n=len(e), median=float(np.median(e)), p95=float(np.percentile(e, 95)),
                                   max=float(e.max()))
            print(f"  {k:12s} n={len(e):6d} median={np.median(e):.2e} p95={np.percentile(e, 95):.2e} "
                  f"p99={np.percentile(e, 99):.2e} max={e.max():.2e} max_abs={max(r['abs']):.2e}", flush=True)
            A = allres.setdefault(k, dict(err=[], abs=[], mag=[]))
            for q in A:
                A[q] += r[q]
    print("\nALL BOARDS (map CPU s per part-rotation: median %.3f, max %.3f)" % (np.median(times), max(times)))
    summary = {}
    for k, r in sorted(allres.items()):
        e = np.array(r["err"])
        summary[k] = dict(n=len(e), median=float(np.median(e)), p95=float(np.percentile(e, 95)),
                          p99=float(np.percentile(e, 99)), max=float(e.max()), within_1pct=float(np.mean(e <= 0.01)),
                          within_5pct=float(np.mean(e <= 0.05)), max_abs=float(max(r["abs"])),
                          median_mag=float(np.median(r["mag"])))
        print(f"{k:12s} " + " ".join(f"{q}={v:.3g}" for q, v in summary[k].items()))
    if a.out:
        Path(a.out).write_text(json.dumps(dict(summary=summary, per_board=per_board,
                                               map_cpu_s=dict(median=float(np.median(times)), max=max(times))),
                                          indent=1))


if __name__ == "__main__":
    main()
