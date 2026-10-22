# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics-first macros from the brief, each micro-placed for its own self term.

1. `structures(P, brief)` normalizes the brief's structures into segments whose length is
   the structure's geometric proxy cost: for a decap, cap rail pad <-> IC power pin (the
   brief's `pin_caps` pairing when given) and cap ground pad <-> nearest IC ground pin; for
   a crystal, crystal pads <-> XIN/XOUT and load caps <-> crystal pads; for a commutation
   cell, consecutive members of the loop (closed); for a connector chain, consecutive
   members from the connector pin inward. The real place terms (Terms.breakdown) replace
   the proxy in the annealer; the micro-placement keeps the proxy because CP-SAT needs a
   linear objective (pin-to-pin L1 path length).
2. `build_macros(P, structs, ...)` unions structures that share parts (IC + decaps +
   crystal + its caps becomes one macro around the IC), anchors each macro on its largest
   (or locked) member, and micro-places the members around the anchor with CP-SAT: 4
   rotations, NoOverlap2D per side, minimizing the weighted segment L1 length plus a little
   compactness. The best K distinct layouts (no-good cuts on the rotation assignment) are
   kept as alternatives for the floorplan and the annealer's re-layout move.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

KIND_WEIGHT = {"commutation_cell": 3.0, "decap": 2.0, "crystal": 2.0, "oscillator": 1.5, "connector_chain": 1.0}
MAX_MACRO = 24


@dataclass
class Struct:
    kind: str
    members: set
    segs: list            # [((part, [pad idx]), (part, [pad idx]), weight)]
    src: dict = field(default_factory=dict)


@dataclass
class Layout:
    offsets: dict         # part -> (dx, dy, k): grid offset from the anchor origin, rotation index
    size: tuple           # (w, h) mm of the members' own rectangles
    cx: float             # bbox centre relative to the anchor origin, mm
    cy: float
    cost: float           # proxy length, mm


@dataclass
class Macro:
    members: list
    anchor: int
    layouts: list
    structs: list
    anchored: bool = False   # the anchor is a locked part


# ----------------------------------------------------------------------------- brief
def _ids(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        out = []
        for x in v:
            if isinstance(x, (list, tuple)) and x:
                out.append(x[0])
            elif isinstance(x, dict):
                out.append(x.get("uuid") or x.get("part"))
            else:
                out.append(x)
        return [x for x in out if x]
    return [v]


def _nums(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


def structures(P, brief):
    """The brief's placement-relevant structures as Structs over part indices.

    Policies: a decoupling cap claimed by several ICs goes to the structure with the highest
    ownership probability (`caps_p`), so two ICs never merge through a shared cap; `pin_caps`
    pairs caps with power pins, other caps get a weaker pull to the rail pins; connector
    chains count only when protected, with the connector and its protection parts (the IC
    at the far end of the chain stays out)."""
    by_uuid = {p.uuid: p.i for p in P.parts}

    def pads(i, nums):
        fp = P.parts[i].fp
        return [k for k, pd in enumerate(fp.pads) if not nums or pd.number in nums]

    def pads_on(i, net):
        return [k for k, pd in enumerate(P.parts[i].fp.pads) if pd.net == net]

    structs_in = list((brief or {}).get("structures", []))
    # owner of each shared decoupling cap
    owner = {}
    for j, s in enumerate(structs_in):
        if s.get("kind") != "decap":
            continue
        cp = s.get("caps_p") or {}
        for c in _ids(s.get("caps")):
            pr = float(cp.get(c, 1.0 / max(1, int(s.get("shared_by") or 1))))
            if c not in owner or pr > owner[c][0]:
                owner[c] = (pr, j)
    out = []
    for j, s in enumerate(structs_in):
        kind = s.get("kind")
        w = KIND_WEIGHT.get(kind)
        if w is None:
            continue
        segs = []
        if kind == "decap":
            ic = by_uuid.get(s.get("ic"))
            if ic is None:
                continue
            rail, gnd = s.get("rail"), s.get("ground")
            pins = _nums(s.get("power_pins"))
            gpins = _nums(s.get("ground_pins"))
            mine = [c for c in _ids(s.get("caps")) if c in by_uuid and owner.get(c, (0, j))[1] == j]
            paired = {}
            pc = s.get("pin_caps")
            if isinstance(pc, dict):
                for pin, caps in pc.items():
                    for c in _ids(caps):
                        if c in mine:
                            paired[c] = [str(pin)]
            hf = set(_ids(s.get("hf_caps")))
            members = {ic}
            for c in mine:
                ci = by_uuid[c]
                members.add(ci)
                ca = pads_on(ci, rail) or [0]
                ia = pads(ic, paired[c]) if c in paired else pads(ic, pins) if pins else pads_on(ic, rail)
                wc = w if (c in paired or c in hf) else 0.3 * w
                if ia:
                    segs.append(((ci, ca), (ic, ia), wc))
                cg = pads_on(ci, gnd)
                ig = pads(ic, gpins) if gpins else pads_on(ic, gnd)
                if cg and ig:
                    segs.append(((ci, cg), (ic, ig), 0.5 * wc))
        elif kind in ("crystal", "oscillator"):
            xt = by_uuid.get(s.get("crystal") or s.get("part") or s.get("oscillator"))
            if xt is None:
                continue
            ic = by_uuid.get(s.get("ic"))
            members = {xt}
            if ic is not None:
                members.add(ic)
                for nm in ("xin", "xout"):
                    if s.get(nm) is None:
                        continue
                    ip = pads(ic, _nums(s.get(nm)))
                    if not ip:
                        continue
                    net = P.parts[ic].fp.pads[ip[0]].net
                    xp = pads_on(xt, net) if net else []
                    if xp:
                        segs.append(((xt, xp), (ic, ip), w))
            xall = [k for k, pd in enumerate(P.parts[xt].fp.pads) if pd.net]
            for c in _ids(s.get("load_caps")):
                if c in by_uuid:
                    ci = by_uuid[c]
                    nets_c = {pd.net for pd in P.parts[ci].fp.pads}
                    xp = [k for k in xall if P.parts[xt].fp.pads[k].net in nets_c] or xall
                    cp = [k for k, pd in enumerate(P.parts[ci].fp.pads) if pd.net in {P.parts[xt].fp.pads[q].net for q in xp}] or [0]
                    members.add(ci)
                    segs.append(((ci, cp), (xt, xp), 0.5 * w))
        elif kind == "commutation_cell":
            loop = []
            for m in s.get("loop", []):
                if isinstance(m, (list, tuple)) and m and m[0] in by_uuid:
                    i = by_uuid[m[0]]
                    loop.append((i, pads(i, _nums(m[1] if len(m) > 1 else None))))
            if len({i for i, _ in loop}) < 2:
                continue
            members = {i for i, _ in loop}
            for a_ in range(len(loop)):
                pa, pb = loop[a_], loop[(a_ + 1) % len(loop)]
                if pa[0] != pb[0]:
                    segs.append((pa, pb, w))
        elif kind == "connector_chain":
            prot = set(_ids(s.get("protection")))
            if not prot or s.get("protected") is False:
                continue
            ch = []
            for m in s.get("chain", []):
                if isinstance(m, (list, tuple)) and m and m[0] in by_uuid and (m[0] == s.get("connector") or m[0] in prot):
                    i = by_uuid[m[0]]
                    ch.append((i, pads(i, _nums(m[1] if len(m) > 1 else None))))
            if len({i for i, _ in ch}) < 2:
                continue
            members = {i for i, _ in ch}
            for a_ in range(len(ch) - 1):
                if ch[a_][0] != ch[a_ + 1][0]:
                    segs.append((ch[a_], ch[a_ + 1], w))
        else:
            continue
        members = {i for i in members if not P.parts[i].decor}
        segs = [sg for sg in segs if sg[0][1] and sg[1][1] and sg[0][0] in members and sg[1][0] in members]
        if segs and len(members) >= 2:
            out.append(Struct(kind=kind, members=members, segs=segs, src=s))
    return out


# ----------------------------------------------------------------------------- grouping
def _groups(P, structs):
    """Union structures that share parts, strongest kinds first, keeping each group at most
    MAX_MACRO parts with at most one locked part. Returns [(members, [Struct])]."""
    parent, size, nfixed, nconn = {}, {}, {}, {}
    for s in structs:
        for i in s.members:
            if i not in parent:
                parent[i] = i
                size[i] = 1
                nfixed[i] = 0 if P.parts[i].movable else 1
                nconn[i] = 1 if getattr(P.parts[i], "kind", "") == "connector" else 0

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    order = sorted(range(len(structs)), key=lambda j: -KIND_WEIGHT.get(structs[j].kind, 1.0))
    taken = []
    for j in order:
        roots = {find(i) for i in structs[j].members}
        if (sum(size[r] for r in roots) > MAX_MACRO or sum(nfixed[r] for r in roots) > 1
                or sum(nconn[r] for r in roots) > 1):
            continue
        roots = list(roots)
        r0 = roots[0]
        for r in roots[1:]:
            parent[r] = r0
            size[r0] += size[r]
            nfixed[r0] += nfixed[r]
            nconn[r0] += nconn[r]
        taken.append(j)
    groups = {}
    for j in taken:
        groups.setdefault(find(next(iter(structs[j].members))), []).append(j)
    out = []
    for js in groups.values():
        mem = set()
        for j in js:
            mem |= structs[j].members
        out.append((sorted(mem), [structs[j] for j in js]))
    return out


# ----------------------------------------------------------------------------- micro-placement
def micro_place(P, members, structs, anchor, time_s=2.0, top_k=3, workers=2, seed=0, compact=0.05):
    """CP-SAT layouts of members around the anchor (at grid origin, its rotation fixed).
    Returns [Layout] best first."""
    g = P.g
    m = cp_model.CpModel()
    ka = 0   # a movable anchor sits at rotation 0; a locked one has its own (only) rotation
    sizes = [max(r.g_own[1] - r.g_own[0], r.g_own[3] - r.g_own[2]) for i in members for r in P.parts[i].rots[:1]]
    R = sum(sizes) + 4
    V = {}
    xi = {0: [], 1: []}
    yi = {0: [], 1: []}
    for i in members:
        p = P.parts[i]
        nk = len(p.rots)
        if i == anchor:
            X = m.new_constant(0)
            Y = m.new_constant(0)
            lits = [m.new_constant(1 if k == ka else 0) for k in range(nk)]
        else:
            X = m.new_int_var(-R, R, "")
            Y = m.new_int_var(-R, R, "")
            lits = [m.new_bool_var("") for _ in range(nk)]
            m.add_exactly_one(lits)
        V[i] = (X, Y, lits)
        si = 0 if p.s > 0 else 1
        for k in range(nk):
            r = p.rots[k]
            rects = [(si, r.g_own)] + [(1 - si, o) for o in r.g_opp]
            for side, (a, b, c, d) in rects:
                if b <= a or d <= c:
                    continue
                if i == anchor:
                    if k != ka:
                        continue
                    xi[side].append(m.new_fixed_size_interval_var(a, b - a, ""))
                    yi[side].append(m.new_fixed_size_interval_var(c, d - c, ""))
                else:
                    xi[side].append(m.new_optional_fixed_size_interval_var(X + a, b - a, lits[k], ""))
                    yi[side].append(m.new_optional_fixed_size_interval_var(Y + c, d - c, lits[k], ""))
    for side in (0, 1):
        if xi[side]:
            m.add_no_overlap_2d(xi[side], yi[side])

    def pin_expr(i, pads):
        X, Y, lits = V[i]
        p = P.parts[i]
        cx, cy = [], []
        for k in range(len(p.rots)):
            pts = p.rots[k].pins[pads]
            cx.append(int(round(float(pts[:, 0].mean()) / g)))
            cy.append(int(round(float(pts[:, 1].mean()) / g)))
        if i == anchor:
            return X + cx[ka], Y + cy[ka]
        return X + sum(c * l for c, l in zip(cx, lits)), Y + sum(c * l for c, l in zip(cy, lits))

    obj = []
    for s in structs:
        for (ia, pa), (ib, pb), w in s.segs:
            ax, ay = pin_expr(ia, pa)
            bx, by = pin_expr(ib, pb)
            dx = m.new_int_var(0, 4 * R, "")
            dy = m.new_int_var(0, 4 * R, "")
            m.add_abs_equality(dx, ax - bx)
            m.add_abs_equality(dy, ay - by)
            wi = max(1, int(round(10 * w)))
            obj += [wi * dx, wi * dy]
    # compactness: half-perimeter of the members' origins
    if compact > 0 and len(members) > 1:
        xs = [V[i][0] for i in members]
        ys = [V[i][1] for i in members]
        a = m.new_int_var(-R, R, "")
        b = m.new_int_var(-R, R, "")
        c = m.new_int_var(-R, R, "")
        d = m.new_int_var(-R, R, "")
        m.add_max_equality(a, xs)
        m.add_min_equality(b, xs)
        m.add_max_equality(c, ys)
        m.add_min_equality(d, ys)
        wc = max(1, int(round(10 * compact)))
        obj += [wc * (a - b), wc * (c - d)]
    m.minimize(sum(obj))
    layouts = []
    rot_lits = [l for i in members if i != anchor for l in V[i][2]]
    t_end = time.monotonic() + time_s * top_k
    for _ in range(top_k):
        left = t_end - time.monotonic()
        if left <= 0.05:
            break
        s = cp_model.CpSolver()
        s.parameters.max_time_in_seconds = min(time_s, left)
        s.parameters.num_workers = workers
        s.parameters.random_seed = seed
        st = s.solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        off = {}
        for i in members:
            X, Y, lits = V[i]
            k = next((k for k, l in enumerate(lits) if s.value(l)), 0)
            off[i] = (int(s.value(X)), int(s.value(Y)), k)
        layouts.append(_layout(P, off, s.objective_value / 10.0 * g))
        # next: a different rotation assignment
        chosen = [l for i in members if i != anchor for k, l in enumerate(V[i][2]) if off[i][2] == k]
        if not rot_lits:
            break
        m.add_bool_or([~l for l in chosen])
    return layouts


def _layout(P, off, cost):
    g = P.g
    xs0, xs1, ys0, ys1 = [], [], [], []
    for i, (dx, dy, k) in off.items():
        a, b, c, d = P.parts[i].rots[k].g_own
        xs0.append(dx + a)
        xs1.append(dx + b)
        ys0.append(dy + c)
        ys1.append(dy + d)
    x0, x1, y0, y1 = min(xs0), max(xs1), min(ys0), max(ys1)
    return Layout(offsets=off, size=((x1 - x0) * g, (y1 - y0) * g), cx=(x0 + x1) / 2 * g, cy=(y0 + y1) / 2 * g,
                  cost=cost)


def build_macros(P, structs, time_s=10.0, top_k=3, workers=2, seed=0, log=None):
    """Macros from structures; the micro-placement budget is split across them."""
    groups = _groups(P, structs)
    if not groups:
        return []
    per = max(0.3, time_s / len(groups) / max(1, top_k))
    out = []
    for mem, sts in groups:
        fixed = [i for i in mem if not P.parts[i].movable]
        anchor = fixed[0] if fixed else max(mem, key=lambda i: P.parts[i].area)
        lay = micro_place(P, mem, sts, anchor, time_s=per, top_k=top_k, workers=workers, seed=seed)
        if not lay:
            if log:
                log(f"macro around {P.parts[anchor].ref}: no layout")
            continue
        out.append(Macro(members=mem, anchor=anchor, layouts=lay, structs=sts, anchored=bool(fixed)))
        if log:
            log(f"macro {P.parts[anchor].ref} +{len(mem) - 1} ({','.join(sorted({s.kind for s in sts}))}): "
                f"{len(lay)} layouts, proxy {lay[0].cost:.1f} mm")
    return out


def macro_item(P, mac, X0=0, Y0=0, v0=0):
    """A cpsat.Item for a movable-anchor macro: variants = layouts x 4 rotations."""
    from .cpsat import Item
    variants = []
    for lay in mac.layouts:
        ka = lay.offsets[mac.anchor][2]
        for q in range(4):
            v = {}
            for i, (dx, dy, k) in lay.offsets.items():
                ddx, ddy = dx, dy
                for _ in range(q):
                    ddx, ddy = ddy, -ddx
                v[i] = (ddx, ddy, (k + q) % len(P.parts[i].rots))
            variants.append(v)
        _ = ka
    return Item(members=list(mac.members), variants=variants, X0=X0, Y0=Y0, v0=v0,
                weight=float(len(mac.members)), name=f"M_{P.parts[mac.anchor].ref}")
