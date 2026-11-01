# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The size of each harm at one point of the parameters' intervals, band by band.

The copper gives, per (observer k, aggressor s) pair, its impedance at the aggressor's switching
fundamental Z_f (current split by the parts' C and ESR there) and its inductance at the edge band
L_e (split by ESL). A switching aggressor is a trapezoid of height I, duty D, edge t_i at f_sw, so:

  peak quantities (overshoot, supply bounce, victim pickup):
      V = |Z_f| c_1 I  +  |L_e| I / t_i          c_1 = (2/pi) |sin(pi D)| (the fundamental's share)
  emissions (cable common mode): per harmonic n, |c_n| <= (2 I / (n pi)) min(1, 1 / (n pi f_sw t_i)),
      V_n = 2 pi n f_sw |L_e| |c_n|, against the CISPR 32 class B limit V_lim(f) = CM_V_LIM_HZ / f
      over 30-230 MHz; the worst harmonic counts.

Both bands are reported, so a result says which one sets it: at slow edges the fundamental, at fast
edges the edge term.
"""
from __future__ import annotations

import math

from .observe import CM_V_LIM_HZ, F_CM


def peak(Zf, Le, I, D, ti):
    c1 = 2 / math.pi * abs(math.sin(math.pi * D))
    vf = abs(Zf) * c1 * I
    ve = abs(Le) * I / ti
    return vf + ve, vf, ve


def cm(Le, I, f_sw, ti):
    """(worst V_n / V_lim, its frequency) over the harmonics in the CISPR band."""
    best, fbest = 0.0, None
    n0 = max(1, int(math.ceil(F_CM[0] / f_sw)))
    n1 = int(F_CM[1] // f_sw)
    # the envelope is monotone between its corners, so the extremes and the corner harmonic suffice
    cand = {n0, n1, max(n0, min(n1, int(round(1 / (math.pi * f_sw * ti)))))}
    for n in sorted(cand):
        if n < 1 or n * f_sw > F_CM[1] * 1.0001 or n * f_sw < F_CM[0] * 0.9999:
            continue
        f = n * f_sw
        cn = 2 * I / (n * math.pi) * min(1.0, 1.0 / (n * math.pi * f_sw * ti))
        v = 2 * math.pi * f * abs(Le) * cn
        r = v / (CM_V_LIM_HZ / f)
        # above the edge corner the ratio is flat in n (1/n^2 envelope x f^2 coupling / f^-1 limit):
        # a tie, reported at its lowest frequency rather than by the last bit of L
        if r > best * (1 + 1e-9):
            best, fbest = r, f
    return best, fbest


def pair_u(kind, bound, Zf, Le, val):
    """u (size / bound) of one (observer, aggressor) pair at one point `val` ({param name: value}) of the
    aggressor's intervals, and its parts: dict(volts, bound, vf, ve) or dict(f_worst)."""
    I, ti = val["I_A"], val["t_i_s"]
    if kind == "cm":
        u, fw = cm(Le, I, val["f_sw_Hz"], ti)
        return u, dict(f_worst=fw)
    V, vf, ve = peak(Zf, Le, I, val.get("D", 0.5), ti)
    if kind == "overshoot" and "V_max_V" in val:
        bound = max(val["V_max_V"] - val.get("V_V", 0.0), 1e-3)          # the switch's own margin
    return (V / bound if bound else 0.0), dict(volts=V, bound=bound, vf=vf, ve=ve)


def phi(u):
    """The margin price: linear to the bound, then a quadratic barrier."""
    return u if u <= 1 else u + 4 * (u - 1) ** 2


# the design objective is the mean total over the worst fifth of the corners (a conditional value at
# risk): a layout that is good only at the typical point, or only at one lucky corner, does not score well
WORST_SHARE = 0.2


def robust(totals):
    """(objective, indices of the corners it averages) from per-corner totals."""
    k = max(1, math.ceil(WORST_SHARE * len(totals)))
    idx = sorted(range(len(totals)), key=lambda c: totals[c])[-k:]
    return sum(totals[c] for c in idx) / k, idx
