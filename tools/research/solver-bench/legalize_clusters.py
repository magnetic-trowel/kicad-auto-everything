# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cluster-wise CP-SAT legalization of a nearly-legal placement (e.g. SA output at N=1000).

For each group of nearby violators: free the k nearest parts, keep the parts overlapping the
window bbox (and decap partners) as FIXED, confine free parts to the window, minimise L1
displacement (+ rotation-change penalty).  Each window is its own small CP-SAT model (no cloning
of the full board model).  Usage: python legalize_clusters.py N GRID POS.json [--k 12] [--t 3]
"""
import argparse, json, math, time
from ortools.sat.python import cp_model
from pcbgen import make_instance, Instance
from cpsat_place import build, rot_offsets
from hier_place import violators, check, full_hpwl, solve


def legalize_clusters(inst, g, pos, k=12, t=3.0, margin_mm=3.0, max_rounds=8, workers=4):
    t0 = time.time(); n = len(inst.comps)
    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    cur = {c: (min(max(X, 0), BW - 1), min(max(Y, 0), BH - 1), kk) for c, (X, Y, kk) in pos.items()}
    kk_of = {}
    stats = dict(windows=0, solved=0)
    for rnd in range(max_rounds):
        bad = sorted(violators(inst, cur, g))
        if not bad:
            break
        # group violators that are within 3 mm of each other
        groups = []
        for b in bad:
            for gr in groups:
                if any(abs(cur[b][0] - cur[o][0]) + abs(cur[b][1] - cur[o][1]) < 3.0 / g for o in gr):
                    gr.append(b); break
            else:
                groups.append([b])
        for gr in groups:
            key = tuple(gr)
            kw = kk_of.get(key, k)
            cx = sum(cur[b][0] for b in gr) / len(gr); cy = sum(cur[b][1] for b in gr) / len(gr)
            free = set(gr) | set(sorted(range(n), key=lambda c: abs(cur[c][0] - cx) + abs(cur[c][1] - cy))[:kw])
            rect = lambda c: (cur[c][0], cur[c][1], cur[c][0] + rot_offsets(inst.comps[c].fp, cur[c][2], g)[0],
                              cur[c][1] + rot_offsets(inst.comps[c].fp, cur[c][2], g)[1])
            fr = [rect(c) for c in free]
            M = int(margin_mm / g)
            wx0, wy0 = max(0, min(r[0] for r in fr) - M), max(0, min(r[1] for r in fr) - M)
            wx1, wy1 = min(BW, max(r[2] for r in fr) + M), min(BH, max(r[3] for r in fr) + M)
            fixed = set()
            for c in range(n):
                if c in free: continue
                r = rect(c)
                if r[0] < wx1 and wx0 < r[2] and r[1] < wy1 and wy0 < r[3]:
                    fixed.add(c)
            for (cc, cp, ic, ip, d) in inst.decaps:
                if cc in free and ic not in free: fixed.add(ic)
                if ic in free and cc not in free: fixed.add(cc)
            ids = sorted(free | fixed); loc = {c: i for i, c in enumerate(ids)}
            from pcbgen import Comp
            sub = Instance([Comp(i, inst.comps[c].fp, 0) for i, c in enumerate(ids)], [],
                           [(loc[cc], cp, loc[ic], ip, d) for (cc, cp, ic, ip, d) in inst.decaps if cc in loc and ic in loc],
                           inst.board_w, inst.board_h, inst.keepouts, {})
            m, V = build(sub, g, rot="var", sides=1, decap=True, objective=False)
            obj = []
            for c in ids:
                X, Y, q = cur[c]; v = V[loc[c]]
                if c in fixed:
                    m.add(v["x"] == X); m.add(v["y"] == Y)
                    for j in range(4): m.add(v["r"][j] == int(j == q))
                else:
                    W, H, _ = rot_offsets(inst.comps[c].fp, 0, g)
                    m.add(v["x"] >= wx0); m.add(v["y"] >= wy0)
                    m.add(v["x"] + min(W, H) <= wx1); m.add(v["y"] + min(W, H) <= wy1)
                    dx = m.new_int_var(0, BW, ""); dy = m.new_int_var(0, BH, "")
                    m.add_abs_equality(dx, v["x"] - X); m.add_abs_equality(dy, v["y"] - Y)
                    obj += [dx, dy, 10 * (1 - v["r"][q])]
                    m.add_hint(v["x"], X); m.add_hint(v["y"], Y)
            m.minimize(sum(obj))
            stats["windows"] += 1
            s, st = solve(m, t, workers=workers, seed=rnd)
            if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                stats["solved"] += 1
                for c in free:
                    v = V[loc[c]]
                    cur[c] = (s.value(v["x"]), s.value(v["y"]), [s.value(r) for r in v["r"]].index(1))
            else:
                kk_of[key] = int(kw * 1.6)
    return cur, rnd + 1, round(time.time() - t0, 1), stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int); ap.add_argument("grid", type=float); ap.add_argument("pos")
    ap.add_argument("--k", type=int, default=12); ap.add_argument("--t", type=float, default=3.0)
    a = ap.parse_args()
    inst = make_instance(a.n, seed=0)
    pos = {int(k): tuple(v) for k, v in json.load(open(a.pos)).items()}
    print(json.dumps(dict(stage="input", hpwl_mm=round(full_hpwl(inst, pos, a.grid), 1), check=check(inst, pos, a.grid))), flush=True)
    out, rounds, secs, st = legalize_clusters(inst, a.grid, pos, k=a.k, t=a.t)
    print(json.dumps(dict(stage="cluster-legalize", rounds=rounds, secs=secs, **st,
                          hpwl_mm=round(full_hpwl(inst, out, a.grid), 1), check=check(inst, out, a.grid))), flush=True)
    json.dump({str(k): v for k, v in out.items()}, open(a.pos.replace(".json", "_legal.json"), "w"))
