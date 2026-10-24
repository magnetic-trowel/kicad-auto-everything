# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Analytic obstruction bounds on the copper layer count of a placed board.

Input is the JSON written by tools/research/pnr/kicad_io.py extract (human placement,
fixed pin positions). Bounds, all computed per board:

  side      SMD pads on both sides need >= 2 layers.
  topo      via-free graph thickness: part-net incidence graph (parts as vertices,
            nets as star vertices) and a wheel model (pads of a part as a rim around
            a hub, so pin order is fixed). Euler bounds and greedy planar peeling.
            With vias any netlist fits on 2 layers, so only planar/non-planar matters
            for the real board.
  cut       capacity: for straight chords of the board, circles on a grid and
            rectangular rings around every part (inside and outside its pad box),
            nets with pads strictly on both sides must cross. Each crossing takes
            pitch p = w + c of free cut length on some layer; pads on the cut block
            their layers (inscribed disc), and a net with a pad on the cut is not
            counted (it may cross through its own pad). Minimal L per cut, max over
            cuts.
  escape    array packages (BGA/LGA): engineering ring-escape formula with t tracks
            between balls on the top layer and between dog-bone vias below.
  area      wiring area: sum of net Steiner lengths (>= 0.824 * MST) times p must fit
            in L times the board area.

Two net sets: "all" (every net with >= 2 pads) and "nopour" (nets that own a copper
zone removed: they are planes/pours).
"""
import math
import re
import time

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.spatial.distance import pdist, squareform
import shapely
from shapely.geometry import Polygon, MultiPolygon

STEINER = 0.824  # Chung-Graham lower bound on Euclidean Steiner ratio
LF, LB, LI = 1, 2, 4  # layer-class bits: front, back, inner


def kicad_rot(x, y, deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return x * c + y * s, -x * s + y * c


def min_routed_track(pcb_path):
    """Smallest track width actually routed on the reference board (mm), or None."""
    try:
        txt = open(pcb_path).read()
    except OSError:
        return None
    ws = [float(w) for w in re.findall(r"\(segment\b[^()]*(?:\([^()]*\)[^()]*)*?\(width ([\d.]+)\)", txt)]
    ws = [w for w in ws if w > 0]
    return min(ws) if ws else None


class Board:
    def __init__(self, d, pcb_path=None, stats=None):
        self.d = d
        self.layers = d["layers"]
        # ---- outline
        rings = [np.asarray(o, float) for o in d["outline"] if len(o) >= 3]
        holes = [np.asarray(h, float) for h in d.get("outline_holes", []) if len(h) >= 3]
        polys = [Polygon(r).buffer(0) for r in rings]
        self.outline_src = "edge-cuts"
        if not polys:  # no Edge.Cuts outline: fall back to the bbox recorded by prepare
            st = stats or {}
            if st.get("board_mm") and st.get("board_origin_mm"):
                (w, h), (x0, y0) = st["board_mm"], st["board_origin_mm"]
                polys = [shapely.box(x0, y0, x0 + w, y0 + h)]
                self.outline_src = "stats-bbox"
            else:
                pts = [(f["x"], f["y"]) for f in d["footprints"]]
                polys = [shapely.MultiPoint(pts).convex_hull.buffer(2.0)]
                self.outline_src = "footprint-hull"
        geom = shapely.unary_union(polys)
        for h in holes:
            geom = geom.difference(Polygon(h).buffer(0))
        self.geom = geom
        self.rings_outer, self.rings_hole = [], []
        for g in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
            if g.is_empty:
                continue
            self.rings_outer.append(np.asarray(g.exterior.coords))
            self.rings_hole += [np.asarray(i.coords) for i in g.interiors]
        self.area = geom.area
        minx, miny, maxx, maxy = geom.bounds
        self.bounds = (minx, miny, maxx, maxy)
        # ---- nets
        zone_nets = {z["net"] for z in d.get("zones", []) if z["net"]}
        self.zone_nets = zone_nets
        # ---- pads
        X, Y, RIN, ROUT, LM, NET, FP, AREA = [], [], [], [], [], [], [], []
        netname = []
        netidx = {}
        self.fps = []
        for fi, fp in enumerate(d["footprints"]):
            loc = []
            for p in fp["pads"]:
                if p["cu"] == "none" and not p.get("npth"):
                    continue
                if p["poly"]:
                    pg = Polygon(p["poly"][0]).buffer(0)
                    if pg.is_empty:
                        continue
                    mrr = np.asarray(pg.minimum_rotated_rectangle.exterior.coords)
                    sides = np.hypot(*np.diff(mrr[:3], axis=0).T)
                    rin = 0.5 * float(sides.min())
                    v = np.asarray(p["poly"][0])
                    rout = float(np.hypot(v[:, 0] - p["x"], v[:, 1] - p["y"]).max())
                    a = pg.area
                else:
                    dr = [x for x in p["drill"] if x > 0] or [0.0]
                    rin, rout, a = min(dr) / 2, max(dr) / 2, math.pi * (min(dr) / 2) ** 2
                lm = {"F": LF, "B": LB}.get(p["cu"], LF | LB | LI)
                bx, by = kicad_rot(p["x"], p["y"], fp["rot"])
                n = -1
                if p["net"] and p["cu"] != "none":
                    n = netidx.setdefault(p["net"], len(netidx))
                    if n == len(netname):
                        netname.append(p["net"])
                X.append(bx + fp["x"]); Y.append(by + fp["y"]); RIN.append(rin); ROUT.append(rout)
                LM.append(lm); NET.append(n); FP.append(fi); AREA.append(a)
                loc.append((p["x"], p["y"]))
            self.fps.append(dict(ref=fp["ref"], x=fp["x"], y=fp["y"], rot=fp["rot"], back=fp["back"],
                                 loc=np.asarray(loc).reshape(-1, 2)))
        self.x, self.y = np.asarray(X), np.asarray(Y)
        self.rin, self.rout = np.asarray(RIN), np.asarray(ROUT)
        self.lm, self.net, self.fp = np.asarray(LM, int), np.asarray(NET, int), np.asarray(FP, int)
        self.parea = np.asarray(AREA)
        # nets with >= 2 pads
        cnt = np.bincount(self.net[self.net >= 0], minlength=len(netname))
        keep = cnt >= 2
        remap = -np.ones(len(netname), int)
        remap[keep] = np.arange(keep.sum())
        self.net = np.where(self.net >= 0, remap[np.maximum(self.net, 0)], -1)
        self.netname = [n for n, k in zip(netname, keep) if k]
        self.nn = len(self.netname)
        self.npads_net = np.bincount(self.net[self.net >= 0], minlength=self.nn)
        self.pour = np.array([n in zone_nets for n in self.netname], bool)
        # connectivity pads
        self.ci = np.nonzero(self.net >= 0)[0]
        # ---- pitch
        rules = d["rules"]
        ncs = {}
        for n in self.netname:
            ncs[n] = d["nets"].get(n) or d["default"]
        used_c = [v["clearance"] for v in ncs.values()] or [d["default"]["clearance"]]
        self.c_lb = max(rules["min_clearance"], min(used_c))
        self.w_routed = min_routed_track(pcb_path) if pcb_path else None
        if rules["min_track"] > 0:
            self.w_lb, self.w_src = rules["min_track"], "rule"
        elif self.w_routed:
            self.w_lb, self.w_src = self.w_routed, "routed-min"
        else:
            self.w_lb, self.w_src = min(v["width"] for v in ncs.values()), "netclass"
        if self.c_lb <= 0:
            self.c_lb = 0.1
        self.p_lb = self.w_lb + self.c_lb
        self.p_nom = np.array([ncs[n]["width"] + ncs[n]["clearance"] for n in self.netname])
        self.via_d = rules["min_via"] if rules["min_via"] > 0 else d["default"]["via_d"]
        self.stats = stats or {}
        self.sides = set()
        for i in self.ci:
            if self.lm[i] == LF:
                self.sides.add("F")
            elif self.lm[i] == LB:
                self.sides.add("B")
        # incidence matrix net x conn-pad (for "net has a pad on the cut")
        self.M = csr_matrix((np.ones(len(self.ci)), (self.net[self.ci], np.arange(len(self.ci)))),
                            shape=(self.nn, len(self.ci)))
        self._mask = None

    # ------------------------------------------------------------------ helpers
    def board_mask(self, h=None):
        if self._mask is None:
            minx, miny, maxx, maxy = self.bounds
            h = h or max((maxx - minx), (maxy - miny)) / 800
            gx = np.arange(minx, maxx + h, h)
            gy = np.arange(miny, maxy + h, h)
            XX, YY = np.meshgrid(gx, gy)
            m = shapely.contains_xy(self.geom, XX.ravel(), YY.ravel()).reshape(XX.shape)
            self._mask = (m, minx, miny, h)
        return self._mask

    def inboard(self, px, py):
        m, x0, y0, h = self.board_mask()
        i = np.round((py - y0) / h).astype(int)
        j = np.round((px - x0) / h).astype(int)
        ok = (i >= 0) & (i < m.shape[0]) & (j >= 0) & (j < m.shape[1])
        out = np.zeros(px.shape, bool)
        out[ok] = m[i[ok], j[ok]]
        return out


def layers_needed(n, fF, fB, fI, p, c):
    """Smallest L with n crossings <= capacity of the first L layers (vectorized)."""
    cap = lambda f: np.floor(np.maximum(f + c, 0) / p)
    cF, cB, cI = cap(fF), cap(fB), cap(fI)
    L = np.where(n <= cF, 1, np.where(n <= cF + cB, 2, 0)).astype(float)
    rest = n - cF - cB
    with np.errstate(divide="ignore", invalid="ignore"):
        more = 2 + np.ceil(rest / cI)
    more = np.where(cI > 0, more, np.inf)
    L = np.where(L == 0, more, L)
    L = np.where(n == 0, 1, L)
    return np.maximum(L, 1)


def demand(n_len, fF, fB):
    """Fractional layers: required crossing length over mean outer-layer free length."""
    f = 0.5 * (fF + fB)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(f > 0, n_len / f, np.where(n_len > 0, np.inf, 0.0))


# ---------------------------------------------------------------------- cuts core
def classify(B, sdf_c, sdf_b, rin_b, lm_b):
    """Given signed distances of conn pads (sdf_c: npads x ncuts, <0 inside) and of
    blocker pads, return crossing masks and per-layer blocked length.
    Returns cross (nn x ncuts bool), blocked dict F/B/I (ncuts)."""
    R = B.rout[B.ci][:, None]
    inside = sdf_c < -R
    on = np.abs(sdf_c) <= R
    outside = ~inside & ~on
    M = B.M
    nin = M @ inside.astype(np.float32)
    non = M @ on.astype(np.float32)
    nout = M @ outside.astype(np.float32)
    cross = (nin > 0) & (nout > 0) & (non == 0)
    ch = 2 * np.sqrt(np.maximum(rin_b[:, None] ** 2 - sdf_b ** 2, 0))
    blk = {k: ((lm_b & bit) > 0).astype(np.float32) @ ch for k, bit in (("F", LF), ("B", LB), ("I", LI))}
    return cross, blk


def evaluate(B, cross, blk, length):
    """Per-cut layer bounds for the two net sets, plus fractional demand."""
    res = {}
    for key, use in (("all", np.ones(B.nn, bool)), ("nopour", ~B.pour)):
        cu = cross & use[:, None]
        n = cu.sum(0)
        fF = np.maximum(length - blk["F"], 0)
        fB = np.maximum(length - blk["B"], 0)
        fI = np.maximum(length - blk["I"], 0)
        L = layers_needed(n, fF, fB, fI, B.p_lb, B.c_lb)
        nlen = B.p_nom @ cu
        # nominal: required length with netclass pitch vs free length per layer
        Lnom = np.where(nlen <= fF, 1, np.where(nlen <= fF + fB, 2,
                        2 + np.ceil(np.maximum(nlen - fF - fB, 0) / np.maximum(fI, 1e-9))))
        Lnom = np.where(n == 0, 1, Lnom)
        res[key] = dict(n=n, L=L, Lnom=Lnom, d=demand(n * B.p_lb, fF, fB), dnom=demand(nlen, fF, fB))
    return res


def ring_length(rings, nx, ny, t):
    """Total length of the line {p . n = t} inside the closed rings (vectorized in t)."""
    tot = np.zeros_like(t)
    for r in rings:
        u = r[:, 0] * nx + r[:, 1] * ny
        v = -r[:, 0] * ny + r[:, 1] * nx
        u1, u2, v1, v2 = u[:-1], u[1:], v[:-1], v[1:]
        du = u2 - u1
        ok = du != 0
        u1, u2, v1, v2, du = u1[ok], u2[ok], v1[ok], v2[ok], du[ok]
        lo, hi = np.minimum(u1, u2)[:, None], np.maximum(u1, u2)[:, None]
        hit = (t[None, :] >= lo) & (t[None, :] < hi)
        vi = v1[:, None] + (t[None, :] - u1[:, None]) * ((v2 - v1) / du)[:, None]
        tot += np.abs((np.sign(du)[:, None] * vi * hit).sum(0))
    return tot


def straight_cuts(B, n_theta=60, n_off=400):
    xc, yc = B.x[B.ci], B.y[B.ci]
    best = {}
    allrec = []
    for th in np.linspace(0, np.pi, n_theta, endpoint=False):
        nx, ny = math.cos(th), math.sin(th)
        proj = np.concatenate([r[:, 0] * nx + r[:, 1] * ny for r in B.rings_outer])
        t = np.linspace(proj.min(), proj.max(), n_off + 2)[1:-1]
        length = ring_length(B.rings_outer, nx, ny, t) - (
            ring_length(B.rings_hole, nx, ny, t) if B.rings_hole else 0)
        sc = (xc * nx + yc * ny)[:, None] - t[None, :]
        sb = (B.x * nx + B.y * ny)[:, None] - t[None, :]
        cross, blk = classify(B, sc, sb, B.rin, B.lm)
        ev = evaluate(B, cross, blk, length)
        allrec.append((th, t, length, ev))
    return allrec


def best_of(recs, key, field="L"):
    """Max over a list of (geom-desc, ev) per-cut arrays: returns (value, demand, desc)."""
    bv, bd, bdesc = 1, 0.0, None
    for desc, ev in recs:
        e = ev[key]
        if not len(e[field]):
            continue
        # tie-break on fractional demand
        score = e[field] * 1e6 + np.where(np.isfinite(e["d"]), e["d"], 1e5)
        i = int(np.argmax(score))
        if (e[field][i], e["d"][i]) > (bv, bd):
            where = [float(v) if np.ndim(v) == 0 and not isinstance(v, str) else v for v in desc[:-1]]
            where.append(float(np.asarray(desc[-1])[i]))
            bv, bd, bdesc = float(e[field][i]), float(e["d"][i]), dict(where=where, n=int(e["n"][i]))
    return bv, bd, bdesc


# ------------------------------------------------------------- closed-curve cuts
def circle_cuts(B, spacing=None, radii=None, paint=None):
    minx, miny, maxx, maxy = B.bounds
    W, H = maxx - minx, maxy - miny
    spacing = spacing or max(max(W, H) / 40, 0.5)
    if radii is None:
        rmax = 0.5 * math.hypot(W, H)
        radii = 0.5 * 2 ** (np.arange(0, 30) / 2)
        radii = radii[radii <= rmax]
    gx = np.arange(minx + spacing / 2, maxx, spacing)
    gy = np.arange(miny + spacing / 2, maxy, spacing)
    C = np.array([(x, y) for y in gy for x in gx])
    C = C[B.inboard(C[:, 0], C[:, 1])]
    xc, yc = B.x[B.ci], B.y[B.ci]
    recs = []
    K = 128
    ang = np.linspace(0, 2 * np.pi, K, endpoint=False)
    for (cx, cy) in C:
        dc = np.hypot(xc - cx, yc - cy)
        db = np.hypot(B.x - cx, B.y - cy)
        sc = dc[:, None] - radii[None, :]
        sb = db[:, None] - radii[None, :]
        cross, blk = classify(B, sc, sb, B.rin, B.lm)
        px = cx + radii[:, None] * np.cos(ang)[None, :]
        py = cy + radii[:, None] * np.sin(ang)[None, :]
        inb = B.inboard(px, py)
        length = 2 * np.pi * radii * inb.mean(1)
        ev = evaluate(B, cross, blk, length)
        recs.append((("circle", float(cx), float(cy), radii), ev))
        if paint is not None:
            paint(px, py, inb, ev)
    return recs


def part_rings(B, min_pads=4, paint=None):
    xc, yc = B.x[B.ci], B.y[B.ci]
    recs = []
    for fi, fp in enumerate(B.fps):
        loc = fp["loc"]
        if len(loc) < min_pads:
            continue
        cx, cy = (loc.min(0) + loc.max(0)) / 2
        hx, hy = (loc.max(0) - loc.min(0)) / 2
        # margins: through every pad row/column inside the box, then outward
        lev = set()
        for a in np.unique(np.round(np.abs(loc[:, 0] - cx), 3)):
            lev.add(round(a - hx, 3))
        for b in np.unique(np.round(np.abs(loc[:, 1] - cy), 3)):
            lev.add(round(b - hy, 3))
        inside = sorted(m for m in lev if m < 0 and hx + m > 0 and hy + m > 0)
        if len(inside) > 30:
            inside = list(np.array(inside)[np.linspace(0, len(inside) - 1, 30).astype(int)])
        margins = np.array(inside + [0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4])
        # pads into the footprint frame (inverse KiCad rotation)
        def to_local(px, py):
            dx, dy = px - fp["x"], py - fp["y"]
            lx, ly = kicad_rot(dx, dy, -fp["rot"])
            return lx - cx, ly - cy

        def rect_sdf(lx, ly):
            ax = hx + margins[None, :]
            ay = hy + margins[None, :]
            qx = np.abs(lx)[:, None] - ax
            qy = np.abs(ly)[:, None] - ay
            outd = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
            ind = np.minimum(np.maximum(qx, qy), 0)
            return outd + ind

        lx, ly = to_local(xc, yc)
        bx, by = to_local(B.x, B.y)
        cross, blk = classify(B, rect_sdf(lx, ly), rect_sdf(bx, by), B.rin, B.lm)
        ax, ay = np.maximum(hx + margins, 1e-6), np.maximum(hy + margins, 1e-6)
        per = 4 * (ax + ay)
        # sample rectangle boundary for in-board length
        K = 160
        s = np.linspace(0, 1, K, endpoint=False)[None, :] * per[:, None]
        sx = np.where(s < 2 * ax[:, None], -ax[:, None] + s, 0.0)
        sy = np.where(s < 2 * ax[:, None], -ay[:, None], 0.0)
        s2 = s - 2 * ax[:, None]
        m2 = (s2 >= 0) & (s2 < 2 * ay[:, None])
        sx = np.where(m2, ax[:, None], sx); sy = np.where(m2, -ay[:, None] + s2, sy)
        s3 = s2 - 2 * ay[:, None]
        m3 = (s3 >= 0) & (s3 < 2 * ax[:, None])
        sx = np.where(m3, ax[:, None] - s3, sx); sy = np.where(m3, ay[:, None], sy)
        s4 = s3 - 2 * ax[:, None]
        m4 = s4 >= 0
        sx = np.where(m4, -ax[:, None], sx); sy = np.where(m4, ay[:, None] - s4, sy)
        gx, gy = kicad_rot(sx + cx, sy + cy, fp["rot"])
        gx, gy = gx + fp["x"], gy + fp["y"]
        inb = B.inboard(gx, gy)
        length = per * inb.mean(1)
        ev = evaluate(B, cross, blk, length)
        recs.append((("ring", fp["ref"], margins), ev))
        if paint is not None:
            paint(gx, gy, inb, ev)
    return recs


# ------------------------------------------------------------------- BGA escape
def escape(B):
    out = []
    for fi, fp in enumerate(B.fps):
        loc = fp["loc"]
        if len(loc) < 16:
            continue
        sel = np.nonzero(B.fp == fi)[0]
        if len(sel) != len(loc):
            continue
        tree = cKDTree(loc)
        dd, _ = tree.query(loc, k=2)
        P = float(np.median(dd[:, 1]))
        if P <= 0:
            continue
        x0, y0 = loc.min(0)
        gi = np.round((loc[:, 0] - x0) / P)
        gj = np.round((loc[:, 1] - y0) / P)
        on_grid = (np.abs(loc[:, 0] - x0 - gi * P) < 0.15 * P) & (np.abs(loc[:, 1] - y0 - gj * P) < 0.15 * P)
        if on_grid.mean() < 0.9:
            continue
        ni, nj = int(gi.max()) + 1, int(gj.max()) + 1
        ring = np.minimum.reduce([gi, ni - 1 - gi, gj, nj - 1 - gj]).astype(int)
        if ni < 4 or nj < 4 or (ring >= 1).sum() < 8 or len(loc) < 0.3 * ni * nj:
            continue
        D = 2 * float(np.median(B.rin[sel]))
        t_top = math.floor((P - D - B.c_lb) / B.p_lb)
        t_in = math.floor((P - B.via_d - B.c_lb) / B.p_lb)
        rec = dict(ref=fp["ref"], pitch=round(P, 3), pads=len(loc), grid=[ni, nj], ball=round(D, 3),
                   t_top=t_top, t_in=t_in)
        for key, use in (("all", np.ones(B.nn, bool)), ("nopour", ~B.pour)):
            nets = B.net[sel]
            # signal ball: counted net that also has pads outside this part
            sig = np.zeros(len(sel), bool)
            for k, n in enumerate(nets):
                if n >= 0 and use[n] and B.npads_net[n] > (nets == n).sum():
                    sig[k] = True
            depth = int(ring[sig].max()) + 1 if sig.any() else 0
            per_top, per_in = max(t_top, 0) + 1, max(t_in, 0) + 1
            if depth == 0:
                L = 1
            elif depth <= per_top:
                L = 1
            else:
                L = 1 + math.ceil((depth - per_top) / per_in)
            rec[key] = dict(depth=depth, sig=int(sig.sum()), L=L)
        out.append(rec)
    return out


# ------------------------------------------------------------------- area bound
def area_bound(B):
    res = {}
    lens = np.zeros(B.nn)
    for n in range(B.nn):
        idx = B.ci[B.net[B.ci] == n]
        if len(idx) < 2:
            continue
        pts = np.c_[B.x[idx], B.y[idx]]
        if len(idx) > 2500:
            idx = idx[:2500]; pts = pts[:2500]
        Dm = squareform(pdist(pts))
        r = B.rout[idx]
        Dm = np.maximum(Dm - r[:, None] - r[None, :], 1e-6)
        np.fill_diagonal(Dm, 0)
        lens[n] = minimum_spanning_tree(csr_matrix(Dm)).sum()
    padF = B.parea[(B.lm & LF) > 0].sum()
    padB = B.parea[(B.lm & LB) > 0].sum()
    for key, use in (("all", np.ones(B.nn, bool)), ("nopour", ~B.pour)):
        wire = STEINER * lens[use].sum() * B.p_lb
        need = wire + padF + padB
        L = max(1, math.ceil(need / B.area)) if B.area > 0 else 1
        res[key] = dict(L=L, util=need / B.area if B.area else 0, mst_mm=float(lens[use].sum()))
    return res


# --------------------------------------------------------------------- topology
def _planar(G):
    import networkx as nx
    return nx.check_planarity(G)[0]


def peel(frame_edges, groups, nodes, time_limit=120.0):
    """Greedy planar peeling: every layer keeps all frame edges and takes whole groups
    (a net's edges) while the layer stays planar. Returns layer count (upper bound on
    via-free thickness of frame+groups) or None on timeout."""
    import networkx as nx
    t0 = time.time()
    remaining = list(groups)
    layers = 0
    while remaining:
        H = nx.Graph()
        H.add_nodes_from(nodes)
        H.add_edges_from(frame_edges)
        if not _planar(H):
            return None
        rejected = []

        def add(chunk):
            if time.time() - t0 > time_limit:
                raise TimeoutError
            es = [e for g in chunk for e in g]
            H.add_edges_from(es)
            if _planar(H):
                return
            # net edges always touch a net vertex, so they never coincide with frame edges
            H.remove_edges_from(es)
            if len(chunk) == 1:
                rejected.append(chunk[0])
                return
            h = len(chunk) // 2
            add(chunk[:h])
            add(chunk[h:])

        try:
            for i in range(0, len(remaining), 64):
                add(remaining[i:i + 64])
        except TimeoutError:
            return None
        layers += 1
        if len(rejected) == len(remaining):
            return None
        remaining = rejected
    return max(layers, 1)


def topology(B, time_limit=120.0):
    """Via-free thickness bounds. Nets are star vertices (equivalent to any Steiner tree
    topology for planarity). Model A: each part one vertex (free pin order). Model W:
    wheel per part with >= 3 pads (rim in angular pin order + hub), 2-pad parts as an
    edge, so pin order is fixed up to mirror."""
    res = {}
    for key, use in (("all", np.ones(B.nn, bool)), ("nopour", ~B.pour)):
        r = {}
        # ---- model A: part-net incidence (bipartite)
        groups, nodes = [], set()
        for n in np.nonzero(use)[0]:
            parts = np.unique(B.fp[B.ci[B.net[B.ci] == n]])
            if len(parts) < 2:
                continue
            groups.append([(("n", int(n)), ("p", int(p))) for p in parts])
        for g in groups:
            for e in g:
                nodes.update(e)
        E = sum(len(g) for g in groups)
        V = len(nodes)
        r["A_V"], r["A_E"] = V, E
        r["A_euler"] = max(1, math.ceil(E / (2 * V - 4))) if V > 2 else 1
        groups.sort(key=len)
        r["A_peel"] = peel([], groups, nodes, time_limit) if groups else 1
        # ---- model W: wheels
        frame, nodesW = [], set()
        for fi, fp in enumerate(B.fps):
            idx = B.ci[B.fp[B.ci] == fi]
            allp = np.nonzero(B.fp == fi)[0]
            if len(allp) < 2:
                continue
            if len(allp) == 2:
                frame.append((("q", int(allp[0])), ("q", int(allp[1]))))
                continue
            cx, cy = B.x[allp].mean(), B.y[allp].mean()
            # boundary pads: on the convex hull boundary (within tolerance)
            pts = np.c_[B.x[allp], B.y[allp]]
            hull = shapely.MultiPoint(pts).convex_hull
            if hull.geom_type != "Polygon":
                order = allp[np.argsort(pts[:, 0] + pts[:, 1])]
                frame += [(("q", int(a)), ("q", int(b))) for a, b in zip(order[:-1], order[1:])]
                continue
            tol = 0.25 * max(np.min(B.rout[allp]), 0.05)
            bd = shapely.distance(hull.exterior, shapely.points(pts)) <= tol
            rim = allp[bd]
            ang = np.arctan2(B.y[rim] - cy, B.x[rim] - cx)
            rim = rim[np.argsort(ang)]
            hub = ("h", fi)
            for a, b in zip(rim, np.roll(rim, -1)):
                frame.append((("q", int(a)), ("q", int(b))))
                frame.append((("q", int(a)), hub))
            # interior pads (EP, inner balls) hang off the hub
            for a in allp[~bd]:
                frame.append((("q", int(a)), hub))
        for e in frame:
            nodesW.update(e)
        groupsW = []
        for n in np.nonzero(use)[0]:
            pads = B.ci[B.net[B.ci] == n]
            groupsW.append([(("n", int(n)), ("q", int(p))) for p in pads])
        for g in groupsW:
            for e in g:
                nodesW.update(e)
        F = len(set(frozenset(e) for e in frame))
        EW = sum(len(g) for g in groupsW)
        VW = len(nodesW)
        r["W_V"], r["W_E"], r["W_F"] = VW, EW, F
        room = 3 * VW - 6 - F
        r["W_euler"] = max(1, math.ceil(EW / room)) if room > 0 else None
        groupsW.sort(key=len)
        r["W_peel"] = peel(frame, groupsW, nodesW, time_limit)
        res[key] = r
    return res
