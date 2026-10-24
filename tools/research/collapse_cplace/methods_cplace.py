# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement methods with layer-collapse terms (terms.CollapseTerms) in the objective.

Plug-ins for tools/research/pnr/run.py:
  combo_collapse  methods_combo.combo (beam with physics -> blocker repair -> physics
                  annealing) with the collapse terms added to (a) the beam's child score,
                  which already routes every candidate, (b) the candidate order inside the
                  beam (HPWL + w_fv * forced vias, so favourable rotations are tried first),
                  and (c) the repair/annealing acceptance (routed cost + phys_w * physics +
                  collapse terms). Switches: beam_terms, rerank, anneal_terms.
  seq_collapse    the no-routing-in-the-loop ablation: seq_phys (HPWL placement, physics
                  descent), then a best-response descent on HPWL + phys_w * physics +
                  collapse terms over each part's top candidates (all four rotations),
                  then route.
Options (run.py --opt k=v): w_fv (mm per forced via, default 4), w_ovf (mm per unit of
cut overflow, default 2), w_x (mm per straight-line ratsnest crossing, default 0), phys_w.
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PNR = HERE.parent / "pnr"
sys.path.insert(0, str(PNR))
sys.path.insert(0, str(HERE.parent / "pnr_mcts"))
sys.path.insert(0, str(HERE))

import methods as M  # noqa: E402
import methods_combo as MC  # noqa: E402
import methods_phys as MP  # noqa: E402
from physics import Phys  # noqa: E402
from placekit import Clock, Kit  # noqa: E402
from terms import CollapseTerms  # noqa: E402

TERM_KW = ("w_fv", "w_ovf", "w_x", "fv_mode")


def _terms(world, kw):
    return CollapseTerms(world, w_fv=float(kw.get("w_fv", 4.0)), w_ovf=float(kw.get("w_ovf", 2.0)),
                         w_x=float(kw.get("w_x", 0.0)), fv_mode=kw.get("fv_mode", "proj"))


def _clean(kw):
    drop = TERM_KW + ("beam_terms", "rerank", "anneal_terms")
    return {k: v for k, v in kw.items() if k not in drop}


class PhysPlus:
    """physics.Phys with the collapse terms added (in physics units: mm / phys_w), so the
    unchanged repair_phys / anneal_phys accept on routed + phys_w * physics + collapse."""

    def __init__(self, ph, ct, phys_w):
        self.ph, self.ct, self.k = ph, ct, 1.0 / phys_w
        self.active = ph.active
        self.key = ph.key

    def sync(self):
        self.ph.sync()
        self.ct.sync()

    def commit(self, pi):
        self.ph.commit(pi)
        self.ct.commit(pi)

    def total(self):
        return self.ph.total() + self.k * self.ct.total()

    def delta(self, pi, pose):
        return self.ph.delta(pi, pose) + self.k * self.ct.delta(pi, pose)

    def coarse_map(self, *a, **kw):
        return self.ph.coarse_map(*a, **kw)

    def __getattr__(self, name):
        return getattr(self.ph, name)


def _fv_rerank(ct, orig):
    """Wrap a candidate generator: re-sort candidates by cost + w_fv * forced-via change."""
    def fc(kit, pi, rots=range(4), k=8, cost_extra=None, nms_cells=None):
        cs = orig(kit, pi, rots=rots, k=k, cost_extra=cost_extra, nms_cells=nms_cells)
        bl = ct.part_buses.get(pi)
        if not bl or len(cs) < 2 or not ct.wt["fv"]:
            return cs
        w = kit.w
        parts = ct._bus_parts(bl)
        base = {q: w.pose[q] for q in parts if q in w.pose and q != pi}
        out = []
        for c in cs:
            base[pi] = c[1:]
            xy, _ = ct.pad_xy(base)
            out.append((c[0] + ct.wt["fv"] * ct.fv(xy, bl),) + tuple(c[1:]))
        out.sort()
        return out
    return fc


def combo_collapse(world, seed=0, budget=300, log=print, phys_w=2.0, beam_terms=True, rerank=True,
                   anneal_terms=True, **kw):
    import mcts
    ct = _terms(world, kw)
    log(f"collapse terms: weights {ct.wt}, {len(ct.buses)} buses "
        f"{[(world.parts[b['a']].ref, world.parts[b['b']].ref, len(b['pa']), b['L']) for b in ct.buses]}")
    rng = random.Random(seed)
    clock = Clock(budget)
    Ctx0, fc0 = mcts.Ctx, mcts.fc

    class CtxC(Ctx0):
        def cost(self):
            c = super().cost()
            if beam_terms:
                c += ct.cost_of(dict(self.w.pose))
            return c

    mcts.Ctx = CtxC
    if rerank:
        mcts.fc = _fv_rerank(ct, fc0)
    try:
        r = mcts.beam(world, seed=seed, budget=budget * 0.45, log=log, phys_w=phys_w, **_clean(kw))
    finally:
        mcts.Ctx, mcts.fc = Ctx0, fc0
    kit = Kit(world, r)
    ph = Phys(world, world.data["path"])
    ph.sync()
    ct.sync()
    if anneal_terms:
        ph = PhysPlus(ph, ct, phys_w)
    world.phys = ph
    log(f"combo_collapse after beam: {r.stats()} phys+={ph.total():.2f} terms={ct.evaluate(ct.poses)}")
    MC.repair_phys(world, kit, ph, phys_w, Clock(budget * 0.25), log, rng)
    r = MP.anneal_phys(world, seed=seed, budget=max(1.0, clock.left()), log=log, phys_w=phys_w, router=r,
                       **_clean(kw))
    ct.sync()
    log(f"combo_collapse {r.stats()} hpwl={world.hpwl():.1f} phys+={ph.total():.2f} terms={ct.evaluate(ct.poses)}")
    world.phys = ph.ph if isinstance(ph, PhysPlus) else ph
    return r


def descent_collapse(world, kit, ph, ct, phys_w, log, rounds=3, k=4, clock=None):
    """Best-response descent on HPWL + phys_w * physics + collapse terms; each part's
    options are its top-k HPWL candidates per rotation plus its current pose."""
    from fastcand import candidates as fc
    bias = M.center_bias(kit, 0.002)
    for rd in range(rounds):
        moved = 0
        for pi in kit.movable():
            if pi not in world.pose:
                continue
            cur = world.pose[pi]
            world.unplace(pi)
            here = kit.hpwl_map(pi, cur[2])[cur[1], cur[0]] + bias(pi, cur[2])[cur[1], cur[0]]
            opts = [(here,) + cur] + fc(kit, pi, k=k, cost_extra=bias)
            best = None
            for hp, cx, cy, ri in opts:
                pose = (cx, cy, ri)
                c = hp + phys_w * ph.delta(pi, pose) + ct.delta(pi, pose)
                if best is None or c < best[0] - 1e-9:
                    best = (c, pose)
            world.place(pi, *best[1])
            if best[1] != cur:
                moved += 1
            ph.commit(pi)
            ct.commit(pi)
            if clock and clock.left() < 0:
                return
        ev = ct.evaluate(ct.poses)
        log(f"  collapse descent round {rd}: moved {moved} hpwl {world.hpwl():.1f} phys {ph.total():.2f} {ev}")
        if not moved:
            break


def seq_collapse(world, seed=0, budget=300, log=print, phys_w=2.0, **kw):
    clock = Clock(budget)
    rng = random.Random(seed)
    ct = _terms(world, kw)
    r, kit = MP._setup(world, seed, log, _clean(kw))
    M.greedy_place(world, kit, M.growth_order(world, kit, rng), log)
    M.descent(world, kit, log, clock=clock)
    ph = Phys(world, world.data["path"])
    ph.sync()
    MP.descent_phys(world, kit, ph, phys_w, log, clock=clock)
    ph.sync()
    ct.sync()
    log(f"  before collapse descent: {ct.evaluate(ct.poses)} buses={len(ct.buses)}")
    descent_collapse(world, kit, ph, ct, phys_w, log, clock=clock)
    r.pathfinder(log=log, iters=40)
    log(f"seq_collapse {r.stats()} hpwl={world.hpwl():.1f} phys={ph.total():.2f} terms={ct.evaluate(ct.poses)}")
    world.phys = ph
    return r
