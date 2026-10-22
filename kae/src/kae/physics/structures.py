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
from .kernels import EPS0, cprime_hj, gmd_rect, trapezoid_envelope

INF = float('inf')
_hyp = math.hypot


class Term:
    """A terminal: part i, library-frame point (lx, ly), effective width a (mm)."""
    __slots__ = ('i', 'lx', 'ly', 'a', 'net')

    def __init__(self, i, lx, ly, a, net=''):
        self.i, self.lx, self.ly, self.a, self.net = i, float(lx), float(ly), float(a), net


def txy(st, t):
    i = t.i
    c, s, g = st.C[i], st.S[i], st.G[i]
    ly = t.ly * g
    return st.X[i] + t.lx * c + ly * s, st.Y[i] - t.lx * s + ly * c


class State:
    """Pose arrays shared by all components (lists for fast scalar access)."""

    def __init__(self, n):
        self.X = [0.0] * n
        self.Y = [0.0] * n
        self.R = [0.0] * n
        self.C = [1.0] * n
        self.S = [0.0] * n
        self.G = [1.0] * n

    def set(self, i, x, y, rot, side):
        self.X[i] = float(x)
        self.Y[i] = float(y)
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
            self.G[i] = -1.0 if side[:1] in ('B', 'b') else 1.0
        else:
            self.G[i] = -1.0 if side < 0 else 1.0

    def get(self, i):
        return (self.X[i], self.Y[i], self.R[i], 'F' if self.G[i] > 0 else 'B')


# ============================================================================ loops
class LoopComp:
    """Loop inductance (nH) of a closed chain of terminals.

    terms: list of Term in current order; kinds[k] for the hop T_k -> T_{k+1}: 'board' or
    'body'; widths[k]; zb[k] body height for 'body' hops; gnd_hop: index of the board hop
    on the return (ground) net, or None; gnd_nets: set of ground net names.

    Fast path: per-height caches for the rigid parts (body self terms, terminations, the via
    return); one fused direct-minus-image kernel per surviving segment pair."""

    def __init__(self, bv, terms, kinds, widths, zb, gnd_hop=None, gnd_nets=(), knobs=None, rvia=0.15):
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
        self.body = [k for k in range(n) if kinds[k] == 'body']
        self.board = [k for k in range(n) if kinds[k] != 'body']
        self.pairs = [(j, k) for j in range(n) for k in range(j + 1, n)]
        self.dmin = [[0.2235 * (min(widths[j], widths[k]) + 0.035) for k in range(n)] for j in range(n)]
        self._hc = {}
        self._vc = {}
        self.tl = [(t.i, t.lx, t.ly) for t in terms]

    def _hcache(self, h):
        key = round(h, 3) if h != INF else INF
        v = self._hc.get(key)
        if v is None:
            hb = 0.0 if h == INF else h
            ties = 0.0
            selfb = {}
            for k in self.body:
                t0, t1 = self.T[k], self.T[(k + 1) % self.n]
                d = _hyp(t0.lx - t1.lx, t0.ly - t1.ly)
                r = gmd_rect(self.w[k])
                z = self.zb[k]
                if h != INF:
                    ties += FL._vertical_terms([], [(0.0, 0.0, hb, hb + z, r), (d, 0.0, hb + z, hb, r)])
                else:
                    ties += 2.0 * FL.m_self(z, r) - 2.0 * FL.m_par(z, z, 0.0, max(d, 1e-6))
                selfb[k] = FL.strip_self(d, self.w[k], (h + z) if h != INF else INF)
            consts = {k: FL.strip_consts(self.w[k], h) for k in self.board}
            v = (ties, selfb, consts)
            self._hc[key] = v
        return v

    def _via_return(self, h, d):
        key = (round(h, 3), round(d, 2))
        v = self._vc.get(key)
        if v is None:
            r = self.rvia
            d = max(d, 2.0 * r)
            v = 2.0 * (FL.m_self(h, r) + FL._collinear(h, h, 0.0)) \
                - 2.0 * (FL.m_par(h, h, 0.0, d) + FL.m_par(h, h, -2.0 * h, d))
            if len(self._vc) < 50000:
                self._vc[key] = v
        return v

    def value(self, st):
        n = self.n
        X, Y, C, S, G = st.X, st.Y, st.C, st.S, st.G
        px = [0.0] * n
        py = [0.0] * n
        sx = sy = 0.0
        for k, (i, lx, ly) in enumerate(self.tl):
            c = C[i]
            s = S[i]
            ly = ly * G[i]
            x = X[i] + lx * c + ly * s
            y = Y[i] - lx * s + ly * c
            px[k] = x
            py[k] = y
            sx += x
            sy += y
        side = G[self.tl[0][0]]
        h = self.bv.h_ref(side, sx / n, sy / n)
        ties, selfb, consts = self._hcache(h)
        zb = self.zb
        hs = [((h + zb[k]) if h != INF else INF) if self.kinds[k] == 'body' else h for k in range(n)]
        f = self.detour
        ex0, ey0, ex1, ey1 = px[:], py[:], px[1:] + px[:1], py[1:] + py[:1]
        if f != 1.0:
            for k in self.board:
                mx, my = 0.5 * (ex0[k] + ex1[k]), 0.5 * (ey0[k] + ey1[k])
                ex0[k], ey0[k] = mx + (ex0[k] - mx) * f, my + (ey0[k] - my) * f
                ex1[k], ey1[k] = mx + (ex1[k] - mx) * f, my + (ey1[k] - my) * f
        g = self.gnd_hop
        A = ties
        B = 0.0
        for k in self.body:
            A += selfb[k]
        msf = FL.m_self
        for k in self.board:
            a, de = consts[k]
            ln = _hyp(ex1[k] - ex0[k], ey1[k] - ey0[k])
            sk = msf(ln, a) - (msf(ln, de) if de != INF else 0.0)
            if k == g:
                B = sk
            else:
                A += sk
        MAB = 0.0
        cm = self.cos_min
        pm = FL.pair_mut
        dmin = self.dmin
        for j, k in self.pairs:
            adj = (k == j + 1 or (j == 0 and k == n - 1)) and hs[j] == hs[k]
            if k == j + 1 or not adj:
                m = pm(ex0[j], ey0[j], ex1[j], ey1[j], ex0[k], ey0[k], ex1[k], ey1[k], hs[j], hs[k], adj, cm, dmin[j][k])
            else:   # (0, n-1): segment n-1 ends where segment 0 starts
                m = pm(ex0[k], ey0[k], ex1[k], ey1[k], ex0[j], ey0[j], ex1[j], ey1[j], hs[k], hs[j], adj, cm, dmin[j][k])
            if j == g or k == g:
                MAB += 0.5 * m
            else:
                A += m
        thru = [k for k in self.board if G[self.tl[k][0]] != G[self.tl[(k + 1) % n][0]]]
        if thru:
            t = self.bv.thickness
            r = self.rvia
            for a_ in range(len(thru)):
                A += FL.m_self(t, r)
                for b_ in range(a_ + 1, len(thru)):
                    ka, kb = thru[a_], thru[b_]
                    d = _hyp(ex1[ka] - ex1[kb], ey1[ka] - ey1[kb])
                    A -= 2.0 * FL.m_par(t, t, 0.0, max(d, r))
        if g is None:
            return A
        lateral = A + B + 2.0 * MAB
        if h == INF:
            return lateral
        if self.bv.plane_net(side, 0.5 * (ex0[g] + ex1[g]), 0.5 * (ey0[g] + ey1[g])) not in self.gnd_nets:
            return lateral
        Cv = self._via_return(h, _hyp(ex1[g] - ex0[g], ey1[g] - ey0[g]))
        if B + Cv <= 1e-12:
            return lateral
        return A + MAB + (B + MAB) * (Cv - MAB) / (B + Cv)


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


_GL3 = np.polynomial.legendre.leggauss(3)
_GL6 = np.polynomial.legendre.leggauss(6)


def mutual_paths(pa, za, pv, zv, ha_via, hv_via, n=3):
    """Neumann mutual (nH) between an aggressor path and a victim path over a plane at z=0.

    pa, pv: (k, 2) arrays of path vertices (closed paths repeat the first vertex);
    za, zv: heights of the horizontal parts; ha_via/hv_via: if not None, the open path is
    closed through the plane by vertical vias of that height at both ends. The aggressor
    is imaged (horizontal reversed, vertical same direction)."""
    def segs(p, z, hv):
        a = np.column_stack([p[:-1], np.full(len(p) - 1, z)])
        b = np.column_stack([p[1:], np.full(len(p) - 1, z)])
        if hv is not None:
            a = np.vstack([[p[0][0], p[0][1], 0.0], a, [p[-1][0], p[-1][1], z]])
            b = np.vstack([[p[0][0], p[0][1], z], b, [p[-1][0], p[-1][1], 0.0]])
        return a, b
    x, wq = (_GL3 if n == 3 else _GL6)
    t = 0.5 * (x + 1.0)
    w = 0.5 * wq

    def gauss(a, b):
        d = b - a
        P = (a[:, None, :] + t[None, :, None] * d[:, None, :]).reshape(-1, 3)
        dl = (w[None, :, None] * d[:, None, :]).reshape(-1, 3)
        return P, dl
    Aa, Ab = segs(np.asarray(pa, float), za, ha_via)
    Va, Vb = segs(np.asarray(pv, float), zv, hv_via)
    Pa, dla = gauss(Aa, Ab)
    Pv, dlv = gauss(Va, Vb)
    diff = Pa[:, None, :] - Pv[None, :, :]
    R = np.sqrt((diff * diff).sum(-1))
    m = ((dla @ dlv.T) / np.maximum(R, 1e-6)).sum()
    Pi = Pa * np.array([1.0, 1.0, -1.0])
    dli = dla * np.array([-1.0, -1.0, 1.0])
    diff = Pi[:, None, :] - Pv[None, :, :]
    R = np.sqrt((diff * diff).sum(-1))
    m += ((dli @ dlv.T) / np.maximum(R, 1e-6)).sum()
    return 0.1 * float(m)


def _cself(A, h, eps_r):
    return EPS0 * eps_r * A / h + EPS0 * 2.0 * math.sqrt(A)       # plate + fringe (E5)


def patches_cm(na, nv, h, eps_r):
    """Mutual capacitance (pF) between the copper of an aggressor node and a victim net,
    given as cached patch sets (patches (x, y, A mm^2), cx, cy, total A, extent), at height
    h over a plane (h = inf: free space, approximated by h = 1.6 mm). First order in the
    potential coefficients with the plane image: C_av ~ C_a C_v p_av,
    p_av = (1/(4 pi eps0)) (1/r - 1/sqrt(r^2 + 4 h^2)); far apart, the totals at the centroids."""
    pa, ax, ay, Aa, ea = na
    pv, vx, vy, Av, ev = nv
    h = 1.6 if h == INF else max(h, 0.05)
    k = 1.0 / (4.0 * math.pi * EPS0)
    r = _hyp(ax - vx, ay - vy)
    if r > 1.5 * (ea + ev) + 2.0 * h:
        p = k * (1.0 / r - 1.0 / math.sqrt(r * r + 4.0 * h * h))
        return _cself(Aa, h, eps_r) * _cself(Av, h, eps_r) * p
    cm = 0.0
    for xa, ya, A1 in pa:
        ca = _cself(A1, h, eps_r)
        for xv, yv, A2 in pv:
            rr = max(_hyp(xa - xv, ya - yv), 0.5 * (math.sqrt(A1) + math.sqrt(A2)))
            p = k * (1.0 / rr - 1.0 / math.sqrt(rr * rr + 4.0 * h * h))
            cm += ca * _cself(A2, h, eps_r) * p
    return cm


def loop_mutual(al, vl, st, h, near_quad=True):
    """|M| (nH) between an aggressor LoopShape and a victim LoopShape over the plane at h
    (inf: free space). Far apart (centroid distance >= 2 max size and >= 4h): point dipoles
    of each loop with its image system; near: Gauss quadrature of the Neumann integral."""
    ga = al.geo(st)
    gv = vl.geo(st)
    ca, cv = ga[1], gv[1]
    r = _hyp(ca[0] - cv[0], ca[1] - cv[1])
    if h == INF:
        if not (al.closed and vl.closed):
            return 0.0
        if r >= 2.0 * max(ga[2], gv[2], 1e-3):
            return abs(0.1 * ga[3] * gv[3] / (r ** 3))        # coplanar dipoles, free space
        return abs(_free_mutual(ga[0], gv[0]))
    if r >= 2.0 * max(ga[2], gv[2]) and r >= 4.0 * h:
        return abs(far_mutual(_dipoles(ga, h, al.closed, al.z), _victim_moments(gv, h, vl.closed, vl.z)))
    m = mutual_paths(ga[0], h + al.z, gv[0], h + vl.z, None if al.closed else h, None if vl.closed else h,
                     n=6 if r < max(ga[2], gv[2]) else 3)
    return abs(m)


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
            self._key = key
        return self._geo


def _dipoles(geo, h, closed, z):
    """Magnetic dipole system (per unit current) of a loop shape plus its plane image:
    list of (x, y, z, mx, my, mz). Closed loop at height h: m = A z^ at +h and -A z^ at -h
    (a quadrupole); a path closed through the plane: its vertical rectangle and image, one
    horizontal dipole m = 2h z^ x chord at the plane."""
    pts, (cx, cy), size, area, chord = geo
    if closed:
        return [(cx, cy, h + z, 0.0, 0.0, area), (cx, cy, -(h + z), 0.0, 0.0, -area)]
    hh = h + z
    # moment of the closed path top (at +hh) -> via down -> image path back (at -hh) -> via up
    return [(cx, cy, 0.0, -2.0 * hh * chord[1], 2.0 * hh * chord[0], 0.0)]


def _victim_moments(geo, h, closed, z):
    """Physical area vectors (no image) of a victim loop: closed on top: A z^ at height h;
    closed through the plane: the curtain under its path, h z^ x chord at height h/2."""
    pts, (cx, cy), size, area, chord = geo
    hh = h + z
    if closed:
        return [(cx, cy, hh, 0.0, 0.0, area)]
    return [(cx, cy, 0.5 * hh, -hh * chord[1], hh * chord[0], 0.0)]


def far_mutual(dip_a, mom_v):
    """M (nH) = sum_v m_v . B_a(r_v) with B of point dipoles: (mu0/4pi)(3 (m.n) n - m)/R^3."""
    M = 0.0
    for xa, ya, za, mx, my, mz in dip_a:
        for xv, yv, zv, vx, vy, vz in mom_v:
            rx, ry, rz = xv - xa, yv - ya, zv - za
            R2 = rx * rx + ry * ry + rz * rz
            R = math.sqrt(R2)
            mr = (mx * rx + my * ry + mz * rz) / R2
            M += (3.0 * mr * (vx * rx + vy * ry + vz * rz) - (mx * vx + my * vy + mz * vz)) / (R2 * R)
    return 0.1 * M


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
            self._key = key
        return self._pat


class CouplingComp:
    """Noise (mV) one aggressor puts on one victim: |M| di/dt + capacitive pickup."""

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
            v += loop_mutual(self.al, self.vl, st, h) * self.didt * 1e3        # nH * A/ns = V -> mV
        if self.an is not None and self.vn is not None:
            na = self.an.patches(st)
            nv = self.vn.patches(st)
            h = bv.h_ref(st.G[self.an.T[0].i], na[1], na[2])
            cm = patches_cm(na, nv, h, bv.er)
            hh = 1.6 if h == INF else max(h, 0.05)
            cv = _cself(nv[3], hh, bv.er) + 5.0                                  # + pins (E5 5 pF)
            # charge division for a high-impedance victim, C dv/dt Z for a low one
            v_c = self.dv * self.tsw * cm / (cm + cv + self.tsw * 1e3 / self.zv)   # ns*1e3/ohm = pF
            v += 1e3 * v_c
        return v


def _free_mutual(pa, pv):
    """Free-space Neumann mutual (nH) of two closed planar loops (no plane)."""
    x, wq = _GL3
    t = 0.5 * (x + 1.0)
    w = 0.5 * wq
    a = np.asarray(pa, float)
    b = np.asarray(pv, float)
    da = a[1:] - a[:-1]
    db = b[1:] - b[:-1]
    Pa = (a[:-1, None, :] + t[None, :, None] * da[:, None, :]).reshape(-1, 2)
    Pb = (b[:-1, None, :] + t[None, :, None] * db[:, None, :]).reshape(-1, 2)
    dla = (w[None, :, None] * da[:, None, :]).reshape(-1, 2)
    dlb = (w[None, :, None] * db[:, None, :]).reshape(-1, 2)
    R = np.sqrt(((Pa[:, None, :] - Pb[None, :, :]) ** 2).sum(-1))
    return 0.1 * float(((dla @ dlb.T) / np.maximum(R, 1e-6)).sum())


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
    lattice of the board's bounding box (`rings` rings); a source's own rise replaces its
    real (r ~ 0) term by the disk-averaged self term (1 - x K1(x)) / (pi a^2 h_tot),
    x = a/lam. Cached as a matrix G[t, s] (K/W); a moved source updates a column, a moved
    victim a row."""

    def __init__(self, bv, sources, victims, gs, lam, rings=1):
        from scipy.special import k0, k1
        self._k0 = k0
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
        # self correction: disk-averaged self term minus the point kernel at r = a
        self.selfcorr = (1.0 - x * k1(x)) / (math.pi * self.a * self.a * htot) - k0(x) / (2.0 * math.pi * gs)
        r = rings
        self.ms = np.arange(-r, r + 1, dtype=float)

    def _imgs(self, xs, ys):
        """x- and y-image coordinates (..., 2(2r+1)) for source positions xs, ys (arrays)."""
        x0, y0, Lx, Ly = self.box
        u = np.asarray(xs, float)[..., None] - x0
        v = np.asarray(ys, float)[..., None] - y0
        m = self.ms
        ix = x0 + np.concatenate([2 * m * Lx + u, 2 * m * Lx - u], axis=-1)
        iy = y0 + np.concatenate([2 * m * Ly + v, 2 * m * Ly - v], axis=-1)
        return ix, iy

    def _kern(self, tx, ty, ix, iy, a):
        """sum over images of K0(max(r, a)/lam)/(2 pi G_s); tx, ty: (n,), ix, iy: (n, k), a: (n,)"""
        dx = tx[:, None, None] - ix[:, :, None]
        dy = ty[:, None, None] - iy[:, None, :]
        r = np.sqrt(dx * dx + dy * dy)
        r = np.maximum(r, a[:, None, None])
        return self._k0(r / self.lam).sum(axis=(1, 2)) / (2.0 * math.pi * self.gs)

    def column(self, st, k):
        i = self.src[k]
        ix, iy = self._imgs([st.X[i]], [st.Y[i]])
        nt = len(self.targets)
        tx = np.array([st.X[t] for t in self.targets])
        ty = np.array([st.Y[t] for t in self.targets])
        g = self._kern(tx, ty, np.repeat(ix, nt, 0), np.repeat(iy, nt, 0), np.full(nt, self.a[k]))
        g[k] += self.selfcorr[k]
        return g

    def row(self, st, t):
        i = self.targets[t]
        xs = np.array([st.X[s] for s in self.src])
        ys = np.array([st.Y[s] for s in self.src])
        ix, iy = self._imgs(xs, ys)
        ns = len(self.src)
        g = self._kern(np.full(ns, st.X[i]), np.full(ns, st.Y[i]), ix, iy, self.a)
        if t < ns:
            g[t] += self.selfcorr[t]
        return g

    def full(self, st):
        for k in range(len(self.src)):
            self.G[:, k] = self.column(st, k)
        return self.G @ self.P


# ============================================================================ world node
class CmComp:
    """Common-mode current (uA) an aggressor drives onto one cable connector's cable."""

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
            i_cm += w * loop_mutual(self.al, self.cl, st, h) * self.Iamp / self.zcm   # nH*rad/ns*A/ohm = A
        if self.an is not None and self.cn is not None:
            na = self.an.patches(st)
            nv = self.cn.patches(st)
            h = bv.h_ref(st.G[self.an.T[0].i], na[1], na[2])
            cm = patches_cm(na, nv, h, bv.er)
            i_cm += w * cm * 1e-3 * self.Vamp                  # pF*rad/ns*V = mA -> A
        return i_cm * 1e6


class EsdComp:
    """ESD path inductance (nH): protection device stub + its ground connection, plus the
    path between the protected pin and the protector when the protected pin is hit first."""

    def __init__(self, bv, t_conn, t_prot, t_ic, t_prot_gnd, w=0.25):
        self.bv = bv
        self.tc, self.tp, self.ti, self.tg = t_conn, t_prot, t_ic, t_prot_gnd
        self.w = w
        self.parts = tuple(sorted({t.i for t in (t_conn, t_prot, t_ic) if t is not None}))

    def value(self, st):
        ax, ay = txy(st, self.tc)
        px, py = txy(st, self.tp)
        side = st.G[self.tp.i]
        h = self.bv.h_ref(side, px, py)
        hh = self.bv.thickness if h == INF else h
        lp = FL.strip_self(1.0, self.w, hh)          # nH per mm (1 mm segment)
        if self.ti is not None:
            bx, by = txy(st, self.ti)
            ux, uy = bx - ax, by - ay
            lab = _hyp(ux, uy)
            if lab > 1e-9:
                ux /= lab
                uy /= lab
                s = (px - ax) * ux + (py - ay) * uy          # projection of the protector on conn->IC
                stub = abs((px - ax) * uy - (py - ay) * ux)
                beyond = max(0.0, s - lab)                     # protector farther than the IC: IC hit first
                before = max(0.0, -s)
                stub += before
            else:
                stub, beyond = _hyp(px - ax, py - ay), 0.0
        else:
            stub, beyond = _hyp(px - ax, py - ay), 0.0
        # ground connection of the protector: a via to the plane (or the board thickness)
        r = 0.15
        lv = FL.m_self(hh, r) + FL._collinear(hh, hh, 0.0)
        return lp * (stub + 2.0 * beyond) + lv


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
