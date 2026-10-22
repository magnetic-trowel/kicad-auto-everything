# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Structure models of the place terms: each returns a spend in physical units from the
current poses, through a shared pose state (lists X, Y, C, S, G per part: position,
cos/sin of the rotation, side sign).

A structure is a sum (or other reduction) of *components*; each component depends on a
few parts and is cached by Terms against those parts' pose epochs, so a move recomputes
only what it touches. Models (derivations and validation: docs/topics/physics/place-terms.md):

* `LoopComp`: loop inductance of a chain of terminals (commutation cell; decap loop) by
  partial inductances with images (fastloop): board hops are straight strips at the
  reference-plane height, part-internal paths are strips at the body height with vertical
  terminations; a ground hop over a plane of its own net is combined in parallel with the
  via return through that plane (two-mesh formula).
* `PlanePairLoop`: decap loop when the rail and ground are an adjacent plane pair:
  mounting (cap body, vias) + plane-pair spreading (mu0 d / 2 pi) ln(D^2 / (r_c r_i)).
* `CouplingComp`: aggressor-victim coupling: Neumann mutual of the two loops with images
  (inductive, M di/dt) and patch mutual capacitance (C dv/dt into the victim impedance).
* `CrystalComp`: Pierce load pulling from the trace capacitance of the XIN/XOUT nets.
* `ThermalField`: fin kernel with adiabatic-edge images; victims' rise from all sources
  and each source's own rise, incremental by rows and columns.
* `CmComp`, `EsdComp`, `FeedComp`: world node (cable common-mode current), protection
  order (ESD loop inductance), antenna feed loss.
"""
from __future__ import annotations

import math

import numpy as np

from . import fastloop as FL
from .kernels import EPS0, cprime_hj, gmd_rect, lprime_hj, trapezoid_envelope

INF = float('inf')
_hyp = math.hypot


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

    def get(self, i):
        return (self.X[i], self.Y[i], self.R[i], 'F' if self.G[i] > 0 else 'B')


# ============================================================================ loops
class LoopComp:
    """Loop inductance (nH) of a closed chain of terminals (kernel: jit.loop_core).

    terms: list of Term in current order; kinds[k] for the hop T_k -> T_{k+1}: 'board' or
    'body'; widths[k]; zb[k] body height for 'body' hops; gnd_hop: index of the board hop
    on the return (ground) net, or None; gnd_nets: set of ground net names."""

    def __init__(self, bv, terms, kinds, widths, zb, gnd_hop=None, gnd_nets=(), knobs=None, rvia=0.15, kern=None,
                 body_min=None):
        self.bv = bv
        self.T = terms
        self.kinds = kinds
        self.w = widths
        self.zb = zb
        self.gnd_hop = gnd_hop
        self.gnd_nets = set(gnd_nets)
        self.parts = tuple(sorted({t.i for t in terms}))
        self.cos_min = knobs.pair_cos_min if knobs else 0.3
        self.detour = knobs.hop_detour if knobs else 1.0
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
        self.l_scr = ([0.0] * n, [0.0] * n, [0.0] * n)
        self.a_scr = (np.zeros(n), np.zeros(n), np.zeros(n))
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
    """Patch capacitance to the plane (pF): plate eps A / h plus an edge term 2 eps0 sqrt(A)."""
    return EPS0 * eps_r * A / h + EPS0 * 2.0 * math.sqrt(A)


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


class CouplingComp:
    """Noise (mV) one aggressor puts on one victim: |M| di/dt + capacitive pickup."""
    kern = None

    def __init__(self, bv, agg_loop, agg_node, vic_loop, vic_node, didt, dv, t_sw, z_v, gnd_plane):
        self.bv = bv
        self.al, self.an, self.vl, self.vn = agg_loop, agg_node, vic_loop, vic_node
        self.didt, self.dv, self.tsw, self.zv = didt, dv, t_sw, z_v
        self.gp = gnd_plane
        ps = set()
        for o in (agg_loop, agg_node, vic_loop, vic_node):
            if o is not None:
                ps |= set(o.parts)
        self.parts = tuple(sorted(ps))

    def value(self, st):
        bv = self.bv
        v = 0.0
        if self.al is not None and self.vl is not None and self.didt > 0:
            ga = self.al.geo(st)
            h = bv.h_ref(st.G[self.al.T[0].i], ga[1][0], ga[1][1])
            v += _mutual(self.kern, self.al, self.vl, st, h) * self.didt * 1e3        # nH * A/ns = V -> mV
        if self.an is not None and self.vn is not None:
            na = self.an.patches(st)
            nv = self.vn.patches(st)
            h = bv.h_ref(st.G[self.an.T[0].i], na[1], na[2])
            cm = _cm(self.kern, self.an, self.vn, st, h, bv.er)
            hh = 1.6 if h == INF else max(h, 0.05)
            cv = _cself(nv[3], hh, bv.er) + 5.0                                  # + pins (E5 5 pF)
            # charge division for a high-impedance victim, C dv/dt Z for a low one
            v_c = self.dv * self.tsw * cm / (cm + cv + self.tsw * 1e3 / self.zv)   # ns*1e3/ohm = pF
            v += 1e3 * v_c
        return v


# ============================================================================ crystal
class CrystalComp:
    """Load pulling (ppm) of a Pierce oscillator from the expected trace capacitance."""

    def __init__(self, bv, xin_terms, xout_terms, s_ppm_per_pf, w=0.2):
        self.bv = bv
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
        dcl = cp * (self.length(st, self.ti) + self.length(st, self.to)) / 4.0
        return self.s * dcl


# ============================================================================ thermal
class ThermalField:
    """Board temperature rise at victims and sources by the fin kernel with images.

    G(t, s) = sum_images K0(|r_t - r_img|/lam) / (2 pi G_s) over the adiabatic-edge image
    lattice of the board's bounding box (`rings` rings: (2(2 rings + 1))^2 images); a
    source's own rise replaces its real (r ~ 0) term by the disk-averaged self term
    (1 - x K1(x)) / (pi a^2 h_tot), x = a/lam. Cached as a matrix G[t, s] (K/W); a moved
    source updates a column and its row, a moved victim its row. K0 is the polynomial of
    jit.k0 in both the JIT and the fallback path."""

    def __init__(self, bv, sources, victims, gs, lam, rings=1, kern=None):
        from scipy.special import k1
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
        self.selfcorr = (1.0 - x * k1(x)) / (math.pi * self.a * self.a * htot) - k0v / (2.0 * math.pi * gs)
        r = rings
        self.ms = np.arange(-r, r + 1, dtype=float)
        self.norm = 1.0 / (2.0 * math.pi * gs)
        self._colbuf = np.zeros(len(self.targets))
        self._rowbuf = np.zeros(ns)

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
        ix, iy = self._imgs(st.X[i], st.Y[i])
        tx = np.array([st.X[t] for t in self.targets])
        ty = np.array([st.Y[t] for t in self.targets])
        out = self._colbuf
        if self.kern is not None:
            self.kern.fin_column(tx, ty, ix, iy, self.a[k], self.lam, out)
        else:
            for t in range(len(tx)):
                out[t] = self.py.fin_sum(tx[t], ty[t], ix, iy, self.a[k], self.lam)
        g = out * self.norm
        g[k] += self.selfcorr[k]
        return g

    def row(self, st, t):
        i = self.targets[t]
        xs = np.array([st.X[s] for s in self.src])
        ys = np.array([st.Y[s] for s in self.src])
        ix, iy = self._imgs(xs, ys)
        out = self._rowbuf
        if self.kern is not None:
            self.kern.fin_row(st.X[i], st.Y[i], ix, iy, self.a, self.lam, out)
        else:
            for k in range(len(xs)):
                out[k] = self.py.fin_sum(st.X[i], st.Y[i], ix[k], iy[k], self.a[k], self.lam)
        g = out * self.norm
        if t < len(self.src):
            g[t] += self.selfcorr[t]
        return g

    def full(self, st):
        for k in range(len(self.src)):
            self.G[:, k] = self.column(st, k)
        return self.G @ self.P


# ============================================================================ world node
class CmComp:
    """Common-mode current (uA) an aggressor drives onto one cable connector's cable."""
    kern = None

    def __init__(self, bv, agg_loop, agg_node, conn_loop, conn_node, I, V, t_sw, gnd_plane, world):
        self.bv = bv
        self.al, self.an, self.cl, self.cn = agg_loop, agg_node, conn_loop, conn_node
        f = world['f_ref_ghz']
        self.f = f
        self.Iamp = trapezoid_envelope(I, f, world['period_ns'], t_sw)
        self.Vamp = trapezoid_envelope(V, f, world['period_ns'], t_sw)
        self.zcm = world['z_cm']
        self.gp = gnd_plane
        ps = set()
        for o in (agg_loop, agg_node, conn_loop, conn_node):
            if o is not None:
                ps |= set(o.parts)
        self.parts = tuple(sorted(ps))

    def value(self, st):
        bv = self.bv
        w = 2.0 * math.pi * self.f        # rad/ns
        i_cm = 0.0
        if self.al is not None and self.cl is not None and self.Iamp > 0:
            ga = self.al.geo(st)
            h = bv.h_ref(st.G[self.al.T[0].i], ga[1][0], ga[1][1])
            i_cm += w * _mutual(self.kern, self.al, self.cl, st, h) * self.Iamp / self.zcm   # nH*rad/ns*A/ohm = A
        if self.an is not None and self.cn is not None:
            na = self.an.patches(st)
            h = bv.h_ref(st.G[self.an.T[0].i], na[1], na[2])
            cm = _cm(self.kern, self.an, self.cn, st, h, bv.er)
            i_cm += w * cm * 1e-3 * self.Vamp                  # pF*rad/ns*V = mA -> A
        return i_cm * 1e6


class EsdComp:
    """ESD surge path (nH): the surge enters at the connector pin, runs along the trace to
    the protector and leaves through the protector's ground via into the plane. Its
    inductance L'(w, h) l(conn -> prot) + L_via sets the area over which the surge's dI/dt
    spreads before it is shunted (designers place the protector at the connector and route
    the protected net through its pad, so a lateral offset from the conn -> IC line costs
    nothing). A protector farther from the connector than the protected pin (projected on
    the conn -> IC line) lets the pin see the surge first: the excess is charged twice."""

    def __init__(self, bv, t_conn, t_prot, t_ic, t_prot_gnd, w=0.25):
        self.bv = bv
        self.tc, self.tp, self.ti, self.tg = t_conn, t_prot, t_ic, t_prot_gnd
        self.w = w
        self._hc = {}
        self.parts = tuple(sorted({t.i for t in (t_conn, t_prot, t_ic) if t is not None}))

    def value(self, st):
        ax, ay = txy(st, self.tc)
        px, py = txy(st, self.tp)
        side = st.G[self.tp.i]
        h = self.bv.h_ref(side, px, py)
        hh = self.bv.thickness if h == INF else h
        cc = self._hc.get(hh)
        if cc is None:
            cc = (lprime_hj(self.w, hh), FL.m_self(hh, 0.15) + FL._collinear(hh, hh, 0.0))
            self._hc[hh] = cc
        lp, lv = cc
        ln = _hyp(px - ax, py - ay)
        beyond = 0.0
        if self.ti is not None:
            bx, by = txy(st, self.ti)
            ux, uy = bx - ax, by - ay
            lab = _hyp(ux, uy)
            if lab > 1e-9:
                beyond = max(0.0, ((px - ax) * ux + (py - ay) * uy) / lab - lab)
        return lp * (ln + 2.0 * beyond) + lv


class FeedComp:
    """Antenna feed loss (dB) from the expected route length between RF pin and antenna."""

    def __init__(self, terms, alpha):
        self.T = terms
        self.alpha = alpha
        self.parts = tuple(sorted({t.i for t in terms}))

    def value(self, st):
        P = [txy(st, t) for t in self.T]
        ln = sum(_hyp(b[0] - a[0], b[1] - a[1]) for a, b in zip(P[:-1], P[1:]))
        return self.alpha * ln
