# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Harmonic-field routing inside joint collapse (idea 19 on top of
tools/research/collapse_joint/jc.py; the continuation, restarts, legalization and polish
are jc's, imported unchanged).

Per collapse iteration, for every net (random order) the harmonic field of field.py is
solved with *priced* walls: coarse conductance from 1 / (1 + hist + beta * foreign), so the
field sees the same prices as PathFinder (beta -> inf: committed copper and foreign pads are
insulating walls). Then, by `mode`:

  stream   (a) the net's route IS its streamline tree (no search), rasterized to 0.1 mm with
               line-of-sight pulling; conflicts are priced as in jc (history on conflicting
               cells, parts pay for foreign route cells under their pads). The final
               legalization (PathFinder + Router.legalize) is jc's.
  bias     (b) topology prior: the engine A* routes the net with a cost bias `lam` outside a
               corridor around the streamline tree (which side of each obstacle).
  astar        plain jc routing (fields only for the part pressure).

and, with press_w > 0, (c) part pressure: each part's best response also pays
beta * press_w * (expected foreign wire occupancy |J|/I of the other nets' fields, summed)
under its pad halos -- the field's "Maxwell stress" on the footprint, which anticipates
where wires want to go before they are routed there.

Fields are warm-started (CG from the previous potential of the same net) each iteration.
Plug-ins for run.py: hjc (bias + pressure), hjc_stream, hjc_bias, hjc_press, *_lv
(phys_w = 0), hroute (route tasks: human placement, harmonic-biased PathFinder).
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")
sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/collapse_joint")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jc as JC  # noqa: E402
import methods as M  # noqa: E402
from field import Field  # noqa: E402
from router import add_hist, conflicts  # noqa: E402
from stream import tree_to_fine  # noqa: E402


def upsample(c, s, H, W):
    """(L, Hc, Wc) -> (L, H, W) by block repetition."""
    return np.repeat(np.repeat(c, s, axis=1), s, axis=2)[:, :H, :W]


def dilate(mask, r):
    """Binary dilation of (L, Hc, Wc) by r cells in-plane (square)."""
    out = mask.copy()
    for _ in range(r):
        m = out.copy()
        m[:, 1:, :] |= out[:, :-1, :]
        m[:, :-1, :] |= out[:, 1:, :]
        m[:, :, 1:] |= out[:, :, :-1]
        m[:, :, :-1] |= out[:, :, 1:]
        out = m
    return out


class Harm:
    """Per-net fields, streamline trees and corridors on a World; shared by hjc and hroute."""

    def __init__(self, world, coarse=0.4, via_sigma=0.2, lam=0.5, corr_r=1, all_layers=True,
                 beta_cap=50.0):
        self.w = world
        self.F = Field(world, coarse_mm=coarse, via_sigma=via_sigma)
        self.lam = lam
        self.corr_r = corr_r
        self.all_layers = all_layers
        self.beta_cap = beta_cap
        self.dens = {}  # net -> coarse expected occupancy (L, Hc, Wc)
        self.t = 0.0

    def field(self, n, beta):
        t0 = time.process_time()
        F, w = self.F, self.w
        b = np.inf if beta is None else min(beta, self.beta_cap)
        sig = F.sigma(n, beta=b, hist=w.hist)
        phi, pins, src = F.solve(n, sig)
        if phi is None:
            self.t += time.process_time() - t0
            return None
        tree = F.streamlines(phi, sig, pins, src)
        self.dens[n] = F.density(phi, sig).reshape(F.L, F.Hc, F.Wc).astype(np.float32)
        self.t += time.process_time() - t0
        return sig, phi, pins, src, tree

    def corridor_bias(self, tree):
        F, w = self.F, self.w
        m = np.zeros((F.L, F.Hc, F.Wc), bool)
        for nodes in tree:
            if nodes is None:
                continue
            l, y, x = F.unravel(nodes)
            if self.all_layers:
                m[:, y, x] = True
            else:
                m[l, y, x] = True
        m = dilate(m, self.corr_r)
        return upsample((~m).astype(np.float32) * self.lam, F.s, w.H, w.W)

    def route_net(self, r, n, beta, mode, hard=False):
        """Rip-up assumed. Returns the field result (or None)."""
        w = self.w
        res = self.field(n, beta)
        if res is None or mode == "astar":
            r.route_net(n, hard=hard)
            return res
        sig, phi, pins, src, tree = res
        if mode == "stream" and all(t is not None for t in tree):
            fine = tree_to_fine(w, self.F, n, tree, pins, src)
            r.routes[n] = fine
            r.unrouted.pop(n, None)
            for p in fine:
                r._stamp(n, p, 1)
            return res
        base = w.hist
        w.hist = base + self.corridor_bias(tree)
        try:
            r.route_net(n, hard=hard)
        finally:
            w.hist = base
        return res

    def density_map(self, skip_nets=()):
        """Fine (L, H, W) expected wire occupancy summed over nets not in skip_nets."""
        F, w = self.F, self.w
        tot = np.zeros((F.L, F.Hc, F.Wc), np.float32)
        for n, d in self.dens.items():
            if n not in skip_nets:
                tot += d
        return tot


class HCollapse(JC.Collapse):
    def __init__(self, world, seed, budget, log, mode="bias", press_w=0.5, coarse=0.4, lam=0.5,
                 corr_r=1, via_sigma=0.2, all_layers=True, press_cap=2.0, **kw):
        super().__init__(world, seed, budget, log, **kw)
        self.mode = mode
        self.press_w = press_w
        self.press_cap = press_cap
        self.H = Harm(world, coarse=coarse, via_sigma=via_sigma, lam=lam, corr_r=corr_r,
                      all_layers=all_layers)
        self.n_routes = 0

    def route_all(self, beta):
        r, w = self.r, self.w
        r.pres = beta
        order = list(self.nets)
        self.rng.shuffle(order)
        harm = self.mode != "astar" or self.press_w > 0
        for n in order:
            r.rip(n)
            if harm and beta > 0:
                self.H.route_net(r, n, beta, self.mode)
            else:
                r.route_net(n)
        self.n_routes += 1
        bad = [n for n in self.nets if r.routes.get(n) and r.net_conflicts(n)]
        for n in bad:
            for p in r.routes[n]:
                add_hist(p, n, w.DT, w.occT, w.hist, self.hist_inc)
        return bad

    def best_response(self, pi, beta, CT, CV, per):
        if self.press_w <= 0 or beta <= 0 or not self.H.dens:
            return super().best_response(pi, beta, CT, CV, per)
        nets = set(self.kit.part_nets([pi]))
        F, w = self.H.F, self.w
        tot = self._dtot
        own = np.zeros_like(tot)
        for n in nets:
            d = self.H.dens.get(n)
            if d is not None:
                own += d
        # expected occupancy per fine cell: coarse occupancy per coarse cell spread over s*s
        # fine cells, times s (a wire crossing a coarse cell covers about s fine cells)
        extra = upsample(np.maximum(tot - own, 0) / F.s, F.s, w.H, w.W)
        # CT is priced at beta * pad_wire by jc; the pressure is a prior, so its price stops
        # growing at press_cap (otherwise parts accept courtyard overlap to escape it)
        CT2 = CT + (self.press_w * min(1.0, self.press_cap / beta)) * extra
        return super().best_response(pi, beta, CT2, CV, per)

    def route_maps(self):
        CT, CV, per = super().route_maps()
        if self.press_w > 0 and self.H.dens:
            self._dtot = self.H.density_map()
        return CT, CV, per


def _run(world, defaults, **kw):
    for k, v in defaults.items():
        kw.setdefault(k, v)
    hk = {k: kw.pop(k) for k in list(kw) if k in ("mode", "press_w", "coarse", "lam", "corr_r", "via_sigma",
                                                "all_layers", "press_cap")}
    orig = JC.Collapse
    log = kw.get("log", print)
    holder = {}

    def factory(world_, seed, budget, log_, **kw_):
        C = HCollapse(world_, seed, budget, log_, **hk, **kw_)
        holder["C"] = C
        return C

    JC.Collapse = factory
    try:
        r = JC.jc(world, **kw)
    finally:
        JC.Collapse = orig
    C = holder.get("C")
    if C is not None:
        log(f"harm: mode={hk.get('mode')} press_w={hk.get('press_w')} field solves={C.H.F.solves} "
            f"field cpu={C.H.t:.1f}s route passes={C.n_routes}")
    return r


def hjc(world, **kw):
    """Corridor bias (b) + part pressure (c), jc's polish."""
    return _run(world, dict(mode="bias", press_w=0.5), **kw)


def hjc_bias(world, **kw):
    return _run(world, dict(mode="bias", press_w=0.0), **kw)


def hjc_press(world, **kw):
    return _run(world, dict(mode="astar", press_w=0.5), **kw)


def hjc_stream(world, **kw):
    """Streamline routes (a) in the continuation + pressure (c)."""
    return _run(world, dict(mode="stream", press_w=0.5), **kw)


def hjc_lv(world, **kw):
    kw["phys_w"] = 0.0
    return hjc(world, **kw)


def hjc_stream_lv(world, **kw):
    kw["phys_w"] = 0.0
    return hjc_stream(world, **kw)


def hroute(world, seed=0, budget=300, log=print, iters=40, mode="bias", lam=0.5, coarse=0.4, **kw):
    """Route task: human placement, PathFinder whose every net routing is harmonic-biased
    (field priced with the current present cost); then Router.legalize."""
    for pi in range(len(world.parts)):
        world.place_original(pi)
    r = M._router(world, kw)
    H = Harm(world, coarse=coarse, lam=lam)
    nets = list(world.net_pins)
    r.pres = 0.5
    for it in range(iters):
        for n in nets:
            r.rip(n)
            H.route_net(r, n, r.pres, mode)
        bad = [n for n in nets if r.net_conflicts(n)]
        log(f"  hpf it={it} pres={r.pres:.2f} conflicted={len(bad)} unrouted={sum(r.unrouted.values())}")
        if not bad:
            break
        for n in bad:
            for p in r.routes[n]:
                add_hist(p, n, world.DT, world.occT, world.hist, r.hist_inc)
        r.pres *= 1.6
    r.legalize(nets)
    log(f"hroute {r.stats()} field solves={H.F.solves} field cpu={H.t:.1f}s")
    return r


def hjc_stream_lv_nopol(world, **kw):
    """Length + vias twin of hjc_stream without polish (pairs with jc_lv_nopol)."""
    kw["phys_w"] = 0.0
    kw.setdefault("polish", 0.0)
    return hjc_stream(world, **kw)


def hjc_stream_nopol(world, **kw):
    kw.setdefault("polish", 0.0)
    return hjc_stream(world, **kw)


def hjc_stream0(world, **kw):
    """Streamline routes in the continuation, no part pressure (isolates (a))."""
    return _run(world, dict(mode="stream", press_w=0.0), **kw)


def hjc_press_lv(world, **kw):
    """Length + vias twin of hjc_press (with jc's polish; pairs with jc_lv)."""
    kw["phys_w"] = 0.0
    return hjc_press(world, **kw)
