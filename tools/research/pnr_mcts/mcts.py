# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tree search over constructive interleaved place-and-route (joint-pnr ideas 7 and 8).

The engine's `grow` places parts one at a time in growth order and keeps, for each part,
the candidate pose whose nets route cheapest: a greedy path through a tree whose levels
are parts and whose branches are candidate poses. This module searches that tree.

  beam       keep B partial boards; expand each with the next part's top-K poses, score
             children by real routed cost (+ phys_w * physics) plus a look-ahead (greedy
             HPWL placement of the next L parts), keep the best B
  mcts       UCT with progressive widening, rolling horizon (search, commit one part,
             move the root down); rollouts finish the board with greedy HPWL placement
             and a short PathFinder and return -(routed cost + unrouted penalty + phys)
  grow_wide  the greedy ablation at equal time: grow with a time-filling K (same scoring)

Every method takes phys_w (default 0): mm of routed copper per unit of the kae.physics
place-terms total (physics.Phys). Unplaced parts are parked at the board centre in the
physics poses, so children of one node (same parts placed) are compared fairly.

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
from pathlib import Path

sys.path.insert(0, "/home/user/kicad-auto-everything/tools/research/pnr")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from fastcand import candidates as fc  # noqa: E402
from methods import _place_fixed, _router, center_bias, greedy_place, growth_order, place_mechanical  # noqa: E402
from placekit import Clock, Kit  # noqa: E402


# ---------------------------------------------------------------- physics tracking
class PhysTrack:
    """kae.physics place terms kept in step with the world: placed parts at their poses,
    unplaced movable parts parked at the board centre."""

    def __init__(self, world, order):
        from physics import Phys
        self.w = world
        self.ph = Phys(world, world.data["path"])
        self.ph.sync()
        cx = float(np.mean([o[:, 0].mean() for o in world.outline]))
        cy = float(np.mean([o[:, 1].mean() for o in world.outline]))
        self.park = {pi: (cx, cy, 0.0, "B" if world.parts[pi].side else "F")
                     for pi in order if pi in self.ph.key}
        for pi in order:
            self.moved(pi)

    def moved(self, pi):
        if pi not in self.ph.key:
            return
        if pi in self.w.pose:
            self.ph.commit(pi)
        elif pi in self.park:
            self.ph.poses[self.ph.key[pi]] = self.park[pi]

    def total(self):
        return self.ph.total() if self.ph.active else 0.0


# ---------------------------------------------------------------- search context
class State:
    __slots__ = ("poses", "routes", "unrouted")

    def __init__(self, poses, routes, unrouted):
        self.poses = poses
        self.routes = routes
        self.unrouted = unrouted


class Ctx:
    def __init__(self, world, seed, kw, phys_w=0.0):
        self.w = world
        self.rng = random.Random(seed)
        _place_fixed(world)
        self.r = _router(world, kw)
        self.kit = Kit(world, self.r)
        place_mechanical(world, self.kit, lambda s: None)
        self.order = growth_order(world, self.kit, self.rng)
        self.mov = list(self.order)
        self.bias = center_bias(self.kit)
        self.stats = {}
        self.phys_w = phys_w
        self.pt = PhysTrack(world, self.order) if phys_w > 0 else None
        if self.pt is not None and not self.pt.ph.active:
            self.pt = None  # no physics structure on this board

    def tick(self, key, t0, n=1):
        self.stats[key + "_s"] = self.stats.get(key + "_s", 0.0) + time.process_time() - t0
        self.stats[key + "_n"] = self.stats.get(key + "_n", 0) + n

    def phys(self):
        return self.pt.total() if self.pt is not None else 0.0

    def cost(self):
        """Routed cost (+ unrouted perimeters) + phys_w * physics of the current world."""
        c = self.kit.total_cost()
        if self.pt is not None:
            c += self.phys_w * self.pt.total()
        return c

    def capture(self):
        w, r = self.w, self.r
        return State({pi: w.pose[pi] for pi in self.mov if pi in w.pose},
                     {n: list(ps) for n, ps in r.routes.items() if ps},
                     {n: u for n, u in r.unrouted.items() if u})

    def place(self, pi, pose):
        self.w.place(pi, *pose)
        if self.pt is not None:
            self.pt.moved(pi)

    def resync(self):
        if self.pt is not None:
            for pi in self.mov:
                self.pt.moved(pi)

    def switch(self, st):
        """Make the world equal to node state `st` (diff against the current state)."""
        t0 = time.process_time()
        w, r = self.w, self.r
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
        for pi in self.mov:
            cur = w.pose.get(pi)
            tgt = st.poses.get(pi)
            if cur != tgt:
                if cur is not None:
                    w.unplace(pi)
                if tgt is not None:
                    w.place(pi, *tgt)
                if self.pt is not None:
                    self.pt.moved(pi)
        for n in diff:
            ps = st.routes.get(n) or []
            r.routes[n] = list(ps)
            for p in ps:
                r._stamp(n, p, 1)
            if st.unrouted.get(n):
                r.unrouted[n] = st.unrouted[n]
        self.tick("switch", t0)

    # ------------------------------------------------------------ steps
    def expand(self, pi, pose, iters=4):
        """Place pi at pose and re-route the nets it completes or blocks. Returns cost."""
        t0 = time.process_time()
        self.place(pi, pose)
        affected = self.kit.part_nets([pi]) | set(self.kit.conflicted_nets())
        self.kit.reroute(affected, iters=iters)
        c = self.cost()
        self.tick("expand", t0)
        return c

    def unplaced_penalty(self, pis):
        """Parts with no legal spot: every connection they own is unrouted, plus three more
        (an illegal placement fails the board, so it must outweigh any detour)."""
        return sum(3 + len(self.kit.part_nets([pi])) for pi in pis) * self.kit.unrouted_mm

    def lookahead(self, rest, L, alpha=1.3):
        """Greedy HPWL placement of the next L unplaced parts (no routing): alpha * HPWL
        added to their nets, plus a penalty for parts with no legal spot. The world (and
        the physics poses, never touched) are left as found."""
        qs = rest[:L]
        if not qs:
            return 0.0
        w = self.w
        nets = self.kit.part_nets(qs)
        h0 = w.hpwl(nets)
        placed, fail = [], []
        for q in qs:
            c = fc(self.kit, q, k=1, cost_extra=self.bias)
            if not c:
                fail.append(q)
                continue
            w.place(q, *c[0][1:])
            placed.append(q)
        h1 = w.hpwl(nets)
        for q in placed:
            w.unplace(q)
        return alpha * (h1 - h0) + self.unplaced_penalty(fail)

    def rollout(self, rest, iters=3):
        """Finish the board: greedy HPWL placement of `rest`, then a short PathFinder over
        the nets they touch. Returns the finished board's cost (penalties included)."""
        t0 = time.process_time()
        fail = []
        for q in rest:
            c = fc(self.kit, q, k=1, cost_extra=self.bias)
            if not c:
                fail.append(q)
                continue
            self.place(q, c[0][1:])
        t1 = time.process_time()
        self.kit.reroute(self.kit.part_nets([q for q in rest if q not in fail]), iters=iters)
        cost = self.cost() + self.unplaced_penalty([q for q in self.order if q not in self.w.pose])
        self.stats["roll_place_s"] = self.stats.get("roll_place_s", 0.0) + t1 - t0
        self.tick("roll_route", t1)
        return cost

    def finalize(self, st, log, iters=40):
        """Switch to st, legalize skipped parts (engine ripple legalizer), full PathFinder.
        Returns the final cost (penalties included)."""
        self.switch(st)
        missing = [q for q in self.order if q not in self.w.pose]
        if missing:
            greedy_place(self.w, self.kit, missing, log)
            self.resync()
            log(f"  legalized {len(missing)} skipped parts, still unplaced: "
                f"{[self.w.parts[q].ref for q in self.order if q not in self.w.pose]}")
        self.r.pathfinder(log=None, iters=iters)
        return self.cost() + self.unplaced_penalty([q for q in self.order if q not in self.w.pose])

    def finals(self, states, log, name, reserve, clock):
        best = None
        for fi, st in enumerate(states):
            if best is not None and clock.left() < reserve * 0.3:
                break
            tot = self.finalize(st, log)
            log(f"  final {fi} -> cost {tot:.1f} {self.r.stats()} phys={self.phys():.2f}")
            if best is None or tot < best[0]:
                best = (tot, self.capture())
        self.switch(best[1])
        log(f"  {name} stats {_fmt(self.stats)}")
        log(f"{name} {self.r.stats()} hpwl={self.w.hpwl():.1f} cost={self.cost():.1f} phys={self.phys():.2f}")
        if self.pt is not None:
            self.w.phys = self.pt.ph
        return self.r


# ---------------------------------------------------------------- greedy ablation
def grow_wide(world, seed=0, budget=300, log=print, k=24, phys_w=0.0, **kw):
    """`methods.grow` with a time-filling K: the greedy path, spending the budget on more
    candidates per part instead of on search width (the equal-time ablation)."""
    clock = Clock(budget)
    cx = Ctx(world, seed, kw, phys_w)
    reserve = 0.12 * budget
    for i, pi in enumerate(cx.order):
        cands = fc(cx.kit, pi, k=k, cost_extra=cx.bias)
        if not cands:
            log(f"  no legal spot for {world.parts[pi].ref}")
            continue
        base = cx.capture()
        t_part = Clock(max(0.0, clock.left() - reserve) / max(1, len(cx.order) - i))
        best = None
        for hp, x, y, ri in cands:
            c = cx.expand(pi, (x, y, ri))
            if best is None or c < best[0]:
                best = (c, cx.capture())
            cx.switch(base)
            if t_part.left() < 0:
                break
        cx.switch(best[1])
    return cx.finals([cx.capture()], log, "grow_wide", reserve, clock)


# ---------------------------------------------------------------- idea 7: beam
def beam(world, seed=0, budget=300, log=print, B=4, k=6, L=2, alpha=1.3, per_parent=None,
         phys_w=0.0, finals=2, **kw):
    """Beam search over growth-order decisions. Children are scored by the real routed cost
    of the placed parts (+ phys_w * physics) plus a look-ahead for the next L parts; the
    best B survive (at most `per_parent` children of one parent, for diversity)."""
    clock = Clock(budget)
    cx = Ctx(world, seed, kw, phys_w)
    order = cx.order
    per_parent = per_parent or max(1, (B + 1) // 2)
    beam_ = [(0.0, 0.0, cx.capture())]  # (score, cost, state)
    reserve = 0.12 * budget
    for i, pi in enumerate(order):
        step = Clock(max(0.0, clock.left() - reserve) / max(1, len(order) - i))
        children = []
        rest = order[i + 1:]
        for bi, (_, _, st) in enumerate(beam_):
            if bi > 0 and step.left() < 0:
                break
            cx.switch(st)
            cands = fc(cx.kit, pi, k=k, cost_extra=cx.bias)
            for ci, (hp, x, y, ri) in enumerate(cands):
                c = cx.expand(pi, (x, y, ri))
                la = cx.lookahead(rest, L, alpha) if L else 0.0
                children.append((c + la, c, cx.capture(), bi))
                cx.switch(st)
                if step.left() < 0 and (bi > 0 or ci >= 1):
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
                f"best={beam_[0][0]:.1f} (cost {beam_[0][1]:.1f}) t={clock.frac():.2f}")
    return cx.finals([st for _, _, st in beam_[:finals]], log, "beam", reserve, clock)


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
         lam=0.5, roll_iters=3, w_prior=1.0, phys_w=0.0, finals=2, **kw):
    """Rolling-horizon UCT. The tree's levels are parts in growth order, branches their
    candidate poses (prior order = HPWL). Progressive widening: a node with N visits may
    have ceil(pw_c * N^pw_alpha) children. Value of a child: (1-lam) * mean + lam * best
    normalized rollout reward, plus a progressive bias from the child's immediate routed
    cost (grow's greedy signal) that fades with visits. After each time slice the root
    commits to the child with the best value + bias and moves down. The committed line and
    the best finished rollouts get a full PathFinder; the cheapest is kept."""
    clock = Clock(budget)
    cx = Ctx(world, seed, kw, phys_w)
    order = cx.order
    nP = len(order)
    root = Node(0, None, None)
    root.state = cx.capture()
    root.cost = cx.cost()
    lo, hi = [math.inf], [-math.inf]  # rollout cost range for normalization
    terminals = []  # (cost, State) of finished rollouts, best few kept
    reserve = 0.15 * budget

    def node_cands(nd):
        if nd.cands is None:
            cx.switch(nd.state)
            nd.cands = [c[1:] for c in fc(cx.kit, order[nd.depth], k=k, cost_extra=cx.bias)]
        return nd.cands

    def value(ch):
        if ch.N == 0 or not math.isfinite(lo[0]) or hi[0] <= lo[0]:
            return 0.5
        span = hi[0] - lo[0]
        return (1 - lam) * (hi[0] - ch.S / ch.N) / span + lam * (hi[0] - ch.best) / span

    def prior(nd):
        """Progressive bias from grow's own signal: the child's immediate cost, normalized
        among its siblings (1 = cheapest), fading as visits accumulate."""
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
        nd = rt
        while nd.depth < nP:  # selection
            cs = node_cands(nd)
            allowed = min(len(cs), max(1, math.ceil(pw_c * (nd.N + 1) ** pw_alpha)))
            if len(nd.children) < allowed or not nd.children:
                break
            lnN = math.log(nd.N + 1)
            nd = max(nd.children, key=lambda ch: value(ch) + c_uct * math.sqrt(lnN / ch.N)
                     + w_prior * prior(ch) / (ch.N + 1) if ch.N else math.inf)
        if nd.depth < nP:  # expansion
            cs = node_cands(nd)
            if len(nd.children) < len(cs):
                pose = cs[len(nd.children)]
                ch = Node(nd.depth + 1, pose, nd)
                cx.switch(nd.state)
                ch.cost = cx.expand(order[nd.depth], pose)
                ch.state = cx.capture()
                nd.children.append(ch)
                nd = ch
            elif not cs:  # the part has no legal spot: skip it (penalized in rollouts)
                ch = Node(nd.depth + 1, None, nd)
                ch.state, ch.cost = nd.state, nd.cost
                nd.children.append(ch)
                nd = ch
        cx.switch(nd.state)  # rollout (its PathFinder history does not leak into the tree)
        h = world.hist.copy()
        cost = cx.rollout(order[nd.depth:], iters=roll_iters)
        keep_terminal(cost, cx.capture())
        world.hist[...] = h
        lo[0] = min(lo[0], cost)
        hi[0] = max(hi[0], cost)
        while nd is not None:  # backup
            nd.N += 1
            nd.S += cost
            nd.best = min(nd.best, cost)
            nd = nd.parent

    rt = root
    its = 0
    while rt.depth < nP:
        slice_ = Clock(max(0.0, clock.left() - reserve) / (nP - rt.depth))
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
    cx.stats["iterations"] = its
    return cx.finals([rt.state] + [st for _, st in terminals[:finals]], log, "mcts", reserve, clock)


def _fmt(stats):
    out = dict(stats)
    for key in ("switch", "expand", "roll_route"):
        s, n = stats.get(key + "_s"), stats.get(key + "_n")
        if s is not None and n:
            out[key + "_ms_each"] = round(1000 * s / n, 1)
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in out.items()}
