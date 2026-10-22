# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered predictions for the short-slot coupon (validation program, coupon SS).

Used by docs/topics/physics/validation-coupons.md. Lens IN found one board-level dispute
whose resolution has decision value: what a SHORT void (1-5 mm, e.g. merged via antipads)
under a fast trace costs. The candidate models disagree most there:

  slotline   dL = mu0 l / (2 ln(4 l / g))          (round 1, fields-si-emi; EMI chain)
  Babinet    dL = pi mu0 l / (8 (ln(4 l / g) - 1))  (lens SY)
  proxy      dL = Z_slot l / (4 v), Z_slot 100 ohm  (round-1 critic pc_refplane RET-COV)
  PEEC       quasi-static return-current solve      (round-1 fe_peec_plane.py, reused)
  Ott fit    dV ~ l ln(l / 2.3 mm), scaled to PEEC at l = 10 mm (pc_budget_calcs.py section 8):
             predicts that slots shorter than ~2.3 mm cost nothing

Coupon (JLC04161H-3313, L1 trace over the L2 plane, h_eff = 0.0994 + 0.0175 + 0.0076 mm):
50-ohm traces (0.19 mm), 20 mm long, SMA at one end, shorted to L2 with two vias at the
other; each crosses one void at mid-length, at right angles. Twins without a void on the
same panel give the differential. Voids: 1/2/3/5/10 x 0.3 mm slots, 2 and 5 x 0.8 mm slots,
five 0.9 mm antipads at 0.8 mm pitch (merged, a 4.1 x 0.9 mm void) and at 1.0 mm pitch
(separate holes). Observable: dL from S11 of each trace against its twin at 20-100 MHz
(NanoVNA, SOL calibration at the SMA). Second observable, Ott's: the plane voltage over
25.4 mm straddling the void, read through a thin Kelvin pair (sense traces on L1, 1 mm
beside the trace). Intervals: PEEC corners at h x 0.9 and x 1.1 and a model-form allowance
of +-15 % (quasi-static, zero-thickness plane, three filaments).

Run:  python tools/research/physics/val_slot_coupon.py     (numpy + scipy, ~4-6 min)
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402,F401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fe_peec_plane as fp  # noqa: E402  (round-1 plane PEEC, reused)

MU0 = 4e-7 * math.pi
C0 = 2.998e8
H_EFF = 0.0994 + 0.0175 + 0.0076      # mm, trace centre to plane centre
W_TR, LT = 0.19, 20.0                  # mm
ER_EFF = 3.1                           # 50-ohm microstrip on er 4.1, for the slot-line proxy
CASES = [  # (label, kind, length mm, width mm)
    ("slot 1 x 0.3", "slot", 1.0, 0.3), ("slot 2 x 0.3", "slot", 2.0, 0.3), ("slot 3 x 0.3", "slot", 3.0, 0.3),
    ("slot 5 x 0.3", "slot", 5.0, 0.3), ("slot 10 x 0.3", "slot", 10.0, 0.3),
    ("slot 2 x 0.8", "slot", 2.0, 0.8), ("slot 5 x 0.8", "slot", 5.0, 0.8),
    ("5 antipads 0.9 @ 0.8 (merged)", "slot", 4.1, 0.9), ("5 antipads 0.9 @ 1.0 (holes)", "holes", 5, 0.9),
]


def peec_dl(kind, l_mm, g_mm, h_mm):
    """Extra loop inductance (nH) of the void under the trace, PEEC in units of h then scaled."""
    h = 1.0
    g = g_mm / h_mm
    # dL is local to the crossing: the modelled trace only needs to extend past the detour region, so it is
    # shortened to max(30 h, 1.3 x void length) (checked: within 0.7 % of the full 20 mm trace on the 5 mm slot)
    extent_mm = l_mm
    w, lt = W_TR / h_mm, min(LT, max(30 * h_mm, 1.3 * extent_mm)) / h_mm

    def run(rem, ykeys, extent):
        X, Y = lt / 2 + 25, max(40.0, extent / 2 + 30)
        xkeys = [(-lt / 2, 0.5), (lt / 2, 0.5), (-g / 2, min(0.5, g / 3)), (g / 2, min(0.5, g / 3))]
        xs = fp.graded_lines(-X, X, xkeys, 8.0)
        ys = fp.graded_lines(-Y, Y, [(0.0, 0.33)] + ykeys, 8.0)
        pl = fp.Plane(xs, ys, rem)
        return fp.solve_loop(pl, 0.0, h, w, -lt / 2, lt / 2)["L"]

    base = run(None, [], 0.0)
    if kind == "slot":
        l = l_mm / h_mm
        rem = (lambda xc, y: abs(xc) < g / 2 and abs(y) <= l / 2 + 1e-9)
        ykeys = [(-l / 2, min(0.5, g / 3)), (l / 2, min(0.5, g / 3))]
        return (run(rem, ykeys, l) - base) * h_mm
    n, pitch = int(l_mm), 1.0 / h_mm
    centres = [(i - (n - 1) / 2) * pitch for i in range(n)]
    rem = (lambda xc, y: abs(xc) < g / 2 and any(abs(y - c) <= g / 2 + 1e-9 for c in centres))
    ykeys = [(c + s * g / 2, min(0.5, g / 3)) for c in centres for s in (-1, 1)]
    return (run(rem, ykeys, n * pitch) - base) * h_mm


def plane_v_1in(l_mm, g_mm, h_mm):
    """Plane voltage between points 25.4 mm apart on the trace axis, straddling the slot (Ott's observable),
    per unit trace current, in nH (V / (j w I)); returns (no slot, with slot)."""
    h, g, w = 1.0, g_mm / h_mm, W_TR / h_mm
    lt = 30.0 / h_mm
    xp = 12.7 / h_mm
    out = []
    for l_ in (0.0, l_mm / h_mm):
        X, Y = lt / 2 + 25, max(40.0, l_ / 2 + 30)
        xkeys = [(-lt / 2, 0.5), (lt / 2, 0.5), (-xp, 0.5), (xp, 0.5), (-g / 2, min(0.5, g / 3)), (g / 2, min(0.5, g / 3))]
        ykeys = [(0.0, 0.33)] + ([(-l_ / 2, min(0.5, g / 3)), (l_ / 2, min(0.5, g / 3))] if l_ else [])
        xs = fp.graded_lines(-X, X, xkeys, 8.0)
        ys = fp.graded_lines(-Y, Y, ykeys, 8.0)
        rem = (lambda xc, y, l_=l_: abs(xc) < g / 2 and abs(y) <= l_ / 2 + 1e-9) if l_ else None
        pl = fp.Plane(xs, ys, rem)
        r = fp.solve_loop(pl, 0.0, h, w, -lt / 2, lt / 2, want_potential=True)
        out.append(abs(fp.phi_at(pl, r["phi"], -xp, 0.0) - fp.phi_at(pl, r["phi"], xp, 0.0)) * h_mm)
    return out


def slotline(l, g):
    return MU0 * l * 1e-3 / (2 * math.log(4 * l / g)) * 1e9


def babinet(l, g):
    return math.pi * MU0 * l * 1e-3 / (8 * (math.log(4 * l / g) - 1)) * 1e9


def proxy(l):
    return 100.0 / (C0 / math.sqrt(ER_EFF)) * l * 1e-3 / 4 * 1e9


def main():
    print(f"== short-slot coupon: 0.19 mm trace, {LT:.0f} mm, h_eff = {H_EFF:.4f} mm over L2; dL in nH")
    base_l = None
    rows = []
    for label, kind, l, g in CASES:
        dl = peec_dl(kind, l, g, H_EFF)
        lo = peec_dl(kind, l, g, 0.9 * H_EFF)
        hi = peec_dl(kind, l, g, 1.1 * H_EFF)
        rows.append((label, kind, l, g, dl, min(lo, hi), max(lo, hi)))
    # Ott fit shape dV ~ l ln(l/l0), anchored to PEEC at the 10 x 0.3 mm slot
    l0 = 2.3
    anchor = [r for r in rows if r[0] == "slot 10 x 0.3"][0][4]
    k_ott = anchor / (10.0 * math.log(10.0 / l0))
    print("  void                              PEEC dL [interval incl. +-15% model]   slotline   Babinet   proxy    Ott-fit shape")
    for label, kind, l, g, dl, lo, hi in rows:
        if kind == "slot":
            sl, bb, px = slotline(l, g), babinet(l, g), proxy(l)
            ott = max(0.0, k_ott * l * math.log(l / l0))
            print(f"  {label:32s}  {dl:6.3f} [{0.85*lo:6.3f}, {1.15*hi:6.3f}]                {sl:6.3f}    {bb:6.3f}   {px:6.3f}   {ott:6.3f}")
        else:
            print(f"  {label:32s}  {dl:6.3f} [{0.85*lo:6.3f}, {1.15*hi:6.3f}]                (separate holes: formulas do not apply)")
    m = [r for r in rows if r[0].startswith("5 antipads") and "merged" in r[0]][0][4]
    s = [r for r in rows if r[0].startswith("5 antipads") and "holes" in r[0]][0][4]
    print(f"\n  merged vs separate antipads: {m:.3f} vs {s:.3f} nH (ratio {m/max(s,1e-6):.1f})")
    # what the critic decides: slot cost relative to the trace's own loop L and to an L budget
    lp = fp.MU0_4PI_NH_PER_MM  # unused, kept for reference to the module's units
    del lp
    print("\n  Ott's observable: plane voltage over 25.4 mm straddling the slot, per unit trace current (nH), 30 mm trace")
    print("    slot          no slot   with slot   ratio   (Ott, 1/4-1.5 in slots at his h: ratios 1.33/1.73/3.27/5.0)")
    for l in (1.0, 2.0, 3.0, 5.0, 10.0):
        v0, v1 = plane_v_1in(l, 0.3, H_EFF)
        print(f"    {l:4.1f} x 0.3    {v0:7.4f}   {v1:7.4f}    {v1/v0:5.2f}")
    print("  decision threshold used in validation-coupons.md: a void matters for an edge-critical net if dL > 0.1 nH")
    print("  (a 30 mA/ns USB-HS-class edge gives 3 mV of ground bounce per 0.1 nH)")


if __name__ == "__main__":
    main()
