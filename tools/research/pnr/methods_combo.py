# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The combination the experiments point to (docs/topics/placement/joint-pnr-experiments.md):

  combo  beam search over place-one-route-it with the physics term (pnr_mcts.beam),
         then blocker-directed window repair, then annealing on routed cost + physics
         (methods_phys.anneal_phys continuing from the board). Budget split 45/25/30 %.
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "pnr_mcts"))

import methods as M  # noqa: E402
import methods_phys as MP  # noqa: E402
from physics import Phys  # noqa: E402
from placekit import Clock, Kit  # noqa: E402


def repair_phys(world, kit, ph, w, clock, log, rng, window=4, k=5):
    """methods.repair from the current board, accepting on routed cost + w * physics."""
    r = kit.r
    mov = [q for q in kit.movable() if q in world.pose]

    def cost():
        return kit.total_cost() + w * ph.total()

    cur = cost()
    tries = acc = 0
    tabu = {}
    while clock.left() > 0 and mov:
        unr = [n for n in world.net_pins if r.unrouted.get(n)]
        if unr:
            net = rng.choice(unr)
        else:
            ratios = {n: kit.net_cost(n, unrouted_mm=0) / (world.hpwl([n]) + 1.0) for n in world.net_pins}
            net = max(ratios, key=lambda n: ratios[n] * rng.uniform(0.7, 1.3))
        snap_all = kit.snapshot(list(world.net_pins))
        poses0 = dict(world.pose)
        bl = M.blockers(world, kit, net)
        own = [pi for pi, _ in world.net_pins[net] if pi in mov]
        cand = sorted(bl, key=lambda q: -bl[q])[:window] + own
        cand = [q for q in dict.fromkeys(cand) if tabu.get(q, -1) < tries and q in mov][: window + 2]
        if not cand:
            cand = [rng.choice(mov)]
        tries += 1
        for q in cand:
            world.unplace(q)
        kit.reroute(list(world.net_pins), iters=3)
        rng.shuffle(cand)
        ok = True
        for q in cand:
            cs = kit.candidates(q, k=k)
            if not cs:
                ok = False
                break
            best = None
            for _, cx, cy, ri in cs:
                world.place(q, cx, cy, ri)
                aff = kit.part_nets([q]) | set(kit.conflicted_nets())
                sn = kit.snapshot(aff)
                kit.reroute(aff, iters=3)
                ph.sync()
                c = cost()
                kit.restore(sn)
                world.unplace(q)
                if best is None or c < best[0]:
                    best = (c, cx, cy, ri)
            world.place(q, *best[1:])
            kit.reroute(kit.part_nets([q]) | set(kit.conflicted_nets()), iters=3)
        new = None
        if ok:
            r.pathfinder(iters=15, log=None)
            ph.sync()
            new = cost()
        if ok and new < cur - 1e-6:
            cur = new
            acc += 1
        else:
            for q in list(world.pose):
                if q in mov:
                    world.unplace(q)
            r.rip_all()
            for q, p in poses0.items():
                if q in mov:
                    world.place(q, *p)
            kit.restore(snap_all)
            ph.sync()
            for q in cand:
                tabu[q] = tries + 3
        if tries % 5 == 0:
            log(f"  repair_phys tries={tries} acc={acc} cost={cur:.1f} phys={ph.total():.2f} {r.stats()}")
    r.legalize(list(world.net_pins))
    log(f"  repair_phys done tries={tries} acc={acc} {r.stats()} phys={ph.total():.2f}")


def combo(world, seed=0, budget=300, log=print, phys_w=2.0, **kw):
    import mcts
    rng = random.Random(seed)
    clock = Clock(budget)
    r = mcts.beam(world, seed=seed, budget=budget * 0.45, log=log, phys_w=phys_w, **kw)
    kit = Kit(world, r)
    ph = Phys(world, world.data["path"])
    ph.sync()
    world.phys = ph
    log(f"combo after beam: {r.stats()} phys={ph.total():.2f}")
    repair_phys(world, kit, ph, phys_w, Clock(budget * 0.25), log, rng)
    r = MP.anneal_phys(world, seed=seed, budget=max(1.0, clock.left()), log=log, phys_w=phys_w, router=r)
    log(f"combo {r.stats()} hpwl={world.hpwl():.1f} phys={ph.total():.2f}")
    return r
