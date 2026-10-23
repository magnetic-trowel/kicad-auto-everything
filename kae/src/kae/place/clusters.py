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
   compactness, several distinct layouts (no-good cuts on the rotation assignment).
3. With the place terms: the layouts are ranked by the structures' own cost
   (Terms.breakdown), the best are annealed on the terms themselves (`refine`: the proxy
   proposes, the physics decides), and the best K are kept as alternatives for the
   floorplan and the annealer's re-layout move.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .cpsat import disjoint_union

KIND_WEIGHT = {"commutation_cell": 3.0, "power_path": 2.0, "decap": 2.0, "crystal": 2.0, "oscillator": 1.5,
               "connector_chain": 1.0}
# power pins closer than this act as one pin (kae.physics.build clusters them the same way);
# a cap paired with "the nearest" of several clusters gets a choice among them in CP-SAT
PIN_CLUSTER_MM = 1.6
# weights of a commutation cell's extra members (kae.brief/1), relative to the loop's: a
# snubber carries the switching edge, the others only gate drive or a parallel shunt
CELL_EXTRA = {"snubbers": 1.0, "series_shunt": 0.5, "bootstrap_cap": 0.5, "bootstrap_r": 0.5,
              "charge_pump_caps": 0.5}
MAX_MACRO = 24
# kae.circuit's cap ownership (caps_p) ranks well but is underconfident (p 0.24 right 52% of
# the time, 0.96 right 91%): it weights the micro-placement softly, and only a cap owned with
# p >= BIND_P is bound into its load's macro. Rails with many interchangeable loads (all caps
# at p <= LOW_OWNERSHIP, shared by 3 or more loads; keyboards, LED strings) get no macro: the
# brief's owner is right 0-20% of the time there, and the place terms charge each such cap
# to its nearest load pin instead.
BIND_P = 0.5
LOW_OWNERSHIP = 0.35


@dataclass
class Struct:
    kind: str
    members: set
    segs: list            # [((part, [pad idx]), (part, [pad idx]), weight)]
    src: dict = field(default_factory=dict)
    choices: dict = field(default_factory=dict)   # seg index -> [[pad idx], ...]: the segment
    #                                               ends at the nearest of these pad groups


@dataclass
class Layout:
    offsets: dict         # part -> (dx, dy, k): grid offset from the anchor origin, rotation index
    size: tuple           # (w, h) mm of the members' own rectangles
    cx: float             # bbox centre relative to the anchor origin, mm
    cy: float
    cost: float           # proxy length, mm
    self_cost: float = None   # the structures' own cost under the place terms, when ranked


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

    Policies (kae.brief/1, docs/topics/physics/comprehension.md 1 and 3.3-3.5):
    - Decaps. A cap claimed by several loads goes to the structure with the highest
      ownership probability (`caps_p`), so two loads never merge through a shared cap, and
      joins it only at p >= BIND_P (below it the cap is unowned); segment weights scale
      with p. `pairing` 'pin': `pin_caps` (may be {}) pairs caps with a pin, the spec's other
      owned caps get a weaker pull to the power pins; 'nearest_pin': each cap goes to the
      nearest cluster of `power_pins` (a CP-SAT choice); 'nearest_load' or a `rail_group`:
      no macro, the place terms charge each cap to its nearest load. Briefs without a
      pairing fall back to LOW_OWNERSHIP. A decap's `ic` is whatever the caps serve: an IC,
      a module, an LED, or (entry, converter_input/output, split_supply) a connector,
      diode, fuse or inductor, whose ground may be another rail (V-).
    - Rail groups make no macro (their caps' decaps say nearest_load).
    - Commutation cells: consecutive loop members (closed), plus `series_shunt`,
      `bootstrap_cap`, `bootstrap_r`, `charge_pump_caps` and `snubbers`, each tied to the
      members it shares nets with.
    - Power paths: switches (every stage's parallel elements), `caps_in` and `caps_out`;
      segments follow `loop` between those (a connector or load in the loop stays out), the
      members off the loop tie in by shared nets. Their heat reaches the terms on its own.
    - Connector chains count only when protected, with the connector and its protection
      parts (the part at the far end of the chain stays out; `protection_order` keeps it
      behind the protection)."""
    by_uuid = {p.uuid: p.i for p in P.parts}

    def pads(i, nums):
        fp = P.parts[i].fp
        return [k for k, pd in enumerate(fp.pads) if not nums or pd.number in nums]

    def pads_on(i, net):
        return [k for k, pd in enumerate(P.parts[i].fp.pads) if pd.net == net]

    def clusters_of(i, ks):
        return _pad_clusters(P.parts[i].fp, ks)

    structs_in = list((brief or {}).get("structures", []))

    def low_ownership(s):
        """Caps that serve whichever load they sit next to: no macro."""
        if s.get("pairing") or s.get("rail_group"):
            return s.get("pairing") == "nearest_load" or bool(s.get("rail_group"))
        ps = [float(v) for v in (s.get("caps_p") or {}).values() if v is not None]
        return bool(ps) and max(ps) <= LOW_OWNERSHIP and int(s.get("shared_by") or 1) >= 3
    # owner of each shared decoupling cap
    owner = {}
    for j, s in enumerate(structs_in):
        if s.get("kind") != "decap" or low_ownership(s):
            continue
        cp = s.get("caps_p") or {}
        for c in _ids(s.get("caps")):
            v = cp.get(c)
            pr = float(v) if v is not None else 1.0 / max(1, int(s.get("shared_by") or 1))
            if c not in owner or pr > owner[c][0]:
                owner[c] = (pr, j)
    out = []
    for j, s in enumerate(structs_in):
        kind = s.get("kind")
        w = KIND_WEIGHT.get(kind)
        if w is None:
            continue
        segs = []
        choices = {}

        def seg(a, b, wt, alts=None):
            if alts is not None and len(alts) > 1:
                choices[len(segs)] = alts
            segs.append((a, b, wt))
        if kind == "decap":
            ic = by_uuid.get(s.get("ic"))
            if ic is None or low_ownership(s):
                continue
            rail, gnd = s.get("rail"), s.get("ground")
            pins = _nums(s.get("power_pins"))
            gpins = _nums(s.get("ground_pins"))
            mine = [c for c in _ids(s.get("caps")) if c in by_uuid and c in owner and owner[c][1] == j
                    and owner[c][0] >= BIND_P]
            paired = {}
            pc = s.get("pin_caps")
            if isinstance(pc, dict):
                for pin, caps in pc.items():
                    for c in _ids(caps):
                        if c in mine:
                            paired[c] = [str(pin)]
            hf = set(_ids(s.get("hf_caps")))
            nearest = s.get("pairing") == "nearest_pin"
            members = {ic}
            ig = pads(ic, gpins) if gpins else pads_on(ic, gnd)
            for c in mine:
                ci = by_uuid[c]
                members.add(ci)
                ca = pads_on(ci, rail) or [0]
                ia = pads(ic, paired[c]) if c in paired else pads(ic, pins) if pins else pads_on(ic, rail)
                wc = (w if (c in paired or c in hf or nearest) else 0.3 * w) * owner[c][0]
                if ia:
                    seg((ci, ca), (ic, ia), wc, clusters_of(ic, ia))
                cg = pads_on(ci, gnd)
                if cg and ig:
                    seg((ci, cg), (ic, ig), 0.5 * wc, clusters_of(ic, ig))
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
            extra = []
            for key, f in CELL_EXTRA.items():
                v = s.get(key)
                if key == "snubbers":                         # [[r, c], ...]: both parts
                    v = [x for pair in (v or []) if isinstance(pair, (list, tuple)) for x in pair]
                extra += [(x, f * w) for x in _ids(v)]
            _tie_in(P, by_uuid, members, extra, seg, pads_on, clusters_of, [i for i, _ in loop])
        elif kind == "power_path":
            keep = set(_ids(s.get("switches"))) | set(_ids(s.get("caps_in"))) | set(_ids(s.get("caps_out")))
            for stg in s.get("stages") or []:
                keep |= set(_ids(stg))
            loop = []
            for m in s.get("loop", []):
                if isinstance(m, (list, tuple)) and m and m[0] in by_uuid:
                    i = by_uuid[m[0]]
                    loop.append((m[0], i, pads(i, _nums(m[1] if len(m) > 1 else None))))
            members = {i for u, i, _ in loop if u in keep}
            for a_ in range(len(loop)):
                (ua, ia_, pa), (ub, ib_, pb) = loop[a_], loop[(a_ + 1) % len(loop)]
                if ia_ != ib_ and ua in keep and ub in keep:
                    segs.append(((ia_, pa), (ib_, pb), w))
            if not members:
                continue
            # parallel elements of a stage, and caps off the loop, in brief order
            rest = list(_ids(s.get("switches"))) + [u for stg in s.get("stages") or [] for u in _ids(stg)] + \
                list(_ids(s.get("caps_in"))) + list(_ids(s.get("caps_out")))
            _tie_in(P, by_uuid, members, [(u, 0.5 * w) for u in dict.fromkeys(rest)], seg, pads_on, clusters_of,
                    [i for u, i, _ in loop if u in keep])
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
        ok = [q for q, sg in enumerate(segs) if sg[0][1] and sg[1][1] and sg[0][0] in members and sg[1][0] in members]
        choices = {n: choices[q] for n, q in enumerate(ok) if q in choices}
        segs = [segs[q] for q in ok]
        if segs and len(members) >= 2:
            out.append(Struct(kind=kind, members=members, segs=segs, src=s, choices=choices))
    return out


def _pad_clusters(fp, ks, dmax=PIN_CLUSTER_MM):
    """Single-linkage clusters (library frame) of a footprint's pads `ks`, as pad lists."""
    ks = list(ks)
    lab = list(range(len(ks)))

    def f(a):
        while lab[a] != a:
            lab[a] = lab[lab[a]]
            a = lab[a]
        return a
    pts = [(fp.pads[k].lx, fp.pads[k].ly) for k in ks]
    for a in range(len(ks)):
        for b in range(a + 1, len(ks)):
            if (pts[a][0] - pts[b][0]) ** 2 + (pts[a][1] - pts[b][1]) ** 2 <= dmax * dmax:
                ra, rb = f(a), f(b)
                if ra != rb:
                    lab[rb] = ra
    out = {}
    for a in range(len(ks)):
        out.setdefault(f(a), []).append(ks[a])
    return list(out.values())


def _tie_in(P, by_uuid, members, extra, seg, pads_on, clusters_of, order=()):
    """Add the parts `extra` [(uuid, weight)] not yet in `members`, each tied by one segment
    per net to one other member on that net: the first of `order` (the loop, in current
    order) that has pads there, else an extra added before it (a star around the loop, not
    all pairs: a bank of parallel FETs sharing a drain tab would make O(n^2) segments)."""
    add = []
    for u, wt in extra:
        i = by_uuid.get(u)
        if i is None or P.parts[i].decor or i in members:      # loop members are tied already
            continue
        members.add(i)
        add.append((i, wt))
    seen = []
    prefer = [j for j in dict.fromkeys(order) if j in members]
    done = set()
    for i, wt in add:
        for net in sorted({pd.net for pd in P.parts[i].fp.pads if pd.net}):
            j = next((j for j in prefer + seen + [a for a, _ in add] if j != i and pads_on(j, net)), None)
            if j is None or (min(i, j), max(i, j), net) in done:
                continue
            done.add((min(i, j), max(i, j), net))
            bj = pads_on(j, net)
            seg((i, pads_on(i, net)), (j, bj), wt, clusters_of(j, bj))
        seen.append(i)


def protection_order(P, brief):
    """Order rules of protected connector chains: each protection part (TVS, ESD array, fuse)
    must sit nearer the connector pin than the part it protects does, and nearer the
    connector than to that part. kae.circuit finds only 60% of human boards following this,
    so it is enforced as a rule (a steep term in the annealer), not learnt from them.
    Returns [((conn, pads), (prot, pads), (target, pads))] over part indices."""
    by_uuid = {p.uuid: p.i for p in P.parts}
    out, seen = [], set()
    for s in (brief or {}).get("structures", []):
        if s.get("kind") != "connector_chain" or s.get("protected") is False:
            continue
        prot = set(_ids(s.get("protection")))
        conn = s.get("connector")
        if not prot or conn not in by_uuid:
            continue
        ch = []
        for m in s.get("chain", []):
            if isinstance(m, (list, tuple)) and m and m[0] in by_uuid:
                i = by_uuid[m[0]]
                nums = _nums(m[1] if len(m) > 1 else None)
                pads = [k for k, pd in enumerate(P.parts[i].fp.pads) if not nums or pd.number in nums]
                if pads:
                    ch.append((m[0], i, pads))
        c = next(((i, pads) for u, i, pads in ch if u == conn), None)
        tgt = next(((i, pads) for u, i, pads in reversed(ch) if u != conn and u not in prot), None)
        if c is None or tgt is None:
            continue
        for u, i, pads in ch:
            if u in prot and i not in (c[0], tgt[0]):
                key = (c[0], tuple(c[1]), i, tuple(pads), tgt[0], tuple(tgt[1]))
                if key not in seen and (P.parts[i].movable or P.parts[tgt[0]].movable or P.parts[c[0]].movable):
                    seen.add(key)
                    out.append((c, (i, pads), tgt))
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
        nk = getattr(p, "n_ortho", len(p.rots))      # macros are laid out at right angles
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
            rects = [(si, q) for q in disjoint_union(list(r.g_own_rects or (r.g_own,)))] + \
                [(1 - si, q) for q in disjoint_union(list(r.g_opp))]
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
        for k in range(len(lits)):
            pts = p.rots[k].pins[pads]
            cx.append(int(round(float(pts[:, 0].mean()) / g)))
            cy.append(int(round(float(pts[:, 1].mean()) / g)))
        if i == anchor:
            return X + cx[ka], Y + cy[ka]
        return X + sum(c * l for c, l in zip(cx, lits)), Y + sum(c * l for c, l in zip(cy, lits))

    obj = []
    for s in structs:
        alts_of = getattr(s, "choices", None) or {}
        for q, ((ia, pa), (ib, pb), w) in enumerate(s.segs):
            ax, ay = pin_expr(ia, pa)
            dx = m.new_int_var(0, 4 * R, "")
            dy = m.new_int_var(0, 4 * R, "")
            alts = alts_of.get(q)
            if alts and len(alts) > 1:
                # the nearest of several pin clusters: one is chosen, its distance bounds dx, dy
                pick = [m.new_bool_var("") for _ in alts]
                m.add_exactly_one(pick)
                for lit, pads_ in zip(pick, alts):
                    bx, by = pin_expr(ib, pads_)
                    m.add(dx >= ax - bx).only_enforce_if(lit)
                    m.add(dx >= bx - ax).only_enforce_if(lit)
                    m.add(dy >= ay - by).only_enforce_if(lit)
                    m.add(dy >= by - ay).only_enforce_if(lit)
            else:
                bx, by = pin_expr(ib, pb)
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


def build_macros(P, structs, time_s=10.0, top_k=3, workers=2, seed=0, log=None, terms=None, candidates=6):
    """Macros from structures; the micro-placement budget is split across them. With `terms`
    (kae.physics.place_terms), CP-SAT proposes `candidates` layouts by the proxy and the
    structures' own self terms (Terms.breakdown of their ids) pick the best `top_k`."""
    groups = _groups(P, structs)
    if not groups:
        return []
    n_try = max(top_k, candidates) if terms is not None else top_k
    # the budget: half to the CP-SAT proposals, half to annealing them on the terms (whose
    # deltas cost milliseconds on big boards); a macro never takes more than its share
    t_start = time.monotonic()
    deadline = t_start + time_s
    per = max(0.3, 0.5 * time_s / len(groups) / max(1, n_try))
    out = []
    for gi, (mem, sts) in enumerate(groups):
        fixed = [i for i in mem if not P.parts[i].movable]
        anchor = fixed[0] if fixed else max(mem, key=lambda i: P.parts[i].area)
        lay = micro_place(P, mem, sts, anchor, time_s=per, top_k=n_try, workers=workers, seed=seed)
        if not lay:
            if log:
                log(f"macro around {P.parts[anchor].ref}: no layout")
            continue
        mac = Macro(members=mem, anchor=anchor, layouts=lay, structs=sts, anchored=bool(fixed))
        if terms is not None:
            try:
                rerank(P, mac, terms)
                # anneal the best few layouts on the place terms themselves, within this
                # macro's share of what is left of the budget
                share = max(0.0, deadline - time.monotonic()) / max(1, len(groups) - gi)
                for lay0 in list(mac.layouts[:top_k]):
                    better = refine(P, mac, lay0, terms, seed=seed,
                                    deadline=time.monotonic() + max(0.05, share / top_k))
                    if better is not None:
                        mac.layouts.append(better)
                rerank(P, mac, terms)
            except Exception as e:   # ranking is an improvement, never a requirement
                if log:
                    log(f"macro {P.parts[anchor].ref}: self-term ranking failed ({type(e).__name__}: {e})")
        uniq, seen = [], set()
        for lay_ in mac.layouts:          # a re-layout to an identical layout is a wasted move
            key = tuple(sorted(lay_.offsets.items()))
            if key not in seen:
                seen.add(key)
                uniq.append(lay_)
        mac.layouts = uniq[:top_k]
        out.append(mac)
        if log:
            st = mac.layouts[0]
            log(f"macro {P.parts[anchor].ref} +{len(mem) - 1} ({','.join(sorted({s.kind for s in sts}))}): "
                f"{len(mac.layouts)} layouts, proxy {st.cost:.1f} mm"
                + (f", self term {st.self_cost:.3f}" if st.self_cost is not None else ""))
    return out


def refine(P, mac, lay, terms, moves=3000, seed=0, w_overlap=5.0, w_compact=0.02, deadline=None):
    """Anneal one macro layout on the place terms themselves (the CP-SAT proxy only proposes):
    members shift and turn around the fixed anchor; cost = Terms total (the macro's
    structures change, everything else is fixed) + overlap of the members' rectangles (per
    side) + a little compactness. Returns a new Layout, or None if it ends with overlaps or
    no better than it started."""
    import math
    import random
    rng = random.Random(seed)
    g = P.g
    a = P.parts[mac.anchor]
    if a.movable:
        x0, y0, x1, y1 = P.outline.bounds
        ax, ay = (x0 + x1) / 2, (y0 + y1) / 2
    else:
        ax, ay = a.x0, a.y0
    off = {i: list(v) for i, v in lay.offsets.items()}
    mem = [i for i in off if i != mac.anchor and P.parts[i].movable]
    if not mem:
        return None
    poses = {p.uuid: (p.x0, p.y0, p.rot0, p.side) for p in P.parts}

    def pose(i):
        dx, dy, k = off[i]
        p = P.parts[i]
        return (ax + dx * g, ay + dy * g, p.rots[k].rot, p.side)
    for i in off:
        if P.parts[i].movable:
            poses[P.parts[i].uuid] = pose(i)

    def rects(i):
        dx, dy, k = off[i]
        p = P.parts[i]
        r = p.rots[k]
        si = 0 if p.s > 0 else 1
        out = [(si, (dx + o[0], dx + o[1], dy + o[2], dy + o[3])) for o in (r.g_own_rects or (r.g_own,))]
        out += [(1 - si, (dx + q[0], dx + q[1], dy + q[2], dy + q[3])) for q in r.g_opp]
        return out

    def overlap(i):
        tot = 0
        ri = rects(i)
        for j in off:
            if j == i:
                continue
            for sa, A in ri:
                for sb, B in rects(j):
                    if sa != sb:
                        continue
                    dx = min(A[1], B[1]) - max(A[0], B[0])
                    dy = min(A[3], B[3]) - max(A[2], B[2])
                    if dx > 0 and dy > 0:
                        tot += dx * dy
        return tot

    def compact():
        xs = [off[i][0] for i in off]
        ys = [off[i][1] for i in off]
        return (max(xs) - min(xs) + max(ys) - min(ys)) * g

    A0 = max(1.0, sum((P.parts[i].rots[0].g_own[1] - P.parts[i].rots[0].g_own[0]) *
                      (P.parts[i].rots[0].g_own[3] - P.parts[i].rots[0].g_own[2]) for i in off) / len(off))
    phys = terms.total(poses)
    start = phys
    ov = sum(overlap(i) for i in off) / 2
    comp = compact()
    cost = phys + w_overlap * ov / A0 + w_compact * comp
    r0 = max(2, int(2.0 / g))
    T0 = 0.05 * max(1e-3, abs(phys))
    best = None
    t_start = time.monotonic()
    tfrac = 0.0
    for it in range(moves):
        if deadline is not None and (it & 31) == 0:
            now = time.monotonic()
            if now > deadline:
                break
            tfrac = (now - t_start) / max(1e-6, deadline - t_start)
        frac = max(it / moves, tfrac)          # cool on whichever runs out first: moves or time
        T = T0 * (1e-3 ** frac)
        r = max(1, int(r0 * (1 - frac)))
        i = mem[rng.randrange(len(mem))]
        old = list(off[i])
        ov_i = overlap(i)
        if rng.random() < 0.7:
            off[i][0] += rng.randint(-r, r)
            off[i][1] += rng.randint(-r, r)
        else:
            k0 = off[i][2]
            k1 = P.parts[i].turn[k0][rng.choice((1, 2, 3))]
            o0, o1 = P.parts[i].rots[k0].g_own, P.parts[i].rots[k1].g_own
            off[i][0] += ((o0[0] + o0[1]) - (o1[0] + o1[1])) // 2
            off[i][1] += ((o0[2] + o0[3]) - (o1[2] + o1[3])) // 2
            off[i][2] = k1
        u = P.parts[i].uuid
        newp = pose(i)
        d_phys = terms.delta(poses, [u], {u: newp})
        d_ov = overlap(i) - ov_i
        comp1 = compact()
        delta = d_phys + w_overlap * d_ov / A0 + w_compact * (comp1 - comp)
        if delta <= 0 or rng.random() < math.exp(-delta / T):
            poses[u] = newp
            phys += d_phys
            ov += d_ov
            comp = comp1
            cost += delta
            if ov == 0 and (best is None or cost < best[0]):
                best = (cost, phys, {j: tuple(v) for j, v in off.items()})
        else:
            off[i] = old
    if best is None or best[1] >= start - 1e-9:
        return None
    new = _layout(P, best[2], lay.cost)
    new.self_cost = None
    return new


def rerank(P, mac, terms):
    """Order a macro's layouts by the summed cost of its own structures under the place
    terms (members at the layout around the anchor; everything else where it is)."""
    ids = {s.src.get("id") for s in mac.structs if s.src.get("id")}
    if not ids:
        return
    mem = {P.parts[i].uuid for i in mac.members}

    def own(r):
        # the macro's structures (decaps split per power-pin cluster carry '#k'), and any
        # other term whose parts all sit in the macro (thermal, a loop of its members)
        rid = str(r.get("id") or "")
        return rid in ids or rid.split("#")[0] in ids or (r.get("uuids") and set(r["uuids"]) <= mem)
    base = {p.uuid: (p.x0, p.y0, p.rot0, p.side) for p in P.parts}
    a = P.parts[mac.anchor]
    if a.movable:
        x0, y0, x1, y1 = P.outline.bounds
        ax, ay = (x0 + x1) / 2, (y0 + y1) / 2
    else:
        ax, ay = a.x0, a.y0
    for lay in mac.layouts:
        poses = dict(base)
        for i, (dx, dy, k) in lay.offsets.items():
            p = P.parts[i]
            if p.movable:
                poses[p.uuid] = (ax + dx * P.g, ay + dy * P.g, p.rots[k].rot, p.side)
        rows = terms.breakdown(poses)
        lay.self_cost = float(sum(r.get("cost", 0.0) for r in rows if own(r)))
    mac.layouts.sort(key=lambda l: (l.self_cost, l.cost))


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
                v[i] = (ddx, ddy, P.parts[i].turn[k][q])
            variants.append(v)
        _ = ka
    return Item(members=list(mac.members), variants=variants, X0=X0, Y0=Y0, v0=v0,
                weight=float(len(mac.members)), name=f"M_{P.parts[mac.anchor].ref}")
