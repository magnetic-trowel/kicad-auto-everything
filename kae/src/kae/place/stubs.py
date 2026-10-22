# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stand-ins for kae.circuit.brief and kae.physics.place_terms until they land.

Same interfaces as the agreed contracts:
- `stub_brief(board) -> dict`: nets{name: {role}}, parts{uuid: {ref, kind, role}}, and
  structures (decap: ic, power_pins, ground_pins, rail, ground, caps; crystal: ic, xin,
  xout, crystal, load_caps, f_Hz; commutation_cell: loop [[uuid, pad|[pads]], ...];
  connector_chain: connector, pin, net, chain [[uuid, pad], ...], protection, external).
  Built from kae.circuit.roles (part kinds, net roles, switch nodes).
- `StubTerms(board, brief)`: total(poses), delta(poses, moved, new_poses), breakdown(poses),
  parts(), structures_of(uuid); poses are {uuid: (x, y, rot, side)}. Each structure costs
  its pin-to-pin loop path length divided by a length budget (a geometric proxy for the
  budget utilization the real terms report).
"""
from __future__ import annotations

import math

from kae.board import transform

BUDGET_MM = {"decap": 4.0, "commutation_cell": 15.0, "crystal": 8.0, "connector_chain": 12.0}


# ----------------------------------------------------------------------------- brief
def stub_brief(board):
    from kae.circuit.netlist import Netlist
    from kae.circuit.roles import infer_roles
    nl = Netlist.from_board(board)
    roles = infer_roles(nl)
    uuid_of = {k: (p.uuid or k) for k, p in nl.parts.items()}
    out = dict(source="kae.place.stubs", nets={}, parts={}, structures=[])
    for name, nr in roles.nets.items():
        out["nets"][name] = dict(role=nr.role)
    for k, pr in roles.parts.items():
        out["parts"][uuid_of[k]] = dict(ref=nl.parts[k].refdes, kind=pr.kind, role=pr.role)
    grounds = set(roles.grounds)
    gnd = roles.gnd

    def pins_on(k, net):
        return [p.number for p in nl.parts[k].pins if p.net == net]

    ics = [k for k, pr in roles.parts.items() if pr.kind in ("ic", "module") and len(nl.parts[k].pins) >= 3]
    # decoupling: caps between a rail and ground, assigned to the IC with most pins on the rail
    for rail, caps in roles.caps_to.items():
        if rail in grounds:
            continue
        users = sorted(((len(pins_on(k, rail)), k) for k in ics if pins_on(k, rail)), reverse=True)
        if not users:
            continue
        ic = users[0][1]
        cl = [c for c, g in caps if roles.parts.get(c) and roles.parts[c].role in ("decoupling", "bulk", "filter_to_ground")]
        if not cl:
            continue
        g = caps[0][1] if caps else gnd
        out["structures"].append(dict(kind="decap", ic=uuid_of[ic], power_pins=pins_on(ic, rail),
                                      ground_pins=[n for gg in grounds for n in pins_on(ic, gg)], rail=rail,
                                      ground=g, caps=[uuid_of[c] for c in cl[:6]], confidence=0.6))
    # crystals
    for k, pr in roles.parts.items():
        if pr.kind != "crystal":
            continue
        sig = sorted({p.net for p in nl.parts[k].pins if p.net and p.net not in grounds})
        if len(sig) < 2:
            continue
        ic = None
        for c in ics:
            if all(pins_on(c, n) for n in sig[:2]):
                ic = c
                break
        load = []
        for n in sig[:2]:
            for (cap, gg) in roles.caps_to.get(n, []):
                load.append(uuid_of[cap])
        out["structures"].append(dict(kind="crystal", ic=uuid_of[ic] if ic else None,
                                      xin=pins_on(ic, sig[0])[0] if ic else None,
                                      xout=pins_on(ic, sig[1])[0] if ic else None,
                                      crystal=uuid_of[k], crystal_pins=[pins_on(k, sig[0])[0], pins_on(k, sig[1])[0]],
                                      nets=sig[:2], load_caps=load, f_Hz=None, confidence=0.6))
    # commutation cells: switch node + inductor + switching part + input capacitor
    for sw, info in roles.switch_nodes.items():
        parts_sw = [k for k in nl.parts if pins_on(k, sw)]
        switches = [k for k in parts_sw if roles.parts.get(k) and roles.parts[k].kind in ("ic", "transistor")]
        diodes = [k for k in parts_sw if roles.parts.get(k) and roles.parts[k].kind == "diode"]
        if not switches:
            continue
        u = switches[0]
        rails = [n for n in {p.net for p in nl.parts[u].pins} if n in roles.rails and n != sw]
        cin = None
        vin = None
        for rail in rails:
            caps = [c for c, g in roles.caps_to.get(rail, [])]
            if caps:
                vin, cin = rail, caps[0]
                break
        loop = []
        if cin:
            loop.append([uuid_of[cin], pins_on(cin, vin)])
            loop.append([uuid_of[u], pins_on(u, vin)])
        loop.append([uuid_of[u], pins_on(u, sw)])
        if diodes:
            d = diodes[0]
            loop.append([uuid_of[d], pins_on(d, sw)])
            dg = [n for gg in grounds for n in pins_on(d, gg)]
            if dg:
                loop.append([uuid_of[d], dg])
        else:
            ug = [n for gg in grounds for n in pins_on(u, gg)]
            if ug:
                loop.append([uuid_of[u], ug])
        if cin:
            cg = [n for gg in grounds for n in pins_on(cin, gg)]
            if cg:
                loop.append([uuid_of[cin], cg])
        if len({m[0] for m in loop}) >= 2:
            out["structures"].append(dict(kind="commutation_cell", net=sw, loop=loop,
                                          inductors=[uuid_of[x] for x in info.get("inductors", []) if x in uuid_of],
                                          confidence=0.5))
    # connector protection chains
    for k, pr in roles.parts.items():
        if pr.kind != "connector":
            continue
        for p in nl.parts[k].pins:
            n = p.net
            if not n or n in grounds or n in roles.rails:
                continue
            chain = [[uuid_of[k], p.number]]
            prot = []
            for q in nl.parts_on(n):
                if q.ref == k:
                    continue
                qr = roles.parts.get(q.ref)
                if qr is None:
                    continue
                if qr.kind == "diode" and qr.subtype in ("tvs", "esd_array", "zener"):
                    chain.append([uuid_of[q.ref], pins_on(q.ref, n)[0]])
                    prot.append(uuid_of[q.ref])
                elif qr.kind in ("resistor", "ferrite") and len(nl.parts[q.ref].pins) == 2:
                    chain.append([uuid_of[q.ref], pins_on(q.ref, n)[0]])
            if len(chain) >= 2 and prot:
                out["structures"].append(dict(kind="connector_chain", connector=uuid_of[k], pin=p.number, net=n,
                                              chain=chain[:5], protection=prot, external=True, confidence=0.5))
    return out


# ----------------------------------------------------------------------------- terms
class _Pins:
    """Pad offsets of a footprint per rotation (cached), by pad number."""

    def __init__(self, fp):
        self.fp = fp
        self.by_num = {}
        for k, p in enumerate(fp.pads):
            self.by_num.setdefault(p.number, []).append(k)
        self.cache = {}

    def offsets(self, rot, side):
        key = (round(rot, 3), side)
        v = self.cache.get(key)
        if v is None:
            v = [transform.to_board(p.lx, p.ly, 0.0, 0.0, rot, side) for p in self.fp.pads]
            self.cache[key] = v
        return v

    def point(self, pose, nums):
        """Centroid of the pads with these numbers at a pose."""
        x, y, rot, side = pose
        offs = self.offsets(rot, side)
        idx = [k for n in nums for k in self.by_num.get(str(n), [])]
        if not idx:
            idx = list(range(len(offs))) or [None]
        if idx == [None]:
            return (x, y)
        sx = sum(offs[k][0] for k in idx) / len(idx)
        sy = sum(offs[k][1] for k in idx) / len(idx)
        return (x + sx, y + sy)


def _nums(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]


class StubTerms:
    """Geometric proxy terms with the place_terms interface (see module docstring)."""

    def __init__(self, board, brief):
        self.board = board
        self.fps = {f.uuid: f for f in board.footprints}
        self.pins = {u: _Pins(f) for u, f in self.fps.items()}
        self.structs = []
        for s in (brief or {}).get("structures", []):
            ev = self._compile(s)
            if ev is not None:
                self.structs.append(ev)
        self.by_part = {}
        for j, st in enumerate(self.structs):
            for u in st["members"]:
                self.by_part.setdefault(u, []).append(j)

    def _compile(self, s):
        kind = s.get("kind")
        b = BUDGET_MM.get(kind)
        if b is None:
            return None
        if kind == "decap":
            ic = s.get("ic")
            caps = [c if isinstance(c, str) else c[0] for c in s.get("caps", [])]
            if ic not in self.fps or not caps:
                return None
            rail, gnd = s.get("rail"), s.get("ground")
            pp, gp = _nums(s.get("power_pins")), _nums(s.get("ground_pins"))
            segs = []
            for c in caps:
                if c not in self.fps:
                    continue
                f = self.fps[c]
                crail = [p.number for p in f.pads if p.net == rail] or [f.pads[0].number]
                cgnd = [p.number for p in f.pads if p.net == gnd] or [f.pads[-1].number]
                segs.append(((c, crail), (ic, pp)))
                if gp:
                    segs.append(((c, cgnd), (ic, gp)))
            members = {ic, *[c for c in caps if c in self.fps]}
            return dict(kind=kind, members=members, segs=segs, budget=b * max(1, len(caps)), src=s)
        if kind == "crystal":
            xt = s.get("crystal")
            if xt not in self.fps:
                return None
            segs = []
            ic = s.get("ic")
            xp = _nums(s.get("crystal_pins")) or [p.number for p in self.fps[xt].pads[:2]]
            if ic in self.fps and s.get("xin") is not None:
                segs.append(((xt, xp[:1]), (ic, _nums(s.get("xin")))))
                if len(xp) > 1 and s.get("xout") is not None:
                    segs.append(((xt, xp[1:2]), (ic, _nums(s.get("xout")))))
            for c in s.get("load_caps", []):
                c = c if isinstance(c, str) else c[0]
                if c in self.fps:
                    segs.append(((c, [self.fps[c].pads[0].number]), (xt, xp)))
            members = {xt} | ({ic} if ic in self.fps else set()) | {c if isinstance(c, str) else c[0] for c in s.get("load_caps", []) if (c if isinstance(c, str) else c[0]) in self.fps}
            return dict(kind=kind, members=members, segs=segs, budget=b, src=s) if segs else None
        if kind == "commutation_cell":
            loop = [(m[0], _nums(m[1])) for m in s.get("loop", []) if m and m[0] in self.fps]
            if len(loop) < 2:
                return None
            segs = [(loop[i], loop[(i + 1) % len(loop)]) for i in range(len(loop))]
            return dict(kind=kind, members={m[0] for m in loop}, segs=segs, budget=b, src=s)
        if kind == "connector_chain":
            ch = [(m[0], _nums(m[1])) for m in s.get("chain", []) if m and m[0] in self.fps]
            if len(ch) < 2:
                return None
            segs = [(ch[i], ch[i + 1]) for i in range(len(ch) - 1)]
            return dict(kind=kind, members={m[0] for m in ch}, segs=segs, budget=b, src=s)
        return None

    # ---------------------------------------------------------------- interface
    def parts(self):
        return set(self.by_part)

    def structures_of(self, uuid):
        return [self.structs[j]["src"] for j in self.by_part.get(uuid, [])]

    def _pose(self, poses, u):
        p = poses.get(u)
        if p is None:
            f = self.fps[u]
            p = (f.x, f.y, f.rot, f.side)
        return p

    def _value(self, st, poses, override=None):
        L = 0.0
        for (ua, na), (ub, nb) in st["segs"]:
            pa = override.get(ua) if override and ua in override else self._pose(poses, ua)
            pb = override.get(ub) if override and ub in override else self._pose(poses, ub)
            ax, ay = self.pins[ua].point(pa, na)
            bx, by = self.pins[ub].point(pb, nb)
            L += math.hypot(ax - bx, ay - by)
        return L

    def total(self, poses):
        return sum(self._value(st, poses) / st["budget"] for st in self.structs)

    def delta(self, poses, moved, new_poses):
        js = set()
        for u in moved:
            js.update(self.by_part.get(u, ()))
        d = 0.0
        for j in js:
            st = self.structs[j]
            d += (self._value(st, poses, new_poses) - self._value(st, poses)) / st["budget"]
        return d

    def breakdown(self, poses):
        out = []
        for st in self.structs:
            L = self._value(st, poses)
            refs = sorted(self.fps[u].ref for u in st["members"])
            out.append(dict(kind=st["kind"], members=refs, value=round(L, 3), unit="mm (loop path proxy)",
                            budget=st["budget"], utilization=round(L / st["budget"], 3)))
        return out


def make_terms(board, brief, barrier=None, **knobs):
    """The real place_terms when importable, else the stub. `barrier` overrides the
    over-budget barrier of phi(u) (0 = linear utilization); other keywords override
    kae.physics.priors.Knobs fields (e.g. u_sat)."""
    try:
        from kae.physics.place_terms import Terms
    except ImportError:
        return StubTerms(board, brief), "kae.place.stubs.StubTerms"
    kn = None
    if barrier is not None or knobs:
        from kae.physics.priors import Knobs
        if barrier is not None:
            knobs["barrier"] = barrier
        kn = Knobs(**knobs)
    return Terms(board, brief, knobs=kn), "kae.physics.place_terms"


def make_brief(board):
    try:
        from kae.circuit.brief import build
        return build(board), "kae.circuit.brief"
    except ImportError:
        return stub_brief(board), "kae.place.stubs.stub_brief"
