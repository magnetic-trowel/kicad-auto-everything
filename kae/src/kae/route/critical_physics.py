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
via barrel R = rho h / (pi (d + t_p) t_p) with plating t_p = 20 um (kae.materials: IPC-6012
class 2). Widths from current use IPC-2221 (external k = 0.048, internal 0.024, dT = 10 K), an E5
thermal proxy (docs/topics/rules/power/high-current.md); the drop budget sets the rest.

Heat: `track_dT` gives a track's rise by IPC-2221 and by IPC-2152 (the Brooks-Adam fit KiCad's
calculator uses; no plane, the conservative case), `via_current` the current one via carries
and `vias_needed` how many a current needs (see there); `heat_hazard` turns copper narrower
than its current asks into a hazard for the report.
"""
from __future__ import annotations

import math

from kae import materials as MAT
from kae.physics import exact as EX
from kae.physics import fastloop as FL
from kae.physics.kernels import cprime_hj, gmd_rect

INF = math.inf
# FR-4 Dk when the board gives no stackup: KiCad's default stackup and critical_space.Space use
# 4.5 (docs/topics/rules/stackup.md: "typically 4.5")
ER_DEFAULT = 4.5
RHO_CU = MAT.RHO_CU_OHM_MM        # ohm mm at 20 C
T_PLATE = MAT.VIA_PLATING_MM      # mm via plating (IPC-6012 class 2 average), opts via_plating_mm
T_AMB_MAX_C = 50.0                # warmest ambient a board is assumed to see (excite.heat's prior: 25-50 C)
T_LAMINATE_MAX_C = 130.0          # FR-4's maximum operating temperature (UL RTI of standard FR-4, Tg 130-140)
T_PARTS_WARN_C = 105.0            # copper hotter than this cooks nearby parts rated 85-105 C (aluminium
                                  # electrolytics, many connectors): a warning even when the laminate is fine


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


def ipc2221_dT(current_a, width_mm, t_mm=0.035, internal=False):
    """Temperature rise (K) of a track (IPC-2221, as ipc2221_width)."""
    A = (width_mm / 0.0254) * (t_mm / 0.0254)
    if current_a <= 0 or A <= 0:
        return 0.0
    return (current_a / ((0.024 if internal else 0.048) * A ** 0.725)) ** (1 / 0.44)


def ipc2152_dT(current_a, width_mm, t_mm=0.035):
    """Temperature rise (K) of an outer track by IPC-2152's chart, as Brooks and Adam fit it
    (dT = 215.3 I^2 W^-1.15 Th^-1, mils; KiCad's track width calculator): a board without a plane,
    the chart's own conservative case. Wider than ~2 mm it runs hotter than IPC-2221 (10 A on 3 mm of
    35 um: 65 K against 42 K)."""
    if current_a <= 0 or width_mm <= 0 or t_mm <= 0:
        return 0.0
    return 215.3 * current_a ** 2 * (width_mm / 0.0254) ** -1.15 * (t_mm / 0.0254) ** -1.0


def track_dT(current_a, width_mm, t_mm=0.035):
    """(IPC-2221 rise, IPC-2152 rise) in K of an outer track."""
    return ipc2221_dT(current_a, width_mm, t_mm), ipc2152_dT(current_a, width_mm, t_mm)


def via_current(drill, plating=T_PLATE, dT=10.0):
    """Current (A) one through via carries at a rise dT: IPC-2221's internal-conductor curve on the
    barrel's cross-section pi (d + t) t. It reproduces TI SLVA959 Table 3-1 (IPC-2152, 1 oz, 10 C:
    0.55 / 0.81 / 0.84 / 1.1 A at 8 / 10 / 12 / 16 mil) within 13 % at 20 um plating (0.62 / 0.72 /
    0.80 / 0.98 A here), so it is high-current.md's 0.8 A default per 12-mil via, for every drill
    and plating. TI's "one via per amp" (SLYT614) is the optimistic side of it for drills under
    0.45 mm; Brooks and Adam (2019) measured a via running cooler than the trace feeding it."""
    A = MAT.barrel_area_mm2(drill, plating) / 0.0254 ** 2
    return 0.024 * dT ** 0.44 * A ** 0.725


def vias_needed(current_a, drill, plating=T_PLATE, dT=10.0, per_via_a=None):
    """Through vias a current needs between two layers (high-current.md HC-02): the larger of
    ceil(I / I_via) (`via_current`, or per_via_a when given: opts via_A) and IPC-2152's rule that the
    vias together have at least the cross-section of the conductor they continue (the IPC-2221 outer
    track for this current), which binds above ~10 A."""
    if current_a <= 0:
        return 1
    iv = per_via_a if per_via_a else via_current(drill, plating, dT)
    n = math.ceil(current_a / iv - 1e-9)
    a_track = ipc2221_width(current_a, dT, 0.035) * 0.035
    n_area = math.ceil(a_track / MAT.barrel_area_mm2(drill, plating) - 1e-9)
    return max(1, n, n_area)


def heat_hazard(code, current_a, width_mm, t_mm, dT_max, objects, nominal_a=None, where="", w_ipc=None,
                t_amb=T_AMB_MAX_C, t_max=T_LAMINATE_MAX_C, t_warn=T_PARTS_WARN_C):
    """A hazard for copper of width_mm carrying current_a (the design current; nominal_a the expected
    one, without the E5 margin) when IPC-2221 puts it above dT_max: 'block' when even at the nominal
    current the hotter of IPC-2221 and IPC-2152 lifts it from t_amb past the laminate's t_max; 'warn'
    when it lifts it past t_warn (nearby parts rated 85-105 C), or when the copper is not within 1.2x of
    its IPC width; else 'info' (within 1.2x: at most 1.35 dT_max, the slack critical_rails' auto gate
    grants). None when the copper is wide enough."""
    d21, d52 = track_dT(current_a, width_mm, t_mm)
    if d21 <= dT_max * 1.001:
        return None
    nom = current_a if nominal_a is None else min(nominal_a, current_a)
    n21, n52 = track_dT(nom, width_mm, t_mm)
    hot = max(n21, n52)
    w_ipc = ipc2221_width(current_a, dT_max, t_mm) if w_ipc is None else w_ipc
    if t_amb + hot > t_max:
        sev = "block"
    elif t_amb + hot > t_warn or w_ipc > 1.2 * width_mm:
        sev = "warn"
    else:
        sev = "info"
    w_safe = ipc2221_width(nom, max(t_max - t_amb, dT_max), t_mm)
    return dict(
        code=code, severity=sev, category="thermal",
        message=(f"{where or objects[0]}: {width_mm:.2f} mm of {1e3 * t_mm:.0f} um copper carries {current_a:.2f} A, "
                 f"a {d21:.0f} K rise by IPC-2221 ({d52:.0f} K by IPC-2152) against {dT_max:g} K; "
                 f"{'it would overheat the board' if sev == 'block' else ('it would cook parts rated to ' + format(t_warn, 'g') + ' C nearby' if t_amb + hot > t_warn else 'it runs warm')} at the expected {nom:.2f} A "
                 f"({n21:.0f}/{n52:.0f} K)"),
        objects=list(objects),
        evidence=dict(current_A=round(current_a, 3), nominal_A=round(nom, 3), width_mm=round(width_mm, 3),
                      copper_mm=t_mm, dT_ipc2221_K=round(d21, 1), dT_ipc2152_K=round(d52, 1),
                      dT_nominal_ipc2221_K=round(n21, 1), dT_nominal_ipc2152_K=round(n52, 1), dT_max_K=dT_max,
                      ipc_width_mm=round(w_ipc, 3), T_amb_C=t_amb, T_laminate_max_C=t_max, T_parts_warn_C=t_warn,
                      T_copper_nominal_C=round(t_amb + hot, 1),
                      source="IPC-2221 (k 0.048), IPC-2152 via Brooks-Adam (no plane); "
                             "docs/topics/rules/power/high-current.md"),
        fix=(f"pour the net (a zone at least {w_ipc:.1f} mm wide along the path), or give it "
             f"{w_ipc:.1f} mm of track (opts rail_max_mm), or heavier copper ({w_safe:.2f} mm keeps the "
             f"expected current under {t_max:g} C)"))


def via_hazard(current_a, placed, needed, drill, plating, dT_max, objects, nominal_a=None, where="",
               per_via_a=None, t_amb=T_AMB_MAX_C, t_max=T_LAMINATE_MAX_C):
    """A hazard for `placed` vias where `needed` (vias_needed) carry current_a between two layers:
    'warn', or 'block' when at the nominal current each via carries more than its barrel takes at a
    rise from t_amb to the laminate's t_max (via_current at t_max - t_amb); with none placed, as if
    one (what the general router will likely draw). None when enough."""
    if placed >= needed or (placed == 0 and needed <= 1):
        return None
    nom = current_a if nominal_a is None else min(nominal_a, current_a)
    iv = per_via_a if per_via_a else via_current(drill, plating, dT_max)
    i_hot = via_current(drill, plating, max(t_max - t_amb, dT_max))
    per = nom / max(placed, 1)
    sev = "block" if per > i_hot else "warn"          # none placed: the general router joins it, likely with one
    return dict(
        code="vias_below_current", severity=sev, category="thermal",
        message=(f"{where or objects[0]}: {placed} via(s) of {drill:.2f} mm carry {current_a:.2f} A where "
                 f"{needed} are needed ({iv:.2f} A each at {dT_max:g} K)"),
        objects=list(objects),
        evidence=dict(current_A=round(current_a, 3), nominal_A=round(nom, 3), vias=placed, vias_needed=needed,
                      drill_mm=drill, plating_mm=plating, via_A=round(iv, 3), via_A_at_laminate_max=round(i_hot, 3),
                      dT_max_K=dT_max, source="IPC-2221 internal curve on pi(d+t)t (TI SLVA959 Table 3-1), "
                                              "IPC-2152 equal cross-section; high-current.md HC-02"),
        fix=(f"room for {needed - placed} more via(s) of the net beside the pad (move neighbours or use "
             f"via-in-pad), a larger drill, or a zone on the pad's own layer so no layer change is needed"))


def r_track(length, width, t_mm=0.035):
    return RHO_CU * length / (max(width, 1e-6) * t_mm)


def r_via(height, drill, plating=T_PLATE):
    return RHO_CU * height / (math.pi * (drill + plating) * plating)


def r_strip(length, width, h, t_mm=0.035, t_plane_mm=0.035):
    """Resistance (ohm) of a strip and, at height h over a plane, of its return in the plane: the
    return of a line current at h spreads as J(x) = I h / (pi (x^2 + h^2)) (the image law), whose
    dissipation equals a uniform strip 2 pi h wide (integral of J^2 = I^2 / (2 pi h)), so a strip of
    width w returns through about w + 2 pi h of plane [I]."""
    r = r_track(length, width, t_mm)
    if h not in (None, INF) and h > 0:
        r += r_track(length, width + 2 * math.pi * h, t_plane_mm)
    return r


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
        self.res = {}       # element -> DC resistance (ohm) of its board copper (r_strip, r_via)

    def _r(self, el, r):
        self.res[el] = self.res.get(el, 0.0) + float(r)

    def _e(self, el):
        return self.el.setdefault(el, ([], []))

    def strip(self, a, b, w, h, el="A", t_mm=0.035, copper=True):
        """A strip of board copper (copper=False: a part's internal path, no board resistance)."""
        if math.dist(a, b) > 1e-6:
            self._e(el)[0].append((float(a[0]), float(a[1]), float(b[0]), float(b[1]), float(w), float(h)))
            if copper:
                self._r(el, r_strip(math.dist(a, b), w, h, t_mm))

    def path(self, pts, w, h, el="A", t_mm=0.035):
        for a, b in zip(pts[:-1], pts[1:]):
            self.strip(a, b, w, h, el, t_mm=t_mm)

    def vert(self, x, y, z0, z1, r, el="A", drill=None):
        """A vertical piece; with `drill`, a plated via barrel (its resistance counts)."""
        if abs(z1 - z0) > 1e-9 and z0 != INF and z1 != INF:
            self._e(el)[1].append((float(x), float(y), float(z0), float(z1), float(r)))
            if drill:
                self._r(el, r_via(abs(z1 - z0), drill))

    def body(self, a, b, h, zb, w, el="A"):
        """A part's internal path from terminal a to b: tie up, strip at h + zb, tie down."""
        r = gmd_rect(max(w, 0.1))
        if h == INF:
            self.strip(a, b, max(w, 0.1), INF, el, copper=False)
            return
        self.vert(a[0], a[1], h, h + zb, r, el)
        self.strip(a, b, max(w, 0.1), h + zb, el, copper=False)
        self.vert(b[0], b[1], h + zb, h, r, el)

    def kcl(self, coeffs, rhs=1.0):
        self.cons.append((dict(coeffs), float(rhs)))

    def _elements(self):
        """Elements as fastloop takes them. A fastloop that takes a loop either over a plane
        or in free space (NaN for a mix) gets a finite stand-in height for strips without a
        plane in a loop that has one: twice the loop's highest strip, at least 3.2 mm, so a
        missing plane costs inductance. A fastloop that handles the mix (coplanar, no image)
        gets the elements as they are."""
        if _MIXED_OK:
            return self.el
        fin = [h[5] for H, _ in self.el.values() for h in H if h[5] != INF]
        if not fin or all(h[5] != INF for H, _ in self.el.values() for h in H):
            return self.el
        hf = max(3.2, 2.0 * max(fin))
        return {k: ([h if h[5] != INF else h[:5] + (hf,) for h in H], V) for k, (H, V) in self.el.items()}

    def value_r(self):
        """(loop inductance nH, loop resistance ohm): the resistance of the board copper (strips,
        their plane return, via barrels; part bodies excluded) carrying the inductive current split
        that `value` finds, sum x_e^2 R_e. At the switching frequency (0.1-3 MHz) the return already
        follows the inductive path (power-copper.md section 5: f_c ~ 0.6 MHz at h = 0.1 mm), so the
        split that minimizes L is the one that carries the AC current; DC values, no skin effect
        (as the evaluator's raster)."""
        got = self.value(shares=True)
        if isinstance(got, tuple) and len(got) == 2 and isinstance(got[1], dict):
            L, x = got
        else:
            L, x = got, {}
        R = 0.0
        for el, r in self.res.items():
            R += float(x.get(el, 1.0)) ** 2 * r
        return L, R

    def value(self, shares=False):
        """Loop inductance (nH); with shares=True also {element: current share}."""
        ex = EX.loop_hook(self, shares)      # --physics-fidelity exact / multi: PEEC (kae.physics.exact)
        if ex is not None:
            return ex
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


def _mixed_ok():
    """Whether fastloop evaluates a loop mixing strips over a plane and over none."""
    try:
        H = [(0, 0, 4, 0, 0.5, 0.2), (4, 0, 4, 2, 0.5, 0.2), (4, 2, 0, 2, 0.5, 0.2), (0, 2, 0, 0, 0.5, INF)]
        v = FL.loop_fast(H, [])
        return math.isfinite(v) and v > 0
    except Exception:  # noqa: BLE001
        return False


_MIXED_OK = _mixed_ok()


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


def dielectric_er(cu, z, er, layer, plane=None):
    """Relative permittivity under a trace on copper `layer` (cu: names top to bottom, z: {name:
    height}, er: per gap): the gaps between it and its `plane` layer, weighted by thickness; without
    a plane, the gap on its inner side (an inner layer: both). er[0] for every layer priced a
    bottom-side crystal with the top prepreg."""
    if not er:
        return ER_DEFAULT
    if len(er) != len(cu) - 1 or layer not in cu:
        return er[0]
    i = cu.index(layer)
    if plane in cu and plane != layer:
        a, b = sorted((i, cu.index(plane)))
        ws = [abs(z[cu[k + 1]] - z[cu[k]]) for k in range(a, b)]
        return sum(er[k] * w for k, w in zip(range(a, b), ws)) / sum(ws) if sum(ws) > 0 else er[a]
    if i == 0:
        return er[0]
    if i == len(cu) - 1:
        return er[-1]
    return 0.5 * (er[i - 1] + er[i])
