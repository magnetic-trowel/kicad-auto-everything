# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Min-plus best-response maps for joint collapse (research_notes/transformations T1, plan 5.1).

jc (tools/research/collapse_joint/jc.py) moves each part to the whole-board argmin of
    wire term (HPWL / g, blended with an L1 pin tension) + beta * conflict + physics.
Here the wire term is replaced (minplus_w = 1) or blended (0 < minplus_w < 1) with

    C(x, r) = sum over the part's nets n of  min over its pads k on n of  D_n(x + R_r p_k)

where D_n is a multi-source Dijkstra distance field from the pins of net n on the other
placed parts, on the current priced grid: a cell costs (1 + hist) * (1 + beta * foreign)
exactly as the PathFinder router prices it, a via via_cost * (1 + sum hist) *
(1 + beta * foreign halo count over all layers). Fields live on a coarse grid
(factor f = round(coarse_mm / g), min-pooled costs: a coarse cell is as cheap as its
cheapest fine cell), are summed at coarse origins with each pad's offset rounded to the
coarse grid, and are bilinearly upsampled to the fine origin grid. Units: fine cells (g),
the currency of jc. Unreachable cells cost a board perimeter (Kit.unrouted_mm).

Plug-ins for run.py (they wrap a private copy of collapse_joint/jc.py by swapping its
Collapse class for MPCollapse; nothing in collapse_joint is edited):
    xf     jc + min-plus map (minplus_w = 1 by default; --opt minplus_w=0.5)
    xf_lv  the same with phys_w = 0 (length + vias objective, no polish, as jc_lv_nopol)
Options: minplus_w, coarse_mm (0.4), mp_from_beta (0: use the map from the first
collapse iteration).
"""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
from numba import njit

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "research" / "pnr"))
sys.path.insert(0, str(ROOT / "tools" / "research" / "collapse_joint"))


from router import _pop, _push  # noqa: E402

SQ2 = math.sqrt(2.0)


def _load_jc():
    # A private copy of the current collapse_joint/jc.py (the one the round-2 baselines run),
    # so swapping its Collapse class touches nothing else.
    path = ROOT / "tools" / "research" / "collapse_joint" / "jc.py"
    spec = importlib.util.spec_from_file_location("jc_for_minplus", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


JC = _load_jc()


@njit(cache=True)
def dijkstra(costT, costV, src, dist, hk, hv):
    """Multi-source Dijkstra on an (nl, H, W) grid, 8-neighbour moves (cost = step *
    cost of the entered cell), through vias at costV[y, x] (inf = no via). dist is
    overwritten (inf where unreachable)."""
    nl, H, W = costT.shape
    HW = H * W
    for i in range(dist.size):
        dist.flat[i] = np.inf
    nh = 0
    for i in range(src.shape[0]):
        l, y, x = src[i, 0], src[i, 1], src[i, 2]
        if dist[l, y, x] > 0.0:
            dist[l, y, x] = 0.0
            nh = _push(hk, hv, nh, 0.0, (l * H + y) * W + x)
    dxs = (1, -1, 0, 0, 1, 1, -1, -1)
    dys = (0, 0, 1, -1, 1, -1, 1, -1)
    cap = hk.shape[0] - 16
    while nh > 0:
        d, node, nh = _pop(hk, hv, nh)
        l = node // HW
        rem = node - l * HW
        y = rem // W
        x = rem - y * W
        if d > dist[l, y, x]:
            continue
        for k in range(8):
            nx = x + dxs[k]
            ny = y + dys[k]
            if nx < 0 or ny < 0 or nx >= W or ny >= H:
                continue
            c = costT[l, ny, nx]
            if not np.isfinite(c):
                continue
            nd = d + (1.0 if k < 4 else 1.4142135623730951) * c
            if nd < dist[l, ny, nx]:
                dist[l, ny, nx] = nd
                if nh < cap:
                    nh = _push(hk, hv, nh, nd, (l * H + ny) * W + nx)
        cv = costV[y, x]
        if nl > 1 and np.isfinite(cv):
            nd = d + cv
            for ll in range(nl):
                if ll != l and nd < dist[ll, y, x]:
                    dist[ll, y, x] = nd
                    if nh < cap:
                        nh = _push(hk, hv, nh, nd, (ll * H + y) * W + x)
    return 0


def _minpool(a, f, Hc, Wc):
    """Min over f x f blocks of the last two axes (pads with +inf)."""
    sh = a.shape[:-2]
    H, W = a.shape[-2:]
    p = np.full(sh + (Hc * f, Wc * f), np.inf, np.float64)
    p[..., :H, :W] = a
    return p.reshape(sh + (Hc, f, Wc, f)).min(axis=(-3, -1))


class MinPlus:
    """Priced distance fields on a coarse grid and the min-plus part maps."""

    def __init__(self, world, router, kit, coarse_mm=0.4, pad_shape=True, tree=False):
        self.w, self.r, self.kit = world, router, kit
        self.tree = tree
        self.last_cells = {}  # part -> {net: terminal cells at its last pose} (set by caller)
        self.pad_shape = pad_shape
        g = world.g
        self.f = f = max(1, int(round(coarse_mm / g)))
        self.Hc = -(-world.H // f)
        self.Wc = -(-world.W // f)
        n = world.nl * self.Hc * self.Wc
        self.hk = np.zeros(8 * n + 64, np.float64)
        self.hv = np.zeros(8 * n + 64, np.int64)
        self.cap = kit.unrouted_mm / g  # fine cells
        self.blockT = world.blockT.astype(bool)
        self.blockV = world.blockV.astype(bool).any(0) | self.blockT.any(0)  # (H, W): no via
        self.nfields = 0
        # bilinear upsampling coefficients (coarse cell b centre = fine b*f + (f-1)/2)
        self.up = [self._lin(world.H, self.Hc), self._lin(world.W, self.Wc)]

    def _lin(self, n, nc):
        t = (np.arange(n) - (self.f - 1) / 2.0) / self.f
        t = np.clip(t, 0, nc - 1)
        i0 = np.minimum(np.floor(t).astype(np.int64), max(nc - 2, 0))
        fr = t - i0
        i1 = np.minimum(i0 + 1, nc - 1)
        return i0, i1, fr

    def upsample(self, S):
        (y0, y1, fy), (x0, x1, fx) = self.up
        R = S[y0] * (1 - fy)[:, None] + S[y1] * fy[:, None]
        return R[:, x0] * (1 - fx)[None, :] + R[:, x1] * fx[None, :]

    def prepare(self, beta):
        """Base costs for the current world state (call with the moving part unplaced)."""
        w, f = self.w, self.f
        self.beta = beta
        hist = w.hist.astype(np.float64)
        fineT = (1.0 + hist) * (1.0 + beta * w.DT)
        fineT[self.blockT] = np.inf
        self.fineT_h = 1.0 + hist
        self.baseT = _minpool(fineT, f, self.Hc, self.Wc)
        vc = self.r.via_cost
        fv = (w.DV.sum(0) + w.DT.sum(0)).astype(np.float64)
        self.hsum = 1.0 + hist.sum(0)
        fineV = vc * self.hsum * (1.0 + beta * fv)
        fineV[self.blockV] = np.inf
        self.fineV_fv = fv
        self.baseV = _minpool(fineV, f, self.Hc, self.Wc)
        self.fields = {}

    def net_costs(self, n):
        """Coarse costs for net n: its own copper is not foreign."""
        w, f, beta = self.w, self.f, self.beta
        cT = self.baseT.copy()
        cV = self.baseV.copy()
        if beta > 0:
            own = w.occT[n] > 0
            l, y, x = np.nonzero(own)
            if len(l):
                ok = ~self.blockT[l, y, x]
                l, y, x = l[ok], y[ok], x[ok]
                v = self.fineT_h[l, y, x] * (1.0 + beta * (w.DT[l, y, x] - 1))
                np.minimum.at(cT, (l, y // f, x // f), v)
            ownv = (w.occV[n] > 0).sum(0) + own.sum(0)
            y, x = np.nonzero(ownv)
            if len(y):
                ok = ~self.blockV[y, x]
                y, x = y[ok], x[ok]
                v = self.r.via_cost * self.hsum[y, x] * (1.0 + beta * (self.fineV_fv[y, x] - ownv[y, x]))
                np.minimum.at(cV, (y // f, x // f), v)
        return cT / 1.0, cV / f  # coarse step = f fine cells: dist * f is in fine cells

    def field(self, n, skip):
        """D_n (coarse, fine-cell units) from the pins of net n on placed parts != skip,
        or None when there are none."""
        key = (n, skip)
        if key in self.fields:
            return self.fields[key]
        w, f = self.w, self.f
        src = []
        for q, k in w.net_pins[n]:
            if q == skip or q not in w.pose:
                continue
            t = np.array(w.terminals(q, k), np.int64).reshape(-1, 3)
            if len(t):
                src.append(t)
        if not src:
            self.fields[key] = None
            return None
        if self.tree and self.r.routes.get(n):
            # the net's routed tree minus every path with an end on the moving part's
            # pads (its stubs): distance to the tree approximates the Steiner increment
            own = set()
            if skip in w.pose:
                for k, ent in enumerate(w.raster(skip)["pads"]):
                    if ent["net"] == n:
                        own |= {tuple(c) for c in w.terminals(skip, k)}
            elif skip in self.last_cells:
                own = self.last_cells[skip].get(n, set())
            for p in self.r.routes[n]:
                if tuple(int(v) for v in p[0]) in own or tuple(int(v) for v in p[-1]) in own:
                    continue
                src.append(p.astype(np.int64))
        s = np.concatenate(src)
        s = s[(s[:, 1] >= 0) & (s[:, 2] >= 0) & (s[:, 1] < w.H) & (s[:, 2] < w.W)]
        s[:, 1] //= f
        s[:, 2] //= f
        s = np.unique(s, axis=0)
        cT, cV = self.net_costs(n)
        D = np.empty((w.nl, self.Hc, self.Wc), np.float64)
        dijkstra(cT, cV, s, D, self.hk, self.hv)
        D *= f
        D = np.minimum(D, self.cap)
        self.nfields += 1
        self.fields[key] = D
        return D

    def part_map(self, pi, ri, fine=True):
        """C(origin) for part pi (unplaced) at orientation ri: fine (H, W) map in fine
        cells, or None when no pad has a net with pins elsewhere."""
        w, f = self.w, self.f
        rr = w.part_raster(w.parts[pi], ri)
        Hc, Wc = self.Hc, self.Wc
        by_net = {}
        for ent in rr["pads"]:
            n = ent["net"]
            if n not in w.net_pins:
                continue
            D = self.field(n, pi)
            if D is None:
                continue
            lay = ent["layers"] or list(range(w.nl))
            Dl = D[lay].min(0)
            # min over the pad's copper (coarse offsets of its cells): a wire may leave
            # the pad anywhere on its copper (min-plus erosion by the pad shape)
            if self.pad_shape and len(ent["cu"]):
                offs = np.unique(np.floor((ent["cu"] + (f - 1) / 2.0) / f).astype(np.int64), axis=0)
            else:
                offs = np.array([[int(round(ent["center"][0] / w.g / f)),
                                  int(round(ent["center"][1] / w.g / f))]])
            S = None
            for ox, oy in offs:
                T = np.full((Hc, Wc), self.cap)
                ys0, ys1 = max(0, -oy), min(Hc, Hc - oy)
                xs0, xs1 = max(0, -ox), min(Wc, Wc - ox)
                if ys1 > ys0 and xs1 > xs0:
                    T[ys0:ys1, xs0:xs1] = Dl[ys0 + oy:ys1 + oy, xs0 + ox:xs1 + ox]
                S = T if S is None else np.minimum(S, T)
            prev = by_net.get(n)
            by_net[n] = S if prev is None else np.minimum(prev, S)
        if not by_net:
            return None
        tot = sum(by_net.values())
        return self.upsample(tot) if fine else tot


class MPCollapse(JC.Collapse):
    """jc's Collapse with the min-plus wire term in the part best response."""

    def __init__(self, world, seed, budget, log, minplus_w=1.0, coarse_mm=0.4, mp_from_beta=0.0,
                 pad_shape=True, mp_tree=False, **kw):
        super().__init__(world, seed, budget, log, **kw)
        self.minplus_w = float(minplus_w)
        self.mp_from_beta = mp_from_beta
        self.mp = MinPlus(world, self.r, self.kit, coarse_mm, pad_shape, mp_tree)
        self.mp_t = 0.0
        self.mp_calls = 0
        log(f"xf minplus_w={self.minplus_w} coarse={self.mp.f * world.g:.2f}mm grid {self.mp.Wc}x{self.mp.Hc}")

    def record_cells(self, pi):
        """Terminal cells per net of placed part pi (for the tree sources)."""
        w = self.w
        d = {}
        for k, ent in enumerate(w.raster(pi)["pads"]):
            if ent["net"] in w.net_pins:
                d.setdefault(ent["net"], set()).update(tuple(c) for c in w.terminals(pi, k))
        self.mp.last_cells[pi] = d

    def best_response(self, pi, beta, CT, CV, per):
        if self.mp.tree and self.minplus_w > 0:
            self.record_cells(pi)
        return super().best_response(pi, beta, CT, CV, per)

    def wire_term(self, pi, ri, beta, anchors, prepared):
        """jc's (HPWL + tension) term blended with the min-plus map, in fine cells."""
        g = self.g
        wmp = self.minplus_w if beta >= self.mp_from_beta else 0.0
        c = 0.0
        if wmp < 1.0:
            c = self.kit.hpwl_map(pi, ri) / g
            if self.tension_w and anchors and beta >= self.tension_beta:
                c = (1 - self.tension_w) * c + self.tension_w * self.tension_map(pi, ri, anchors)
        if wmp > 0.0:
            import time
            t0 = time.process_time()
            if not prepared[0]:
                self.mp.prepare(beta)
                prepared[0] = True
            m = self.mp.part_map(pi, ri)
            self.mp_t += time.process_time() - t0
            self.mp_calls += 1
            if m is None:  # no net with pins elsewhere: keep jc's term
                return c if wmp < 1.0 else self.kit.hpwl_map(pi, ri) / g
            c = (1.0 - wmp) * c + wmp * m
        return c

    def part_cost_maps(self, pi, beta, CT, CV, anchors):
        """As jc's, with the wire term from wire_term()."""
        w = self.w
        g = self.g
        F = self.F
        FP = FT = FV = None
        if beta > 0:
            FP = [F.map(beta * (w.court[p] > 0) * (1.0 + self.hist_c[p]) + self.hist_p * self.hist_c[p])
                  for p in range(w.P)]
            FC = F.map(beta * ((w.court[0] > 0) | (w.court[1] > 0)))
            FH = F.map(beta * self.hole_map(skip=pi))
            bw = beta * self.pad_wire
            FT = [F.map(bw * CT[l]) if (bw and CT[l].any()) else None for l in range(w.nl)]
            FV = F.map(bw * CV) if (bw and CV.any()) else None
        prepared = [False]
        for ri in range(4):
            inside = self.inside_map(pi, ri)
            if not inside.any():
                continue
            c = self.wire_term(pi, ri, beta, anchors, prepared)
            c = c + self.bias(pi, ri) * 0.1 / g
            if beta > 0:
                keep, ht, hv = self.kernels(pi, ri)
                pairs = [(FP[p], cells) for p, cells in keep]
                pairs += [(FT[l], cells) for l, cells in ht.items()]
                pairs.append((FV, hv))
                h, side = self.holes(pi, ri)
                pairs += [(FC, h), (FH, side)]
                c = c + F.corr(pairs)
                if self.cut_parts:
                    c = c + beta * self.cut_cost(pi, ri)
            yield ri, c, inside


def _with_mp(fn, world, kw):
    old = JC.Collapse
    JC.Collapse = MPCollapse
    try:
        r = fn(world, **kw)
    finally:
        JC.Collapse = old
    return r


def xf(world, **kw):
    """jc (physics objective, 15 % polish) with the min-plus wire term."""
    kw.setdefault("minplus_w", 1.0)
    return _with_mp(JC.jc, world, kw)


def xf_lv(world, **kw):
    """Length + vias objective (phys_w = 0, no polish), as jc_lv_nopol, with min-plus."""
    kw.setdefault("minplus_w", 1.0)
    return _with_mp(JC.jc_lv_nopol, world, kw)


def xf_h(world, **kw):
    """xf with minplus_w = 0.5 (blend with jc's HPWL + tension term)."""
    kw["minplus_w"] = 0.5
    return xf(world, **kw)


def xf_lv_h(world, **kw):
    kw["minplus_w"] = 0.5
    return xf_lv(world, **kw)


def xf0(world, **kw):
    """Control: the wrapper with minplus_w = 0 (must equal jc)."""
    kw["minplus_w"] = 0.0
    return xf(world, **kw)
