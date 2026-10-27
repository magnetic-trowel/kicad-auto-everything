# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-aware variants: kae.physics place terms (physics.Phys) inside the objective.

Plug-in methods for run.py (`run.py .../methods_phys.py:anneal_phys ...`):
  seq_phys     HPWL placement, then descent on HPWL + w * physics, then route
  grow_phys    place-one-route-it (methods.grow), then the physics descent, then re-route
  anneal_phys  seq_phys start; annealing on routed cost + w * physics, physics parts
               moved more often and able to jump to their best HPWL + physics spot
Option phys_w (mm of routed copper per unit of the place-terms total, default 2).
"""
import math
import random

import numpy as np

import methods as M
from physics import Phys
from placekit import Clock, Kit


def descent_phys(world, kit, ph, w, log, rounds=4, clock=None):
    """Best-response descent on HPWL + w * physics delta. Physics parts use a coarse
    physics map over legal origins; the rest plain HPWL (as methods.descent)."""
    bias = M.center_bias(kit, 0.002)
    for rd in range(rounds):
        moved = 0
        order = sorted(kit.movable(), key=lambda q: q not in ph.active)
        for pi in order:
            if pi not in world.pose:
                continue
            cur = world.pose[pi]
            world.unplace(pi)
            here = kit.hpwl_map(pi, cur[2])[cur[1], cur[0]]
            best = None
            for ri in range(4):
                L = kit.legal_map(pi, ri)
                if not L.any():
                    continue
                c = kit.hpwl_map(pi, ri) + bias(pi, ri)
                if pi in ph.active:
                    c = c + w * ph.coarse_map(pi, ri, legal=L)
                c = np.where(L, c, np.inf)
                j = int(np.argmin(c))
                if np.isfinite(c.flat[j]) and (best is None or c.flat[j] < best[0]):
                    best = (c.flat[j], j % world.W, j // world.W, ri)
            if best is not None and pi in ph.active:
                # exact physics at the chosen spot (the map is sampled)
                exact = kit.hpwl_map(pi, best[3])[best[2], best[1]] + w * ph.delta(pi, best[1:])
                best = (exact,) + best[1:]
            if best is not None and best[0] < here - 1e-6:
                world.place(pi, best[1], best[2], best[3])
                moved += 1
            else:
                world.place(pi, *cur)
            ph.commit(pi)
            if clock and clock.left() < 0:
                return
        log(f"  phys descent round {rd}: moved {moved} hpwl {world.hpwl():.1f} phys {ph.total():.2f}")
        if not moved:
            break


def _setup(world, seed, log, kw):
    M._place_fixed(world)
    r = M._router(world, kw)
    kit = Kit(world, r)
    M.place_mechanical(world, kit, log)
    return r, kit


def seq_phys(world, seed=0, budget=300, log=print, phys_w=2.0, **kw):
    rng = random.Random(seed)
    clock = Clock(budget)
    r, kit = _setup(world, seed, log, kw)
    M.greedy_place(world, kit, M.growth_order(world, kit, rng), log)
    M.descent(world, kit, log, clock=clock)
    ph = Phys(world, world.data["path"])
    ph.sync()
    log(f"  physics parts {len(ph.active)}; phys after HPWL placement {ph.total():.2f}")
    descent_phys(world, kit, ph, phys_w, log, clock=clock)
    r.pathfinder(log=log, iters=40)
    log(f"seq_phys {r.stats()} hpwl={world.hpwl():.1f} phys={ph.total():.2f}")
    world.phys = ph
    return r


def grow_phys(world, seed=0, budget=300, log=print, phys_w=2.0, **kw):
    clock = Clock(budget)
    r = M.grow(world, seed=seed, budget=budget * 0.6, log=log, **kw)
    kit = Kit(world, r)
    ph = Phys(world, world.data["path"])
    ph.sync()
    log(f"  phys after grow {ph.total():.2f}")
    descent_phys(world, kit, ph, phys_w, log, clock=clock)
    r.pathfinder(log=log, iters=40)
    log(f"grow_phys {r.stats()} hpwl={world.hpwl():.1f} phys={ph.total():.2f}")
    world.phys = ph
    return r


def anneal_phys(world, seed=0, budget=300, log=print, phys_w=2.0, router=None, **kw):
    """Annealing whose cost is routed copper (incremental rip-up/re-route) + phys_w * place
    terms. Half the moves pick a physics part; a third of those jump to the part's best
    HPWL + physics spot. With `router` (and world.phys) it continues from the current
    board instead of starting from seq_phys."""
    rng = random.Random(seed)
    clock = Clock(budget)
    if router is None:
        r = seq_phys(world, seed=seed, budget=budget * 0.3, log=log, phys_w=phys_w, **kw)
    else:
        r = router
    ph = world.phys
    kit = Kit(world, r)
    mov = [q for q in kit.movable() if q in world.pose]
    act = [q for q in mov if q in ph.active]
    w = phys_w
    cur_r = kit.total_cost()
    cur_p = ph.total()
    best = (cur_r + w * cur_p, dict(world.pose), kit.snapshot(list(world.net_pins)))
    T0 = kw.get("t0", 1.5)
    nacc = ntry = 0
    diag = math.hypot(world.W, world.H)
    while clock.left() > 0 and mov:
        f = clock.frac()
        T = T0 * 0.01 ** f
        rad = max(3, int(diag * 0.3 * 0.03 ** f))
        pi = rng.choice(act) if act and rng.random() < 0.5 else rng.choice(mov)
        old = world.pose[pi]
        world.unplace(pi)
        newpose = None
        kind = rng.random()
        if pi in ph.active and kind < 0.33:
            ri = rng.randrange(4)
            L = kit.legal_map(pi, ri)
            if L.any():
                c = np.where(L, kit.hpwl_map(pi, ri) + w * ph.coarse_map(pi, ri, legal=L), np.inf)
                j = int(np.argmin(c))
                newpose = (j % world.W, j // world.W, ri)
        else:
            rots = [old[2]] if kind < 0.85 else [q for q in range(4) if q != old[2]]
            ri = rng.choice(rots)
            L = kit.legal_map(pi, ri)
            y0, y1 = max(0, old[1] - rad), min(world.H, old[1] + rad + 1)
            x0, x1 = max(0, old[0] - rad), min(world.W, old[0] + rad + 1)
            sub = np.argwhere(L[y0:y1, x0:x1])
            if len(sub):
                yy, xx = sub[rng.randrange(len(sub))]
                newpose = (x0 + int(xx), y0 + int(yy), ri)
        if newpose is None or newpose == old:
            world.place(pi, *old)
            continue
        ntry += 1
        dphys = ph.delta(pi, newpose)
        world.place(pi, *newpose)
        affected = kit.part_nets([pi]) | set(kit.conflicted_nets())
        snap = kit.snapshot(affected)
        before = sum(kit.net_cost(n) for n in affected)
        kit.reroute(affected, iters=4)
        after = sum(kit.net_cost(n) for n in affected)
        delta = (after - before) + w * dphys
        if delta <= 0 or rng.random() < math.exp(-delta / T):
            cur_r += after - before
            ph.commit(pi)
            cur_p = ph.total()
            nacc += 1
            if cur_r + w * cur_p < best[0] - 1e-6:
                best = (cur_r + w * cur_p, dict(world.pose), kit.snapshot(list(world.net_pins)))
        else:
            kit.restore(snap)
            world.unplace(pi)
            world.place(pi, *old)
        world.hist *= 0.98
        if ntry % 50 == 0:
            log(f"  anneal_phys t={clock.frac():.2f} T={T:.2f} routed={cur_r:.1f} phys={cur_p:.2f} "
                f"best={best[0]:.1f} acc={nacc}/{ntry} {r.stats()}")
    for q in list(world.pose):
        if q in mov:
            world.unplace(q)
    r.rip_all()
    for q, p in best[1].items():
        if q in mov:
            world.place(q, *p)
    kit.restore(best[2])
    ph.sync()
    r.legalize(list(world.net_pins))
    if any(r.unrouted.values()):
        r.pathfinder(log=log, iters=20)
    log(f"anneal_phys {r.stats()} hpwl={world.hpwl():.1f} phys={ph.total():.2f} tries={ntry} acc={nacc}")
    return r
