# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Methods: each takes a World, places every part and returns a Router with routes.

Controls
  route_only   keep the input placement, negotiate routes (use on route tasks)
  seq          decoupled: HPWL placement (greedy + best-response descent), then route
Joint / interleaved (see docs/ideas/original/joint-pnr.md)
  grow         place one part, route it, next part (candidates scored by real routing)
  anneal       simulated annealing whose cost is re-routed copper (incremental rip-up)
  tension      envelope-theorem forces from routed tracks + Lagrange price gradient
  bloat        route, inflate parts where routing failed or detoured, re-place, repeat
"""
import math
import random

import numpy as np

from placekit import Clock, Kit
from raster import disc
from router import Router

ROUTER_KW = ("via_cost_mm", "dir_pen")


def _router(world, kw):
    return Router(world, **{k: v for k, v in kw.items() if k in ROUTER_KW})


def _place_fixed(world):
    for p in world.parts:
        if p.locked:
            world.place_original(p.idx)


def route_only(world, seed=0, budget=300, log=print, **kw):
    for pi in range(len(world.parts)):
        world.place_original(pi)
    r = _router(world, kw)
    r.pathfinder(log=log, iters=kw.get("iters", 40))
    log(f"route_only {r.stats()}")
    return r


# ---------------------------------------------------------------- placement building blocks
def place_mechanical(world, kit, log):
    """Mechanical first: parts without nets (mounting holes, logos, fiducials) go to the
    free spot farthest from the board centre, largest first, before anything else."""
    mech = [pi for pi in kit.movable() if not kit.part_nets([pi])]
    mech.sort(key=lambda pi: -world.parts[pi].area)
    far = center_bias(kit, -1.0)
    for pi in mech:
        best = None
        for ri in range(4):
            L = kit.legal_map(pi, ri)
            if not L.any():
                continue
            c = np.where(L, far(pi, ri), np.inf)
            j = int(np.argmin(c))
            if best is None or c.flat[j] < best[0]:
                best = (c.flat[j], j % world.W, j // world.W, ri)
        if best is None:
            log(f"  no legal spot for {world.parts[pi].ref}")
            continue
        world.place(pi, best[1], best[2], best[3])
    world.mech = set(mech)  # placed once, not optimized further
    return set(mech)


def growth_order(world, kit, rng):
    """Most-connected part first, then repeatedly the part with most connections to placed
    parts (ties: more pins, then random)."""
    mov = [pi for pi in kit.movable() if pi not in world.pose]
    nets_of = {pi: kit.part_nets([pi]) for pi in mov}
    placed_nets = set()
    for pi in world.pose:
        placed_nets |= kit.part_nets([pi])
    order = []
    left = set(mov)
    amax = max([world.parts[pi].area for pi in mov] + [1e-9])
    nmax = max([len(v) for v in nets_of.values()] + [1])
    while left:
        def key(pi):
            # big rocks first, then connectivity to what is already placed
            return (2.0 * world.parts[pi].area / amax + len(nets_of[pi] & placed_nets) / nmax,
                    len(world.parts[pi].pads), rng.random())
        pi = max(left, key=key)
        order.append(pi)
        left.remove(pi)
        placed_nets |= nets_of[pi]
    return order


def center_bias(kit, weight=0.02):
    w = kit.w
    cx = np.mean([o[:, 0].mean() for o in w.outline])
    cy = np.mean([o[:, 1].mean() for o in w.outline])
    D = kit.dist_map(cx, cy) * weight
    return lambda pi, ri: D


def greedy_place(world, kit, order, log, rots=range(4)):
    bias = center_bias(kit)
    for pi in order:
        c = kit.candidates(pi, rots=rots, k=1, cost_extra=bias)
        if not c:
            log(f"  no legal spot for {world.parts[pi].ref}")
            continue
        _, cx, cy, ri = c[0]
        world.place(pi, cx, cy, ri)


def descent(world, kit, log, rounds=6, clock=None, rots=range(4)):
    """Best-response coordinate descent on HPWL: each part jumps to its best legal pose."""
    bias = center_bias(kit, 0.002)
    for rd in range(rounds):
        moved = 0
        for pi in kit.movable():
            if pi not in world.pose:
                continue
            cur = world.pose[pi]
            world.unplace(pi)
            here = kit.hpwl_map(pi, cur[2])[cur[1], cur[0]]
            c = kit.candidates(pi, rots=rots, k=1, cost_extra=bias)
            if c and c[0][0] < here - 1e-6:
                _, cx, cy, ri = c[0]
                world.place(pi, cx, cy, ri)
                moved += 1
            else:
                world.place(pi, *cur)
            if clock and clock.left() < 0:
                return
        log(f"  descent round {rd}: moved {moved}, hpwl {world.hpwl():.1f}")
        if not moved:
            break


def seq(world, seed=0, budget=300, log=print, **kw):
    """Control: conventional place-then-route."""
    rng = random.Random(seed)
    clock = Clock(budget)
    _place_fixed(world)
    r = _router(world, kw)
    kit = Kit(world, r)
    place_mechanical(world, kit, log)
    greedy_place(world, kit, growth_order(world, kit, rng), log)
    descent(world, kit, log, clock=clock)
    r.pathfinder(log=log, iters=40)
    log(f"seq {r.stats()} hpwl={world.hpwl():.1f}")
    return r


# ---------------------------------------------------------------- idea 6: grow
def grow(world, seed=0, budget=300, log=print, **kw):
    """Place-one, route-it. Each part's K candidate poses are scored by actually routing the
    nets the part completes (and re-routing nets its pads now block)."""
    rng = random.Random(seed)
    clock = Clock(budget)
    _place_fixed(world)
    r = _router(world, kw)
    kit = Kit(world, r)
    place_mechanical(world, kit, log)
    order = growth_order(world, kit, rng)
    K = kw.get("k", 6)
    bias = center_bias(kit)
    per_part = budget * 0.7 / max(1, len(order))
    for i, pi in enumerate(order):
        cands = kit.candidates(pi, k=K, cost_extra=bias)
        if not cands:
            log(f"  no legal spot for {world.parts[pi].ref}")
            continue
        nets = kit.part_nets([pi])
        best = None
        t_part = Clock(per_part)
        for hp, cx, cy, ri in cands:
            world.place(pi, cx, cy, ri)
            affected = nets | set(kit.conflicted_nets())
            snap = kit.snapshot(affected)
            kit.reroute(affected, iters=4)
            cost = kit.total_cost()
            kit.restore(snap)
            world.unplace(pi)
            if best is None or cost < best[0]:
                best = (cost, cx, cy, ri)
            if t_part.left() < 0 and best is not None:
                break
        _, cx, cy, ri = best
        world.place(pi, cx, cy, ri)
        kit.reroute(nets | set(kit.conflicted_nets()), iters=4)
        if i % 5 == 0:
            log(f"  grow {i + 1}/{len(order)} {world.parts[pi].ref} cost={best[0]:.1f} {r.stats()}")
    r.pathfinder(log=log, iters=40)
    log(f"grow {r.stats()} hpwl={world.hpwl():.1f}")
    return r


# ---------------------------------------------------------------- idea 11: anneal
def anneal(world, seed=0, budget=300, log=print, start="seq", **kw):
    """Simulated annealing over poses where the cost is re-routed copper. Moves: jump to a
    random legal pose nearby (radius shrinks), rotate in place, or swap two parts."""
    rng = random.Random(seed)
    clock = Clock(budget)
    r = (seq if start == "seq" else grow)(world, seed=seed, budget=budget * 0.25, log=log, **kw)
    kit = Kit(world, r)
    mov = kit.movable()
    cur = kit.total_cost()
    best = (cur, dict(world.pose), kit.snapshot(list(world.net_pins)))
    T0 = kw.get("t0", 1.5)
    nacc = ntry = 0
    diag = math.hypot(world.W, world.H)
    while clock.left() > 0 and mov:
        f = clock.frac()
        T = T0 * 0.01 ** f
        rad = max(3, int(diag * 0.3 * 0.03 ** f))
        pi = rng.choice(mov)
        old = world.pose[pi]
        moves = [(pi, old)]
        world.unplace(pi)
        kind = rng.random()
        newpose = None
        if kind < 0.15 and len(mov) > 1:  # swap
            pj = rng.choice([q for q in mov if q != pi])
            oj = world.pose[pj]
            world.unplace(pj)
            Li = kit.legal_map(pi, old[2])
            if Li[oj[1], oj[0]]:
                world.place(pi, oj[0], oj[1], old[2])
                Lj = kit.legal_map(pj, oj[2])
                if Lj[old[1], old[0]]:
                    world.place(pj, old[0], old[1], oj[2])
                    moves.append((pj, oj))
                    newpose = True
                else:
                    world.unplace(pi)
            if not newpose:
                world.place(pj, *oj)
        elif kind < 0.4:  # jump to one of the part's best HPWL spots
            c = kit.candidates(pi, k=5)
            if c:
                _, cx, cy, ri = c[rng.randrange(len(c))]
                world.place(pi, cx, cy, ri)
                newpose = True
        else:
            rots = [old[2]] if kind < 0.85 else [q for q in range(4) if q != old[2]]
            ri = rng.choice(rots)
            L = kit.legal_map(pi, ri)
            y0, y1 = max(0, old[1] - rad), min(world.H, old[1] + rad + 1)
            x0, x1 = max(0, old[0] - rad), min(world.W, old[0] + rad + 1)
            sub = np.argwhere(L[y0:y1, x0:x1])
            if len(sub):
                yy, xx = sub[rng.randrange(len(sub))]
                world.place(pi, x0 + int(xx), y0 + int(yy), ri)
                newpose = True
        if not newpose:
            world.place(pi, *old)
            continue
        ntry += 1
        moved = [m[0] for m in moves]
        affected = kit.part_nets(moved) | set(kit.conflicted_nets())
        snap = kit.snapshot(affected)
        before = sum(kit.net_cost(n) for n in affected)
        # nets that were already broken count at their old cost
        kit.reroute(affected, iters=4)
        after = sum(kit.net_cost(n) for n in kit.part_nets(moved) | affected)
        delta = after - before
        if delta <= 0 or rng.random() < math.exp(-delta / T):
            cur += delta
            nacc += 1
            if cur < best[0] - 1e-6:
                best = (cur, dict(world.pose), kit.snapshot(list(world.net_pins)))
        else:
            kit.restore(snap)
            for q, _ in moves:
                world.unplace(q)
            for q, p in moves:
                world.place(q, *p)
        world.hist *= 0.98
        if ntry % 50 == 0:
            log(f"  anneal t={clock.frac():.2f} T={T:.2f} cost={cur:.1f} best={best[0]:.1f} "
                f"acc={nacc}/{ntry} {r.stats()}")
    # restore best
    for q in list(world.pose):
        if q in mov:
            world.unplace(q)
    r.rip_all()
    for q, p in best[1].items():
        if q in mov:
            world.place(q, *p)
    kit.restore(best[2])
    r.legalize(list(world.net_pins))
    if any(r.unrouted.values()):
        r.pathfinder(log=log, iters=20)
    log(f"anneal {r.stats()} hpwl={world.hpwl():.1f} tries={ntry} acc={nacc}")
    return r


# ---------------------------------------------------------------- ideas 2+3+26: tension
def pin_tensions(world, kit, pi):
    """Unit vectors along which each routed pin of part pi is pulled: from the pad centre
    towards the track ~1 mm away along its route (envelope theorem: d len / d pin)."""
    r = kit.r
    out = []
    rr = world.raster(pi)
    cx, cy, ri = world.pose[pi]
    look = max(3, int(1.0 / world.g))
    for k, ent in enumerate(rr["pads"]):
        n = ent["net"]
        if n not in r.routes:
            continue
        cells = {(int(x + cx), int(y + cy)) for x, y in ent["cu"]}
        px, py = cx + ent["center"][0] / world.g, cy + ent["center"][1] / world.g
        vec = np.zeros(2)
        for p in r.routes[n]:
            for end, step in ((0, 1), (len(p) - 1, -1)):
                if (int(p[end, 2]), int(p[end, 1])) in cells:
                    j = end
                    # walk out of the pad, then `look` cells further
                    while 0 <= j + step < len(p) and (int(p[j, 2]), int(p[j, 1])) in cells:
                        j += step
                    j = min(max(j + step * look, 0), len(p) - 1)
                    d = np.array([p[j, 2] - px, p[j, 1] - py], float)
                    nd = np.linalg.norm(d)
                    if nd > 0:
                        vec += d / nd
        if np.any(vec):
            out.append((k, ent["center"], vec))
    return out


def tension(world, seed=0, budget=300, log=print, start="seq", **kw):
    """Iterate: route; move each part along the sum of its pin tensions plus the downhill
    direction of the congestion price field under its courtyard; pick the orientation whose
    pins best face their tensions; re-route the nets touched. Keep the best board."""
    rng = random.Random(seed)
    clock = Clock(budget)
    r = (seq if start == "seq" else grow)(world, seed=seed, budget=budget * 0.25, log=log, **kw)
    kit = Kit(world, r)
    mov = kit.movable()
    cur = kit.total_cost()
    best = (cur, dict(world.pose), kit.snapshot(list(world.net_pins)))
    step_mm = kw.get("step_mm", 2.0)
    it = 0
    while clock.left() > 0:
        it += 1
        price = world.hist.sum(0)
        gy, gx = np.gradient(price)
        rng.shuffle(mov)
        moved = 0
        for pi in mov:
            if clock.left() < 0:
                break
            ts = pin_tensions(world, kit, pi)
            F = sum((t[2] for t in ts), np.zeros(2))
            cx, cy, ri = world.pose[pi]
            rr = world.raster(pi)
            c = rr["court"]
            xs = np.clip(c[:, 0] + cx, 0, world.W - 1)
            ys = np.clip(c[:, 1] + cy, 0, world.H - 1)
            G = -np.array([gx[ys, xs].sum(), gy[ys, xs].sum()])
            F = F + kw.get("price_w", 0.2) * G
            # orientation: maximize sum t . (R p) over pins (pins face their pulls)
            score = {}
            for q in range(4):
                pr = world.part_raster(world.parts[pi], q)["pads"]
                score[q] = sum(float(np.dot(t[2], pr[t[0]]["center"])) for t in ts)
            nri = max(score, key=score.get) if ts else ri
            if np.linalg.norm(F) < 1e-6 and nri == ri:
                continue
            fn = F / (np.linalg.norm(F) + 1e-9)
            s = step_mm * (1 - 0.8 * clock.frac()) / world.g
            tx, ty = cx + fn[0] * s, cy + fn[1] * s
            old = (cx, cy, ri)
            world.unplace(pi)
            L = kit.legal_map(pi, nri)
            if not L.any():
                world.place(pi, *old)
                continue
            yy, xx = np.nonzero(L)
            j = int(np.argmin((xx - tx) ** 2 + (yy - ty) ** 2))
            newp = (int(xx[j]), int(yy[j]), nri)
            if newp == old:
                world.place(pi, *old)
                continue
            world.place(pi, *newp)
            affected = kit.part_nets([pi]) | set(kit.conflicted_nets())
            snap = kit.snapshot(affected)
            before = sum(kit.net_cost(n) for n in affected)
            kit.reroute(affected, iters=4)
            after = sum(kit.net_cost(n) for n in affected)
            if after <= before + kw.get("slack_mm", 1.0):
                cur += after - before
                moved += 1
            else:
                kit.restore(snap)
                world.unplace(pi)
                world.place(pi, *old)
        if cur < best[0] - 1e-6:
            best = (cur, dict(world.pose), kit.snapshot(list(world.net_pins)))
        log(f"  tension it={it} moved={moved} cost={cur:.1f} best={best[0]:.1f} {r.stats()}")
        if moved == 0:
            step_mm *= 0.6
            if step_mm < world.g * 2:
                break
    for q in list(world.pose):
        if q in mov:
            world.unplace(q)
    r.rip_all()
    for q, p in best[1].items():
        if q in mov:
            world.place(q, *p)
    kit.restore(best[2])
    r.legalize(list(world.net_pins))
    if any(r.unrouted.values()):
        r.pathfinder(log=log, iters=20)
    log(f"tension {r.stats()} hpwl={world.hpwl():.1f}")
    return r


# ---------------------------------------------------------------- SimPLR-style bloat
def bloat(world, seed=0, budget=300, log=print, **kw):
    """Route; parts near failed or detoured nets get an inflated keep-out; re-place by HPWL
    descent with the inflation; re-route; keep the best."""
    rng = random.Random(seed)
    clock = Clock(budget)
    _place_fixed(world)
    r = _router(world, kw)
    kit = Kit(world, r)
    place_mechanical(world, kit, log)
    order = growth_order(world, kit, rng)
    greedy_place(world, kit, order, log)
    descent(world, kit, log, clock=clock)
    r.pathfinder(iters=30, log=None)
    cur = kit.total_cost()
    best = (cur, dict(world.pose), kit.snapshot(list(world.net_pins)))
    mov = kit.movable()
    infl = {pi: 0.0 for pi in mov}
    rnd = 0
    while clock.left() > budget * 0.15:
        rnd += 1
        # per-net badness: unrouted or detour ratio vs HPWL
        bad = {}
        for n in world.net_pins:
            hp = world.hpwl([n]) + 1e-6
            L = kit.net_cost(n, via_mm=2.0, unrouted_mm=0.0)
            bad[n] = (3.0 if r.unrouted.get(n) else 0.0) + max(0.0, L / hp - 1.3)
        for pi in mov:
            b = sum(bad.get(n, 0) for n in kit.part_nets([pi]))
            infl[pi] = min(3.0, 0.7 * infl[pi] + 0.3 * b)
        # re-place everything with inflated courtyards (inflation stamps on other parts)
        r.rip_all()
        for pi in mov:
            world.unplace(pi)
        for pi in mov:
            p = world.parts[pi]
            if not hasattr(p, "_court0"):
                p._court0 = [c.copy() for c in p.court]
            m = infl[pi] * 0.5
            p.court = [_grow_poly(c, m) for c in p._court0] if m > world.g else [c.copy() for c in p._court0]
            p.cache = {}
        greedy_place(world, kit, growth_order(world, kit, rng), log=lambda s: None)
        descent(world, kit, log=lambda s: None, rounds=3, clock=clock)
        poses = dict(world.pose)
        for pi in mov:
            if pi in world.pose:
                world.unplace(pi)
        for pi in mov:
            p = world.parts[pi]
            p.court = [c.copy() for c in p._court0]
            p.cache = {}
        for pi in mov:
            if pi in poses:
                world.place(pi, *poses[pi])
        r.pathfinder(iters=30, log=None)
        cur = kit.total_cost()
        log(f"  bloat round {rnd} cost={cur:.1f} best={best[0]:.1f} {r.stats()} "
            f"mean_infl={np.mean(list(infl.values())):.2f}")
        if cur < best[0]:
            best = (cur, dict(world.pose), kit.snapshot(list(world.net_pins)))
    for q in list(world.pose):
        if q in mov:
            world.unplace(q)
    r.rip_all()
    for q, p in best[1].items():
        if q in mov:
            world.place(q, *p)
    kit.restore(best[2])
    r.legalize(list(world.net_pins))
    log(f"bloat {r.stats()} hpwl={world.hpwl():.1f}")
    return r


def _grow_poly(poly, m):
    """Offset a courtyard polygon outward by m mm (mitred corners)."""
    from shapely.geometry import Polygon
    g = Polygon(poly).buffer(0).buffer(m, join_style=2)
    if g.geom_type != "Polygon":
        g = g.convex_hull
    return np.array(g.exterior.coords)[:-1]


# ---------------------------------------------------------------- idea 1: one market
def _wire_map(world, r):
    m = np.zeros((world.H, world.W))
    for n, ps in r.routes.items():
        for p in ps:
            m[p[:, 1], p[:, 2]] += 1
    return np.minimum(m, 1.0)


def negotiate(world, seed=0, budget=300, log=print, **kw):
    """PathFinder for parts and wires together. Parts start where HPWL wants them,
    overlapping freely. Each round: wires re-route under present/history prices; each part
    best-responds to HPWL + priced courtyard overlap + priced wire cells under its pads
    + courtyard history. Prices rise until parts are legal; then wires finish negotiating.
    The best legal, fully evaluated state is kept."""
    rng = random.Random(seed)
    clock = Clock(budget)
    _place_fixed(world)
    r = _router(world, kw)
    kit = Kit(world, r)
    place_mechanical(world, kit, log)
    mov = kit.movable()
    order = growth_order(world, kit, rng)
    bias = center_bias(kit, 0.05)
    # soft start: every part at its HPWL-best spot ignoring other parts
    for pi in order:
        best = None
        for ri in range(4):
            c = kit.hpwl_map(pi, ri) + bias(pi, ri)
            inside = _inside_map(world, kit, pi, ri)
            c = np.where(inside, c, np.inf)
            j = int(np.argmin(c))
            if np.isfinite(c.flat[j]) and (best is None or c.flat[j] < best[0]):
                best = (c.flat[j], j % world.W, j // world.W, ri)
        world.place(pi, best[1], best[2], best[3])
    hist_c = np.zeros((2, world.H, world.W))
    p_ov = kw.get("p_ov0", 0.02)
    p_w = kw.get("p_w0", 0.05)
    best_state = None
    rnd = 0
    cell_area = world.g * world.g
    while clock.left() > 0:
        rnd += 1
        r.pres = min(50.0, 0.3 * 1.4 ** rnd)
        for n in world.net_pins:
            r.rip(n)
            r.route_net(n)
        bad_w = [n for n in world.net_pins if r.net_conflicts(n)]
        for n in bad_w:
            from router import add_hist
            for p in r.routes[n]:
                add_hist(p, n, world.DT, world.occT, world.hist, r.hist_inc)
        wires = _wire_map(world, r)
        rng.shuffle(mov)
        for pi in mov:
            cur = world.pose[pi]
            world.unplace(pi)
            best = None
            for ri in range(4):
                rr = world.part_raster(world.parts[pi], ri)
                c = kit.hpwl_map(pi, ri) + bias(pi, ri) * 0.1
                ov = kit.overlap_map(pi, ri)
                c = c + p_ov * ov
                for s in world.parts[pi].sides:
                    c = c + 0.5 * corr_offs(hist_c[s], rr["court"])
                halo = np.unique(np.concatenate([e["hT"] for e in rr["pads"]]), axis=0) if rr["pads"] else np.zeros((0, 2), np.int32)
                c = c + p_w * corr_offs(wires, halo)
                inside = _inside_map(world, kit, pi, ri)
                c = np.where(inside, c, np.inf)
                j = int(np.argmin(c))
                if best is None or c.flat[j] < best[0]:
                    best = (c.flat[j], j % world.W, j // world.W, ri)
            world.place(pi, best[1], best[2], best[3])
        overl = 0
        for s in (0, 1):
            over = world.court[s] > 1
            hist_c[s] += over
            overl += int(over.sum())
        p_ov *= 1.5
        p_w = p_w * 1.3 if bad_w else max(kw.get("p_w0", 0.05) * 0.2, p_w * 0.6)
        st = r.stats()
        legal = overl == 0
        log(f"  negotiate rnd={rnd} overlap_mm2={overl * cell_area:.2f} wire_conflicts={len(bad_w)} "
            f"p_ov={p_ov:.3f} p_w={p_w:.3f} {st} hpwl={world.hpwl():.1f}")
        if legal:
            r.pathfinder(iters=25, log=None)
            cost = kit.total_cost()
            if best_state is None or cost < best_state[0]:
                best_state = (cost, dict(world.pose), kit.snapshot(list(world.net_pins)))
            log(f"  legal state cost={cost:.1f} best={best_state[0]:.1f} {r.stats()}")
            if not any(r.unrouted.values()) and rnd > 3:
                p_ov *= 0.5  # loosen and keep exploring around the legal state
    if best_state is None:
        log("  no legal state reached; legalizing greedily")
        for pi in mov:
            if world.part_violation(pi) != (0, 0):
                cur = world.pose[pi]
                world.unplace(pi)
                c = kit.candidates(pi, k=1, cost_extra=lambda q, ri: kit.dist_map(*world.xy(cur[0], cur[1])))
                if c:
                    world.place(pi, c[0][1], c[0][2], c[0][3])
        r.pathfinder(iters=30, log=None)
        return r
    for q in list(world.pose):
        if q in mov:
            world.unplace(q)
    r.rip_all()
    for q, p in best_state[1].items():
        if q in mov:
            world.place(q, *p)
    kit.restore(best_state[2])
    r.legalize(list(world.net_pins))
    log(f"negotiate {r.stats()} hpwl={world.hpwl():.1f}")
    return r


def corr_offs(arr, offs):
    from placekit import corr
    return corr(arr, offs, pad_value=0.0)


def _inside_map(world, kit, pi, ri):
    """Origins where the part lies inside the board (ignoring other parts)."""
    from placekit import corr
    rr = world.part_raster(world.parts[pi], ri)
    bad = corr(~world.ok_court, rr["court"])
    if len(rr["cu"]):
        bad += corr(~world.ok_cu, rr["cu"])
    return bad < 0.5


# ---------------------------------------------------------------- control: spacing only
def _inflate(world, pis, margin_of):
    """Grow the courtyards of parts `pis` (bounding-box growth by margin_of[pi] mm)."""
    for pi in pis:
        p = world.parts[pi]
        if not hasattr(p, "_court0"):
            p._court0 = [c.copy() for c in p.court]
        m = margin_of.get(pi, 0.0)
        p.court = [_grow_poly(c, m) for c in p._court0] if m > 0 else [c.copy() for c in p._court0]
        p.cache = {}


def _deflate(world, pis):
    for pi in pis:
        p = world.parts[pi]
        if hasattr(p, "_court0"):
            p.court = [c.copy() for c in p._court0]
            p.cache = {}


def seq_margin(world, seed=0, budget=300, log=print, margin_mm=0.6, density=True, **kw):
    """Control for 'does routing in the loop matter?': place-then-route with every part's
    keep-out grown by a margin set a priori from its pin count (no routing feedback)."""
    rng = random.Random(seed)
    clock = Clock(budget)
    _place_fixed(world)
    r = _router(world, kw)
    kit = Kit(world, r)
    place_mechanical(world, kit, log)
    mov = [pi for pi in kit.movable()]
    npins = {pi: sum(1 for e in world.part_raster(world.parts[pi], 0)["pads"] if e["net"] in world.net_pins)
             for pi in mov}
    mean = np.mean(list(npins.values()) or [1]) or 1
    # scale by how much free board area there is (dense boards get thin margins)
    board_area = float(world.ok_court.sum()) * world.g ** 2
    used = sum(world.parts[pi].area for pi in range(len(world.parts)))
    slack = max(0.0, 1.0 - used / max(board_area, 1e-9))
    margin_mm *= min(1.0, slack / 0.5)
    log(f"  seq_margin slack={slack:.2f} margin={margin_mm:.2f} mm")
    margins = {pi: margin_mm * (math.sqrt(npins[pi] / mean) if density else 1.0) for pi in mov}
    _inflate(world, mov, margins)
    for pi in growth_order(world, kit, rng):
        for shrink in (1.0, 0.5, 0.0, -1, -1, -1, -1, -1):  # deflate the part, then everyone
            if shrink < 0:
                for q in [q for q in mov if q in world.pose]:
                    pose = world.pose[q]
                    world.unplace(q)
                    margins[q] *= 0.5
                    _inflate(world, [q], margins)
                    world.place(q, *pose)
                shrink = 0.0
            _inflate(world, [pi], {pi: margins[pi] * shrink})
            c = kit.candidates(pi, k=1, cost_extra=center_bias(kit))
            if c:
                world.place(pi, c[0][1], c[0][2], c[0][3])
                break
        else:
            log(f"  no legal spot for {world.parts[pi].ref}")
    descent(world, kit, log, clock=clock)
    poses = {pi: world.pose[pi] for pi in mov if pi in world.pose}
    for pi in poses:
        world.unplace(pi)
    _deflate(world, mov)
    for pi, p in poses.items():
        world.place(pi, *p)
    r.pathfinder(log=log, iters=40)
    log(f"seq_margin {r.stats()} hpwl={world.hpwl():.1f}")
    return r


# ---------------------------------------------------------------- ideas 12+13: blocker LNS
def blockers(world, kit, net):
    """Parts whose footprint lies under the cells where `net`'s cheapest soft route has to
    cross foreign copper (A* blocker attribution)."""
    r = kit.r
    r.rip(net)
    r.route_net(net, hard=False, pres=5.0)
    mask = np.zeros((world.H, world.W), bool)
    for p in r.routes.get(net, []):
        for l, y, x in p:
            if world.DT[l, y, x] - (1 if world.occT[net, l, y, x] > 0 else 0) > 0:
                mask[y, x] = True
    r.rip(net)
    out = {}
    for pi in kit.movable():
        if pi not in world.pose:
            continue
        rr = world.raster(pi)
        cx, cy, _ = world.pose[pi]
        c = rr["court"]
        xs = np.clip(c[:, 0] + cx, 0, world.W - 1)
        ys = np.clip(c[:, 1] + cy, 0, world.H - 1)
        hit = int(mask[ys, xs].sum())
        if hit:
            out[pi] = hit
    return out


def repair(world, seed=0, budget=300, log=print, start="seq", window=4, **kw):
    """Start from a placement, then repeatedly: pick an unrouted (or most detoured) net,
    find which parts block its cheapest route, rip up those parts plus the net's own parts,
    re-place them one by one with candidates scored by real routing (grow), keep if the
    board got better."""
    rng = random.Random(seed)
    clock = Clock(budget)
    starter = {"seq": seq, "grow": grow, "seq_margin": seq_margin}[start]
    r = starter(world, seed=seed, budget=budget * 0.25, log=log, **kw)
    kit = Kit(world, r)
    mov = kit.movable()
    cur = kit.total_cost()
    tries = acc = 0
    tabu = {}
    while clock.left() > 0 and mov:
        unr = [n for n in world.net_pins if r.unrouted.get(n)]
        if unr:
            net = rng.choice(unr)
        else:
            # most detoured net relative to its HPWL
            ratios = {n: kit.net_cost(n, unrouted_mm=0) / (world.hpwl([n]) + 1.0) for n in world.net_pins}
            net = max(ratios, key=lambda n: ratios[n] * rng.uniform(0.7, 1.3))
        snap_all = kit.snapshot(list(world.net_pins))
        poses0 = dict(world.pose)
        bl = blockers(world, kit, net)
        own = [pi for pi, k in world.net_pins[net] if pi in mov]
        cand = sorted(bl, key=lambda q: -bl[q])[:window] + own
        cand = [q for q in dict.fromkeys(cand) if tabu.get(q, -1) < tries]
        if not cand:
            cand = [rng.choice(mov)]
        cand = cand[: window + 2]
        tries += 1
        for q in cand:
            world.unplace(q)
        # reroute what is left so the window sees the real congestion
        kit.reroute([n for n in world.net_pins], iters=3)
        rng.shuffle(cand)
        ok = True
        for q in cand:
            cs = kit.candidates(q, k=kw.get("k", 5))
            if not cs:
                ok = False
                break
            best = None
            for _, cx, cy, ri in cs:
                world.place(q, cx, cy, ri)
                aff = kit.part_nets([q]) | set(kit.conflicted_nets())
                sn = kit.snapshot(aff)
                kit.reroute(aff, iters=3)
                c = kit.total_cost()
                kit.restore(sn)
                world.unplace(q)
                if best is None or c < best[0]:
                    best = (c, cx, cy, ri)
            world.place(q, *best[1:])
            kit.reroute(kit.part_nets([q]) | set(kit.conflicted_nets()), iters=3)
        if ok:
            r.pathfinder(iters=15, log=None)
            new = kit.total_cost()
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
            for q in cand:
                tabu[q] = tries + 3
        if tries % 5 == 0:
            log(f"  repair tries={tries} acc={acc} cost={cur:.1f} {r.stats()}")
    r.legalize(list(world.net_pins))
    log(f"repair {r.stats()} hpwl={world.hpwl():.1f} tries={tries} acc={acc}")
    return r
