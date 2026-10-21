# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hierarchical CP-SAT placement + LNS refinement benchmark.

Stage 1  per-cluster CP-SAT (IC + its decaps + its passives) in a private box  -> rigid macro
Stage 2  top-level CP-SAT floorplan of macros (4 rotations, keep-outs, inter-cluster HPWL)
Stage 3  flatten, then windowed LNS on the full model (fix everything outside a k-NN window)

Usage: python hier_place.py N GRID_MM [--cluster-time 2] [--top-time 30] [--lns-time 60]
                                      [--window 40] [--iter-time 3] [--seed 0]
Prints JSON lines: one per stage with wall time and exact full-board HPWL (mm).
"""
import argparse
import json
import math
import random
import time
from dataclasses import replace

from ortools.sat.python import cp_model

from pcbgen import make_instance, Fp, Comp, Instance
from cpsat_place import build, rot_offsets


def solve(m, t, workers=4, seed=0):
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = t
    s.parameters.num_workers = workers
    s.parameters.random_seed = seed
    st = s.solve(m)
    return s, st


def full_hpwl(inst, pos, g):
    """pos[c] = (X, Y, k) bottom-left in grid units + rotation; exact pin-level HPWL in mm."""
    tot = 0.0
    for net in inst.nets:
        xs, ys = [], []
        for (c, p) in net:
            X, Y, k = pos[c]
            _, _, offs = rot_offsets(inst.comps[c].fp, k, g)
            xs.append(X + offs[p][0]); ys.append(Y + offs[p][1])
        tot += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return tot * g


def check(inst, pos, g):
    """returns (#overlapping pairs, #decap violations, #out-of-board, #keep-out intrusions)"""
    rects = []
    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    oob = 0
    for c in inst.comps:
        X, Y, k = pos[c.id]
        W, H, _ = rot_offsets(c.fp, k, g)
        rects.append((X, Y, X + W, Y + H))
        if X < 0 or Y < 0 or X + W > BW or Y + H > BH:
            oob += 1
    ov = 0
    order = sorted(range(len(rects)), key=lambda i: rects[i][0])
    for a_i, i in enumerate(order):
        for j in order[a_i + 1:]:
            if rects[j][0] >= rects[i][2]:
                break
            if rects[i][1] < rects[j][3] and rects[j][1] < rects[i][3]:
                ov += 1
    ko = 0
    for (kx, ky, kw, kh) in inst.keepouts:
        X0, Y0, X1, Y1 = math.floor(kx / g), math.floor(ky / g), math.ceil((kx + kw) / g), math.ceil((ky + kh) / g)
        for (a0, b0, a1, b1) in rects:
            if a0 < X1 and X0 < a1 and b0 < Y1 and Y0 < b1:
                ko += 1
    dv = 0
    for (cc, cp, ic, ip, dmax) in inst.decaps:
        def pin(c, p):
            X, Y, k = pos[c]; _, _, o = rot_offsets(inst.comps[c].fp, k, g); return X + o[p][0], Y + o[p][1]
        a, b = pin(cc, cp), pin(ic, ip)
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) > math.floor(dmax / g):
            dv += 1
    return ov, dv, oob, ko


def extract(s, V, ids):
    out = {}
    for local, cid in ids.items():
        v = V[local]
        k = [s.value(r) for r in v["r"]].index(1)
        out[cid] = (s.value(v["x"]), s.value(v["y"]), k)
    return out


def lns_polish(inst, g, pos, lns_time, window=40, iter_time=2.0, workers=4, seed=0):
    """Windowed CP-SAT LNS starting from a legal placement `pos`. Returns (best_pos, best_hp, iters, accepted)."""
    rnd = random.Random(seed)
    n = len(inst.comps)
    full, FV = build(inst, g, rot="var", sides=1, decap=True, objective=True)
    best = dict(pos); best_hp = full_hpwl(inst, pos, g); it = 0; acc = 0
    t0 = time.time()
    while time.time() - t0 < lns_time:
        it += 1
        sc = rnd.randrange(n); cx, cy = best[sc][0], best[sc][1]
        win = set(sorted(range(n), key=lambda c: abs(best[c][0] - cx) + abs(best[c][1] - cy))[:window])
        m2 = full.clone()
        for c in range(n):
            X, Y, k = best[c]; v = FV[c]
            xv = m2.get_int_var_from_proto_index(v["x"].index); yv = m2.get_int_var_from_proto_index(v["y"].index)
            rv = [m2.get_bool_var_from_proto_index(r.index) for r in v["r"]]
            if c in win:
                m2.add_hint(xv, X); m2.add_hint(yv, Y)
                for kk in range(4): m2.add_hint(rv[kk], int(kk == k))
            else:
                m2.add(xv == X); m2.add(yv == Y)
                for kk in range(4): m2.add(rv[kk] == int(kk == k))
        s2, st2 = solve(m2, iter_time, workers=workers, seed=seed + it)
        if st2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            cand = {}
            for c in range(n):
                v = FV[c]
                k = [s2.value(m2.get_bool_var_from_proto_index(r.index)) for r in v["r"]].index(1)
                cand[c] = (s2.value(m2.get_int_var_from_proto_index(v["x"].index)), s2.value(m2.get_int_var_from_proto_index(v["y"].index)), k)
            hp = full_hpwl(inst, cand, g)
            if hp < best_hp - 1e-9:
                best, best_hp, acc = cand, hp, acc + 1
    return best, best_hp, it, acc


def legalize(inst, g, pos, t_limit, workers=4, seed=0):
    """CP-SAT legalization: hard constraints (no-overlap, keep-outs, board, decap), minimise displacement
    (L1) from an illegal placement `pos` (+ penalty for changing rotation). Returns (pos or None, status, secs)."""
    t0 = time.time()
    m, V = build(inst, g, rot="var", sides=1, decap=True, objective=False)
    obj = []
    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    for c in inst.comps:
        X0, Y0, k0 = pos[c.id]; v = V[c.id]
        X0 = min(max(X0, 0), BW); Y0 = min(max(Y0, 0), BH)
        dx = m.new_int_var(0, BW, ""); dy = m.new_int_var(0, BH, "")
        m.add_abs_equality(dx, v["x"] - X0); m.add_abs_equality(dy, v["y"] - Y0)
        m.add_hint(v["x"], X0); m.add_hint(v["y"], Y0)
        for kk in range(4): m.add_hint(v["r"][kk], int(kk == k0))
        obj += [dx, dy, 10 * (1 - v["r"][k0])]
    m.minimize(sum(obj))
    s, st = solve(m, t_limit, workers=workers, seed=seed)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, s.status_name(st), round(time.time() - t0, 2)
    out = {c.id: (s.value(V[c.id]["x"]), s.value(V[c.id]["y"]), [s.value(r) for r in V[c.id]["r"]].index(1)) for c in inst.comps}
    return out, s.status_name(st), round(time.time() - t0, 2)


def violators(inst, pos, g):
    """ids of parts involved in any overlap / out-of-board / keep-out / decap violation"""
    bad = set()
    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    rects = []
    for c in inst.comps:
        X, Y, k = pos[c.id]; W, H, _ = rot_offsets(c.fp, k, g)
        rects.append((X, Y, X + W, Y + H))
        if X < 0 or Y < 0 or X + W > BW or Y + H > BH:
            bad.add(c.id)
    order = sorted(range(len(rects)), key=lambda i: rects[i][0])
    for a_i, i in enumerate(order):
        for j in order[a_i + 1:]:
            if rects[j][0] >= rects[i][2]:
                break
            if rects[i][1] < rects[j][3] and rects[j][1] < rects[i][3]:
                bad.add(i); bad.add(j)
    for (kx, ky, kw, kh) in inst.keepouts:
        X0, Y0, X1, Y1 = math.floor(kx / g), math.floor(ky / g), math.ceil((kx + kw) / g), math.ceil((ky + kh) / g)
        for i, (a0, b0, a1, b1) in enumerate(rects):
            if a0 < X1 and X0 < a1 and b0 < Y1 and Y0 < b1:
                bad.add(i)
    for (cc, cp, ic, ip, dmax) in inst.decaps:
        def pin(c, p):
            X, Y, k = pos[c]; _, _, o = rot_offsets(inst.comps[c].fp, k, g); return X + o[p][0], Y + o[p][1]
        a_, b_ = pin(cc, cp), pin(ic, ip)
        if abs(a_[0] - b_[0]) + abs(a_[1] - b_[1]) > math.floor(dmax / g):
            bad.add(cc); bad.add(ic)
    return bad


def legalize_windowed(inst, g, pos, k=30, t_iter=10.0, max_rounds=10, workers=4, seed=0):
    """Repair only the neighbourhoods of violators: free the k nearest parts around each violator,
    fix everything else, minimise displacement. Returns (pos, rounds, secs, legal)."""
    t0 = time.time()
    m_full, V = build(inst, g, rot="var", sides=1, decap=True, objective=False)
    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    cur = {c: (min(max(X, 0), BW - 1), min(max(Y, 0), BH - 1), kk) for c, (X, Y, kk) in pos.items()}
    n = len(inst.comps)
    for rnd_ in range(max_rounds):
        bad = violators(inst, cur, g)
        if not bad:
            return cur, rnd_, round(time.time() - t0, 1), True
        free = set()
        for b in bad:
            bx, by = cur[b][0], cur[b][1]
            free.update(sorted(range(n), key=lambda c: abs(cur[c][0] - bx) + abs(cur[c][1] - by))[:k])
        m = m_full.clone(); obj = []
        for c in range(n):
            X, Y, kk = cur[c]; v = V[c]
            xv = m.get_int_var_from_proto_index(v["x"].index); yv = m.get_int_var_from_proto_index(v["y"].index)
            rv = [m.get_bool_var_from_proto_index(r.index) for r in v["r"]]
            if c in free:
                dx = m.new_int_var(0, BW, ""); dy = m.new_int_var(0, BH, "")
                m.add_abs_equality(dx, xv - X); m.add_abs_equality(dy, yv - Y)
                obj += [dx, dy, 10 * (1 - rv[kk])]
                m.add_hint(xv, X); m.add_hint(yv, Y)
            else:
                m.add(xv == X); m.add(yv == Y)
                for q in range(4): m.add(rv[q] == int(q == kk))
        m.minimize(sum(obj))
        s, st = solve(m, t_iter, workers=workers, seed=seed + rnd_)
        if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for c in free:
                v = V[c]
                cur[c] = (s.value(m.get_int_var_from_proto_index(v["x"].index)), s.value(m.get_int_var_from_proto_index(v["y"].index)),
                          [s.value(m.get_bool_var_from_proto_index(r.index)) for r in v["r"]].index(1))
        else:
            k = int(k * 1.5)          # window too tight: grow it
    return cur, max_rounds, round(time.time() - t0, 1), not violators(inst, cur, g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int); ap.add_argument("grid", type=float)
    ap.add_argument("--cluster-time", type=float, default=2.0)
    ap.add_argument("--top-time", type=float, default=30.0)
    ap.add_argument("--lns-time", type=float, default=60.0)
    ap.add_argument("--window", type=int, default=40)
    ap.add_argument("--iter-time", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--util", type=float, default=0.45)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cluster-util", type=float, default=0.65)
    ap.add_argument("--aspects", type=float, nargs="+", default=[1.0, 2.0])
    a = ap.parse_args()
    W_ = a.workers
    g = a.grid
    rnd = random.Random(a.seed)
    inst = make_instance(a.n, seed=a.seed, util=a.util)
    T0 = time.time()

    # ---------------- stage 1: clusters (soft macros: several aspect-ratio variants) ----------------
    clusters = {}
    for c in inst.comps:
        key = ("conn", c.id) if c.fp.tht else ("cl", c.cluster)   # connectors stay top-level singletons
        clusters.setdefault(key, []).append(c.id)
    macros = []          # list of dict(members=[...], variants=[(loc, MW, MH)])
    for key, members in clusters.items():
        if len(members) == 1:
            cid = members[0]
            W, H, _ = rot_offsets(inst.comps[cid].fp, 0, g)
            macros.append(dict(members=members, variants=[({cid: (0, 0, 0)}, W, H)]))
            continue
        mset = set(members)
        idmap = {cid: i for i, cid in enumerate(members)}
        comps = [Comp(i, inst.comps[cid].fp, 0) for i, cid in enumerate(members)]
        nets = []
        for net in inst.nets:
            inner = [(idmap[c], p) for (c, p) in net if c in mset]
            if len(inner) >= 2:
                nets.append(inner)
        dec = [(idmap[cc], cp, idmap[ic], ip, d) for (cc, cp, ic, ip, d) in inst.decaps if cc in mset and ic in mset]
        area = sum(inst.comps[cid].fp.w * inst.comps[cid].fp.h for cid in members)
        big = max(members, key=lambda cid: max(inst.comps[cid].fp.w, inst.comps[cid].fp.h))
        bmax = max(inst.comps[big].fp.w, inst.comps[big].fp.h) + 0.5
        bmin = min(inst.comps[big].fp.w, inst.comps[big].fp.h) + 0.5
        variants = []
        for asp in a.aspects:
            bw = max(math.sqrt(area / a.cluster_util * asp), bmax)
            bh = max(math.sqrt(area / a.cluster_util / asp), bmin)
            ok = False
            for attempt in range(8):
                sub = Instance(comps, nets, dec, bw, bh, [], {})
                m, V = build(sub, g, rot="var", sides=1, decap=True, objective=True)
                s, st = solve(m, a.cluster_time, workers=W_, seed=a.seed)
                if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    ok = True
                    break
                bw *= 1.1; bh *= 1.1
            if not ok:
                continue
            loc = extract(s, V, {i: cid for cid, i in idmap.items()})
            x0 = min(loc[cid][0] for cid in members); y0 = min(loc[cid][1] for cid in members)
            x1 = max(loc[cid][0] + rot_offsets(inst.comps[cid].fp, loc[cid][2], g)[0] for cid in members)
            y1 = max(loc[cid][1] + rot_offsets(inst.comps[cid].fp, loc[cid][2], g)[1] for cid in members)
            loc = {cid: (X - x0, Y - y0, k) for cid, (X, Y, k) in loc.items()}
            variants.append((loc, x1 - x0, y1 - y0))
        macros.append(dict(members=members, variants=variants))
    t1 = time.time() - T0

    # ---------------- stage 2: top-level floorplan with variant x rotation one-hot ----------------
    def mrot(u, v, K, MW, MH):
        if K == 0: return u, v
        if K == 1: return MH - v, u
        if K == 2: return MW - u, MH - v
        return v, MW - u

    BW, BH = math.floor(inst.board_w / g), math.floor(inst.board_h / g)
    m = cp_model.CpModel()
    xi, yi, MV, owner = [], [], [], {}
    pinX, pinY = {}, {}
    for mi, mac in enumerate(macros):
        for cid in mac["members"]:
            owner[cid] = mi
        x = m.new_int_var(0, BW, ""); y = m.new_int_var(0, BH, "")
        lits = [[m.new_bool_var("") for K in range(4)] for _ in mac["variants"]]
        m.add_exactly_one([l for row in lits for l in row])
        for vi, (loc, MW, MH) in enumerate(mac["variants"]):
            for par in (0, 1):
                pres = m.new_bool_var("")
                m.add(pres == lits[vi][par] + lits[vi][par + 2])
                w, h = (MW, MH) if par == 0 else (MH, MW)
                m.add(x + w <= BW).only_enforce_if(pres); m.add(y + h <= BH).only_enforce_if(pres)
                xi.append(m.new_optional_fixed_size_interval_var(x, w, pres, ""))
                yi.append(m.new_optional_fixed_size_interval_var(y, h, pres, ""))
        for cid in mac["members"]:
            for p in range(len(inst.comps[cid].fp.pins)):
                ex, ey = 0, 0
                for vi, (loc, MW, MH) in enumerate(mac["variants"]):
                    X, Y, k = loc[cid]
                    _, _, offs = rot_offsets(inst.comps[cid].fp, k, g)
                    u, v = X + offs[p][0], Y + offs[p][1]
                    for K in range(4):
                        ru, rv = mrot(u, v, K, MW, MH)
                        ex += lits[vi][K] * ru; ey += lits[vi][K] * rv
                pinX[(cid, p)] = x + ex; pinY[(cid, p)] = y + ey
        MV.append(dict(x=x, y=y, lits=lits))
    for (kx, ky, kw, kh) in inst.keepouts:
        X0, Y0 = math.floor(kx / g), math.floor(ky / g)
        X1, Y1 = min(math.ceil((kx + kw) / g), BW), min(math.ceil((ky + kh) / g), BH)
        xi.append(m.new_fixed_size_interval_var(X0, X1 - X0, "")); yi.append(m.new_fixed_size_interval_var(Y0, Y1 - Y0, ""))
    m.add_no_overlap_2d(xi, yi)
    obj = []
    for net in inst.nets:
        if len({owner[c] for (c, _) in net}) < 2:
            continue
        xs = [pinX[pp] for pp in net]; ys = [pinY[pp] for pp in net]
        A = m.new_int_var(0, BW, ""); B = m.new_int_var(0, BW, ""); C = m.new_int_var(0, BH, ""); D = m.new_int_var(0, BH, "")
        m.add_max_equality(A, xs); m.add_min_equality(B, xs); m.add_max_equality(C, ys); m.add_min_equality(D, ys)
        obj += [A - B, C - D]
    m.minimize(sum(obj))
    s, st = solve(m, a.top_time, workers=W_, seed=a.seed)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(json.dumps(dict(n=a.n, grid_mm=g, stage="top", status=s.status_name(st), t=round(time.time() - T0, 1))))
        return
    t2 = time.time() - T0

    # ---------------- flatten ----------------
    pos = {}
    for mi, mac in enumerate(macros):
        MX, MY = s.value(MV[mi]["x"]), s.value(MV[mi]["y"])
        vi, K = next((vi, K) for vi in range(len(mac["variants"])) for K in range(4) if s.value(MV[mi]["lits"][vi][K]))
        loc, MW, MH = mac["variants"][vi]
        for cid in mac["members"]:
            X, Y, k = loc[cid]
            W, H, _ = rot_offsets(inst.comps[cid].fp, k, g)
            rc = [mrot(u, v, K, MW, MH) for (u, v) in [(X, Y), (X + W, Y), (X, Y + H), (X + W, Y + H)]]
            pos[cid] = (MX + min(p[0] for p in rc), MY + min(p[1] for p in rc), (k + K) % 4)
    hp_flat = full_hpwl(inst, pos, g)
    print(json.dumps(dict(n=a.n, grid_mm=g, stage="hier", clusters=len(macros), variants=len(a.aspects), t_clusters=round(t1, 1),
                          t_total=round(t2, 1), top_status=s.status_name(st), hpwl_mm=round(hp_flat, 1),
                          check=check(inst, pos, g))), flush=True)

    # ---------------- stage 3: LNS on full model ----------------
    full, FV = build(inst, g, rot="var", sides=1, decap=True, objective=True)
    t_lns0 = time.time()
    best = dict(pos); best_hp = hp_flat; it = 0; acc = 0
    traj = [(round(time.time() - T0, 1), round(best_hp, 1))]
    while time.time() - t_lns0 < a.lns_time:
        it += 1
        seed_c = rnd.randrange(a.n)
        cx = best[seed_c][0]; cy = best[seed_c][1]
        order = sorted(range(a.n), key=lambda c: abs(best[c][0] - cx) + abs(best[c][1] - cy))
        window = set(order[:a.window])
        m2 = full.clone()
        for c in range(a.n):
            X, Y, k = best[c]
            v = FV[c]
            xv = m2.get_int_var_from_proto_index(v["x"].index)
            yv = m2.get_int_var_from_proto_index(v["y"].index)
            rv = [m2.get_bool_var_from_proto_index(r.index) for r in v["r"]]
            if c in window:
                m2.add_hint(xv, X); m2.add_hint(yv, Y)
                for kk in range(4): m2.add_hint(rv[kk], int(kk == k))
            else:
                m2.add(xv == X); m2.add(yv == Y)
                for kk in range(4): m2.add(rv[kk] == int(kk == k))
        s2, st2 = solve(m2, a.iter_time, workers=W_, seed=a.seed + it)
        if st2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            cand = {}
            for c in range(a.n):
                v = FV[c]
                k = [s2.value(m2.get_bool_var_from_proto_index(r.index)) for r in v["r"]].index(1)
                cand[c] = (s2.value(m2.get_int_var_from_proto_index(v["x"].index)),
                           s2.value(m2.get_int_var_from_proto_index(v["y"].index)), k)
            hp = full_hpwl(inst, cand, g)
            if hp < best_hp - 1e-9:
                best, best_hp, acc = cand, hp, acc + 1
        traj.append((round(time.time() - T0, 1), round(best_hp, 1)))
    print(json.dumps(dict(n=a.n, grid_mm=g, stage="lns", iters=it, accepted=acc, window=a.window,
                          iter_time=a.iter_time, t_total=round(time.time() - T0, 1), hpwl_mm=round(best_hp, 1),
                          check=check(inst, best, g),
                          traj=traj[::max(1, len(traj) // 12)])), flush=True)


if __name__ == "__main__":
    main()
