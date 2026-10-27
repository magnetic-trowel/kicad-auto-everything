# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-move validation of the min-plus map (plan 5.1 diagnostic).

Runs jc's lift and collapse iterations on one board; at chosen betas it takes random
parts, scores candidate poses (local: within `local_mm` of the current pose, any
rotation; global: anywhere legal) by the HPWL map, jc's wire term (HPWL + tension) and
the min-plus map, then actually moves the part, re-routes its nets at the current price
(PathFinder present cost beta, other nets fixed), and records the routed cost of those
nets (mm + 2 mm/via + a perimeter per unrouted connection). Prints Spearman rho per
predictor, pooled and within part.

    python validate.py BOARD_ID [--betas 0.05,1,5,20] [--parts 15] [--out file.jsonl]
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
WORK = Path(os.environ.get("XF_WORK", ROOT / "kae-work2"))
sys.path.insert(0, str(ROOT / "tools" / "research" / "pnr"))

import minplus as MPm  # noqa: E402
import methods as M  # noqa: E402
from run import kicad  # noqa: E402
from world import World  # noqa: E402



def load(board_id, cache):
    cache.mkdir(parents=True, exist_ok=True)
    ext = cache / f"{board_id}.json"
    if not ext.exists():
        kicad("extract", WORK / "tasks" / board_id / "place" / "input" / "board.kicad_pcb", ext)
    return json.loads(ext.read_text())


def sample(C, beta, rng, nparts, nlocal, nglobal, local_mm, rows, tag):
    w, r, kit = C.w, C.r, C.kit
    mov = [q for q in kit.movable() if q in w.pose]
    parts = rng.sample(mov, min(nparts, len(mov)))
    r.pres = beta
    for pi in parts:
        nets = sorted(kit.part_nets([pi]))
        if not nets:
            continue
        cur = w.pose[pi]
        anchors = C.anchors(pi) if C.tension_w else []
        snap = kit.snapshot(nets)
        C.record_cells(pi)
        w.unplace(pi)
        C.mp.prepare(beta)
        maps = {}
        for ri in range(4):
            L = C.legal_map(pi, ri)
            if L.sum() < 50:  # lift state: parts overlap, so sample poses inside the board
                L = C.inside_map(pi, ri)
            if not L.any():
                continue
            h = kit.hpwl_map(pi, ri) / w.g
            t = (1 - C.tension_w) * h + C.tension_w * C.tension_map(pi, ri, anchors) if anchors else h
            m = C.mp.part_map(pi, ri)
            if m is None:
                continue
            maps[ri] = (L, h, t, m)
        if not maps:
            w.place(pi, *cur)
            continue
        rad = int(local_mm / w.g)
        poses = []
        tries = 0
        while len(poses) < nlocal + nglobal and tries < 2000:
            tries += 1
            ri = rng.choice(list(maps))
            L = maps[ri][0]
            if len(poses) < nlocal:
                x = cur[0] + rng.randint(-rad, rad)
                y = cur[1] + rng.randint(-rad, rad)
                if not (0 <= x < w.W and 0 <= y < w.H) or not L[y, x]:
                    continue
                kind = "local"
            else:
                ys, xs = np.nonzero(L)
                j = rng.randrange(len(ys))
                x, y = int(xs[j]), int(ys[j])
                kind = "global"
            poses.append((x, y, ri, kind))
        for x, y, ri, kind in poses:
            for n in nets:
                r.rip(n)
            w.place(pi, x, y, ri)
            order = list(nets)
            rng.shuffle(order)
            for n in order:
                r.route_net(n)
            cost = sum(kit.net_cost(n) for n in nets)
            vias = sum(int((np.diff(p[:, 0]) != 0).sum()) for n in nets for p in r.routes.get(n, []))
            unr = sum(r.unrouted.get(n, 0) for n in nets)
            pc = priced(w, r, nets, beta, kit)
            L, h, t, m = maps[ri]
            rows.append(dict(tag=tag, beta=beta, part=pi, kind=kind, hpwl=float(h[y, x]),
                             jc=float(t[y, x]), mp=float(m[y, x]), cost=cost, pcost=pc, vias=vias, unr=unr))
            for n in nets:
                r.rip(n)
            w.unplace(pi)
        w.place(pi, *cur)
        kit.restore(snap)


def priced(w, r, nets, beta, kit):
    """Priced cost (fine cells, the router's own currency) of the nets' routes."""
    tot = 0.0
    for n in nets:
        for p in r.routes.get(n, []):
            if len(p) < 2:
                continue
            d = np.abs(np.diff(p, axis=0))
            same = d[:, 0] == 0
            l, y, x = p[1:, 0], p[1:, 1], p[1:, 2]
            fr = w.DT[l, y, x] - (w.occT[n, l, y, x] > 0)
            c = (1.0 + w.hist[l, y, x]) * (1.0 + beta * fr)
            step = np.where((d[:, 1] + d[:, 2]) == 2, np.sqrt(2), 1.0)
            tot += float(np.sum(np.where(same, step * c, r.via_cost * (1.0 + beta * fr))))
        tot += r.unrouted.get(n, 0) * kit.unrouted_mm / w.g
    return tot


def rho_table(rows, target="cost"):
    out = {}
    for kind in ("local", "global", "all"):
        sel = [x for x in rows if kind == "all" or x["kind"] == kind]
        if len(sel) < 5:
            continue
        res = {}
        for k in ("hpwl", "jc", "mp"):
            pooled = spearmanr([x[k] for x in sel], [x[target] for x in sel])[0]
            per = []
            by = {}
            for x in sel:
                by.setdefault((x["tag"], x["beta"], x["part"]), []).append(x)
            for v in by.values():
                if len(v) >= 4 and len({y[target] for y in v}) > 1 and len({y[k] for y in v}) > 1:
                    per.append(spearmanr([y[k] for y in v], [y[target] for y in v])[0])
            res[k] = (round(float(pooled), 3), round(float(np.nanmean(per)), 3) if per else None, len(per))
        out[kind] = (len(sel), res)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--betas", default="0.05,1,5,20")
    ap.add_argument("--parts", type=int, default=12)
    ap.add_argument("--local", type=int, default=8)
    ap.add_argument("--global_", type=int, default=4)
    ap.add_argument("--local-mm", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--coarse", type=float, default=0.4)
    ap.add_argument("--no-shape", action="store_true")
    ap.add_argument("--tree", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    betas = [float(b) for b in a.betas.split(",")]
    cache = WORK / "xf_minplus" / "extract"
    allrows = []
    for bid in a.boards:
        t0 = time.process_time()
        data = load(bid, cache)
        w = World(data, g=0.1)
        rng = random.Random(a.seed)
        C = MPm.MPCollapse(w, a.seed, 1e9, lambda s: None, phys_w=0.0, minplus_w=0.0,
                             coarse_mm=a.coarse, pad_shape=not a.no_shape, mp_tree=a.tree)
        mov = [q for q in C.kit.movable() if q not in w.pose]
        C.lift(mov)
        mov = [q for q in C.kit.movable() if q in w.pose]
        rows = []
        beta = betas[0]
        bi = 0
        while bi < len(betas):
            C.route_all(beta)
            if beta >= betas[bi] * 0.999:
                sample(C, beta, rng, a.parts, a.local, a.global_, a.local_mm, rows, bid)
                bi += 1
            CT, CV, per = C.route_maps()
            order = list(mov)
            C.rng.shuffle(order)
            for pi in order:
                C.best_response(pi, beta, CT, CV, per)
            C.hist_c += C.hist_inc * (w.court > 1)
            beta = min(betas[bi], beta * 1.6) if bi < len(betas) else beta
        tab = rho_table(rows)
        print(bid, f"t={time.process_time() - t0:.0f}s", json.dumps(tab), flush=True)
        for b in betas:
            print("   beta", b, json.dumps(rho_table([x for x in rows if x["beta"] == b])), flush=True)
        allrows += rows
    print("ALL", json.dumps(rho_table(allrows)))
    print("ALL priced", json.dumps(rho_table(allrows, "pcost")))
    for b in betas:
        print("ALL beta", b, json.dumps(rho_table([x for x in allrows if x["beta"] == b])))
    if a.out:
        Path(a.out).write_text("\n".join(json.dumps(x) for x in allrows))


if __name__ == "__main__":
    main()
