# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Length + vias variants (no physics term) of the collapse-term methods.

  combo_collapse_lv  methods_combo.combo_lv (phys_w = 0: routed length + 2 mm/via +
                     unrouted penalty) with the collapse terms in the beam score, the beam's
                     candidate order and the repair/annealing acceptance.
  seq_collapse_lv    seq_collapse with phys_w = 0 (HPWL + collapse terms, then route).

The repair/annealing stages (methods_combo.repair_phys, methods_phys.anneal_phys) accept on
routed + w * ph; here ph carries no physics, only the collapse terms, and w = 1.
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import methods_cplace as MCP  # noqa: E402  (sets up the engine paths)
import methods_combo as MC  # noqa: E402
import methods_phys as MP  # noqa: E402
from placekit import Clock, Kit  # noqa: E402


class TermsOnly:
    """Phys-like object whose total/delta are the collapse terms alone (mm)."""

    def __init__(self, world, ct):
        import numpy as np
        self.w, self.ct, self.np = world, ct, np
        self.active = set()
        self.key = {}

    def sync(self):
        self.ct.sync()

    def commit(self, pi):
        self.ct.commit(pi)

    def total(self):
        return self.ct.total()

    def delta(self, pi, pose):
        return self.ct.delta(pi, pose)

    def coarse_map(self, pi, ri, step_mm=0.8, legal=None):
        return self.np.zeros((self.w.H, self.w.W))


def combo_collapse_lv(world, seed=0, budget=300, log=print, beam_terms=True, rerank=True, **kw):
    import mcts
    kw.pop("phys_w", None)
    ct = MCP._terms(world, kw)
    log(f"collapse terms (lv): weights {ct.wt}, {len(ct.buses)} buses")
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
        mcts.fc = MCP._fv_rerank(ct, fc0)
    try:
        r = mcts.beam(world, seed=seed, budget=budget * 0.45, log=log, phys_w=0.0, **MCP._clean(kw))
    finally:
        mcts.Ctx, mcts.fc = Ctx0, fc0
    kit = Kit(world, r)
    ct.sync()
    ph = TermsOnly(world, ct)
    world.phys = ph
    log(f"combo_collapse_lv after beam: {r.stats()} terms={ct.evaluate(ct.poses)}")
    MC.repair_phys(world, kit, ph, 1.0, Clock(budget * 0.25), log, rng)
    r = MP.anneal_phys(world, seed=seed, budget=max(1.0, clock.left()), log=log, phys_w=1.0, router=r,
                       **MCP._clean(kw))
    ct.sync()
    log(f"combo_collapse_lv {r.stats()} hpwl={world.hpwl():.1f} terms={ct.evaluate(ct.poses)}")
    del world.phys
    return r


def seq_collapse_lv(world, seed=0, budget=300, log=print, **kw):
    kw["phys_w"] = 0.0
    return MCP.seq_collapse(world, seed=seed, budget=budget, log=log, **kw)
