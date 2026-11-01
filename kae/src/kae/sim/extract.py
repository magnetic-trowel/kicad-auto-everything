# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Routed copper as a circuit: R, L, C, mutual L and coupling C per piece of copper.

`extract(rb, nets)` reads the copper graph of each net (kae.route.copper.NetGraph: pads,
round-ended tracks split where they touch, vias, refilled pours; connected as KiCad connects them) and returns a Network of elements between
node keys ('pin:U5.12' at a pad, '<net>#...' inside the copper, '0' the reference).

Model (each piece is a line over its reference plane; the plane carries the return directly under it):

- a track piece of length l, width w at height h over the nearest plane layer of any net
  (RoutedBoard.strip_h): series R = rho l / (w t) and L = L'(w, h) l, with C = C'(w, h, eps_r) l split to
  both ends (Hammerstad-Jensen, kae.physics.kernels); pieces longer than `lmax` are split into sections,
  so delay sqrt(L C) and impedance sqrt(L/C) follow the line;
- a via: R and L of its barrel (partial self inductance of a tube) between the layers it joins;
- a pour of a non-ground net: the copper graph's pour links (2 mm strips between nearby contacts, as
  `rail_drops`) for R and L, and its plate capacitance eps A / h spread over its contacts (coarse);
- a ground net: its pours are the reference node; its tracks and vias between pads and pours are extracted;
- neighbours: same-layer pieces of different nets within `couple_mm` get mutual inductance with plane
  images (m_seg plus the image term) as a K element, and coupling capacitance from patch potential
  coefficients (patch_coupling).

Reduction: track pieces shorter than `lmin` keep their resistance but not their inductance, and their
capacitance moves to their ends (micrometre pieces from junction splitting would otherwise put
femtofarads behind micro-ohms, and the circuit matrix near-singular); every resistance is at least R_MIN.

Limits, recorded in `notes`: the plane is ideal (slots, splits and plane impedance are left to the
geometric checks), power planes are AC ground for line capacitance, broadside coupling across layers
is not modelled, a pad's own copper and thermal spokes are not extracted, skin effect is ignored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point

from kae.physics import fastloop as FL
from kae.physics.kernels import cprime_hj, image, lprime_hj, m_seg, patch_coupling
from kae.route.critical_physics import INF, r_track, r_via

GROUND = "0"
EPS0_PF_MM = 8.854e-3
R_MIN = 1e-4
K_SUM = 0.8           # largest sum of |k| over one inductor's couplings


@dataclass
class Element:
    kind: str                 # R | L | C | K
    key: str
    a: str = ""
    b: str = ""
    value: float = 0.0        # ohm, H, F; K: coupling coefficient
    l1: str = ""              # K: keys of the two inductors
    l2: str = ""


@dataclass
class Network:
    elements: list = field(default_factory=list)
    pins: dict = field(default_factory=dict)       # pin key -> net
    alias: dict = field(default_factory=dict)      # pin key -> node key it was merged into
    nets: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    groups: dict = field(default_factory=dict)     # net -> [[pin keys]] connected by copper (R/L)

    def add(self, kind, key, a="", b="", value=0.0, **kw):
        self.elements.append(Element(kind, key, a, b, value, **kw))

    def node_of(self, pin):
        return self.alias.get(pin, pin)


@dataclass
class _Piece:
    net: str
    a: str
    b: str
    R: float
    L: float
    C: float
    length: float              # mm along the copper (0 for a via barrel: never merged)
    geom: tuple | None = None  # (layer, p0, p1, w, h) of a track piece that may couple


class _Builder:
    def __init__(self, rb, lmax, lmin, couple_mm, k_min):
        self.rb, self.lmax, self.lmin, self.couple_mm, self.k_min = rb, lmax, lmin, couple_mm, k_min
        self.net = Network()
        self.pieces = []
        self.caps = {}                 # node key -> F to the reference
        st = rb.board.stackup
        self.t_cu = dict(zip(st.copper, st.cu_thickness)) if st and st.cu_thickness else {}
        self.line_c = True
        self._n = 0

    def uid(self, prefix):
        self._n += 1
        return f"{prefix}{self._n}"

    def line(self, net, layer, na, nb, a, c, w, ground, pour=False):
        rb = self.rb
        ln = math.dist(a, c)
        h = rb.strip_h(layer, a, c) if ln > 1e-6 else INF
        if h == INF:
            h = rb.thickness
            if ln > 1e-6 and not pour:
                self.net.stats["no_reference_mm"] = self.net.stats.get("no_reference_mm", 0.0) + ln
        t = self.t_cu.get(layer, 0.035)
        R = r_track(ln, w, t)
        L = lprime_hj(w, h) * ln * 1e-9
        C = 0.0 if (ground or pour or not self.line_c) else cprime_hj(w, h, rb.er) * ln * 1e-12
        geom = None if (ground or pour) else (layer, (a[0], a[1], h), (c[0], c[1], h), w, h)
        self.pieces.append(_Piece(net, na, nb, R, L, C, ln, geom))
        if not pour:
            self.net.stats["track_mm"] = self.net.stats.get("track_mm", 0.0) + ln

    def add_net(self, name):
        rb = self.rb
        g = rb.graph(name)
        ground = name in rb.gnd
        pin_of = {}
        for (fu, num), ks in g.pad_node.items():
            key = f"pin:{rb.fp[fu].ref}.{num}"
            self.net.pins[key] = name
            for k in ks:
                pin_of[k] = key
        pour = {}
        for u, lst in g.adj.items():
            for _v, _w, piece in lst:
                if piece[0] == "pour":
                    pour.setdefault(u, set()).add(piece[1])
        via_obj = {(round(v.x, 4), round(v.y, 4)): v for v in rb.board.vias if v.net == name}
        via_layers = {}

        def nk(u, layer):
            kind = g.nodes[u][0]
            if ground and layer in pour.get(u, ()):
                key = GROUND
            elif u in pin_of:
                key = pin_of[u]
            elif kind == "via":
                key = f"{name}#v{u}@{layer}"
            else:
                key = f"{name}#{u}"
            if kind == "via":
                via_layers.setdefault(u, {})[layer] = key
            return key

        for u in pin_of:
            if ground and pour.get(u):
                self.pieces.append(_Piece(name, pin_of[u], GROUND, R_MIN, 0.0, 0.0, 0.0))   # pad in the ground pour
        seen = set()
        for u, lst in g.adj.items():
            for v, _w, piece in lst:
                kind, layer, a, c, w = piece
                sig = (min(u, v), max(u, v), kind, layer, tuple(np.round(a, 4)), tuple(np.round(c, 4)))
                if sig in seen:
                    continue
                seen.add(sig)
                na, nb = nk(u, layer), nk(v, layer)
                if na != nb:
                    self.line(name, layer, na, nb, a, c, w, ground, pour=kind == "pour")
        for u, lay in via_layers.items():
            v = via_obj.get((round(g.nodes[u][2], 4), round(g.nodes[u][3], 4)))
            drill = v.drill if v is not None and getattr(v, "drill", 0) else 0.3
            ordered = sorted(lay.items(), key=lambda kv: rb.z[kv[0]])
            for (l1, k1), (l2, k2) in zip(ordered[:-1], ordered[1:]):
                if k1 != k2:
                    dz = abs(rb.z[l2] - rb.z[l1])
                    self.pieces.append(_Piece(name, k1, k2, r_via(dz, drill), FL.m_self(dz, drill / 2) * 1e-9, 0.0, 0.0))
        if not ground:
            fills = (rb.fills or {}).get(name) if rb.fills is not None else None
            shapes = (getattr(rb.board, "copper", {}) or {}).get(name, {})
            for l, pg in [(l, pg) for src in (fills or {}, shapes) for l, polys in src.items() for pg in polys]:
                cont = [k for k, nd in enumerate(g.nodes) if l in nd[1] and (pg.contains(Point(nd[2], nd[3]))
                                                                            or (nd[0] == "pad" and pg.intersects(nd[4])))]
                if not cont:
                    continue
                cx, cy = pg.representative_point().coords[0]
                h = rb.h_at(l, cx, cy)
                if h == INF:
                    continue
                C = EPS0_PF_MM * rb.er * pg.area / h * 1e-12
                for k in cont:
                    key = nk(k, l)
                    self.caps[key] = self.caps.get(key, 0.0) + C / len(cont)
                self.net.stats["pour_mm2"] = self.net.stats.get("pour_mm2", 0.0) + pg.area
        self.net.nets.append(name)

    def build(self, coupling):
        def f(x):
            return x
        caps = {}
        short = 0

        def cap(node, c):
            if node != GROUND and c > 0:
                caps[node] = caps.get(node, 0.0) + c
        sections = []
        for p in self.pieces:
            a, b = f(p.a), f(p.b)
            if a == b:
                continue
            if 0.0 < p.length < self.lmin:
                # a short piece keeps its resistance; its sub-nH inductance and fF capacitance are left
                # out (to the ends), which keeps the circuit free of THz parasitic resonances
                self.net.add("R", self.uid("r"), a, b, max(p.R, R_MIN))
                cap(a, p.C / 2)
                cap(b, p.C / 2)
                short += 1
                continue
            n = max(1, math.ceil(p.length / self.lmax)) if p.length > 0 else 1
            nodes = [a] + [f"{p.net}#{self.uid('q')}" for _ in range(n - 1)] + [b]
            for i in range(n):
                if p.L > 0:
                    mid = f"{p.net}#{self.uid('m')}"
                    self.net.add("R", self.uid("r"), nodes[i], mid, max(p.R / n, R_MIN))
                    lk = self.uid("l")
                    self.net.add("L", lk, mid, nodes[i + 1], p.L / n)
                else:
                    lk = None
                    self.net.add("R", self.uid("r"), nodes[i], nodes[i + 1], max(p.R / n, R_MIN))
                cap(nodes[i], p.C / n / 2)
                cap(nodes[i + 1], p.C / n / 2)
                if p.geom is not None and lk is not None:
                    layer, g0, g1, w, h = p.geom
                    t0, t1 = i / n, (i + 1) / n
                    q0 = tuple(g0[k] + t0 * (g1[k] - g0[k]) for k in range(3))
                    q1 = tuple(g0[k] + t1 * (g1[k] - g0[k]) for k in range(3))
                    sections.append((p.net, layer, q0, q1, w, h, lk, p.L / n, (nodes[i], nodes[i + 1])))
        self.net.stats["short_pieces_r_only"] = short
        for node, c in self.caps.items():
            cap(f(node), c)
        for node, c in caps.items():
            self.net.add("C", self.uid("c"), node, GROUND, c)
        if coupling:
            self._couple(sections)
        return sections

    def _couple(self, S):
        if len(S) < 2:
            return
        lines = [LineString([s[2][:2], s[3][:2]]) for s in S]
        tree = STRtree(lines)
        nk = nc = 0
        for i, s in enumerate(S):
            for j in tree.query(lines[i], predicate="dwithin", distance=self.couple_mm):
                j = int(j)
                if j <= i:
                    continue
                t = S[j]
                if t[0] == s[0] or t[1] != s[1]:
                    continue
                M = m_seg(s[2], s[3], t[2], t[3]) + m_seg(s[2], s[3], *image((t[2], t[3])))
                k = M * 1e-9 / math.sqrt(s[7] * t[7])
                if abs(k) >= self.k_min:
                    self.net.add("K", self.uid("k"), value=max(-0.9, min(0.9, k)), l1=s[6], l2=t[6])
                    nk += 1
                cm = self._cm(s, t)
                if cm > 1e-16:
                    sa, sb = s[8]
                    ta, tb = t[8]
                    straight = math.dist(s[2][:2], t[2][:2]) + math.dist(s[3][:2], t[3][:2]) <= \
                        math.dist(s[2][:2], t[3][:2]) + math.dist(s[3][:2], t[2][:2])
                    for x, y in (((sa, ta), (sb, tb)) if straight else ((sa, tb), (sb, ta))):
                        if x != y:
                            self.net.add("C", self.uid("cm"), x, y, cm / 2)
                    nc += 1
        # keep the inductance matrix positive definite: where an inductor's couplings sum above K_SUM,
        # scale them down (Gershgorin: a diagonally dominant normalised matrix is positive definite);
        # without this, many neighbours each below 0.9 can make the circuit non-passive and unstable
        ks = [e for e in self.net.elements if e.kind == "K"]
        tot = {}
        for e in ks:
            tot[e.l1] = tot.get(e.l1, 0.0) + abs(e.value)
            tot[e.l2] = tot.get(e.l2, 0.0) + abs(e.value)
        scaled = 0
        for e in ks:
            s = min(1.0, K_SUM / tot[e.l1], K_SUM / tot[e.l2])
            if s < 1.0:
                e.value *= s
                scaled += 1
        self.net.stats["mutual_L"] = nk
        self.net.stats["mutual_L_scaled"] = scaled
        self.net.stats["coupling_C"] = nc

    def _cm(self, s, t, dl=1.0):
        def patches(x):
            p0, p1, w, h = np.array(x[2][:2]), np.array(x[3][:2]), x[4], x[5]
            ln = float(np.linalg.norm(p1 - p0))
            n = max(1, math.ceil(ln / dl))
            return [(p0 + (k + 0.5) / n * (p1 - p0), w * ln / n, h) for k in range(n)]
        tot = 0.0
        for pa, aa, ha in patches(s):
            for pv, av, hv in patches(t):
                tot += patch_coupling(aa, av, float(np.linalg.norm(pa - pv)), ha, hv, eps_r=self.rb.er)
        return tot * 1e-12

    def finish(self):
        parent = {}

        def f(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for e in self.net.elements:
            if e.kind in ("R", "L"):
                ra, rb_ = f(e.a), f(e.b)
                if ra != rb_:
                    parent[ra] = rb_
        for net in self.net.nets:
            groups = {}
            for p, n in self.net.pins.items():
                if n == net:
                    groups.setdefault(f(self.net.node_of(p)), []).append(p)
            self.net.groups[net] = sorted((sorted(v) for v in groups.values()), key=len, reverse=True)
        counts = {}
        for e in self.net.elements:
            counts[e.kind] = counts.get(e.kind, 0) + 1
        self.net.stats["elements"] = counts
        self.net.notes = [
            "plane ideal under each piece (slots and splits: geometric checks)",
            "power planes taken as AC ground for line capacitance",
            "no broadside coupling across layers; pad copper and thermal spokes not extracted; no skin effect",
            "pours of non-ground nets: coarse 2 mm strip mesh plus plate capacitance",
            f"track pieces shorter than {self.lmin} mm: R only; sections <= {self.lmax} mm; R >= {R_MIN} ohm",
            f"couplings of one inductor scaled to a sum of |k| <= {K_SUM} (positive definite)",
        ] + ([] if self.line_c else ["no line capacitance (power profile)"])
        return self.net


# Extraction profiles. signal: line capacitance, coupling and short sections for delay, impedance
# and crosstalk. power: series R and L in long sections, plate capacitance of pours and via inductance,
# no line capacitance (0.1 pF/mm against microfarads of decoupling) and no coupling; it keeps the
# circuit free of the GHz parasitic resonances that would force picosecond steps over microseconds.
PROFILES = {"signal": dict(lmax=5.0, lmin=0.5, line_c=True, coupling=True),
            "power": dict(lmax=20.0, lmin=0.0, line_c=False, coupling=False)}


def extract(rb, nets, profile="signal", couple_mm=1.0, k_min=0.01, **over):
    """Network of the given nets' copper on RoutedBoard `rb` (see the module docstring)."""
    o = dict(PROFILES[profile], **over)
    b = _Builder(rb, o["lmax"], o["lmin"], couple_mm, k_min)
    b.line_c = o["line_c"]
    for n in nets:
        b.add_net(n)
    b.build(o["coupling"])
    net = b.finish()
    net.stats["profile"] = profile
    return net
