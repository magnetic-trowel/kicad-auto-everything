# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""jc and jc_full with exact physics maps (physmap.ExactPhys) instead of Phys.coarse_map.

Plug-ins for pnr/run.py (collapse_joint/jc.py is loaded and wrapped, not edited):

  jc_x           jc (phys_w = 2, polish 15 %) with exact maps
  jc_lv_nopol_x  jc_lv_nopol (phys_w = 0); maps are never consulted at phys_w = 0
  jc_full_x      jc_full (restarts judged with 5 x routed physics, no polish) with exact maps

Where the maps enter:
  lift          Phys.coarse_map(step 1.2 mm) -> exact map over the legal cells
  polish        anneal_phys's coarse_map jumps -> exact map
  best response the whole-board argmin includes phys_w * map / g (it had no physics; kae's
                delta was evaluated only at the top HPWL/conflict candidates); the top
                candidates are still re-scored with the exact Terms.delta.
Each map has a CPU budget (map_budget, s: lift and polish; br_budget: best responses, where
the top candidates are re-scored exactly anyway). While best-response maps hold more than
max_share of the CPU since the first one, best responses fall back to jc's candidate
rescoring (counts logged).
"""
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "pnr"))

import physmap  # noqa: E402

_spec = importlib.util.spec_from_file_location("jc_base", str(HERE.parent / "collapse_joint" / "jc.py"))
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)

OPTS = dict(map_budget=0.3, br_budget=0.05, max_share=0.35)


class XPhys(physmap.ExactPhys):
    def __init__(self, world, board_path):
        super().__init__(world, board_path, map_budget=OPTS["map_budget"])


class XCollapse(J.Collapse):
    def __init__(self, world, seed, budget, log, **kw):
        self.max_share = kw.pop("max_share", OPTS["max_share"])
        super().__init__(world, seed, budget, log, **kw)
        self.br_map = self.br_fallback = 0
        self.br_cpu = 0.0
        self.t_br0 = None

    def _maps_ok(self):
        # best-response maps may take at most max_share of the CPU since the first one
        if self.t_br0 is None:
            self.t_br0 = time.process_time()
        used = time.process_time() - self.t_br0
        return used < 2.0 or self.br_cpu < self.max_share * used

    def best_response(self, pi, beta, CT, CV, per):
        w, ph = self.w, self.ph
        if not (pi in ph.active and self.phys_w > 0 and not self.trust and self._maps_ok()):
            if pi in ph.active and self.phys_w > 0:
                self.br_fallback += 1
            return super().best_response(pi, beta, CT, CV, per)
        self.br_map += 1
        cur = w.pose[pi]
        anchors = self.anchors(pi) if (self.tension_w and beta >= self.tension_beta) else []
        nets = self.kit.part_nets([pi])
        for n in nets:
            if n in per:
                a, v = per[n]
                CT[a[:, 0], a[:, 1], a[:, 2]] -= 1
                if len(v):
                    CV[v[:, 0], v[:, 1]] -= 1
        w.unplace(pi)
        cands = []
        for ri, c, inside in self.part_cost_maps(pi, beta, CT, CV, anchors):
            t0 = time.process_time()
            pm = self.phys_w * ph.exact_map(pi, ri, legal=inside, budget=OPTS["br_budget"]) / self.g
            self.br_cpu += time.process_time() - t0
            c = np.where(inside, c + pm, np.inf)
            flat = np.argpartition(c, min(self.k_phys * 20, c.size - 1), axis=None)[: self.k_phys * 20]
            flat = flat[np.argsort(c.flat[flat])]
            taken = []
            nms = max(3, int(0.6 / w.g))
            for f in flat:
                v = c.flat[f]
                if not np.isfinite(v):
                    break
                y, x = divmod(int(f), w.W)
                if any(abs(x - a) < nms and abs(y - b) < nms for a, b in taken):
                    continue
                taken.append((x, y))
                cands.append((float(v - pm[y, x]), x, y, ri))
                if len(taken) >= self.k_phys // 4 + 2:
                    break
            if ri == cur[2] and inside[cur[1], cur[0]]:
                cands.append((float(c[cur[1], cur[0]] - pm[cur[1], cur[0]]), cur[0], cur[1], ri))
        if cands:
            cands = [(v + self.phys_w * ph.delta(pi, (x, y, ri)) / self.g, x, y, ri) for v, x, y, ri in cands]
        best = min(cands) if cands else (0.0,) + tuple(cur)
        w.place(pi, best[1], best[2], best[3])
        ph.commit(pi)
        for n in nets:
            if n in per:
                a, v = per[n]
                CT[a[:, 0], a[:, 1], a[:, 2]] += 1
                if len(v):
                    CV[v[:, 0], v[:, 1]] += 1
        return tuple(best[1:]) != tuple(cur)


def _patched(fn, world, log=print, **kw):
    J.Phys = XPhys
    J.Collapse = XCollapse
    for k in ("map_budget", "br_budget", "max_share"):
        if k in kw:
            OPTS[k] = kw.pop(k)
    holder = {}
    orig_init = XCollapse.__init__

    def init(self, *a, **k):
        orig_init(self, *a, **k)
        holder["C"] = self
    XCollapse.__init__ = init
    t0 = time.process_time()
    try:
        r = fn(world, log=log, **kw)
    finally:
        XCollapse.__init__ = orig_init
    C = holder.get("C")
    if C is not None:
        ph = C.ph
        used = time.process_time() - t0
        msg = (f"xf_physmap: maps={ph.calls} cache_hits={ph.hits} capped={ph.capped} refined_cells={ph.refined} "
            f"map_cpu={ph.map_cpu:.1f}s of {used:.1f}s ({100 * ph.map_cpu / max(used, 1e-9):.0f}%) "
            f"best_responses map={C.br_map} fallback={C.br_fallback} br_map_cpu={C.br_cpu:.1f}s")
        log(msg)
        print(msg, file=sys.stderr, flush=True)
    return r


def jc_x(world, **kw):
    return _patched(J.jc, world, **kw)


def jc_lv_nopol_x(world, **kw):
    return _patched(J.jc_lv_nopol, world, **kw)


def jc_full_x(world, **kw):
    return _patched(J.jc_full, world, **kw)
