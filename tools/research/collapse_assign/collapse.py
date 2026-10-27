# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Layer collapse as a routing method (docs/ideas/original/layer-collapse.md, steps 1, 3, 5).

  lift      every net routed alone on one virtual layer: static blocks and foreign pads
            only, no other nets' copper. A cell is hard-blocked if every real layer has a
            foreign pad halo there (through-hole pads, stacked SMD pads); a cell where only
            some layers do (SMD pads) costs soft_cost extra and records the forbidden layers.
  conflict  lifted paths of two nets closer than the track-track halo radius conflict.
            Each path is cut into runs of constant signature (set of conflicting nets,
            layers forbidden by foreign pads); runs are the variables.
  assign    x_r in {0..L-1}. Cost: VIA per continuity edge (consecutive runs, tree
            junctions) with different layers, VIA per run end on an SMD pad of another
            layer, BIG per conflict edge on the same layer and per run on a forbidden
            layer, POUR per run of a plane net off its plane layers (4+ layers).
            Hadlock / Pinter constrained via minimization when L = 2; solved exactly by
            CP-SAT (optimality proven on every A/B board) and by L-state Potts annealing.
  realize   the assignment becomes a per-net layer prior: within radius_mm of a net's
            lifted path, layers other than the assigned one cost +beta in the history
            term while that net is routed; then the engine's PathFinder + legalize.
"""
import os
import json
import math
import random
import sys
import time

import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pnr"))

from raster import stamp_disc_path  # noqa: E402
from router import Router, astar  # noqa: E402

VIA = 10      # objective units per predicted via
BIG = 1000    # per unresolved conflict (two nets on one layer, or a run on a foreign pad)
POUR = 5      # per plane-net run off its plane layers


def zone_layer(world, lid):
    return 0 if lid == 0 else (world.nl - 1 if lid == 2 else (lid - 4) // 2 + 1)


# ---------------------------------------------------------------- 1. lift
class Lift:
    """Single virtual layer A* (the engine's astar kernel with nl = 1)."""

    def __init__(self, world, soft_cost=1.0, margin_mm=3.0):
        self.w = w = world
        H, W = w.H, w.W
        n = H * W
        self.static = w.blockT.any(0)
        self.gcost = np.zeros(n, np.float64)
        self.parent = np.zeros(n, np.int64)
        self.visit = np.zeros(n, np.int32)
        self.tgt = np.zeros(n, np.int32)
        self.hk = np.zeros(8 * n + 64, np.float64)
        self.hv = np.zeros(8 * n + 64, np.int64)
        self.buf = np.zeros((n, 3), np.int32)
        self.occ0 = np.zeros((1, 1, H, W), np.uint8)
        self.D0 = np.zeros((1, H, W), np.int16)
        self.noV = np.ones((1, H, W), bool)
        self.sid = 0
        self.soft = soft_cost
        self.margin = int(margin_mm / w.g)
        self.pres = 0.0
        self.net = 0
        self.D1 = self.occ1 = None

    def enable_spread(self):
        """Track the other lifted nets' halos on the virtual layer (spread lift)."""
        w = self.w
        self.D1 = np.zeros((1, w.H, w.W), np.int16)
        self.occ1 = np.zeros((w.N, 1, w.H, w.W), np.uint8)

    def stamp(self, net, res, delta):
        for p in res["paths"]:
            p3 = np.concatenate([np.zeros((len(p), 1), np.int32), p], 1).astype(np.int32)
            stamp_disc_path(self.occ1, self.D1, net, p3, self.w.offs_TT, delta, False, 1)

    def route(self, net, pres=0.0):
        """Returns dict(paths=[(k,2) y,x], start=[owner], end=[pin], pins=[(cells, layers)],
        forb=(L,H,W) foreign-halo map of this net, failed)."""
        w = self.w
        H, W, L = w.H, w.W, w.nl
        forb = (w.DT - (w.occT[net] > 0)) > 0
        nf = forb.sum(0)
        pins = []
        own = np.zeros((H, W), bool)
        for pi, k in w.net_pins[net]:
            if pi not in w.pose:
                continue
            t = np.array(w.terminals(pi, k), np.int32).reshape(-1, 3)
            t = t[(t[:, 1] >= 0) & (t[:, 2] >= 0) & (t[:, 1] < H) & (t[:, 2] < W)]
            cells = np.unique(t[:, 1:], axis=0) if len(t) else np.zeros((0, 2), np.int32)
            lay = sorted(set(int(v) for v in t[:, 0])) if len(t) else list(range(L))
            if len(cells):
                own[cells[:, 0], cells[:, 1]] = True
                pins.append((cells, lay))
        res = dict(paths=[], start=[], end=[], pins=pins, forb=forb, own=own, failed=0)
        self.pres, self.net = (pres, net) if pres > 0 else (0.0, 0)
        if len(pins) < 2:
            return res
        hard = self.static | ((nf == L) & ~own)
        hist = np.where((nf > 0) & ~hard, self.soft, 0.0).astype(np.float32)[None]
        ok = self._prim(res, hard, hist)
        if not ok:  # unreachable on one layer: drop the foreign-pad blocks
            res.update(paths=[], start=[], end=[], failed=0)
            hist = np.where(nf > 0, self.soft * 4, 0.0).astype(np.float32)[None]
            self._prim(res, self.static.copy(), hist)
        return res

    def _prim(self, res, hard, hist):
        w = self.w
        H, W = w.H, w.W
        pins = res["pins"]
        cents = np.array([c.mean(0) for c, _ in pins])
        start = int(np.argmin(((cents - cents.mean(0)) ** 2).sum(1)))
        owner = {}  # (y, x) -> ("pin", i) | ("path", j, c)
        tree = []

        def add_pin(i):
            c = pins[i][0]
            tree.append(c)
            for y, x in c:
                owner[(int(y), int(x))] = ("pin", i)

        add_pin(start)
        remaining = [i for i in range(len(pins)) if i != start]
        blockT = np.ascontiguousarray(hard[None])
        while remaining:
            src2 = np.concatenate(tree)
            src = np.concatenate([np.zeros((len(src2), 1), np.int32), src2], 1).astype(np.int32)
            allp = np.concatenate([src2] + [pins[i][0] for i in remaining])
            tc = np.array([cents[i][::-1] for i in remaining], np.float64)
            n = -1
            for m in (self.margin, max(H, W)):
                self.sid += 1
                sid = self.sid
                for i in remaining:
                    c = pins[i][0]
                    self.tgt[c[:, 0] * W + c[:, 1]] = sid
                by0, bx0 = np.maximum(allp.min(0) - m, 0)
                by1, bx1 = allp.max(0) + m
                bx1, by1 = min(W - 1, bx1), min(H - 1, by1)
                D, occ = (self.D1, self.occ1) if self.pres > 0 else (self.D0, self.occ0)
                n = astar(1, H, W, blockT, self.noV, D, self.D0, occ, self.occ0, self.net,
                          hist, self.pres, False, src, self.tgt, sid, bx0, by0, bx1, by1, 1e9, 0.0, tc,
                          self.gcost, self.parent, self.visit, self.hk, self.hv, self.buf,
                          np.zeros(1, np.int64))
                if n >= 0:
                    break
            if n < 0:
                res["failed"] += len(remaining)
                return False
            p = self.buf[:n, 1:].copy()
            ey, ex = int(p[-1, 0]), int(p[-1, 1])
            hit = next(i for i in remaining if np.any((pins[i][0][:, 0] == ey) & (pins[i][0][:, 1] == ex)))
            j = len(res["paths"])
            res["start"].append(owner[(int(p[0, 0]), int(p[0, 1]))])
            res["end"].append(hit)
            res["paths"].append(p)
            for c, (y, x) in enumerate(p):
                owner.setdefault((int(y), int(x)), ("path", j, c))
            tree.append(p)
            add_pin(hit)
            remaining.remove(hit)
        return True


# ---------------------------------------------------------------- 2. conflict graph
class Graph:
    pass


def build_graph(world, lifts, pour=None):
    """Runs, continuity edges, conflict edges and unary terms from the lifted nets."""
    w = world
    H, W, L = w.H, w.W, w.nl
    rad = w.R.R_TT / w.g
    pour = pour or {}
    nets = [n for n in lifts if lifts[n]["paths"]]
    cells, owner_idx = {}, {}
    for n in nets:
        ps = lifts[n]["paths"]
        cells[n] = np.concatenate(ps)
        owner_idx[n] = np.concatenate([np.stack([np.full(len(p), j), np.arange(len(p))], 1)
                                       for j, p in enumerate(ps)])
    conf = {n: [[set() for _ in p] for p in lifts[n]["paths"]] for n in nets}
    pairs = []  # (n, j, c, m, j', c')
    r1 = int(math.ceil(rad)) + 1
    lab = np.full((H, W), -1, np.int64)
    for m in nets:
        cm = cells[m]
        y0, x0 = np.maximum(cm.min(0) - r1, 0)
        y1, x1 = np.minimum(cm.max(0) + r1 + 1, (H, W))
        mask = np.ones((y1 - y0, x1 - x0), bool)
        mask[cm[:, 0] - y0, cm[:, 1] - x0] = False
        dist, (iy, ix) = ndimage.distance_transform_edt(mask, return_indices=True)
        lab[cm[:, 0], cm[:, 1]] = np.arange(len(cm))
        for n in nets:
            if n == m:
                continue
            cn = cells[n]
            inb = (cn[:, 0] >= y0) & (cn[:, 0] < y1) & (cn[:, 1] >= x0) & (cn[:, 1] < x1)
            idx = np.nonzero(inb)[0]
            if not len(idx):
                continue
            yy, xx = cn[idx, 0] - y0, cn[idx, 1] - x0
            hit = dist[yy, xx] <= rad
            for q in idx[hit]:
                yy_, xx_ = cn[q, 0] - y0, cn[q, 1] - x0
                k = lab[iy[yy_, xx_] + y0, ix[yy_, xx_] + x0]
                j, c = owner_idx[n][q]
                jm, cmi = owner_idx[m][k]
                conf[n][j][c].add(m)
                pairs.append((n, int(j), int(c), m, int(jm), int(cmi)))
        lab[cm[:, 0], cm[:, 1]] = -1
    # runs
    G = Graph()
    G.L = L
    G.runs = []      # dict(net, path, a, b, conf, forb, critical, ncells)
    G.run_of = {}    # (net, path) -> int array cell -> run id
    for n in nets:
        lf = lifts[n]
        forb, own = lf["forb"], lf["own"]
        for j, p in enumerate(lf["paths"]):
            fb = forb[:, p[:, 0], p[:, 1]].copy()
            fb[:, own[p[:, 0], p[:, 1]]] = False
            bits = (fb * (1 << np.arange(L))[:, None]).sum(0)
            sig = [(frozenset(conf[n][j][c]), int(bits[c])) for c in range(len(p))]
            ids = np.zeros(len(p), np.int64)
            a = 0
            for c in range(1, len(p) + 1):
                if c == len(p) or sig[c] != sig[a]:
                    rid = len(G.runs)
                    s, b = sig[a]
                    G.runs.append(dict(net=n, path=j, a=a, b=c, conf=s, forb=b,
                                       critical=bool(s) or b != 0))
                    ids[a:c] = rid
                    a = c
            G.run_of[(n, j)] = ids
    R = len(G.runs)
    cont, unary = set(), []  # unary: (run, allowed layer set, weight)
    for n in nets:
        lf = lifts[n]
        allL = set(range(L))
        for j, p in enumerate(lf["paths"]):
            ids = G.run_of[(n, j)]
            for c in range(1, len(p)):
                if ids[c] != ids[c - 1]:
                    cont.add((int(ids[c - 1]), int(ids[c])))
            st = lf["start"][j]
            if st[0] == "path":
                cont.add((int(G.run_of[(n, st[1])][st[2]]), int(ids[0])))
            else:
                lay = set(lf["pins"][st[1]][1])
                if lay != allL:
                    unary.append((int(ids[0]), lay, VIA))
            lay = set(lf["pins"][lf["end"][j]][1])
            if lay != allL:
                unary.append((int(ids[-1]), lay, VIA))
        if n in pour:
            for j in range(len(lf["paths"])):
                for rid in set(G.run_of[(n, j)].tolist()):
                    unary.append((rid, set(pour[n]), POUR))
    for rid, r in enumerate(G.runs):
        if r["forb"]:
            unary.append((rid, {l for l in range(L) if not (r["forb"] >> l) & 1}, BIG))
    confl = set()
    for n, j, c, m, jm, cm in pairs:
        a, b = int(G.run_of[(n, j)][c]), int(G.run_of[(m, jm)][cm])
        confl.add((min(a, b), max(a, b)))
    G.cont = sorted((min(a, b), max(a, b)) for a, b in cont if a != b)
    G.cont = sorted(set(G.cont))
    G.confl = sorted(confl)
    G.unary = unary
    G.nets = nets
    G.R = R
    G.net_pairs = sorted({(min(n, m), max(n, m)) for n, _, _, m, _, _ in pairs})
    # junction degrees of the lifted trees (Steiner points on a path: 2 + branches;
    # pads: number of paths ending or starting there). Planar max-cut is exact for
    # constrained via minimization only when every junction has degree <= 3.
    deg = {}
    for n in nets:
        lf = lifts[n]
        for j, st in enumerate(lf["start"]):
            key = (n,) + tuple(st[:3]) if st[0] == "path" else (n, "pin", st[1])
            deg[key] = deg.get(key, 2 if st[0] == "path" else 0) + 1
        for e in lf["end"]:
            deg[(n, "pin", e)] = deg.get((n, "pin", e), 0) + 1
    G.junction_deg = list(deg.values())
    return G


def energy(G, x):
    e = 0
    for a, b in G.cont:
        e += VIA * (x[a] != x[b])
    for a, b in G.confl:
        e += BIG * (x[a] == x[b])
    for r, lay, wgt in G.unary:
        e += wgt * (x[r] not in lay)
    return e


def breakdown(G, x):
    vias = sum(int(x[a] != x[b]) for a, b in G.cont) + \
        sum(int(x[r] not in lay) for r, lay, wgt in G.unary if wgt == VIA)
    unres = sum(int(x[a] == x[b]) for a, b in G.confl) + \
        sum(int(x[r] not in lay) for r, lay, wgt in G.unary if wgt == BIG)
    return dict(vias=vias, unresolved=unres, energy=int(energy(G, x)))


# ---------------------------------------------------------------- 3. assignment
def components(G):
    par = list(range(G.R))

    def f(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in G.cont + G.confl:
        ra, rb = f(a), f(b)
        if ra != rb:
            par[ra] = rb
    comp = {}
    for r in range(G.R):
        comp.setdefault(f(r), []).append(r)
    return list(comp.values())


def solve_cpsat(G, time_limit=30.0, hint=None, workers=1):
    """Exact minimum of the assignment energy, one CP-SAT model per connected component.
    L = 2: Boolean x (layer 1 if true), the Hadlock/Pinter via-minimization ILP; L > 2:
    one-hot. Returns (x, status, lower bound)."""
    from ortools.sat.python import cp_model
    L = G.L
    x = np.zeros(G.R, np.int64)
    worst, bound = "OPTIMAL", 0.0
    comps = sorted(components(G), key=len)
    t_end = time.time() + time_limit
    for ci, comp in enumerate(comps):
        cs = set(comp)
        loc = {r: i for i, r in enumerate(comp)}
        cont = [(loc[a], loc[b]) for a, b in G.cont if a in cs]
        confl = [(loc[a], loc[b]) for a, b in G.confl if a in cs]
        un = [(loc[r], lay, wgt) for r, lay, wgt in G.unary if r in cs]
        n = len(comp)
        m = cp_model.CpModel()
        obj = []
        if L == 2:
            v = [m.NewBoolVar("") for _ in range(n)]
            for a, b in cont:
                d = m.NewBoolVar("")
                m.AddBoolOr([v[a], v[b].Not(), d])
                m.AddBoolOr([v[a].Not(), v[b], d])
                obj.append(VIA * d)
            for a, b in confl:
                s = m.NewBoolVar("")
                m.AddBoolOr([v[a], v[b], s])
                m.AddBoolOr([v[a].Not(), v[b].Not(), s])
                obj.append(BIG * s)
            for r, lay, wgt in un:
                if 0 not in lay:
                    obj.append(wgt * v[r].Not())
                if 1 not in lay:
                    obj.append(wgt * v[r])
            if hint is not None:
                for r in range(n):
                    m.AddHint(v[r], int(hint[comp[r]] == 1))
        else:
            y = [[m.NewBoolVar("") for _ in range(L)] for _ in range(n)]
            for r in range(n):
                m.AddExactlyOne(y[r])
            for a, b in cont:
                zs = []
                for l in range(L):
                    z = m.NewBoolVar("")
                    m.AddImplication(z, y[a][l])
                    m.AddImplication(z, y[b][l])
                    zs.append(z)
                s = m.NewBoolVar("")
                m.Add(sum(zs) >= s)
                obj.append(VIA * (1 - s))
            for a, b in confl:
                for l in range(L):
                    z = m.NewBoolVar("")
                    m.AddBoolOr([y[a][l].Not(), y[b][l].Not(), z])
                    obj.append(BIG * z)
            for r, lay, wgt in un:
                for l in range(L):
                    if l not in lay:
                        obj.append(wgt * y[r][l])
            if hint is not None:
                for r in range(n):
                    for l in range(L):
                        m.AddHint(y[r][l], int(hint[comp[r]] == l))
        if not obj:
            continue
        m.Minimize(sum(obj))
        sv = cp_model.CpSolver()
        left = max(1.0, (t_end - time.time()) / (len(comps) - ci))
        sv.parameters.max_time_in_seconds = left
        sv.parameters.num_workers = workers
        if workers == 1:  # core-based (max-SAT style) search proves these quickly
            sv.parameters.optimize_with_core = True
        st = sv.Solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            x[comp] = hint[comp] if hint is not None else 0
            worst = "UNKNOWN"
            continue
        if st == cp_model.FEASIBLE:
            worst = "FEASIBLE"
        bound += sv.BestObjectiveBound()
        for r in range(n):
            x[comp[r]] = int(sv.Value(v[r])) if L == 2 else \
                next(l for l in range(L) if sv.Value(y[r][l]))
    if hint is not None and energy(G, hint) < energy(G, x):
        x = np.array(hint, np.int64)  # time-limited search did not reach the hint
    return x, worst, bound


def solve_potts(G, seed=0, sweeps=400, restarts=4, t0=60.0, t1=0.5):
    """L-state Potts annealing (Metropolis, single-site moves, geometric schedule)."""
    L, R = G.L, G.R
    rng = random.Random(seed)
    nb = [[] for _ in range(R)]  # (other, kind) kind: 0 ferro VIA, 1 antiferro BIG
    for a, b in G.cont:
        nb[a].append((b, VIA, 0))
        nb[b].append((a, VIA, 0))
    for a, b in G.confl:
        nb[a].append((b, BIG, 1))
        nb[b].append((a, BIG, 1))
    un = [np.zeros(L) for _ in range(R)]
    for r, lay, wgt in G.unary:
        for l in range(L):
            if l not in lay:
                un[r][l] += wgt

    def local(x, r, l):
        e = un[r][l]
        for o, wgt, k in nb[r]:
            e += wgt * ((x[o] == l) if k else (x[o] != l))
        return e

    best, best_e = None, math.inf
    for _ in range(restarts):
        x = [rng.randrange(L) for _ in range(R)]
        for s in range(sweeps):
            T = t0 * (t1 / t0) ** (s / max(1, sweeps - 1))
            for r in rng.sample(range(R), R):
                cur = x[r]
                l = rng.randrange(L - 1)
                l = l + (l >= cur)
                d = local(x, r, l) - local(x, r, cur)
                if d <= 0 or rng.random() < math.exp(-d / T):
                    x[r] = l
        # zero-temperature polish
        changed = True
        while changed:
            changed = False
            for r in range(R):
                es = [local(x, r, l) for l in range(L)]
                l = int(np.argmin(es))
                if es[l] < es[x[r]]:
                    x[r] = l
                    changed = True
        e = energy(G, x)
        if e < best_e:
            best, best_e = list(x), e
    return np.array(best, np.int64)


# ---------------------------------------------------------------- graph statistics
def graph_stats(G):
    import networkx as nx
    out = dict(nets=len(G.nets), runs=G.R, critical=sum(r["critical"] for r in G.runs),
               cont_edges=len(G.cont), conflict_edges=len(G.confl), net_pairs=len(G.net_pairs),
               pad_forbid=sum(1 for _, _, wgt in G.unary if wgt == BIG),
               pad_layer_ends=sum(1 for _, _, wgt in G.unary if wgt == VIA))
    gn = nx.Graph()
    gn.add_nodes_from(G.nets)
    gn.add_edges_from(G.net_pairs)
    out["junction_max_deg"] = max(G.junction_deg, default=0)
    out["junctions_deg4plus"] = sum(1 for d in G.junction_deg if d >= 4)
    out["net_graph_planar"] = bool(nx.check_planarity(gn)[0])
    out["net_graph_bipartite"] = bool(nx.is_bipartite(gn))
    try:
        out["net_graph_clique"] = max((len(c) for c in nx.find_cliques(gn)), default=0)
    except Exception:
        out["net_graph_clique"] = -1
    gr = nx.Graph()
    gr.add_nodes_from(range(G.R))
    gr.add_edges_from(G.confl)
    out["run_conflict_bipartite"] = bool(nx.is_bipartite(gr))
    gfull = nx.Graph()
    gfull.add_nodes_from(range(G.R))
    gfull.add_edges_from(G.confl)
    gfull.add_edges_from(G.cont)
    out["run_graph_planar"] = bool(nx.check_planarity(gfull)[0])
    # odd cycles in the run conflict graph: minimum number of conflict edges left
    # monochromatic by any 2-colouring is a lower bound on unresolved conflicts at L = 2
    return out


# ---------------------------------------------------------------- 4. realize
def bias_maps(world, lifts, G, x, beta=1.0, beta_free=0.3, radius_mm=1.0):
    w = world
    H, W, L = w.H, w.W, w.nl
    rr = radius_mm / w.g
    r1 = int(math.ceil(rr)) + 1
    out = {}
    for n in G.nets:
        cs, lays, wts = [], [], []
        for j, p in enumerate(lifts[n]["paths"]):
            ids = G.run_of[(n, j)]
            cs.append(p)
            lays.append(x[ids])
            wts.append(np.array([beta if G.runs[i]["critical"] else beta_free for i in ids]))
        c = np.concatenate(cs)
        lay = np.concatenate(lays)
        wt = np.concatenate(wts)
        y0, x0 = np.maximum(c.min(0) - r1, 0)
        y1, x1 = np.minimum(c.max(0) + r1 + 1, (H, W))
        labl = np.full((y1 - y0, x1 - x0), -1, np.int64)
        labw = np.zeros((y1 - y0, x1 - x0), np.float32)
        labl[c[:, 0] - y0, c[:, 1] - x0] = lay
        labw[c[:, 0] - y0, c[:, 1] - x0] = wt
        dist, (iy, ix) = ndimage.distance_transform_edt(labl < 0, return_indices=True)
        near = labl[iy, ix]
        nw = np.where(dist <= rr, labw[iy, ix], 0.0).astype(np.float32)
        b = np.zeros((L, y1 - y0, x1 - x0), np.float32)
        for l in range(L):
            b[l] = np.where(near != l, nw, 0.0)
        if b.any():
            out[n] = (int(y0), int(x0), b)
    return out


class BiasRouter(Router):
    """Router whose history term carries a per-net layer prior while that net routes."""

    def __init__(self, world, bias, decay=1.0, **kw):
        super().__init__(world, **kw)
        self.bias = bias
        self.decay = decay
        self.calls = {}

    def route_net(self, net, hard=False, pres=None):
        b = self.bias.get(net)
        if b is None:
            return super().route_net(net, hard=hard, pres=pres)
        k = self.calls.get(net, 0)
        self.calls[net] = k + 1
        s = self.decay ** k
        if s < 1e-3:
            return super().route_net(net, hard=hard, pres=pres)
        y0, x0, arr = b
        h = self.w.hist
        sl = (slice(None), slice(y0, y0 + arr.shape[1]), slice(x0, x0 + arr.shape[2]))
        saved = h[sl].copy()
        h[sl] += s * arr
        try:
            return super().route_net(net, hard=hard, pres=pres)
        finally:
            h[sl] = saved


def agreement(router, bias):
    """Share of routed cells (inside a net's prior corridor) on the assigned layer."""
    tot = good = 0
    for n, ps in router.routes.items():
        b = bias.get(n)
        if b is None:
            continue
        y0, x0, arr = b
        corr = arr.max(0) > 0
        for p in ps:
            yy, xx = p[:, 1] - y0, p[:, 2] - x0
            ok = (yy >= 0) & (xx >= 0) & (yy < arr.shape[1]) & (xx < arr.shape[2])
            l, yy, xx = p[ok, 0], yy[ok], xx[ok]
            inc = corr[yy, xx]
            tot += int(inc.sum())
            good += int((arr[l, yy, xx][inc] == 0).sum())
    return round(good / tot, 3) if tot else None


# ---------------------------------------------------------------- the pipeline
def pour_layers(world):
    """Plane nets (4+ layers): nets with a zone on an inner layer -> their zone layers."""
    if world.nl < 4:
        return {}
    out = {}
    for z in world.data.get("zones", []):
        if not z["net"]:
            continue
        ls = {zone_layer(world, lid) for lid in z["layers"]}
        if any(0 < l < world.nl - 1 for l in ls) and z["net"] in world.net_id:
            out.setdefault(world.net_id[z["net"]], set()).update(ls)
    return out


def lift_and_assign(world, seed=0, solver="cpsat", log=print, soft_cost=1.0, cpsat_s=40.0,
                    spread=0, spread_pres=0.5):
    """spread > 0: after the pure lift, `spread` rounds of single-layer negotiation where
    each net is re-lifted with the other lifted nets priced at spread_pres per foreign
    halo (crossings stay cheap, shared corridors do not)."""
    t0 = time.time()
    lift = Lift(world, soft_cost=soft_cost)
    lifts = {n: lift.route(n) for n in world.net_pins}
    if spread:
        lift.enable_spread()
        for n, lf in lifts.items():
            lift.stamp(n, lf, 1)
        for _ in range(spread):
            for n in list(lifts):
                if not lifts[n]["paths"]:
                    continue
                lift.stamp(n, lifts[n], -1)
                lifts[n] = lift.route(n, pres=spread_pres)
                lift.stamp(n, lifts[n], 1)
    t_lift = time.time() - t0
    G = build_graph(world, lifts, pour=pour_layers(world))
    st = graph_stats(G)
    st["lift_failed"] = sum(lf["failed"] for lf in lifts.values())
    st["lift_len_mm"] = round(sum(float(np.sum(np.sqrt((np.diff(p, axis=0) ** 2).sum(1))))
                                  for lf in lifts.values() for p in lf["paths"]) * world.g, 1)
    t1 = time.time()
    xp = solve_potts(G, seed=seed) if G.R else np.zeros(0, np.int64)
    st["potts"] = breakdown(G, xp)
    t2 = time.time()
    xe, status, bound = solve_cpsat(G, time_limit=cpsat_s, hint=xp) if G.R else (xp, "EMPTY", 0)
    t3 = time.time()
    if xe is not None:
        st["exact"] = breakdown(G, xe)
        st["exact"].update(status=status, bound=bound)
    st["t"] = dict(lift=round(t_lift, 2), potts=round(t2 - t1, 2), cpsat=round(t3 - t2, 2))
    x = xe if (solver == "cpsat" and xe is not None) else xp
    if solver == "random":  # control: same prior machinery, assignment carries no information
        rng = np.random.default_rng(seed + 12345)
        x = rng.integers(0, world.nl, G.R)
        st["random"] = breakdown(G, x)
    log(f"collapse graph {st}")
    return lifts, G, x, st


def collapse(world, seed=0, budget=300, log=print, beta=1.0, beta_free=0.3, radius_mm=1.0,
             solver="cpsat", iters=40, decay=1.0, soft_cost=1.0, spread=0, spread_pres=0.5, **kw):
    for pi in range(len(world.parts)):
        world.place_original(pi)
    lifts, G, x, st = lift_and_assign(world, seed=seed, solver=solver, log=log, soft_cost=soft_cost,
                                      spread=spread, spread_pres=spread_pres)
    bias = bias_maps(world, lifts, G, x, beta=beta, beta_free=beta_free, radius_mm=radius_mm)
    rk = {k: v for k, v in kw.items() if k in ("via_cost_mm", "dir_pen")}
    r = BiasRouter(world, bias, decay=decay, **rk)
    r.pathfinder(log=log, iters=iters)
    rs = r.stats()
    st.update(realized=rs, agreement=agreement(r, bias),
              params=dict(beta=beta, beta_free=beta_free, radius_mm=radius_mm, solver=solver,
                          decay=decay, soft_cost=soft_cost, spread=spread, spread_pres=spread_pres))
    log(f"collapse {rs}")
    print("COLLAPSE " + json.dumps(st, default=str), flush=True)
    return r


def collapse_potts(world, **kw):
    kw.setdefault("solver", "potts")
    return collapse(world, **kw)


def control(world, seed=0, budget=300, log=print, iters=40, **kw):
    """Same pipeline statistics, no prior (= methods.route_only + the graph report)."""
    for pi in range(len(world.parts)):
        world.place_original(pi)
    lifts, G, x, st = lift_and_assign(world, seed=seed, log=log)
    r = Router(world)
    r.pathfinder(log=log, iters=iters)
    st.update(realized=r.stats())
    print("COLLAPSE " + json.dumps(st, default=str), flush=True)
    return r
