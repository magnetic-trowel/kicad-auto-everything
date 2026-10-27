# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""jc (collapse_joint) with T4 pour-damage maps, by subclassing (collapse_joint is not
edited): run.py plug-ins pjc (physics objective, phys_w 2, polish 0.15, as xf-base-jc)
and pjc_lv_nopol (length + vias, phys_w 0, no polish, as xf-base-jc_lv_nopol).

  part best response   cost(ri) += pour_w / g * sum over pours (n, l) of
                       corr(E_{n,l}, the part's halo cells of pads not on net n, layer l)
                       (one FFTCorr kernel per part, orientation and pour)
  routing              for net m, hist on layer l += route_w / g * sum over pours (n, l),
                       n != m, of corr(E_{n,l}, track halo disc) / disc diameter
                       (a track step on a pour layer costs the pour damage it does)
  coupled (pjc2*)      one solve per net over its pour layers, linked by its plated pads
                       and routed vias (round 2); otherwise one sheet per layer (round 1)
  refresh              PourMaps.refresh() at every jc iteration, after the nets are
                       re-routed and before the parts move (pours see the current
                       parts and tracks); skipped when it would use > 10 % of the time.

E is the relative R_eff increase of the net per removed cell (pourmap.py), so pour_w and
route_w are mm of wire per unit (100 %) increase of a pour net's resistance.
"""
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "research" / "pnr"))
sys.path.insert(0, str(HERE))

from placekit import corr  # noqa: E402
from pourmap import PourMaps  # noqa: E402
from router import Router, vias_of  # noqa: E402


def _load_jc():
    name = "xf_pour_jc"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "research" / "collapse_joint" / "jc.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


JC = _load_jc()


class PourRouter(Router):
    """Router whose cell cost adds the pour damage of foreign pours (via world.hist)."""
    pour_extra = None  # (per-layer total (L,H,W) float32, {(net, l): (H,W)})

    def route_net(self, net, hard=False, pres=None):
        ex = self.pour_extra
        if not ex:
            return super().route_net(net, hard=hard, pres=pres)
        tot, own = ex
        w = self.w
        h0 = w.hist
        h = h0 + tot
        for (n, l), m in own.items():
            if n == net:
                h[l] -= m
        w.hist = h
        try:
            return super().route_net(net, hard=hard, pres=pres)
        finally:
            w.hist = h0


class PourCollapse(JC.Collapse):
    def __init__(self, world, seed, budget, log, pour_w=100.0, route_w=100.0, coarse_mm=0.4,
                 pour_frac=0.10, coupled=False, **kw):
        super().__init__(world, seed, budget, log, **kw)
        self.r.__class__ = PourRouter
        self.pm = PourMaps(world, coarse_mm=coarse_mm, seed=seed, coupled=coupled, vias=self.net_vias)
        self.pour_w = pour_w
        self.route_w = route_w
        self.pour_frac = pour_frac
        self.FE = {}
        self.pkern = {}
        self.t_pour = 0.0
        self.n_ref = 0
        self.n_skip = 0
        if self.pm.pours:
            log(f"xf_pour: pours {[(world.net_names[n], l) for n, l in self.pm.pours]} "
                f"pour_w={pour_w} route_w={route_w} coarse={coarse_mm} coupled={coupled}")

    def net_vias(self, n):
        v = [vias_of(p)[:, 1:] for p in self.r.routes.get(n, [])]
        return np.concatenate(v) if v else np.zeros((0, 2), np.int64)

    def pour_kernel(self, pi, ri, n, l):
        key = (pi, ri, n, l)
        c = self.pkern.get(key)
        if c is None:
            w = self.w
            rr = w.part_raster(w.parts[pi], ri)
            cs = [e["hT"] for e in rr["pads"] if e["net"] != n and l in e["layers_halo"] and len(e["hT"])]
            c = self.pkern[key] = np.ascontiguousarray(np.unique(np.concatenate(cs), axis=0), np.int32) \
                if cs else np.zeros((0, 2), np.int32)
        return c

    def refresh_pours(self):
        if not self.pm.pours:
            return
        used = self.clock.budget - self.clock.left()
        if self.n_ref and self.t_pour > self.pour_frac * max(used, 1e-3):
            self.n_skip += 1
            return
        t0 = time.process_time()
        w = self.w
        E = self.pm.refresh()
        self.FE = {k: self.F.map(v) for k, v in E.items()} if self.pour_w else {}
        if self.route_w and E:
            disc = w.offs_TT
            diam = 2.0 * w.R.R_TT / w.g
            tot = np.zeros((w.nl, w.H, w.W), np.float32)
            own = {}
            for (n, l), v in E.items():
                m = (self.route_w / w.g / diam * corr(v, disc, pad_value=0.0)).astype(np.float32)
                tot[l] += m
                own[(n, l)] = m
            self.r.pour_extra = (tot, own)
        self.t_pour += time.process_time() - t0
        self.n_ref += 1

    def route_maps(self):
        # called once per jc iteration, after route_all and before the parts' best responses
        self.refresh_pours()
        return super().route_maps()

    def part_cost_maps(self, pi, beta, CT, CV, anchors):
        for ri, c, inside in super().part_cost_maps(pi, beta, CT, CV, anchors):
            if self.FE:
                pairs = [(FM, self.pour_kernel(pi, ri, n, l)) for (n, l), FM in self.FE.items()]
                c = c + (self.pour_w / self.g) * self.F.corr(pairs)
            yield ri, c, inside

    def pour_report(self):
        if not self.pm.pours:
            return "xf_pour: no pours"
        self.pm.refresh()
        w = self.w
        s = {f"{w.net_names[n]}|{l}": (None if v["R_eff"] is None else round(v["R_eff"], 3))
             for (n, l), v in self.pm.info.items()}
        return f"xf_pour: R_eff per pour {s} refreshes={self.n_ref} skipped={self.n_skip} t={self.t_pour:.2f}s"


def _run(world, kw, defaults):
    for k, v in defaults.items():
        kw.setdefault(k, v)
    holder = {}

    class _C(PourCollapse):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            holder["C"] = self

    old = JC.Collapse
    JC.Collapse = _C
    try:
        r = JC.jc(world, **kw)
    finally:
        JC.Collapse = old
    C = holder.get("C")
    if C is not None:
        kw.get("log", print)(C.pour_report())
    return r


def pjc(world, **kw):
    """jc (physics objective phys_w 2, polish 0.15) + pour-damage maps."""
    return _run(world, kw, {})


def pjc_lv_nopol(world, **kw):
    """jc_lv_nopol (length + vias, phys_w 0, no polish) + pour-damage maps."""
    kw["phys_w"] = 0.0
    return _run(world, kw, {"polish": 0.0})


def pjc2(world, **kw):
    """pjc with the layer-coupled maps (round 2): a net's pour layers solved together,
    linked by its plated pads and routed vias."""
    return _run(world, kw, {"coupled": True})


def pjc2_lv_nopol(world, **kw):
    """pjc_lv_nopol with the layer-coupled maps."""
    kw["phys_w"] = 0.0
    return _run(world, kw, {"polish": 0.0, "coupled": True})


def pjc_route_only(world, **kw):
    """Ablation: only the routing term."""
    return _run(world, kw, {"pour_w": 0.0})


def pjc_place_only(world, **kw):
    """Ablation: only the placement term."""
    return _run(world, kw, {"route_w": 0.0})


# weight sweep on dev6 (K = pour_w = route_w, mm of wire per 100 % pour-R increase)
def _mk(K, lv):
    def f(world, **kw):
        if lv:
            kw["phys_w"] = 0.0
            return _run(world, kw, {"polish": 0.0, "coupled": True, "pour_w": float(K), "route_w": float(K)})
        return _run(world, kw, {"coupled": True, "pour_w": float(K), "route_w": float(K)})
    f.__name__ = f"pjc2{'_lv_nopol' if lv else ''}_k{K}"
    return f


for _K in (30, 100, 300):
    for _lv in (False, True):
        _f = _mk(_K, _lv)
        globals()[_f.__name__] = _f
