# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Layer-collapse quantities as placement objective terms (XY and rotation).

Source: research_notes/layer-collapse/analogs.md (C2, C3).

  fv    forced vias of buses. For every pair of parts joined by >= 3 two-pin nets, number
        the nets by their pin position across the gap (projection on the axis normal to
        the line between the two pin groups) on each part. The straight connections cross
        iff the orders are inverted; the most nets that fit via-free on L layers is
        lambda_1 + ... + lambda_L of the RSK shape of that sequence (Greene), and every
        other net needs a via. L is the number of copper layers both pins of a net are on
        (SMD to SMD on one side: 1). Ties count as compatible (optimistic).
  xings straight-line ratsnest crossings: geometric crossings between the MST segments of
        different nets (the classic via proxy, joint-pnr catalog idea 25).
  ovf   cut-capacity overflow. Over Delaunay edges between pads of different parts (and
        board-edge samples), demand N = nets whose MST segments cross the edge (nets of the
        two end pads excluded) vs supply sum_l floor((l_free(l) + s) / (w + s)), with
        l_free(l) the edge length minus each end pad's extent + clearance on layers the pad
        is on. Overflow = sum max(0, N - supply).

All terms read poses from their own cache (`self.poses`, kept in step with commit/sync), so
`delta(pi, pose)` works while pi is unplaced in the world, as physics.Phys does. Costs are
in mm of routed copper: total = w_fv * fv + w_x * xings + w_ovf * ovf.
"""
import math
from bisect import bisect_right

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.spatial import Delaunay

from world import ROTS, rot_pts


def rsk_shape(seq):
    """Row lengths of the RSK insertion tableau of a word (weak: equal values never bump)."""
    rows = []
    for v in seq:
        for row in rows:
            j = bisect_right(row, v)
            if j == len(row):
                row.append(v)
                v = None
                break
            row[j], v = v, row[j]
        if v is not None:
            rows.append([v])
    return [len(r) for r in rows]


def lds_len(seq):
    """Longest strictly decreasing subsequence (= minimum via-free layers)."""
    tails = []
    for v in seq:
        x = -v
        lo, hi = 0, len(tails)
        while lo < hi:
            m = (lo + hi) // 2
            if tails[m] < x:
                lo = m + 1
            else:
                hi = m
        if lo == len(tails):
            tails.append(x)
        else:
            tails[lo] = x
    return len(tails)


def bus_perm(pa, pb):
    """Sequence of b-ranks in a-order, from pin coordinates pa, pb (n, 2) of one bus."""
    d = pb.mean(0) - pa.mean(0)
    nd = math.hypot(*d)
    if nd < 1e-9:
        d = np.array([1.0, 0.0])
        nd = 1.0
    u = np.array([-d[1], d[0]]) / nd
    xa, xb = pa @ u, pb @ u
    # quantize so pins in one column tie (ties are compatible: optimistic)
    xa, xb = np.round(xa / 0.05), np.round(xb / 0.05)
    order = np.lexsort((xb, xa))
    return list(xb[order])


def bus_fv_cyclic(pa, pb, ca, cb, L):
    """Cyclic variant (wires may wrap around a part): pins ordered by angle around each
    part's centre (ccw on a, cw on b); planar iff the two cyclic orders agree. Forced vias
    = n - max over cyclic re-starts of lambda_1 + ... + lambda_L."""
    ta = np.arctan2(pa[:, 1] - ca[1], pa[:, 0] - ca[0])
    tb = -np.arctan2(pb[:, 1] - cb[1], pb[:, 0] - cb[0])
    oa = np.argsort(ta, kind="stable")
    rb = np.argsort(np.argsort(tb, kind="stable"))
    seq = [int(rb[i]) for i in oa]
    n = len(seq)
    best = 0
    for r in range(n):
        s = seq[r:] + seq[:r]
        for t in range(n):
            sh = rsk_shape([(v - t) % n for v in s])
            best = max(best, sum(sh[:L]))
            if best == n:
                return 0
    return n - best


def seg_cross(A, B, C, D):
    """Proper crossings of segments AB (n, 2) with CD (m, 2): bool (n, m)."""
    def orient(P, Q, R):
        return ((Q[..., 0] - P[..., 0]) * (R[..., 1] - P[..., 1]) -
                (Q[..., 1] - P[..., 1]) * (R[..., 0] - P[..., 0]))
    A_, B_ = A[:, None, :], B[:, None, :]
    C_, D_ = C[None, :, :], D[None, :, :]
    d1 = orient(A_, B_, C_)
    d2 = orient(A_, B_, D_)
    d3 = orient(C_, D_, A_)
    d4 = orient(C_, D_, B_)
    eps = 1e-9
    return (((d1 > eps) & (d2 < -eps)) | ((d1 < -eps) & (d2 > eps))) & \
           (((d3 > eps) & (d4 < -eps)) | ((d3 < -eps) & (d4 > eps)))


class CollapseTerms:
    def __init__(self, world, w_fv=4.0, w_x=0.0, w_ovf=2.0, min_bus=3, max_edge_mm=4.0, edge_step_mm=1.0,
                 fv_mode="proj"):
        self.w = world
        self.fv_mode = fv_mode
        self.wt = dict(fv=w_fv, x=w_x, ovf=w_ovf)
        R = world.R
        self.s, self.tw, self.ec = R.c, R.w, R.ec
        self.max_edge = max_edge_mm
        self.L = world.nl
        # pads: (part, k) -> net id, layer bitmask; per-orientation centres / half extents
        self.pads = []  # (pi, k, net, mask)
        self.pad_ix = {}
        for p in world.parts:
            for k, pad in enumerate(p.pads):
                if pad["npth"]:
                    continue
                lay = world.pad_layers(p, pad)
                if not lay:
                    continue
                net = world.net_id.get(pad["net"], 0) if pad["net"] else 0
                self.pad_ix[(p.idx, k)] = len(self.pads)
                self.pads.append((p.idx, k, net, sum(1 << l for l in lay)))
        self.part_pads = {}
        for j, (pi, k, net, m) in enumerate(self.pads):
            self.part_pads.setdefault(pi, []).append(j)
        self.pad_net = np.array([t[2] for t in self.pads], np.int64)
        self.pad_mask = np.array([t[3] for t in self.pads], np.int64)
        self.pad_part = np.array([t[0] for t in self.pads], np.int64)
        self._geo = {}
        # nets routed by the engine
        self.nets = {n: [self.pad_ix[q] for q in pins if q in self.pad_ix] for n, pins in world.net_pins.items()}
        self.nets = {n: v for n, v in self.nets.items() if len(v) >= 2}
        self.net_parts = {n: {self.pad_part[j] for j in v} for n, v in self.nets.items()}
        self.part_nets = {}
        for n, ps in self.net_parts.items():
            for pi in ps:
                self.part_nets.setdefault(pi, set()).add(n)
        # buses
        pairs = {}
        for n, v in self.nets.items():
            if len(v) == 2 and self.pad_part[v[0]] != self.pad_part[v[1]]:
                a, b = v if self.pad_part[v[0]] < self.pad_part[v[1]] else (v[1], v[0])
                pairs.setdefault((int(self.pad_part[a]), int(self.pad_part[b])), []).append((a, b))
        self.buses = []
        for (a, b), lst in sorted(pairs.items()):
            if len(lst) < min_bus:
                continue
            Ls = [bin(int(self.pad_mask[x] & self.pad_mask[y])).count("1") for x, y in lst]
            Le = min(Ls)
            if Le == 0:
                continue  # every net needs a via whatever the orientation
            self.buses.append(dict(a=a, b=b, pa=[x for x, _ in lst], pb=[y for _, y in lst], L=Le))
        self.part_buses = {}
        for i, bu in enumerate(self.buses):
            self.part_buses.setdefault(bu["a"], []).append(i)
            self.part_buses.setdefault(bu["b"], []).append(i)
        # board-edge samples (zero-extent points of "part" -1)
        pts = []
        for poly in world.outline + world.holes:
            P = np.asarray(poly, float)
            for i in range(len(P)):
                a, b = P[i], P[(i + 1) % len(P)]
                n = max(1, int(math.ceil(np.hypot(*(b - a)) / edge_step_mm)))
                for t in range(n):
                    pts.append(a + (b - a) * t / n)
        self.edge_pts = np.array(pts) if pts else np.zeros((0, 2))
        self.poses = {}
        self.sync()

    # ------------------------------------------------------------ geometry
    def _part_geo(self, pi, ri):
        key = (pi, ri)
        g = self._geo.get(key)
        if g is not None:
            return g
        part = self.w.parts[pi]
        deg = ROTS[ri] if ri < 4 else part.rot0
        idx = self.part_pads.get(pi, [])
        cen, ext = [], []
        for j in idx:
            pad = part.pads[self.pads[j][1]]
            cen.append(rot_pts(np.array([[pad["x"], pad["y"]]]), deg)[0])
            polys = [rot_pts(np.array(q, float), deg) for q in pad["poly"] if len(q) >= 3]
            if polys:
                allp = np.concatenate(polys)
                ext.append(np.abs(allp - cen[-1]).max(0))
            else:
                ext.append(np.zeros(2))
        g = (np.array(cen).reshape(-1, 2), np.array(ext).reshape(-1, 2))
        self._geo[key] = g
        return g

    def _xy(self, pi, pose):
        cx, cy, ri = pose
        x, y = self.w.xy(cx, cy)
        if self.w.pose.get(pi) == pose:
            fx, fy = self.w.frac.get(pi, (0.0, 0.0))
            x, y = x + fx, y + fy
        return np.array([x, y])

    def pad_xy(self, poses):
        """(P, 2) pad centres (nan for unplaced parts) and (P, 2) half extents."""
        P = len(self.pads)
        xy = np.full((P, 2), np.nan)
        ex = np.zeros((P, 2))
        for pi, pose in poses.items():
            idx = self.part_pads.get(pi)
            if not idx:
                continue
            cen, e = self._part_geo(pi, pose[2])
            xy[idx] = cen + self._xy(pi, pose)
            ex[idx] = e
        return xy, ex

    # ------------------------------------------------------------ pose cache
    def sync(self):
        self.poses = dict(self.w.pose)
        self._cache = None

    def commit(self, pi):
        if pi in self.w.pose:
            self.poses[pi] = self.w.pose[pi]
        else:
            self.poses.pop(pi, None)
        self._cache = None

    # ------------------------------------------------------------ fv
    def bus_fv(self, bi, xy):
        bu = self.buses[bi]
        pa, pb = xy[bu["pa"]], xy[bu["pb"]]
        if np.isnan(pa).any() or np.isnan(pb).any():
            return 0, 0
        if self.fv_mode == "cyc":
            ia, ib = self.part_pads[bu["a"]], self.part_pads[bu["b"]]
            return bus_fv_cyclic(pa, pb, np.nanmean(xy[ia], 0), np.nanmean(xy[ib], 0), bu["L"]), 0
        seq = bus_perm(pa, pb)
        sh = rsk_shape(seq)
        return len(seq) - sum(sh[:bu["L"]]), len(sh)  # forced vias, LDS (min via-free layers)

    def fv(self, xy, buses=None):
        bl = range(len(self.buses)) if buses is None else buses
        return sum(self.bus_fv(i, xy)[0] for i in bl)

    # ------------------------------------------------------------ MST segments
    def segments(self, xy, nets=None):
        """MST segments of each net over placed pins: list of (net, (k,2) A, (k,2) B)."""
        out = []
        for n in (self.nets if nets is None else nets):
            v = [j for j in self.nets[n] if not np.isnan(xy[j, 0])]
            if len(v) < 2:
                continue
            p = xy[v]
            if len(v) == 2:
                out.append((n, p[:1], p[1:]))
                continue
            D = np.hypot(p[:, None, 0] - p[None, :, 0], p[:, None, 1] - p[None, :, 1]) + 1e-6
            T = minimum_spanning_tree(np.triu(D)).tocoo()
            out.append((n, p[T.row], p[T.col]))
        return out

    def xings(self, segs, among=None):
        """Crossings between segments of different nets. With `among` (set of nets), only
        pairs that involve at least one of those nets."""
        if not segs:
            return 0
        A = np.concatenate([s[1] for s in segs])
        B = np.concatenate([s[2] for s in segs])
        net = np.concatenate([np.full(len(s[1]), s[0]) for s in segs])
        X = seg_cross(A, B, A, B) & (net[:, None] != net[None, :])
        if among is not None:
            m = np.isin(net, list(among))
            X = X & (m[:, None] | m[None, :])
        return int(np.triu(X).sum())

    # ------------------------------------------------------------ ovf
    def overflow(self, xy, ex, segs, detail=False):
        ok = ~np.isnan(xy[:, 0])
        idx = np.nonzero(ok)[0]
        if len(idx) < 3 or not segs:
            return (0.0, []) if detail else 0.0
        pts = np.concatenate([xy[idx], self.edge_pts])
        npad = len(idx)
        try:
            tri = Delaunay(pts)
        except Exception:
            return (0.0, []) if detail else 0.0
        s = tri.simplices
        E = np.concatenate([s[:, [0, 1]], s[:, [1, 2]], s[:, [0, 2]]])
        E = np.unique(np.sort(E, 1), axis=0)
        E = E[E[:, 0] < npad]  # at least one pad (sorted: the first)
        pa = idx[E[:, 0]]
        isedge = E[:, 1] >= npad
        pb = np.where(isedge, -1, idx[np.minimum(E[:, 1], npad - 1)])
        diffpart = isedge | (self.pad_part[pa] != np.where(pb >= 0, self.pad_part[np.maximum(pb, 0)], -1))
        P0, P1 = pts[E[:, 0]], pts[E[:, 1]]
        dvec = P1 - P0
        dl = np.hypot(dvec[:, 0], dvec[:, 1])
        keep = diffpart & (dl > 1e-6) & (dl <= self.max_edge)
        if not keep.any():
            return (0.0, []) if detail else 0.0
        E, pa, pb, isedge, P0, P1, dvec, dl = E[keep], pa[keep], pb[keep], isedge[keep], P0[keep], P1[keep], dvec[keep], dl[keep]
        ud = np.abs(dvec / dl[:, None])
        exa = (ex[pa] * ud).sum(1)
        exb = np.where(isedge, 0.0, (ex[np.maximum(pb, 0)] * ud).sum(1))
        ma = self.pad_mask[pa]
        mb = np.where(isedge, 0, self.pad_mask[np.maximum(pb, 0)])
        supply = np.zeros(len(E))
        for l in range(self.L):
            on_a = (ma >> l) & 1
            on_b = (mb >> l) & 1
            lf = dl - on_a * (exa + self.s) - on_b * (exb + self.s) - isedge * self.ec
            supply += np.maximum(0, np.floor((lf + self.s) / (self.tw + self.s)))
        A = np.concatenate([q[1] for q in segs])
        B = np.concatenate([q[2] for q in segs])
        net = np.concatenate([np.full(len(q[1]), q[0]) for q in segs])
        X = seg_cross(P0, P1, A, B)
        # exclude nets of the end pads
        na = self.pad_net[pa]
        nb = np.where(isedge, -1, self.pad_net[np.maximum(pb, 0)])
        X &= (net[None, :] != na[:, None]) & (net[None, :] != nb[:, None])
        # distinct nets per edge
        ii, jj = np.nonzero(X)
        if len(ii) == 0:
            return (0.0, []) if detail else 0.0
        pairs = np.unique(np.stack([ii, net[jj]], 1), axis=0)
        demand = np.bincount(pairs[:, 0], minlength=len(E))
        over = np.maximum(0, demand - supply)
        tot = float(over.sum())
        if detail:
            return tot, [(P0[i], P1[i], int(demand[i]), int(supply[i])) for i in np.nonzero(over)[0]]
        return tot

    # ------------------------------------------------------------ totals / deltas
    def parts_of(self, poses):
        return poses

    def evaluate(self, poses, which=("fv", "x", "ovf")):
        xy, ex = self.pad_xy(poses)
        out = {}
        if "fv" in which:
            out["fv"] = self.fv(xy)
        segs = None
        if "x" in which or "ovf" in which:
            segs = self.segments(xy)
        if "x" in which:
            out["x"] = self.xings(segs)
        if "ovf" in which:
            out["ovf"] = self.overflow(xy, ex, segs)
        return out

    def _active(self):
        return tuple(k for k, v in self.wt.items() if v)

    def cost_of(self, poses):
        ev = self.evaluate(poses, self._active())
        return sum(self.wt[k] * ev[k] for k in ev)

    def total(self):
        if self._cache is None:
            self._cache = self.cost_of(self.poses)
        return self._cache

    def delta(self, pi, pose):
        """Cost change if part pi moves to pose (others at their cached poses)."""
        act = self._active()
        if not act:
            return 0.0
        new = dict(self.poses)
        new[pi] = pose
        d = 0.0
        if "fv" in act:
            bl = self.part_buses.get(pi, [])
            if bl:
                xy0, _ = self.pad_xy({q: self.poses[q] for q in self._bus_parts(bl) if q in self.poses})
                xy1, _ = self.pad_xy({q: new[q] for q in self._bus_parts(bl) if q in new})
                d += self.wt["fv"] * (self.fv(xy1, bl) - self.fv(xy0, bl))
        if "x" in act or "ovf" in act:
            xy0, ex0 = self.pad_xy(self.poses)
            xy1, ex1 = self.pad_xy(new)
            s0, s1 = self.segments(xy0), self.segments(xy1)
            if "x" in act:
                among = self.part_nets.get(pi, set())
                d += self.wt["x"] * (self.xings(s1, among) - self.xings(s0, among))
            if "ovf" in act:
                d += self.wt["ovf"] * (self.overflow(xy1, ex1, s1) - self.overflow(xy0, ex0, s0))
        return d

    def _bus_parts(self, bl):
        s = set()
        for i in bl:
            s.add(self.buses[i]["a"])
            s.add(self.buses[i]["b"])
        return s
