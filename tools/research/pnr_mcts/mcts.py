# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tree search over constructive interleaved place-and-route (joint-pnr ideas 7 and 8).

The engine's `grow` places parts one at a time in growth order and keeps, for each part,
the candidate pose whose nets route cheapest: a greedy path through a tree whose levels
are parts and whose branches are candidate poses. This module searches that tree.

  beam       keep B partial boards; expand each with the next part's top-K poses, score
             children by real routed cost plus a look-ahead (greedy HPWL placement of the
             next L parts), keep the best B
  mcts       UCT with progressive widening, rolling horizon (search, commit one part,
             move the root down); rollouts finish the board with greedy HPWL placement
             and a short PathFinder and return -(routed cost + unrouted penalty)
  grow_wide  the greedy ablation at equal time: grow with a larger K

Switching between tree nodes: a node stores its poses and a shallow copy of the route
dict (path arrays are never mutated by the router, so they can be shared). `switch`
restores a node by diffing: only parts whose pose differs are moved and only nets whose
path list differs (by identity) are ripped and re-stamped. This is much cheaper than
re-playing the decisions (which would re-route every step); see RESULTS.md.
"""
import math
import random
import sys
import time

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")

import numpy as np  # noqa: E402

from methods import _place_fixed, _router, center_bias, growth_order, place_mechanical  # noqa: E402
from placekit import Clock, Kit  # noqa: E402

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from fastcand import candidates as fc  # noqa: E402


# ---------------------------------------------------------------- node state
class State:
    __slots__ = ("poses", "routes", "unrouted")

    def __init__(self, poses, routes, unrouted):
        self.poses = poses
        self.routes = routes
        self.unrouted = unrouted


def capture(world, r, mov):
    return State({pi: world.pose[pi] for pi in mov if pi in world.pose},
                 {n: list(ps) for n, ps in r.routes.items() if ps},
                 {n: u for n, u in r.unrouted.items() if u})


def switch(world, r, mov, st, stats=None):
    """Make the world equal to node state `st` (diff against the current state)."""
    t0 = time.time()
    nets = set(n for n, ps in r.routes.items() if ps) | set(st.routes) | set(r.unrouted) | set(st.unrouted)
    diff = []
    for n in nets:
        cur = r.routes.get(n) or []
        tgt = st.routes.get(n) or []
        if (len(cur) != len(tgt) or any(a is not b for a, b in zip(cur, tgt))
                or r.unrouted.get(n, 0) != st.unrouted.get(n, 0)):
            diff.append(n)
    for n in diff:
        r.rip(n)
    moved = 0
    for pi in mov:
        cur = world.pose.get(pi)
        tgt = st.poses.get(pi)
        if cur != tgt:
            if cur is not None:
                world.unplace(pi)
            if tgt is not None:
                world.place(pi, *tgt)
            moved += 1
    for n in diff:
        ps = st.routes.get(n) or []
        r.routes[n] = list(ps)
        for p in ps:
            r._stamp(n, p, 1)
        if st.unrouted.get(n):
            r.unrouted[n] = st.unrouted[n]
    if stats is not None:
        stats["switch_s"] = stats.get("switch_s", 0.0) + time.time() - t0
        stats["switch_n"] = stats.get("switch_n", 0) + 1
        stats["switch_nets"] = stats.get("switch_nets", 0) + len(diff)
        stats["switch_parts"] = stats.get("switch_parts", 0) + moved


# ---------------------------------------------------------------- shared steps
def _setup(world, seed, kw):
    rng = random.Random(seed)
    _place_fixed(world)
    r = _router(world, kw)
    kit = Kit(world, r)
    place_mechanical(world, kit, lambda s: None)
    order = growth_order(world, kit, rng)
    return rng, r, kit, order


def expand(world, kit, pi, pose, iters=4, stats=None):
    """Place pi at pose and re-route the nets it completes or blocks. Returns total cost."""
    t0 = time.time()
    world.place(pi, *pose)
    affected = kit.part_nets([pi]) | set(kit.conflicted_nets())
    kit.reroute(affected, iters=iters)
    c = kit.total_cost()
    if stats is not None:
        stats["expand_s"] = stats.get("expand_s", 0.0) + time.time() - t0
        stats["expand_n"] = stats.get("expand_n", 0) + 1
    return c


def unplaced_penalty(world, kit, pis):
    """Cost of parts that found no legal spot: every connection they own is unrouted."""
    tot = 0
    for pi in pis:
        for n in kit.part_nets([pi]):
            tot += 1
    return tot * kit.unrouted_mm


def lookahead(world, kit, rest, L, bias, alpha=1.3):
    """Greedy HPWL placement of the next L unplaced parts (no routing): alpha * HPWL added
    to their nets, plus a penalty for parts with no legal spot. The world is left as found."""
    qs = rest[:L]
    if not qs:
        return 0.0
    nets = kit.part_nets(qs)
    h0 = world.hpwl(nets)
    placed, fail = [], []
    for q in qs:
        c = fc(kit, q, k=1, cost_extra=bias)
        if not c:
            fail.append(q)
            continue
        world.place(q, *c[0][1:])
        placed.append(q)
    h1 = world.hpwl(nets)
    for q in placed:
        world.unplace(q)
    return alpha * (h1 - h0) + unplaced_penalty(world, kit, fail)


def rollout(world, kit, rest, bias, iters=3, stats=None):
    """Finish the board: greedy HPWL placement of `rest`, then a short PathFinder over the
    nets they touch. Returns (cost, failed parts)."""
    t0 = time.time()
    fail = []
    for q in rest:
        c = fc(kit, q, k=1, cost_extra=bias)
        if not c:
            fail.append(q)
            continue
        world.place(q, *c[0][1:])
    t1 = time.time()
    nets = kit.part_nets([q for q in rest if q not in fail])
    kit.reroute(nets, iters=iters)
    cost = kit.total_cost() + unplaced_penalty(world, kit, fail)
    if stats is not None:
        stats["roll_place_s"] = stats.get("roll_place_s", 0.0) + t1 - t0
        stats["roll_route_s"] = stats.get("roll_route_s", 0.0) + time.time() - t1
        stats["roll_n"] = stats.get("roll_n", 0) + 1
    return cost, fail


def finish(world, r, kit, log, name, iters=40):
    r.pathfinder(log=None, iters=iters)
    log(f"{name} {r.stats()} hpwl={world.hpwl():.1f} cost={kit.total_cost():.1f}")
    return r


# ---------------------------------------------------------------- greedy ablation
def grow_wide(world, seed=0, budget=300, log=print, k=24, **kw):
    """`methods.grow` with a time-aware K: the greedy path, spending the budget on more
    candidates per part instead of on search width (the equal-time ablation)."""
    clock = Clock(budget)
    rng, r, kit, order = _setup(world, seed, kw)
    mov = list(order)
    bias = center_bias(kit)
    stats = {}
    for i, pi in enumerate(order):
        cands = fc(kit, pi, k=k, cost_extra=bias)
        if not cands:
            log(f"  no legal spot for {world.parts[pi].ref}")
            continue
        base = capture(world, r, mov)
        t_part = Clock(max(0.0, clock.left() - 0.12 * budget) / max(1, len(order) - i))
        best = None
        for hp, cx, cy, ri in cands:
            c = expand(world, kit, pi, (cx, cy, ri), stats=stats)
            if best is None or c < best[0]:
                best = (c, capture(world, r, mov))
            switch(world, r, mov, base, stats)
            if t_part.left() < 0:
                break
        switch(world, r, mov, best[1], stats)
    log(f"  grow_wide stats {_fmt(stats)}")
    return finish(world, r, kit, log, "grow_wide")


# ---------------------------------------------------------------- idea 7: beam
def beam(world, seed=0, budget=300, log=print, B=4, k=6, L=2, alpha=1.3, per_parent=None, **kw):
    """Beam search over growth-order decisions. Children are scored by the real routed cost
    of the placed parts plus a look-ahead for the next L parts; the best B survive (at
    most `per_parent` children of one parent, for diversity)."""
    clock = Clock(budget)
    rng, r, kit, order = _setup(world, seed, kw)
    mov = list(order)
    bias = center_bias(kit)
    stats = {}
    per_parent = per_parent or max(1, (B + 1) // 2)
    beam_ = [(0.0, 0.0, capture(world, r, mov))]  # (score, routed cost, state)
    reserve = 0.12 * budget
    for i, pi in enumerate(order):
        step = Clock(max(0.0, clock.left() - reserve) / max(1, len(order) - i))
        children = []
        rest = order[i + 1:]
        for bi, (_, _, st) in enumerate(beam_):
            if bi > 0 and step.left() < 0:
                break
            switch(world, r, mov, st, stats)
            cands = fc(kit, pi, k=k, cost_extra=bias)
            for ci, (hp, cx, cy, ri) in enumerate(cands):
                c = expand(world, kit, pi, (cx, cy, ri), stats=stats)
                la = lookahead(world, kit, rest, L, bias, alpha) if L else 0.0
                children.append((c + la, c, capture(world, r, mov), bi))
                switch(world, r, mov, st, stats)
                if step.left() < 0 and ci >= 0 and (bi > 0 or ci >= 1):
                    break
        if not children:
            log(f"  no legal spot for {world.parts[pi].ref}")
            continue
        children.sort(key=lambda t: t[0])
        nb, per = [], {}
        for ch in children:
            if per.get(ch[3], 0) >= per_parent:
                continue
            per[ch[3]] = per.get(ch[3], 0) + 1
            nb.append(ch[:3])
            if len(nb) >= B:
                break
        beam_ = nb
        if i % 5 == 0 or i == len(order) - 1:
            log(f"  beam {i + 1}/{len(order)} {world.parts[pi].ref} children={len(children)} "
                f"best={beam_[0][0]:.1f} (routed {beam_[0][1]:.1f}) t={clock.frac():.2f}")
    # finish the best few with a full PathFinder and keep the cheapest
    best = None
    for sc, c, st in beam_[: kw.get("finals", 2)]:
        if best is not None and clock.left() < reserve * 0.3:
            break
        switch(world, r, mov, st, stats)
        r.pathfinder(log=None, iters=40)
        tot = kit.total_cost()
        log(f"  final candidate score={sc:.1f} -> cost {tot:.1f} {r.stats()}")
        if best is None or tot < best[0]:
            best = (tot, capture(world, r, mov))
    switch(world, r, mov, best[1], stats)
    log(f"  beam stats {_fmt(stats)}")
    log(f"beam {r.stats()} hpwl={world.hpwl():.1f} cost={kit.total_cost():.1f}")
    return r


# ---------------------------------------------------------------- idea 8: MCTS
class Node:
    __slots__ = ("depth", "pose", "parent", "children", "cands", "state", "cost", "N", "S", "best")

    def __init__(self, depth, pose, parent):
        self.depth = depth
        self.pose = pose
        self.parent = parent
        self.children = []
        self.cands = None
        self.state = None
        self.cost = None
        self.N = 0
        self.S = 0.0
        self.best = math.inf


def mcts(world, seed=0, budget=300, log=print, k=8, c_uct=0.7, pw_c=1.5, pw_alpha=0.5,
         lam=0.5, roll_iters=3, w_prior=1.0, **kw):
    """Rolling-horizon UCT. The tree's levels are parts in growth order, branches their
    candidate poses (prior order = HPWL). Progressive widening: a node with N visits may
    have ceil(pw_c * N^pw_alpha) children. Value of a child: (1-lam) * mean + lam * best
    normalized rollout reward, plus a progressive bias from the child's immediate routed
    cost (grow's greedy signal) that fades with visits. After each time slice the root
    commits to the child with the best value + bias and moves down. The best finished board over all rollouts and
    the committed line are both finished with a full PathFinder; the cheaper is kept."""
    clock = Clock(budget)
    rng, r, kit, order = _setup(world, seed, kw)
    mov = list(order)
    bias = center_bias(kit)
    stats = {}
    nP = len(order)
    root = Node(0, None, None)
    root.state = capture(world, r, mov)
    root.cost = kit.total_cost()
    lo, hi = [math.inf], [-math.inf]  # rollout cost range for normalization
    terminals = []  # (cost, State) of finished rollouts, best few kept
    reserve = 0.15 * budget

    def node_cands(nd):
        if nd.cands is None:
            switch(world, r, mov, nd.state, stats)
            nd.cands = [c[1:] for c in fc(kit, order[nd.depth], k=k, cost_extra=bias)]
        return nd.cands

    def value(ch):
        if ch.N == 0 or not math.isfinite(lo[0]) or hi[0] <= lo[0]:
            return 0.5
        span = hi[0] - lo[0]
        mean = (hi[0] - ch.S / ch.N) / span
        best = (hi[0] - ch.best) / span
        return (1 - lam) * mean + lam * best

    def prior(nd):
        """Progressive bias from grow's own signal: the child's immediate routed cost,
        normalized among its siblings (1 = cheapest), fading as visits accumulate."""
        sib = [c.cost for c in nd.parent.children if c.cost is not None]
        if len(sib) < 2 or max(sib) <= min(sib):
            return 1.0
        return (max(sib) - nd.cost) / (max(sib) - min(sib))

    def keep_terminal(cost, st):
        for i, (c0, s0) in enumerate(terminals):
            if s0.poses == st.poses:
                if cost < c0:
                    terminals[i] = (cost, st)
                    terminals.sort(key=lambda t: t[0])
                return
        terminals.append((cost, st))
        terminals.sort(key=lambda t: t[0])
        del terminals[4:]

    def iterate(rt):
        # selection
        nd = rt
        while nd.depth < nP:
            cs = node_cands(nd)
            allowed = min(len(cs), max(1, math.ceil(pw_c * (nd.N + 1) ** pw_alpha)))
            if len(nd.children) < allowed:
                break
            if not nd.children:
                break
            lnN = math.log(nd.N + 1)
            nd = max(nd.children, key=lambda ch: value(ch) + c_uct * math.sqrt(lnN / (ch.N + 1e-9))
                     + w_prior * prior(ch) / (ch.N + 1) if ch.N else math.inf)
        # expansion
        if nd.depth < nP:
            cs = node_cands(nd)
            if len(nd.children) < len(cs):
                pose = cs[len(nd.children)]
                ch = Node(nd.depth + 1, pose, nd)
                switch(world, r, mov, nd.state, stats)
                ch.cost = expand(world, kit, order[nd.depth], pose, stats=stats)
                ch.state = capture(world, r, mov)
                nd.children.append(ch)
                nd = ch
            elif not cs:  # the part has no legal spot: skip it (penalized in rollouts)
                ch = Node(nd.depth + 1, None, nd)
                ch.state = nd.state
                ch.cost = nd.cost
                nd.children.append(ch)
                nd = ch
        # rollout
        switch(world, r, mov, nd.state, stats)
        hist0 = world.hist.copy()
        rest = [q for q in order[nd.depth:]]
        cost, fail = rollout(world, kit, rest, bias, iters=roll_iters, stats=stats)
        skipped = [q for q in order[:nd.depth] if q not in world.pose]
        cost += unplaced_penalty(world, kit, skipped)
        keep_terminal(cost, capture(world, r, mov))
        world.hist[...] = hist0
        lo[0] = min(lo[0], cost)
        hi[0] = max(hi[0], cost)
        # backup
        while nd is not None:
            nd.N += 1
            nd.S += cost
            nd.best = min(nd.best, cost)
            nd = nd.parent
        return cost

    rt = root
    its = 0
    while rt.depth < nP:
        left_steps = nP - rt.depth
        slice_ = Clock(max(0.0, clock.left() - reserve) / left_steps)
        n0 = its
        while True:
            iterate(rt)
            its += 1
            if slice_.left() < 0 and its - n0 >= 2:
                break
        if not rt.children:
            break
        nxt = max(rt.children, key=lambda ch: value(ch) + w_prior * prior(ch) / (ch.N + 1))
        if rt.depth % 5 == 0 or rt.depth == nP - 1:
            log(f"  mcts depth {rt.depth + 1}/{nP} {world.parts[order[rt.depth]].ref} its={its - n0} "
                f"children={len(rt.children)}/{len(rt.cands or [])} commit N={nxt.N} best={nxt.best:.1f} "
                f"t={clock.frac():.2f}")
        rt.children = [nxt]  # free the rest of the tree
        rt = nxt
    # finals: the committed line, then the best finished rollouts
    finals = [rt.state] + [st for _, st in terminals[: kw.get("finals", 2)]]
    best = None
    for fi, st in enumerate(finals):
        if best is not None and clock.left() < reserve * 0.3:
            break
        switch(world, r, mov, st, stats)
        if fi == 0:  # the committed line may have skipped parts: place them greedily
            missing = [q for q in order if q not in world.pose]
            if missing:
                rollout(world, kit, missing, bias, iters=roll_iters)
        r.pathfinder(log=None, iters=40)
        tot = kit.total_cost() + unplaced_penalty(world, kit, [q for q in order if q not in world.pose])
        log(f"  final {'line' if fi == 0 else 'rollout'} -> cost {tot:.1f} {r.stats()}")
        if best is None or tot < best[0]:
            best = (tot, capture(world, r, mov))
    switch(world, r, mov, best[1], stats)
    log(f"  mcts its={its} stats {_fmt(stats)}")
    log(f"mcts {r.stats()} hpwl={world.hpwl():.1f} cost={kit.total_cost():.1f}")
    return r


def _fmt(stats):
    out = dict(stats)
    for key in ("switch", "expand", "roll_place", "roll_route"):
        s, n = stats.get(key + "_s"), stats.get(key + "_n", stats.get("roll_n"))
        if s is not None and n:
            out[key + "_ms_each"] = round(1000 * s / n, 1)
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in out.items()}
