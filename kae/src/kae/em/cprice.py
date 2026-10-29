# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Capacitive router prices (stage E3 of docs/topics/architecture/physics-frequency-coverage.md): the
electric field of every fast-swinging net prices the high-impedance copper beside it, and by
reciprocity each victim's field prices the swinging net's copper.

Harm. A victim observer k (kae.excite.observe: feedback, analog, crystal, reset ...) reads net n; an
aggressor net a (a commutation cell's switch node, a clock: kae.excite.capacitive.aggressors) swings
V in an edge t_v. Capacitive coupling is voltage-forced: the swing drives i = C_m V / t_v into n for
the edge's duration. To the edge the victim node is a resistance R (the circuit's driving-point
impedance at low frequency: a feedback divider's R_top || R_bot) in parallel with C_node, the
circuit's capacitance at the edge band (pin, capacitors) plus the net's own copper capacitance (its
Maxwell diagonal from the static solve). A ramp into that node peaks at the end of the edge:

    v_k = C_m (V / t_v) R (1 - exp(-t_v / (R C_node)))

the divider C_m V / C_node when the edge is fast against R C_node (a feedback node: 29 kOhm and 6 pF,
170 ns, against 0.2-8 ns edges), C_m R dV/dt when it is slow. So u = v_k / bound = g C_m, with g at
every corner of the ledger (V, and t_v = C_sw V / I for a cell: kae.excite.params; a clock's edge).
Each (k, a) pair adds phi(u) to the router's per-corner totals, and its weight is the robust
objective's derivative per farad, W = mean over the objective's corners of phi'(u) g.

Why not the evaluator's linear circuit: there a cell is a current source with its rectifier
conducting, so the switch node moves by the hot loop's I Z (its ring), not by the commutation swing
V; on the boost board 18 fF give u = 1.0 there against 2.6 here. Both are linear in C_m, so the price
fields below serve either; only the weight differs.

Price fields. With a at 1 V and every other conductor at 0 V (kae.em.static), phi_a is the potential
on every cell of every layer. A short piece of net n's conductor placed at x, held at 0 V there,
takes the charge -C' phi_a(x) per length, C' its capacitance per length to everything else, so the
mutual capacitance grows by

    dC_m = C'(x; w, layer) phi_a(x) dl                      (first order in the piece)

and by Green's reciprocity a piece of a's copper at x adds C' phi_n(x) dl, phi_n with n at 1 V. A hop
of net X costs, per mm, C' Phi_X with Phi_X the sum over X's pairs of W phi_(the other net):
non-negative, additive along the path, added to the A* self term. C' is a closed form over the
cell's nearest copper above and below (microstrip, Hammerstad-Jensen, with its effective
permittivity; capacitances to both sides add) and beside it on the layer (coplanar, one side), at the
width the static raster carries (a chain one pitch wide below three pitches, kae.em.mesh): the solve
that refreshes the prices sees that width.

Limits of first order: the hop's copper is not in the field it is priced on. A piece beside its own
net's earlier copper is over-priced (that copper already took part of the charge: 1.04-1.12 against
a fresh solve at 1 mm), a free track end under-priced (its fringe: 0.83 end-on). After each hop of an
aggressor or a victim net, its copper is painted into the static raster and that net's own field
re-solved (conjugate gradients from its previous charges), so the next hop sees the copper; the other
fields miss the new copper's screening (second order) until the router's refresh re-meshes and
re-solves every field. The victim's own copper also raises C_node, which lowers u: the harm counts
it, the prices do not (a negative price per length would reward wandering).
"""
from __future__ import annotations

import copy
import math
import time

import numpy as np

from kae.excite.harm import phi

C0 = 299792458.0
EPS0 = 8.8541878128e-12
F_LO = 1e3              # Hz: the victim node's resistance is its impedance's real part here
H_NONE = 1.6            # mm: the plane height assumed where a cell has no copper above or below
# coplanar copper at edge gap g beside a strip over a plane at h adds CO_A exp(-CO_B g / h) of the strip's
# microstrip C' (one side; sides add): fitted to raster solves (kae.em.static) of 0.25 and 0.5 mm strips at
# h = 0.2 and 1.51 mm beside a 5 mm coplanar ground, g / h 0.17-1.3, within 0.04 C_ms of each solve
CO_A, CO_B = 0.25, 3.0


def victim_rc(circuit, o, t_e):
    """(R ohm, C F) of victim observer o's node, from the circuit: R the real part of its driving-point
    impedance at F_LO, C from its reactance at the edge band 1 / (2 pi t_e) (inf if that is inductive)."""
    s = circuit.src(f"cap:{o.name}", o.a, o.b, o.pa, o.pb, kind="adjoint")
    circuit.sources.remove(s)

    def z(f):
        V = circuit.solve(f, [s])[s.name]["V"]
        return complex(V.get(o.b, 0) - V.get(o.a, 0))
    R = max(z(F_LO).real, 0.0)
    fe = 1 / (2 * math.pi * t_e)
    x = z(fe).imag
    return R, (-1 / (2 * math.pi * fe * x) if x < 0 else math.inf)


def swing(v, V0):
    """(V, t_v) of an aggressor at one corner's values v: a cell's bus and voltage edge, else its meta
    voltage V0 and its edge t_i."""
    return float(v.get("V_V") or V0), float(v.get("t_v_s") or v.get("t_i_s") or 1e-9)


def edge_gain(V, t_v, R, C):
    """Peak victim volts per farad of C_m for a swing V in t_v into R || C."""
    if R <= 0 or t_v <= 0:
        return 0.0
    return V / t_v * R * -math.expm1(-t_v / (R * C)) if math.isfinite(C) and C > 0 else 0.0


def strip_C_per_mm(w, h, er, surface):
    """C' (F/mm) of a zero-thickness strip of width w at height h (mm) over a plane: c^-2 eps_eff / L'
    with the air inductance of kae.em.pnr (Hammerstad-Jensen) and eps_eff of the microstrip (surface)
    or of the filled dielectric (buried)."""
    from .pnr import strip_L_per_mm
    w, h = np.maximum(w, 1e-3), np.maximum(h, 1e-3)
    ee = (er + 1) / 2 + (er - 1) / 2 / np.sqrt(1 + 12 * h / w) if surface else er
    return ee / (C0 ** 2 * strip_L_per_mm(w, h, t=1e-6) * 1e6)


def coplanar_C_per_mm(w, g, er, surface):
    """C' (F/mm) of a strip of width w to coplanar copper at gap g on one side: 2 eps0 eps K(k) / K(k'),
    k = w / (w + 2 g), eps the mean of the two half spaces at a surface."""
    from scipy.special import ellipk
    k = np.clip(w / (w + 2 * np.maximum(g, 1e-3)), 1e-6, 1 - 1e-9)
    ee = (er + 1) / 2 if surface else er
    return 2 * EPS0 * ee * ellipk(k * k) / ellipk(1 - k * k) * 1e-3


_KAPPA = {}


def raster_kappa(wq, h, er, pitch, surface):
    """The static raster's C' of a strip (width wq, at h over a plane, mm) over the closed form's: the
    raster's charge is uniform per cell where the true one crowds to the edges, so it is low by up to a
    quarter where w ~ h (two lengths' difference cancels the ends). Cached per geometry."""
    key = (round(wq, 4), round(h, 3), round(er, 3), round(pitch, 4), surface)
    if key not in _KAPPA:
        from .mesh import Layer, Mesh
        from .static import Electrostatic, Stack
        gw = math.ceil(max(8 * h, 4.0) / pitch) * pitch
        q = []
        for length in (8.0, 16.0):
            m = Mesh.over(0, -gw, length + 2, gw, pitch, [Layer("T", h, 0.035, 1), Layer("G", 0, 0.035, 1)])
            m.rect(1, "GND", 0, -gw, length + 2, gw)
            m.rect(0, "S", 1, 0, 1 + length, wq)
            st = Stack([0.0, h * 1e-3], [er]) if surface else Stack([0.0, h * 1e-3, 2 * h * 1e-3], [er, er])
            C, _ = Electrostatic(m, st, [h * 1e-3, 0.0]).capacitance(["S"])
            q.append(C["S"]["S"])
        _KAPPA[key] = float((q[1] - q[0]) / 8.0 / strip_C_per_mm(wq, h, er, surface))
    return _KAPPA[key]


class Fields:
    """One state of the capacitive fields: the static raster's labels, each driven net's cell charges and
    potentials, its Maxwell column, the pairs' C_m, harms per corner and weights, the hop prices."""

    def __init__(self, mesh, lab=None, nets=None):
        self.mesh = mesh
        self.lab = mesh.lab.copy() if lab is None else lab
        self.nets = list(mesh.nets) if nets is None else nets
        self.layers, self.pitch, self.x0, self.y0 = mesh.layers, mesh.pitch, mesh.x0, mesh.y0
        self.Q, self.pot, self.col = {}, {}, {}
        self.Cm, self.Cself, self.g, self.u, self.W = {}, {}, {}, {}, {}
        self.Phi, self._cp = {}, {}
        self.its, self.stale = [], set()

    def cell(self, x, y):
        return int(math.floor((y - self.y0) / self.pitch)), int(math.floor((x - self.x0) / self.pitch))


class CapPrices:
    """The capacitive pairs of a board and their prices for kae.em.pnr.PhysRouter (`cap`); the field
    state lives in the router's `capf` (a new Fields per solve or hop, so its candidates can restore it)."""

    def __init__(self, bd, brief, srcs, obs, cval, log=print, tol=1e-6):
        from kae.excite.capacitive import aggressors
        self.log, self.tol, self.cval = log, tol, cval
        agg = aggressors(bd, brief, srcs)
        src_of = {}
        for s in srcs:
            n = s.meta.get("sw") if s.kind == "cell" else s.meta.get("net") if s.kind == "clock" else None
            if n in agg:
                src_of.setdefault(n, s)
        # a victim tied to the aggressor through one part (a crystal's two pins, a bootstrap capacitor) is
        # left out: that part's coupling is the circuit's, and dwarfs the copper's
        tied = {frozenset((e.a, e.b)) for e in bd.circuit.elems}
        self.pairs = []
        for o in obs:
            if o.kind != "victim" or not o.bound:
                continue
            n = o.meta.get("net")
            for a, s in src_of.items():
                if a == n or frozenset((a, n)) in tied:
                    continue
                V0 = float(s.meta.get("V") or 3.3)
                t_e = float(np.median([swing(v, V0)[1] for v in cval[s.name]]))
                R, C = victim_rc(bd.circuit, o, t_e)
                self.pairs.append(dict(obs=o.name, src=s.name, a=a, n=n, bound=o.bound, R=R, Cc=C, V0=V0))
                log(f"cap: pair {o.name} <- {a} ({s.name}): victim node R {R / 1e3:.3g} kOhm, circuit C "
                    f"{C * 1e12:.3g} pF at the {t_e * 1e9:.2g} ns edge, bound {o.bound * 1e3:.3g} mV")
        self.nets = sorted({p["a"] for p in self.pairs} | {p["n"] for p in self.pairs})
        self._es = None

    # ------------------------------------------------------------------ solves
    def _operator(self, bm, b):
        from kae.excite.capacitive import stack_of
        from .static import Electrostatic
        m = bm.m
        st, zs = stack_of(bm, b.stackup)
        key = (m.nx, m.ny, m.pitch, tuple(zs), tuple(st.z), tuple(st.eps))
        if self._es is None or self._es[0] != key:
            t0 = time.time()
            self._es = (key, Electrostatic(m, st, zs))
            self.log(f"cap: static kernels {m.nx}x{m.ny}x{len(m.layers)} in {time.time() - t0:.1f}s")
        es = self._es[1]
        es.m = m
        return es

    def solve(self, bm, b, prev=None):
        """Every field on the router's mesh as it stands (a refresh)."""
        if not self.pairs:
            return None
        es = self._operator(bm, b)
        m = bm.m
        F = Fields(m)
        self._drive(es, F, [n for n in self.nets if n in F.nets], prev)
        self._pairs(F)
        if prev is not None and prev.Cm:
            self.log("cap: refresh: C_m " + ", ".join(f"{k[1][:20]}~{k[2][:20]} {prev.Cm.get(k, 0) * 1e15:.2f} -> "
                                                      f"{v * 1e15:.2f} fF" for k, v in F.Cm.items()))
        return F

    def _drive(self, es, F, nets, prev=None):
        """Charges, potentials and Maxwell columns of `nets` at 1 V in turn on F's raster (in place);
        conjugate gradients start from prev's charges where it has them."""
        t0 = time.time()
        lab = F.lab
        idx = np.nonzero(lab >= 0)
        t00 = np.array([es._t00(l) for l in range(es.L)])
        for n in nets:
            k = F.nets.index(n)
            v = (lab[idx] == k).astype(float)
            if not v.any():
                continue
            q0 = prev.Q[n][idx] if prev is not None and n in prev.Q and prev.Q[n].shape == lab.shape else None
            q, its = es._cg(v, idx, t00, self.tol, 2000, q0=q0)
            Q = np.zeros(lab.shape)
            Q[idx] = q
            F.Q[n], F.pot[n] = Q, np.clip(es.apply(Q), 0.0, 1.0)
            F.col[n] = np.bincount(lab[idx], weights=q, minlength=len(F.nets))
            F.its.append(its)
        F.seconds = time.time() - t0

    def _pairs(self, F):
        """C_m of every pair (the mean of both columns, Maxwell's matrix being symmetric; only the fresh
        one's where the other predates new copper), each victim's own capacitance, and u per corner."""
        for n in self.nets:
            if n in F.col:
                F.Cself[n] = float(F.col[n][F.nets.index(n)])
        for p in self.pairs:
            a, n = p["a"], p["n"]
            if a not in F.col or n not in F.col:
                continue
            key = (p["obs"], a, n)
            cols = [-F.col[x][F.nets.index(y)] for x, y in ((a, n), (n, a)) if x not in F.stale] or \
                [-F.col[a][F.nets.index(n)], -F.col[n][F.nets.index(a)]]
            F.Cm[key] = max(float(np.mean(cols)), 0.0)
            Cn = p["Cc"] + F.Cself[n]
            F.g[key] = np.array([edge_gain(*swing(v, p["V0"]), p["R"], Cn) / p["bound"] for v in self.cval[p["src"]]])
            F.u[key] = F.g[key] * F.Cm[key]

    # ------------------------------------------------------------------ objective
    def corner_phi(self, F):
        """Per corner, the sum of phi(u) over the pairs (joins the router's totals)."""
        if F is None or not F.u:
            return 0.0
        return np.sum([[phi(x) for x in us] for us in F.u.values()], axis=0)

    def set_weights(self, F, idx, phi_prime):
        """W per pair: the robust objective's derivative per farad over its corners idx; then the hop price
        fields Phi_X (per farad of C' per mm: harm per mm once multiplied by C')."""
        if F is None:
            return
        for key, us in F.u.items():
            g = F.g[key]
            F.W[key] = float(np.mean([phi_prime(us[c]) * g[c] for c in idx]))
        self._phi_fields(F)

    def _phi_fields(self, F):
        F.Phi = {}
        for (o, a, n), W in F.W.items():
            if n in F.pot:
                F.Phi[a] = F.Phi.get(a, 0.0) + W * F.pot[n]      # a's copper priced by the victim's field
            if a in F.pot:
                F.Phi[n] = F.Phi.get(n, 0.0) + W * F.pot[a]      # the victim's copper by the aggressor's

    def report(self, F):
        if F is None:
            return ""
        return "; ".join(f"{o} <- {a}: C_m {F.Cm[(o, a, n)] * 1e15:.2f} fF, C_node {(self._pair(o, a)['Cc'] + F.Cself[n]) * 1e12:.2f} pF, "
                         f"u typ {F.u[(o, a, n)][0]:.3g} max {F.u[(o, a, n)].max():.3g}, W {F.W.get((o, a, n), 0) * 1e-15:.3g}/fF"
                         for (o, a, n) in F.Cm)

    def _pair(self, o, a):
        return next(p for p in self.pairs if p["obs"] == o and p["a"] == a)

    # ------------------------------------------------------------------ prices
    @staticmethod
    def wq(w, pitch):
        """The width the static raster carries for a track of width w."""
        return pitch if w < 3 * pitch else w

    def cprime(self, F, L, w, net):
        """C' (F/mm) of a track of net `net`, width w, on every cell of layer L of F's raster."""
        key = (L, round(w, 4), net)
        if key in F._cp:
            return F._cp[key]
        from scipy import ndimage
        from . import t1 as T1
        m = F.mesh
        es = self._es[1]
        wq = self.wq(w, F.pitch)
        own = F.nets.index(net) if net in F.nets else -2
        mm = copy.copy(m)
        mm.lab = F.lab
        up, dn, _, _, _, _ = T1.references(mm, L, None)
        zL = es.z[L]
        nl = len(F.layers)
        surface = L in (0, nl - 1)
        C = np.zeros((m.ny, m.nx))
        hs = []
        for ref in (up, dn):
            # heights between the solver's sheets (the dielectric gaps, copper thickness folded out)
            er, h = np.ones((m.ny, m.nx)), np.full((m.ny, m.nx), np.inf)
            for k in np.unique(ref[ref >= 0]):
                er[ref == k] = self._eps_between(es.stack, zL, es.z[int(k)])
                h[ref == k] = abs(es.z[int(k)] - zL) * 1e3
            hs.append(h)
            C += np.where(np.isfinite(h), strip_C_per_mm(wq, np.where(np.isfinite(h), h, 1.0), er, surface), 0.0)
        hmin = np.minimum(*hs)
        if np.isfinite(hmin).any():
            h0 = float(np.median(hmin[np.isfinite(hmin)]))
            C *= raster_kappa(wq, h0, float(np.mean(es.stack.eps)), F.pitch, surface)
        other = (F.lab[L] >= 0) & (F.lab[L] != own)
        g = ndimage.distance_transform_edt(~other) * F.pitch - wq / 2 if other.any() else np.full((m.ny, m.nx), np.inf)
        g = np.maximum(g, 0.05)
        er0 = float(np.mean(es.stack.eps))
        plane = np.isfinite(hmin)
        # beside a plane, coplanar copper takes part of the field the plane would: the raster's strip
        # beside a wide coplanar conductor adds C_ms CO_A exp(-CO_B g / h) (the fit of CO_A, CO_B)
        C = np.where(plane, C * (1 + CO_A * np.exp(-CO_B * g / np.where(plane, hmin, 1.0))), C)
        # no plane: the nearest coplanar copper, else a plane at H_NONE
        lone = ~plane
        if lone.any():
            C[lone] = np.where(np.isfinite(g[lone]), coplanar_C_per_mm(wq, np.where(np.isfinite(g[lone]), g[lone], 1.0), er0, surface),
                               strip_C_per_mm(wq, H_NONE, er0, surface))
        F._cp[key] = C
        return C

    @staticmethod
    def _eps_between(stack, z1, z2):
        """Thickness-weighted permittivity of the dielectric between heights z1 and z2 (m)."""
        lo, hi = min(z1, z2), max(z1, z2)
        if hi - lo < 1e-12:
            return float(np.mean(stack.eps))
        zz, e = stack.z, stack.eps
        tot = sum(max(0.0, min(hi, zz[i + 1]) - max(lo, zz[i])) * e[i] for i in range(len(e)))
        return float(tot / (hi - lo)) if tot > 0 else 1.0

    def cost(self, F, net, w, L, sel):
        """Harm per mm of a hop of `net` (width w) on layer L, at the routing grid's cells `sel`, or None."""
        if F is None or net not in F.Phi:
            return None
        return (self.cprime(F, L, w, net) * F.Phi[net][L])[sel]

    def predict(self, F, net, new, w):
        """{pair: predicted dC_m (F)} of new copper of `net` (mask (L, ny, nx) of the cells it paints) from
        F's fields: C' phi_other p summed over the cells, the raster's own quadrature of the path integral
        the search pays (which differs by the cells a pad's edge cuts and by a diagonal's staircase)."""
        out = {}
        for (o, a, n) in F.Cm:
            other = n if net == a else a if net == n else None
            if other is None or other not in F.pot:
                continue
            out[(o, a, n)] = sum(float((self.cprime(F, L, w, net)[new[L]] * F.pot[other][L][new[L]]).sum()) * F.pitch
                                 for L in range(len(F.layers)) if new[L].any())
        return out

    def after_hop(self, F, net, segs, vias, w, via_d, layer_names):
        """A committed hop of `net`: (new Fields with its copper painted and its own field re-solved,
        {pair: (predicted, actual) dC_m}); F itself when the hop's net has no pair."""
        if F is None or net not in self.nets:
            return F, {}
        from shapely.geometry import LineString, Point
        m = F.mesh
        mm = copy.copy(m)
        mm.lab, mm.cov, mm.thin, mm.nets = F.lab.copy(), m.cov.copy(), {}, list(F.nets)
        for l, p0, p1 in segs:
            if l not in layer_names:
                continue
            L = layer_names.index(l)
            if w < 3 * F.pitch:
                mm.paint_line(L, net, [p0, p1], w)
            else:
                mm.paint(L, net, geom=LineString([p0, p1]).buffer(w / 2, quad_segs=8))
        for (x, y) in vias:
            j, i = mm.cell(x, y)
            for L in range(len(F.layers)):
                mm.paint(L, net, geom=Point(x, y).buffer(via_d / 2, quad_segs=8))
                if 0 <= j < mm.ny and 0 <= i < mm.nx:
                    mm.lab[L, j, i] = mm.net_id(net)
        k = mm.nets.index(net)
        pred = self.predict(F, net, (mm.lab == k) & (F.lab != (F.nets.index(net) if net in F.nets else -2)), w)
        G = Fields(mm, mm.lab, mm.nets)
        G.Q, G.pot, G.col = dict(F.Q), dict(F.pot), dict(F.col)
        # only the hop net's field is re-solved: it is the one the hop changes at first order (its partners'
        # copper is priced by it). The others keep their fields, which miss the new copper's screening
        # (second order) until the refresh, and their columns are not read for the pairs it touches.
        G.stale = (F.stale | set(self.nets)) - {net}
        self._drive(self._es[1], G, [net] if net in G.nets else [], prev=F)
        self._pairs(G)
        G.W = dict(F.W)
        self._phi_fields(G)
        out = {k: (pred.get(k, 0.0), G.Cm[k] - F.Cm.get(k, 0.0)) for k in G.Cm if k in pred}
        return G, out

    def hop(self, R, net, rt):
        """kae.em.pnr's hook after a committed physics hop: the fields with its copper, the predicted
        against the solved change of each of its pairs' C_m logged, the predicted harm added to the
        router's running prediction. Returns the new Fields."""
        F = R.capf
        if F is None or net not in self.nets:
            return F
        D = R.sp.via_size(net)[0] if rt.vias else 0.6
        G, ch = self.after_hop(F, net, rt.segs, rt.vias, rt.width, D, R.layer_names)
        for key, (p, x) in ch.items():
            R._pred = (R._pred or 0.0) + F.W.get(key, 0.0) * p
            R.log(f"cap:   hop {net}: C_m {key[0]} <- {key[1]} {F.Cm[key] * 1e15:.2f} -> {G.Cm[key] * 1e15:.2f} fF: "
                  f"change predicted {p * 1e15:+.3f}, solved {x * 1e15:+.3f} fF; u typ {F.u[key][0]:.3g} -> {G.u[key][0]:.3g} "
                  f"(CG {G.its}, {G.seconds:.1f}s)")
        return G
