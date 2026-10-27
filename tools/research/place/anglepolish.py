# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Paired test of free part angles (kae.place `--angles STEP`) from common starting points.

A full placement run with and without free angles differs mostly by its random trajectory
(seed-to-seed spread on split B is larger than the effect), so this starts both arms from
the same finished, legal placement and gives each the same number of low-temperature
annealing moves (geometric from T0*hot to T0*1e-4, T0 measured as in the annealer, the
legality weight at its final value), same seed. Each start is priced by the annealer's own
cost terms: HPWL, the linear physics scorecard (place terms, barrier 0, u_sat 3), parts at
non-right angles, and the exact legality check of the result. A start that is grid-illegal
as read (its run relaxed bodies on a crowded board) gets its bodies relaxed first.

    python tools/research/place/anglepolish.py --out OUT.json --step 15 --moves 2000 \\
        --seeds 0,1 START_DIR/<id>/board.kicad_pcb ...

Imports kae from PYTHONPATH (a snapshot or the source tree); never writes boards.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from kae.board.kicad_file import load
from kae.place import clusters
from kae.place.anneal import make_annealer
from kae.place.engine import I_OVERFLOW, run_batch, sample_uphill
from kae.place.legalize import exact_check
from kae.place.pipeline import SA_U_SAT, _net_kinds, physics_summary
from kae.place.problem import Problem
from kae.place.state import State, grid_violations
from kae.place.stubs import make_brief, make_terms


def state_from_board(P):
    st = State(P)
    for p in P.parts:
        if not p.movable:
            continue
        X, Y = P.grid_of(p.x0, p.y0)
        rots = [r.rot for r in p.rots]
        k = min(range(len(rots)), key=lambda kk: min(abs(rots[kk] - p.rot0) % 360, 360 - abs(rots[kk] - p.rot0) % 360))
        st.X[p.i], st.Y[p.i], st.K[p.i] = X, Y, k
    return st


def polish(ann, n_moves, hot, batch=2000):
    """n_moves annealing moves from T0*hot down to T0*1e-4 at the final legality weight."""
    n = len(ann.mov)
    r0 = max(2, int(0.25 * ann.ann._span()))
    ups = np.zeros(400)
    m = sample_uphill(ann.E, ann.fast, ann.swap_ptr, ann.swap_ids, min(200, 20 * n), ann.lam0, r0, ups) \
        if len(ann.fast) else 0
    ups = sorted(ups[:m].tolist())
    T0 = ups[len(ups) // 2] / math.log(1 / 0.3) if ups else 1e-3
    Ta, Tb = T0 * hot, T0 * 1e-4
    fstats = np.zeros(6, np.int64)
    share_py = (len(ann.slow) + 0.25 * len(ann.mac_np)) / max(1, n)
    share_fast = 1.0 - share_py if len(ann.fast) else 0.0
    py = bool(ann.slow or ann.mac_np)
    done = 0
    while done < n_moves:
        f = done / n_moves
        T = Ta * (Tb / Ta) ** f
        r = max(1, int(r0 * (T / T0) ** 0.5))
        nf = int(round(batch * share_fast))
        if nf and len(ann.fast):
            run_batch(ann.E, ann.fast, ann.swap_ptr, ann.swap_ids, nf, T, ann.lam1, r, fstats)
            if ann.E.ip[I_OVERFLOW]:
                ann._rebuild()
        for _ in range(batch - nf if py else 0):
            mv = ann._propose_python(r)
            if mv is not None:
                ann._try_python(mv[0], mv[1], T, ann.lam1, mv[2])
        done += batch
    return dict(T0=T0, rot_tried=int(fstats[2]), rot_accepted=int(fstats[3]))


def one(path, step, moves_per_part, seeds, hot):
    board = load(path)
    brief, _ = make_brief(board)
    rows = []
    for arm in (None, step):
        P = Problem.build(board, net_kinds=_net_kinds(brief), angle_step=arm)
        P.set_margin(0.0)
        if grid_violations(state_from_board(P)):
            P.relax_bodies()        # as the run that made the start did (a crowded board)
        terms = None
        if (brief or {}).get("structures"):
            terms, _ = make_terms(board, brief, barrier=0.0, u_sat=SA_U_SAT)
        order = clusters.protection_order(P, brief)
        for seed in seeds:
            st0 = state_from_board(P)
            ann = make_annealer(P, st0.copy(), terms=terms, seed=seed, w_phys=1.0 if terms is not None else 0.0,
                                order=order)
            w0, p0 = ann.wl, ann.phys
            t = time.process_time()
            info = polish(ann, moves_per_part * len(P.mov), hot)
            cpu = time.process_time() - t
            ann.write_back()
            st = ann.st
            poses = {p.uuid: st.pose(p.i) for p in P.parts}
            sc = physics_summary(terms, poses, breakdown=False) if terms is not None else {"total_linear": 0.0}
            odd = sum(1 for p in P.parts if p.movable and abs(st.rot(p.i) % 90.0) > 1e-6
                      and abs(st.rot(p.i) % 90.0 - 90.0) > 1e-6)
            ex = exact_check(P, st)
            rows.append(dict(arm="right" if arm is None else f"step{arm:g}", seed=seed, hpwl0=round(w0, 2),
                             phys0=round(p0, 4), hpwl=round(ann.wl, 2), phys=round(ann.phys, 4),
                             scorecard=sc["total_linear"], odd=odd, parts=len(P.mov), grid_bad=len(grid_violations(st)),
                             exact=len(ex), cpu=round(cpu, 1), **info))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("starts", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--step", type=float, default=15.0)
    ap.add_argument("--moves", type=int, default=2000, help="moves per movable part")
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--hot", type=float, default=1e-2, help="start temperature as a fraction of T0")
    a = ap.parse_args(argv)
    seeds = [int(s) for s in a.seeds.split(",")]
    out = []
    for path in a.starts:
        bid = Path(path).parent.name
        try:
            rows = one(path, a.step, a.moves, seeds, a.hot)
        except Exception as e:      # noqa: BLE001 - one bad board must not end the sweep
            print(f"{bid}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        for r in rows:
            r.update(board=bid, start=str(path))
            print(json.dumps(r), flush=True)
        out += rows
    Path(a.out).write_text(json.dumps(out, indent=1))
    # paired summary: per start and seed, step arm minus right arm
    by = {}
    for r in out:
        by.setdefault((r["start"], r["seed"]), {})[r["arm"]] = r
    dh, dp, odd = [], [], []
    for v in by.values():
        if len(v) == 2:
            rr, aa = v["right"], next(x for k, x in v.items() if k != "right")
            dh.append(aa["hpwl"] - rr["hpwl"])
            dp.append(aa["scorecard"] - rr["scorecard"])
            odd.append(aa["odd"])
    if dh:
        print(f"pairs {len(dh)}: dHPWL mean {statistics.mean(dh):+.2f} median {statistics.median(dh):+.2f} "
              f"(better {sum(x < -1e-6 for x in dh)}, worse {sum(x > 1e-6 for x in dh)}); "
              f"dPhysics mean {statistics.mean(dp):+.4f} median {statistics.median(dp):+.4f} "
              f"(better {sum(x < -1e-6 for x in dp)}, worse {sum(x > 1e-6 for x in dp)}); odd parts {sum(odd)}")


if __name__ == "__main__":
    main()
