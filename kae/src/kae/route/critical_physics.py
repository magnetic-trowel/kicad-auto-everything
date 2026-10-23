# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics of routed copper: what the critical router optimizes and what `recheck` measures.

Loops (hot loops, decoupling loops) are evaluated on the routed segments with the place
terms' closed forms (kae.physics.fastloop: partial inductances with plane images,
Hammerstad-Jensen strip self terms, Grover mutuals; the same physics as
kae.physics.kernels.loop_L, which is within 5 % of PEEC on routed loops,
docs/topics/physics/place-terms.md section 2). A loop is a chain of pieces in current
order: horizontal strips (x0, y0, x1, y1, w, h) at height h above the reference plane and
vertical pieces (x, y, z0, z1, r): vias down to the plane and the terminations of a part's
internal current path, which runs as a strip at the body height (BoardView.body_z).

Where the current can take several paths (a ground track on the surface, and vias down to
the plane at both ends of the return, each via with its stub), the loop is a small network
of elements e with currents x_e: the series part carries x = 1, the alternatives obey
Kirchhoff's current law (the vias at one end of a return carry together what the surface
track does not). The current splits so as to minimize the stored energy x^T M x, where M
holds the elements' partial inductances (with images; M_ij from the pairwise sums of
fastloop), which is a small KKT system; the loop inductance is that minimum (the inductive
limit of parallel paths; for one alternative pair it reduces to
L(x) = P_AA + 2x P_AB + 2(1-x) P_AC + x^2 P_BB + (1-x)^2 P_CC + 2x(1-x) P_BC).

DC: a track of length l and width w on copper of thickness t has R = rho l / (w t); a
via barrel R = rho h / (pi (d + t_p) t_p) with plating t_p = 20 um (as the DC passports).
Widths from current use IPC-2221 (external k = 0.048, internal 0.024, dT = 10 K), an E5
thermal proxy (docs/topics/rules/power/high-current.md); the drop budget sets the rest.
"""
from __future__ import annotations

import math

from kae.physics import fastloop as FL
from kae.physics.kernels import cprime_hj, gmd_rect

INF = math.inf
RHO_CU = 1.72e-5          # ohm mm at 20 C
T_PLATE = 0.020           # mm via plating (as the DC passports)


# ----------------------------------------------------------------------------- DC
def ipc2221_width(current_a, dT=10.0, t_mm=0.035, internal=False):
    """Track width (mm) for a current at a temperature rise (IPC-2221: I = k dT^0.44 A^0.725,
    A in mil^2)."""
    if current_a <= 0:
        return 0.0
    k = 0.024 if internal else 0.048
    area_mil2 = (current_a / (k * dT ** 0.44)) ** (1.0 / 0.725)
    t_mil = t_mm / 0.0254
    return area_mil2 / t_mil * 0.0254


def r_track(length, width, t_mm=0.035):
    return RHO_CU * length / (max(width, 1e-6) * t_mm)


def r_via(height, drill, plating=T_PLATE):
    return RHO_CU * height / (math.pi * (drill + plating) * plating)


def drop_width(current_a, length_mm, dv_v, t_mm=0.035):
    """Width (mm) that keeps the drop of `current_a` over `length_mm` within dv_v."""
    if current_a <= 0 or length_mm <= 0 or dv_v <= 0:
        return 0.0
    return RHO_CU * length_mm * current_a / (t_mm * dv_v)


# ----------------------------------------------------------------------------- loops
class Loop:
    """A closed current loop as a network of elements (see the module docstring).

        lp = Loop()
        lp.strip(a, b, w, h)                 # series element 'A' by default
        lp.body(a, b, h, zb, w)              # a part's internal path
        lp.vert(x, y, z0, z1, r, el='v1')    # an alternative element
        lp.kcl({'lat': 1, 'v1': 1})          # currents of these elements sum to 1
        lp.value()                           # nH, the energy-minimizing split

    Elements other than 'A' must be tied by kcl constraints; without any, they are
    taken in series."""

    def __init__(self):
        self.el = {"A": ([], [])}
        self.cons = []

    def _e(self, el):
        return self.el.setdefault(el, ([], []))

    def strip(self, a, b, w, h, el="A"):
        if math.dist(a, b) > 1e-6:
            self._e(el)[0].append((float(a[0]), float(a[1]), float(b[0]), float(b[1]), float(w), float(h)))

    def path(self, pts, w, h, el="A"):
        for a, b in zip(pts[:-1], pts[1:]):
            self.strip(a, b, w, h, el)

    def vert(self, x, y, z0, z1, r, el="A"):
        if abs(z1 - z0) > 1e-9 and z0 != INF and z1 != INF:
            self._e(el)[1].append((float(x), float(y), float(z0), float(z1), float(r)))

    def body(self, a, b, h, zb, w, el="A"):
        """A part's internal path from terminal a to b: tie up, strip at h + zb, tie down."""
        r = gmd_rect(max(w, 0.1))
        if h == INF:
            self.strip(a, b, max(w, 0.1), INF, el)
            return
        self.vert(a[0], a[1], h, h + zb, r, el)
        self.strip(a, b, max(w, 0.1), h + zb, el)
        self.vert(b[0], b[1], h + zb, h, r, el)

    def kcl(self, coeffs, rhs=1.0):
        self.cons.append((dict(coeffs), float(rhs)))

    def _elements(self):
        """Elements with a finite stand-in height for strips without a plane in a loop that
        has one (fastloop takes a loop either over a plane or in free space): twice the
        loop's highest strip, at least 3.2 mm, so a missing plane costs inductance."""
        fin = [h[5] for H, _ in self.el.values() for h in H if h[5] != INF]
        if not fin or all(h[5] != INF for H, _ in self.el.values() for h in H):
            return self.el
        hf = max(3.2, 2.0 * max(fin))
        return {k: ([h if h[5] != INF else h[:5] + (hf,) for h in H], V) for k, (H, V) in self.el.items()}

    def value(self, shares=False):
        """Loop inductance (nH); with shares=True also {element: current share}."""
        el = self._elements()
        names = [n for n, (H, V) in el.items() if H or V]
        if not self.cons or names == ["A"]:
            H = [h for n in names for h in el[n][0]]
            V = [v for n in names for v in el[n][1]]
            val = _P(H, V)
            return (val, {n: 1.0 for n in names}) if shares else val
        import numpy as np
        n = len(names)
        P = np.zeros((n, n))
        single = [_P(*el[k]) for k in names]
        for i in range(n):
            P[i, i] = single[i]
            for j in range(i + 1, n):
                Hi, Vi = el[names[i]]
                Hj, Vj = el[names[j]]
                # both concatenation orders: fastloop's corner formula joins consecutive
                # pieces that share an end, so one order alone is not symmetric
                m = 0.25 * (_P(Hi + Hj, Vi + Vj) + _P(Hj + Hi, Vj + Vi)) - 0.5 * (single[i] + single[j])
                P[i, j] = P[j, i] = m
        # Closed forms are not exactly a partial-inductance matrix where two elements overlap
        # (wide strips leaving one pad side by side): clip P to positive definite, so the
        # minimum energy is bounded.
        ev, U = np.linalg.eigh(P)
        floor = 1e-3 * max(float(ev.max()), 1e-9)
        if ev.min() < floor:
            P = (U * np.maximum(ev, floor)) @ U.T
        rows, rhs = [], []
        if "A" in names:
            r = np.zeros(n)
            r[names.index("A")] = 1.0
            rows.append(r)
            rhs.append(1.0)
        for co, v in self.cons:
            r = np.zeros(n)
            ok = False
            for k, c in co.items():
                if k in names:
                    r[names.index(k)] = c
                    ok = True
            if ok:
                rows.append(r)
                rhs.append(v)
        # Minimum of x'Px under the KCL rows, with an active set keeping the alternatives'
        # currents non-negative (a reverse current in a parallel path is a model artefact
        # here); never pins the last free element of a constraint.
        pinned = []
        x = np.zeros(n)
        for _ in range(n + 1):
            R = rows + [np.eye(n)[k] for k in pinned]
            C = np.array(R)
            m = C.shape[0]
            K = np.zeros((n + m, n + m))
            K[:n, :n] = 2.0 * P
            K[:n, n:] = C.T
            K[n:, :n] = C
            b = np.zeros(n + m)
            b[n:] = rhs + [0.0] * len(pinned)
            try:
                x = np.linalg.lstsq(K, b, rcond=None)[0][:n]
            except np.linalg.LinAlgError:
                break
            neg = [k for k in np.argsort(x) if x[k] < -1e-9 and names[k] != "A" and k not in pinned
                   and all(sum(1 for q in np.nonzero(r)[0] if q != k and q not in pinned) > 0
                           for r in rows if r[k] != 0)]
            if not neg:
                break
            pinned.append(int(neg[0]))
        val = float(x @ P @ x)
        if shares:
            return val, {k: float(v) for k, v in zip(names, x)}
        return val


def _P(H, V):
    if not H and not V:
        return 0.0
    return FL.loop_fast(list(H), list(V))


# ----------------------------------------------------------------------------- crystals
def trace_capacitance_pf(length_mm, w, h, er):
    """Capacitance (pF) of a microstrip of the given length to its reference plane."""
    if h == INF or length_mm <= 0:
        return 0.0
    return cprime_hj(w, h, er) * length_mm
