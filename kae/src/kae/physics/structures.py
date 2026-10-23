# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Structure models of the place terms: each returns a spend in physical units from the
current poses, through a shared pose state (lists X, Y, C, S, G per part: position,
cos/sin of the rotation, side sign).

A structure is a sum (or other reduction) of *components*; each component depends on a
few parts and is cached by Terms against those parts' pose epochs, so a move recomputes
only what it touches. Models (derivations and validation: docs/topics/physics/place-terms.md):

* `LoopComp`: loop inductance of a chain of terminals (commutation cell; decap loop) by
  partial inductances with images (_kernels.loop_core): board hops are strips at the
  reference-plane height under them, stretched by their expected detour 1 + c sqrt(l);
  part-internal paths are strips at the body height with vertical terminations; a ground
  hop over a plane of its own net is combined in parallel with the via return through
  that plane (two-mesh formula).
* `DecapLoop`: a decap loop through the rail and ground pours when both join its ends
  (mounting + plane-pair spreading (mu0 d / 2 pi) ln(D^2 / r^2)), else its LoopComp.
  `PlanePairLoop` is the earlier adjacent-plane-pair form, kept for tools.
* `CouplingComp`: aggressor-victim coupling: Neumann mutual of the two loops with images
  (inductive, M di/dt) and patch mutual capacitance (C dv/dt into the victim impedance),
  as two sub-terms that `CouplingEngine` evaluates in batches.
* `CrystalComp`: Pierce load pulling from the trace capacitance of the XIN/XOUT nets.
* `ThermalField`: fin kernel with adiabatic-edge images; victims' rise from all sources
  and each source's own rise, incremental by rows and columns.
* `CmComp`, `EsdComp`, `FeedComp`: world node (cable common-mode current, windowed by the
  copper gap), protection order (ESD loop inductance), antenna feed loss.
"""
from __future__ import annotations

import math

import numpy as np

from . import fastloop as FL
from .kernels import EPS0, cprime_hj, lprime_hj, trapezoid_envelope
from .priors import WORLD

INF = float('inf')
_hyp = math.hypot
WIN_R = (WORLD['cm_r0_mm'], WORLD['cm_r1_mm'])       # cable-pickup window (CmComp)


class Term:
    """A terminal: part i, library-frame point (lx, ly), effective width a (mm), and the
    pad indices it stands for (ks; the point is their centroid)."""
    __slots__ = ('i', 'lx', 'ly', 'a', 'net', 'ks')

    def __init__(self, i, lx, ly, a, net='', ks=()):
        self.i, self.lx, self.ly, self.a, self.net = i, float(lx), float(ly), float(a), net
        self.ks = tuple(ks)


def txy(st, t):
    i = t.i
    c, s, g = st.C[i], st.S[i], st.G[i]
    ly = t.ly * g
    return st.X[i] + t.lx * c + ly * s, st.Y[i] - t.lx * s + ly * c


class State:
    """Pose arrays shared by all components: Python lists for scalar access and numpy
    mirrors for the JIT kernels (kept in step by `set`)."""

    def __init__(self, n):
        self.X = [0.0] * n
        self.Y = [0.0] * n
        self.R = [0.0] * n
        self.C = [1.0] * n
        self.S = [0.0] * n
        self.G = [1.0] * n
        self.Xa = np.zeros(n)
        self.Ya = np.zeros(n)
        self.Ca = np.ones(n)
        self.Sa = np.zeros(n)
        self.Ga = np.ones(n)
        # pose ids: every `set` draws a fresh id, so a value cached against its parts' ids
        # is exact; a caller restoring a saved pose may restore its id (see Terms._delta)
        self.V = [0] * n
        self._vid = 0

    def set(self, i, x, y, rot, side):
        x = float(x)
        y = float(y)
        self.X[i] = x
        self.Y[i] = y
        rot = float(rot) % 360.0
        self.R[i] = rot
        if rot == 0.0:
            c, s = 1.0, 0.0
        elif rot == 90.0:
            c, s = 0.0, 1.0
        elif rot == 180.0:
            c, s = -1.0, 0.0
        elif rot == 270.0:
            c, s = 0.0, -1.0
        else:
            r = math.radians(rot)
            c, s = math.cos(r), math.sin(r)
        self.C[i] = c
        self.S[i] = s
        if isinstance(side, str):
            g = -1.0 if side[:1] in ('B', 'b') else 1.0
        else:
            g = -1.0 if side < 0 else 1.0
        self.G[i] = g
        self.Xa[i] = x
        self.Ya[i] = y
        self.Ca[i] = c
        self.Sa[i] = s
        self.Ga[i] = g
        self._vid += 1
        self.V[i] = self._vid

    def get(self, i):
        return (self.X[i], self.Y[i], self.R[i], 'F' if self.G[i] > 0 else 'B')


# ============================================================================ loops
class LoopComp:
    """Loop inductance (nH) of a closed chain of terminals (kernel: jit.loop_core).

    terms: list of Term in current order; kinds[k] for the hop T_k -> T_{k+1}: 'board' or
    'body'; widths[k]; zb[k] body height for 'body' hops; gnd_hop: index of the board hop
    on the return (ground) net, or None; gnd_nets: set of ground net names."""

    def __init__(self, bv, terms, kinds, widths, zb, gnd_hop=None, gnd_nets=(), knobs=None, rvia=0.15, kern=None,
                 body_min=None, detour=1.0):
        self.bv = bv
        self.T = terms
        self.kinds = kinds
        self.w = widths
        self.zb = zb
        self.gnd_hop = gnd_hop
        self.gnd_nets = set(gnd_nets)
        self.parts = tuple(sorted({t.i for t in terms}))
        self.cos_min = knobs.pair_cos_min if knobs else 0.3
        self.detour = float(detour)          # c of the expected detour 1 + c sqrt(l) (priors.HOP_DETOUR)
        self.rvia = rvia
        n = len(terms)
        self.n = n
        bodyd = []
        for k in range(n):
            t0, t1 = terms[k], terms[(k + 1) % n]
            d = _hyp(t0.lx - t1.lx, t0.ly - t1.ly) if kinds[k] == 'body' else 0.0
            if kinds[k] == 'body' and body_min:
                # two pad groups whose centroids nearly coincide (interleaved BGA balls) are
                # still at least one pad pitch apart
                d = max(d, body_min[k])
            bodyd.append(d)
        self.l_ti = [t.i for t in terms]
        self.l_lx = [t.lx for t in terms]
        self.l_ly = [t.ly for t in terms]
        self.l_body = [k == 'body' for k in kinds]
        self.l_w = list(map(float, widths))
        self.l_zb = list(map(float, zb))
        self.l_bd = bodyd
        self.a_ti = np.array(self.l_ti, np.int64)
        self.a_lx = np.array(self.l_lx)
        self.a_ly = np.array(self.l_ly)
        self.a_body = np.array(self.l_body, np.bool_)
        self.a_w = np.array(self.l_w)
        self.a_zb = np.array(self.l_zb)
        self.a_bd = np.array(bodyd)
        self.g = -1 if gnd_hop is None else int(gnd_hop)
        self.l_scr = ([0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n)
        self.a_scr = (np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n))
        self.kern = kern

    def value(self, st):
        bv = self.bv
        x0, y0, res, Hf, Nf = bv._hraster[1]
        _, _, _, Hb, Nb = bv._hraster[-1]
        if self.kern is not None:
            return self.kern.loop_core(st.Xa, st.Ya, st.Ca, st.Sa, st.Ga, self.a_ti, self.a_lx, self.a_ly, self.a_body,
                                       self.a_w, self.a_zb, self.a_bd, self.n, self.g, self.cos_min, bv.clearance,
                                       self.detour,
                                       bv.thickness, self.rvia, Hf, Hb, Nf, Nb, bv.gmask(self.gnd_nets), x0, y0, res,
                                       *self.a_scr)
        from .jit import PY
        return PY.loop_core(st.X, st.Y, st.C, st.S, st.G, self.l_ti, self.l_lx, self.l_ly, self.l_body, self.l_w,
                            self.l_zb, self.l_bd, self.n, self.g, self.cos_min, bv.clearance, self.detour,
                            bv.thickness, self.rvia,
                            Hf, Hb, Nf, Nb, bv.gmask(self.gnd_nets), x0, y0, res, *self.l_scr)


class NearestLoopComp:
    """Loop inductance (nH) to the nearest of several candidate load pins: a capacitor on a
    rail with many interchangeable loads serves whichever load it sits next to. Each
    candidate is a LoopComp [load power pin, cap rail pad, cap ground pad, load return]; the
    nearest by power-pin to rail-pad distance at the current poses is evaluated.

    A rail with n loads and n caps gives n such components over the same n loads, so moving
    one load touches all of them; each candidate's value is therefore cached against its
    parts' pose ids (State.V), and a move that leaves a cap's nearest load unchanged costs
    only the nearest-pin search."""

    def __init__(self, loops):
        self.loops = loops
        self.tr = loops[0].T[1]
        self.parts = tuple(sorted({i for c in loops for i in c.parts}))
        self.mode = None              # the evaluated candidate's mode ('pour', 'hops', None)
        self._cand = [(c.T[0].i, c.T[0].lx, c.T[0].ly) for c in loops]
        self._memo = [None] * len(loops)

    @property
    def kern(self):
        return self.loops[0].kern

    @kern.setter
    def kern(self, k):
        for c in self.loops:
            c.kern = k
        self._memo = [None] * len(self.loops)

    def value(self, st):
        x, y = txy(st, self.tr)
        X, Y, C, S, G = st.X, st.Y, st.C, st.S, st.G
        b = 0
        bd = INF
        for k, (i, lx, ly) in enumerate(self._cand):
            c = C[i]
            s = S[i]
            gy = ly * G[i]
            dx = X[i] + lx * c + gy * s - x
            dy = Y[i] - lx * s + gy * c - y
            d = dx * dx + dy * dy
            if d < bd:
                bd = d
                b = k
        best = self.loops[b]
        V = st.V
        key = tuple([V[i] for i in best.parts])
        m = self._memo[b]
        if m is not None and m[0] == key:
            self.mode = m[2]
            return m[1]
        v = best.value(st)
        self.mode = getattr(best, 'mode', None)
        self._memo[b] = (key, v, self.mode)
        return v


class PlanePairLoop:
    """Decap loop over a rail/ground plane pair: cap mounting + spreading + IC mounting."""

    def __init__(self, bv, t_pwr, cap_terms, d_pair, mount_cap, mount_ic, r_eff=0.3):
        self.bv = bv
        self.tp = t_pwr          # IC power terminal
        self.tc = cap_terms      # (rail pad terminal, gnd pad terminal)
        self.d = d_pair
        self.mc = mount_cap      # function(h) -> nH
        self.mi = mount_ic
        self.r = r_eff
        self.parts = tuple(sorted({t_pwr.i, cap_terms[0].i}))

    def value(self, st):
        px, py = txy(st, self.tp)
        cx, cy = txy(st, self.tc[0])
        D = max(_hyp(px - cx, py - cy), self.r)
        side = st.G[self.tc[0].i]
        h = self.bv.h_ref(side, cx, cy)
        return self.mc(h if h != INF else self.bv.thickness) + self.mi + \
            0.2 * self.d * math.log(D * D / (self.r * self.r))


class DecapLoop:
    """Decoupling loop IC power pin -> capacitor -> IC return, pour-aware. When a zone of
    the rail on layer Lr joins the IC power pin and the capacitor's rail pad and a ground
    zone on Lg joins the capacitor's ground pad and the IC return (at the current poses;
    pairs tried in the order given), the current spreads in those pours: the loop is the
    capacitor's mounting and the IC's mounting down to the nearer of the two layers plus the
    spreading between them, (mu0 d / 2 pi) ln(D^2 / r^2) with d = |z(Lr) - z(Lg)|, D the
    IC pin to capacitor distance (r = 0.3 mm). Otherwise it is the straight-hop loop
    (LoopComp, with its expected detours)."""

    def __init__(self, bv, loop, pairs, rail, gnd_nets, mount_cap, mount_ic, r_eff=0.3):
        self.bv = bv
        self.loop = loop
        self.T = loop.T
        self.tp, self.tr, self.tc, self.tg = loop.T
        self.pairs = pairs            # [(Lr, Lg, d)]
        self.rail = rail
        self.gnd = set(gnd_nets)
        self.mc = mount_cap           # function(h) -> nH
        self.mi = mount_ic
        self.r = r_eff
        self.parts = loop.parts
        self.mode = None              # 'pour' or 'hops' at the last evaluation

    @property
    def kern(self):
        return self.loop.kern

    @kern.setter
    def kern(self, k):
        self.loop.kern = k

    def _depth(self, side, ly):
        bv = self.bv
        z = bv.zcu[ly]
        return z if side > 0 else bv.zcu[bv.copper[-1]] - z

    def value(self, st):
        if self.pairs:
            bv = self.bv
            pi = txy(st, self.tp)
            pr = txy(st, self.tr)
            pc = txy(st, self.tc)
            pg = txy(st, self.tg)
            for lr, lg, d in self.pairs:
                a = bv.zone_piece(lr, pi[0], pi[1])
                if a < 0 or a != bv.zone_piece(lr, pr[0], pr[1]) or bv.zone_labels(lr)[1][a] != self.rail:
                    continue
                b = bv.zone_piece(lg, pc[0], pc[1])
                if b < 0 or b != bv.zone_piece(lg, pg[0], pg[1]) or bv.zone_labels(lg)[1][b] not in self.gnd:
                    continue
                sc = st.G[self.tr.i]
                si = st.G[self.tp.i]
                hc = min(self._depth(sc, lr), self._depth(sc, lg))
                hi = min(self._depth(si, lr), self._depth(si, lg))
                D = max(_hyp(pi[0] - pr[0], pi[1] - pr[1]), self.r)
                self.mode = 'pour'
                return self.mc(hc) + self.mi(hi) + 0.2 * d * math.log(D * D / (self.r * self.r))
        self.mode = 'hops'
        return self.loop.value(st)


# ============================================================================ coupling
def _loop_points(st, terms, closed):
    return [txy(st, t) for t in terms] + ([txy(st, terms[0])] if closed else [])




class LoopShape:
    """A loop for coupling: terminals in order, closed on top or (closed=False) through the
    reference plane by vias at both ends. Geometry is cached per pose of its parts."""

    def __init__(self, terms, closed=True, z_extra=0.0):
        self.T = terms
        self.closed = closed
        self.z = z_extra
        self.parts = tuple(sorted({t.i for t in terms}))
        self._key = None
        self._geo = None

    def points(self, st):
        return _loop_points(st, self.T, self.closed)

    def geo(self, st):
        """(points list, centroid (x, y), size, signed area, chord (dx, dy))."""
        key = tuple((st.X[i], st.Y[i], st.R[i], st.G[i]) for i in self.parts)
        if key != self._key:
            pts = self.points(st)
            n = len(pts) - (1 if self.closed else 0)
            cx = sum(p[0] for p in pts[:n]) / n
            cy = sum(p[1] for p in pts[:n]) / n
            size = max(max(abs(p[0] - cx), abs(p[1] - cy)) for p in pts) * 2.0
            area = 0.0
            if self.closed:
                for a, b in zip(pts[:-1], pts[1:]):
                    area += a[0] * b[1] - a[1] * b[0]
                area *= 0.5
            chord = (pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
            self._geo = (pts, (cx, cy), size, area, chord)
            self._arr = np.array(pts[:n], float)
            self._key = key
        return self._geo

    def arr(self, st):
        self.geo(st)
        return self._arr


class NodeShape:
    """Copper of a net for capacitive coupling: its pads (terminals with areas) plus the
    expected hops between consecutive pads (strips of width w). Cached per pose."""

    def __init__(self, terms, areas, w=0.25):
        self.T = terms
        self.A = areas
        self.w = w
        self.parts = tuple(sorted({t.i for t in terms}))
        self._key = None
        self._pat = None

    def patches(self, st):
        key = tuple((st.X[i], st.Y[i], st.R[i], st.G[i]) for i in self.parts)
        if key != self._key:
            P = [txy(st, t) for t in self.T]
            out = [(x, y, a) for (x, y), a in zip(P, self.A)]
            for (x0, y0), (x1, y1) in zip(P[:-1], P[1:]):
                ln = _hyp(x1 - x0, y1 - y0)
                if ln > 1e-6 and self.w > 0:
                    out.append((0.5 * (x0 + x1), 0.5 * (y0 + y1), ln * self.w))
            at = sum(a for _, _, a in out) or 1e-6
            cx = sum(x * a for x, _, a in out) / at
            cy = sum(y * a for _, y, a in out) / at
            ext = max(max(abs(x - cx), abs(y - cy)) for x, y, _ in out) * 2.0
            self._pat = (out, cx, cy, at, ext)
            a = np.array(out, float)
            self._arrs = (np.ascontiguousarray(a[:, 0]), np.ascontiguousarray(a[:, 1]), np.ascontiguousarray(a[:, 2]))
            self._key = key
        return self._pat

    def arrs(self, st):
        self.patches(st)
        return self._arrs


_SCR = None


def _scratch():
    global _SCR
    if _SCR is None:
        _SCR = tuple(np.zeros((512, 3)) for _ in range(4))
    return _SCR


def _mutual(kern, al, vl, st, h):
    """|M| (nH) between an aggressor and a victim LoopShape (kernel: jit.loop_mutual_core)."""
    from .jit import GAUSS, PY
    kern = kern or PY
    PA = al.arr(st)
    PV = vl.arr(st)
    za = (1.6 if h == INF else h) + al.z
    zv = (1.6 if h == INF else h) + vl.z
    return kern.loop_mutual_core(PA, al.closed, za, PV, vl.closed, zv, h, *GAUSS, *_scratch())


def _cself(A, h, eps_r):
    """Capacitance to the plane (pF) of copper of area A at height h in a dielectric eps_r:
    a square of side s with the microstrip per-length capacitance C'(s, h, eps_r) along it
    and its fringe across the ends, s (2 C' - eps0 eps_r s / h) (cf. jit cext)."""
    s = math.sqrt(max(A, 1e-6))
    return s * (2.0 * cprime_hj(s, h, eps_r) - EPS0 * eps_r * s / h)


def _cm(kern, an, vn, st, h, eps_r):
    """Mutual capacitance (pF) between two NodeShapes over the plane at h (kernel:
    jit.patches_cm_core: first order in the potential coefficients with the plane image,
    air-side patch strengths eps0 A / h, lens SY D1)."""
    from .jit import PY
    kern = kern or PY
    xa, ya, aa = an.arrs(st)
    xv, yv, av = vn.arrs(st)
    hh = 1.6 if h == INF else max(h, 0.05)
    return kern.patches_cm_core(xa, ya, aa, xv, yv, av, hh, eps_r, EPS0)


def _sub_parts(a, b):
    return tuple(sorted(set(a.parts) | set(b.parts)))


class _Coupled:
    """An aggressor (loop al, node an) against one target (loop tl, node tn), as two
    additive sub-terms: inductive k_l |M(al, tl)| over the parts of the two loops, and
    capacitive over the parts of the two nodes (jit.ind_one, jit.cap_one; target kind 0 a
    victim, 1 a cable connector). `subparts` lets Terms cache and invalidate the two
    separately; the board's CouplingEngine evaluates any set of sub-terms in one kernel call
    (`pid`: this component's pair index per sub-term, -1 when inactive)."""
    kern = None
    kind_code = 0
    engine = None

    def _setup(self, al, an, tl, tn, k_l, k_c, k_c2):
        self.tl, self.tn = tl, tn
        self.k_l = float(k_l) if (al is not None and tl is not None and k_l > 0) else 0.0
        self.k_c = float(k_c) if (an is not None and tn is not None and k_c > 0) else 0.0
        self.k_c2 = float(k_c2)
        self.subparts = (_sub_parts(al, tl) if self.k_l else (), _sub_parts(an, tn) if self.k_c else ())
        ps = set()
        for o in (al, an, tl, tn):
            if o is not None:
                ps |= set(o.parts)
        self.parts = tuple(sorted(ps))
        self.pid = [-1, -1]

    def value_sub(self, st, si):
        if self.engine is None:
            CouplingEngine(self.bv, [self])
        p = self.pid[si]
        if p < 0:
            return 0.0
        one = np.array([p], np.int64)
        none = np.zeros(0, np.int64)
        ol, oc = self.engine.eval(st, one if si == 0 else none, none if si == 0 else one)
        return float(ol[0] if si == 0 else oc[0])

    def value(self, st):
        return self.value_sub(st, 0) + self.value_sub(st, 1)


class CouplingComp(_Coupled):
    """Noise (mV) one aggressor puts on one victim: |M| di/dt (inductive) + the charge
    division dV Cm / (Cm + C_victim + t_sw / Z_v) of the aggressor's swing (capacitive)."""
    kind_code = 0

    def __init__(self, bv, agg_loop, agg_node, vic_loop, vic_node, didt, dv, t_sw, z_v, gnd_plane):
        self.bv = bv
        self.al, self.an, self.vl, self.vn = agg_loop, agg_node, vic_loop, vic_node
        self.didt, self.dv, self.tsw, self.zv = didt, dv, t_sw, z_v
        self.gp = gnd_plane
        # nH * A/ns = V -> mV; dV Cm / (Cm + Cv + t_sw / Z_v) with t_sw / Z_v in pF (ns * 1e3 / ohm)
        self._setup(agg_loop, agg_node, vic_loop, vic_node, didt * 1e3, dv, t_sw * 1e3 / z_v)


# ============================================================================ crystal
class CrystalComp:
    """Load pulling (ppm) of a Pierce oscillator from the expected trace capacitance."""

    def __init__(self, bv, xin_terms, xout_terms, s_ppm_per_pf, w=0.2, detour=1.0):
        self.bv = bv
        self.detour = float(detour)
        self.ti = xin_terms
        self.to = xout_terms
        self.s = s_ppm_per_pf
        self.w = w
        self.parts = tuple(sorted({t.i for t in xin_terms + xout_terms}))
        self._cp = {}

    def _cprime(self, h):
        key = round(h, 3) if h != INF else INF
        v = self._cp.get(key)
        if v is None:
            if h == INF:
                v = cprime_hj(self.w, self.bv.thickness, 1.0) * 0.6      # no plane: weak, E5
            else:
                v = cprime_hj(self.w, h, self.bv.er)
            self._cp[key] = v
        return v

    def length(self, st, terms):
        xs, ys = zip(*[txy(st, t) for t in terms])
        return (max(xs) - min(xs)) + (max(ys) - min(ys))      # RSMT = HPWL for <= 3 pins

    def value(self, st):
        x0, y0 = txy(st, self.ti[0])
        h = self.bv.h_ref(st.G[self.ti[0].i], x0, y0)
        cp = self._cprime(h)
        li = self.length(st, self.ti)
        lo = self.length(st, self.to)
        c = self.detour
        dcl = cp * (li * (1.0 + c * math.sqrt(li)) + lo * (1.0 + c * math.sqrt(lo))) / 4.0
        return self.s * dcl


# ============================================================================ thermal
class ThermalField:
    """Board temperature rise at victims and sources by the fin kernel with images.

    G(t, s) = sum_images K0(|r_t - r_img|/lam) / (2 pi G_s) over the adiabatic-edge image
    lattice of the board's bounding box (`rings` rings: (2(2 rings + 1))^2 images); a
    source's own rise replaces its real (r ~ 0) term by the disk-averaged self term
    (1 - x K1(x)) / (pi a^2 h_tot), x = a/lam; the images beyond the rings are added as a
    continuum (a constant per watt). Cached as a matrix G[t, s] (K/W); a moved
    source updates a column and its row, a moved victim its row. K0 is the polynomial of
    jit.k0 in both the JIT and the fallback path."""

    def __init__(self, bv, sources, victims, gs, lam, rings=1, kern=None):
        from .jit import PY
        self.kern = kern
        self.py = PY
        self.bv = bv
        self.src = [s[0] for s in sources]
        self.P = np.array([s[1] for s in sources], float)
        self.a = np.array([max(s[2], 0.5) for s in sources], float)
        self.vic = list(victims)
        self.gs = gs
        self.lam = lam
        self.rings = rings
        x0, y0, x1, y1 = bv.bbox
        self.box = (x0, y0, max(x1 - x0, 1e-3), max(y1 - y0, 1e-3))
        self.targets = list(self.src) + [v for v in self.vic]
        self.parts = tuple(sorted(set(self.targets)))
        ns = len(self.src)
        self.G = np.zeros((len(self.targets), ns))
        x = self.a / lam
        htot = gs / (lam * lam)
        k0v = np.array([PY.k0(float(v)) for v in x])
        k1v = np.array([PY.k1(float(v)) for v in x])
        self.selfcorr = (1.0 - x * k1v) / (math.pi * self.a * self.a * htot) - k0v / (2.0 * math.pi * gs)
        r = rings
        self.ms = np.arange(-r, r + 1, dtype=float)
        self.norm = 1.0 / (2.0 * math.pi * gs)
        # images beyond the computed rings, as a continuum of density 1/(Lx Ly) outside the
        # radius R of the computed lattice: lam R K1(R/lam) / (G_s Lx Ly), the same at every
        # target (it restores the board's total heat balance; rankings are unaffected)
        Lx, Ly = self.box[2], self.box[3]
        R = (2 * r + 1) * 2.0 * math.sqrt(Lx * Ly / math.pi)
        self.tail = lam * R * PY.k1(R / lam) / (gs * Lx * Ly)
        # the board's mean rise (heat balance): placement-invariant, subtracted before the
        # budgets apply (only the local excess above it can be changed by placement)
        self.T_mean = float(self.P.sum()) * lam * lam / (gs * Lx * Ly)
        self._colbuf = np.zeros(len(self.targets))
        self._rowbuf = np.zeros(ns)
        self._tidx = np.array(self.targets, np.int64)
        self._sidx = np.array(self.src, np.int64)
        self._boxa = np.array(self.box, float)

    def _imgs(self, xs, ys):
        x0, y0, Lx, Ly = self.box
        u = np.asarray(xs, float)[..., None] - x0
        v = np.asarray(ys, float)[..., None] - y0
        m = self.ms
        ix = x0 + np.concatenate([2 * m * Lx + u, 2 * m * Lx - u], axis=-1)
        iy = y0 + np.concatenate([2 * m * Ly + v, 2 * m * Ly - v], axis=-1)
        return ix, iy

    def _fin(self, tx, ty, ix, iy, a):
        k = self.kern if self.kern is not None else self.py
        return k.fin_sum(tx, ty, ix, iy, a, self.lam)

    def column(self, st, k):
        i = self.src[k]
        out = self._colbuf
        (self.kern or self.py).fin_col_xy(st.Xa, st.Ya, self._tidx, st.X[i], st.Y[i], self._boxa, self.ms, self.a[k],
                                          self.lam, out)
        g = out * self.norm + self.tail
        g[k] += self.selfcorr[k]
        return g

    def row(self, st, t):
        i = self.targets[t]
        out = self._rowbuf
        (self.kern or self.py).fin_row_xy(st.Xa, st.Ya, self._sidx, st.X[i], st.Y[i], self._boxa, self.ms, self.a,
                                          self.lam, out)
        g = out * self.norm + self.tail
        if t < len(self.src):
            g[t] += self.selfcorr[t]
        return g

    def full(self, st):
        for k in range(len(self.src)):
            self.G[:, k] = self.column(st, k)
        return self.G @ self.P


# ============================================================================ world node
class CmComp(_Coupled):
    """Common-mode current (uA) an aggressor drives onto one cable connector's cable:
    omega (M I / Z_cm + Cm V) at f_ref, windowed by the gap between the copper extents
    (priors.WORLD cm_r0_mm, cm_r1_mm)."""
    kind_code = 1

    def __init__(self, bv, agg_loop, agg_node, conn_loop, conn_node, I, V, t_sw, gnd_plane, world):
        self.bv = bv
        self.al, self.an, self.cl, self.cn = agg_loop, agg_node, conn_loop, conn_node
        f = world['f_ref_ghz']
        self.f = f
        self.Iamp = trapezoid_envelope(I, f, world['period_ns'], t_sw)
        self.Vamp = trapezoid_envelope(V, f, world['period_ns'], t_sw)
        self.zcm = world['z_cm']
        self.gp = gnd_plane
        w = 2.0 * math.pi * f          # rad/ns
        # nH * rad/ns * A / ohm = A; pF * rad/ns * V = mA; both to uA
        self._setup(agg_loop, agg_node, conn_loop, conn_node, w * self.Iamp / self.zcm * 1e6, w * self.Vamp * 1e3, 0.0)


class CouplingEngine:
    """Every coupling sub-term of a board (victims, cable connectors) for one kernel call
    over any selection of them (jit.eng_eval): shapes are laid out once as terminal arrays
    and evaluated from the pose arrays, at most once per call."""

    def __init__(self, bv, comps):
        self.bv = bv
        self.kern = None
        self.stamp = 0
        lid, nid = {}, {}
        LT_i, LT_xy, L_meta, L_f = [], [], [], []
        NT_i, NT_xya, N_meta, N_w = [], [], [], []
        npts = [0]

        def loop(o):
            k = lid.get(id(o))
            if k is None:
                k = lid[id(o)] = len(L_meta)
                L_meta.append((len(LT_i), len(o.T)))
                L_f.append((1.0 if o.closed else 0.0, o.z))
                for t in o.T:
                    LT_i.append(t.i)
                    LT_xy.append((t.lx, t.ly))
            return k

        def node(o):
            k = nid.get(id(o))
            if k is None:
                k = nid[id(o)] = len(N_meta)
                n = len(o.T)
                m = n + (n - 1 if o.w > 0 else 0)
                N_meta.append((len(NT_i), n, npts[0], m))
                npts[0] += m
                N_w.append(float(o.w))
                for t, a in zip(o.T, o.A):
                    NT_i.append(t.i)
                    NT_xya.append((t.lx, t.ly, float(a)))
            return k
        Lp, Lk, Cp, Ck = [], [], [], []
        for c in comps:
            c.engine = self
            c.pid = [-1, -1]
            if c.k_l:
                c.pid[0] = len(Lp)
                Lp.append((loop(c.al), loop(c.tl), c.kind_code))
                Lk.append(c.k_l)
            if c.k_c:
                c.pid[1] = len(Cp)
                Cp.append((node(c.an), node(c.tn), c.kind_code))
                Ck.append((c.k_c, c.k_c2))
        i64 = np.int64
        self.LT_i = np.array(LT_i or [0], i64)
        self.LT_xy = np.array(LT_xy or [(0.0, 0.0)], float).reshape(-1, 2)
        self.L_meta = np.array(L_meta or [(0, 0)], i64).reshape(-1, 2)
        self.L_f = np.array(L_f or [(0.0, 0.0)], float).reshape(-1, 2)
        self.NT_i = np.array(NT_i or [0], i64)
        self.NT_xya = np.array(NT_xya or [(0.0, 0.0, 0.0)], float).reshape(-1, 3)
        self.N_meta = np.array(N_meta or [(0, 0, 0, 0)], i64).reshape(-1, 4)
        self.N_w = np.array(N_w or [0.0], float)
        self.Lp = np.array(Lp or [(0, 0, 0)], i64).reshape(-1, 3)
        self.Lk = np.array(Lk or [0.0], float)
        self.Cp = np.array(Cp or [(0, 0, 0)], i64).reshape(-1, 3)
        self.Ck = np.array(Ck or [(0.0, 0.0)], float).reshape(-1, 2)
        nL = self.L_meta.shape[0]
        nN = self.N_meta.shape[0]
        self.GP = np.zeros((max(1, len(LT_i)), 2))
        self.Lc = np.zeros((nL, 3))
        self.Ls = np.full(nL, -1, i64)
        m = max(1, npts[0])
        self.PX, self.PY, self.PA, self.PC = np.zeros(m), np.zeros(m), np.zeros(m), np.zeros(m)
        self.Nc = np.zeros((nN, 4))
        self.Ns = np.full(nN, -1, i64)
        self.n_l = len(Lp)
        self.n_c = len(Cp)

    def eval(self, st, sel_l, sel_c):
        """(inductive values, capacitive values) of the selected pair indices at st's poses."""
        from .jit import GAUSS, PY
        kern = self.kern or PY
        self.stamp += 1
        out_l = np.empty(sel_l.shape[0])
        out_c = np.empty(sel_c.shape[0])
        x0, y0, res, Hf, _ = self.bv._hraster[1]
        Hb = self.bv._hraster[-1][3]
        r0, r1 = WIN_R
        kern.eng_eval(st.Xa, st.Ya, st.Ca, st.Sa, st.Ga, self.LT_i, self.LT_xy, self.L_meta, self.L_f, self.NT_i,
                      self.NT_xya, self.N_meta, self.N_w, Hf, Hb, x0, y0, res, self.bv.er, self.Lp, self.Lk, self.Cp,
                      self.Ck, sel_l, sel_c, r0, r1, self.GP, self.Lc, self.Ls, self.PX, self.PY, self.PA, self.PC,
                      self.Nc, self.Ns, self.stamp, *GAUSS, *_scratch(), out_l, out_c)
        return out_l, out_c


class EsdComp:
    """ESD surge path (nH): the surge enters at the connector pin, runs along the trace to
    the protector and leaves through the protector's ground via into the plane. Its
    inductance L'(w, h) l(conn -> prot) + L_via sets the area over which the surge's dI/dt
    spreads before it is shunted (designers place the protector at the connector and route
    the protected net through its pad, so a lateral offset from the conn -> IC line costs
    nothing). A protector farther from the connector than the protected pin (projected on
    the conn -> IC line) lets the pin see the surge first: the excess is charged twice."""

    def __init__(self, bv, t_conn, t_prot, t_ic, t_prot_gnd, w=0.25, detour=1.0):
        self.bv = bv
        self.detour = float(detour)
        self.tc, self.tp, self.ti, self.tg = t_conn, t_prot, t_ic, t_prot_gnd
        self.w = w
        self._hc = {}
        self.parts = tuple(sorted({t.i for t in (t_conn, t_prot, t_ic) if t is not None}))

    def _lp_lv(self, st, px, py):
        """(L' of the surge trace, L of the protector's via down to the plane under it)."""
        h = self.bv.h_ref(st.G[self.tp.i], px, py)
        hh = self.bv.thickness if h == INF else h
        cc = self._hc.get(hh)
        if cc is None:
            cc = (lprime_hj(self.w, hh), FL.m_self(hh, 0.15) + FL._collinear(hh, hh, 0.0))
            self._hc[hh] = cc
        return cc

    def via(self, st):
        """The via part of the value (nH)."""
        px, py = txy(st, self.tp)
        return self._lp_lv(st, px, py)[1]

    def value(self, st):
        ax, ay = txy(st, self.tc)
        px, py = txy(st, self.tp)
        lp, lv = self._lp_lv(st, px, py)
        ln = _hyp(px - ax, py - ay)
        beyond = 0.0
        if self.ti is not None:
            bx, by = txy(st, self.ti)
            ux, uy = bx - ax, by - ay
            lab = _hyp(ux, uy)
            if lab > 1e-9:
                beyond = max(0.0, ((px - ax) * ux + (py - ay) * uy) / lab - lab)
        return lp * (1.0 + self.detour * math.sqrt(ln)) * (ln + 2.0 * beyond) + lv


class FeedComp:
    """Antenna feed loss (dB): alpha (dB/mm) times the expected route length of the feed net
    group (antenna, matching parts, RF pin), taken as the Euclidean minimum spanning tree of
    the terminals: series parts along the line add nothing, shunt parts add their stubs, and
    the result does not depend on the order the brief lists them in."""

    kern = None

    def __init__(self, terms, alpha):
        self.T = terms
        self.alpha = alpha
        self.parts = tuple(sorted({t.i for t in terms}))
        n = len(terms)
        self._ti = np.array([t.i for t in terms], np.int64)
        self._lx = np.array([t.lx for t in terms], float)
        self._ly = np.array([t.ly for t in terms], float)
        self._scr = (np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n, np.bool_))

    def value(self, st):
        from .jit import PY
        return self.alpha * (self.kern or PY).mst_len(st.Xa, st.Ya, st.Ca, st.Sa, st.Ga, self._ti, self._lx, self._ly,
                                                      *self._scr)
