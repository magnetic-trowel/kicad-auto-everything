# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""First-principles radiated-EMI budget chain for one fast net (docs/topics/physics/fields-emi-budget.md).

Chain, per harmonic n of a trapezoidal source:
  1. spectrum      V_n = 2 A d |sinc(n pi d)| |sinc(n pi t_r / T)|
  2. drive current I_n = V_n * |Y_load(f)|, Y = j w C / (1 + j w R_s C)   (lumped, short line)
  3. coupling      V_cm = 2 pi f L_cm I_n  (current-driven: net plane inductance between
                   the two cable attachment points; LearnEMC/MREMC L_ret, plus a slot term
                   calibrated with fe_peec_plane.py), optionally shunted by a stitching cap
  4. antenna       E_max = F_max * 0.55 * V_cm * cablefactor   (LearnEMC MREMC current-driven
                   two-cable model, read from CMode_algr.js; worst-case cable resonance)
                   cross-check: I_cm = V_cm / Z_cm with Z_cm = 36 ohm (quarter-wave monopole
                   resonance, worst case) and 150 ohm (typical), E from Ott's short-antenna
                   formula E = 1.257e-6 f L I / r capped at the resonant value 2*60*I/r.
  5. limit         CISPR 32 Class B at 3 m: 40 dBuV/m (30-230 MHz), 47 dBuV/m (230-1000 MHz).
Prints the worst margin per case and the cable common-mode current vs Ott's 5 uA rule.

Run:  python tools/research/physics/fe_emi_budget.py    (pure Python + numpy, < 1 s)
"""
import math

import numpy as np

MU0 = 4e-7 * math.pi
C0 = 2.998e8


def mremc_lret(h, lt, d1, d2):
    """LearnEMC MREMC return-plane inductance (H); h trace height, lt trace length, d1/d2 to edges (m)."""
    we, off = d1 + d2, abs(d1 - d2) / 2
    return MU0 / math.pi * h * lt / we / math.sqrt(1 - 4 * (1 - 2 * h / we) * off ** 2 / we ** 2)


def slot_inductance(l, g):
    """Slotline estimate of the loop inductance a slot adds under a crossing trace (H).
    fe_peec_plane.py: within ~15 % of PEEC for l >= 25 h, g >= 2 h; overestimates short/narrow slots."""
    return MU0 * l / (2 * math.log(4 * l / g))


def cispr32_b_3m(f):
    if f < 30e6:
        return float("nan")
    return 40.0 if f <= 230e6 else 47.0


def fmax_factor(f, lcable=1.0):
    if f <= C0 / 2 / lcable:
        return 2 / math.sin(math.sqrt(2))
    return 2 / math.sin(math.sqrt(C0 / f / lcable))


def cable_factor(f):
    lam = C0 / f
    return math.sin(2 * math.pi / lam) if lam >= 4 else 1.0


def dbuv(v):
    return 20 * math.log10(max(v, 1e-30) * 1e6)


def run_case(name, *, A=3.3, f0=50e6, duty=0.5, tr=1e-9, Rs=33.0, C=10e-12, L_cm=30e-12,
             slot=None, cap=None, same_edge_db=0.0, r=3.0, lcable=1.0, fmax=1e9, verbose=False):
    """L_cm: solid-plane net inductance between cable points (H).
    slot = (L_slot, kappa): slot loop inductance and the share of its voltage seen between cables.
    cap = (C_stitch, L_path): stitching capacitor across the slot at the crossing."""
    T = 1 / f0
    worst = (1e9, None)
    rows = []
    imax = 0.0
    for n in range(1, int(fmax / f0) + 1):
        f = n * f0
        if f < 30e6:
            continue
        Vn = 2 * A * duty * abs(np.sinc(n * duty)) * abs(np.sinc(n * tr / T))
        w = 2 * math.pi * f
        In = Vn * w * C / math.sqrt(1 + (w * Rs * C) ** 2)
        Z = 1j * w * L_cm
        if slot is not None:
            Ls, kappa = slot
            Zslot = 1j * w * Ls
            if cap is not None:
                Cs, Lp = cap
                Zcap = 1j * w * Lp + 1 / (1j * w * Cs) + 0.03
                Zslot = Zslot * Zcap / (Zslot + Zcap)
            Z = Z + kappa * Zslot
        Vcm = abs(Z) * In * 10 ** (-same_edge_db / 20)
        E = fmax_factor(f, lcable) * 0.55 * Vcm * cable_factor(f)
        Icm_res, Icm_typ = Vcm / 36.0, Vcm / 150.0
        E_ott = min(1.257e-6 * f * lcable * Icm_typ / r, 2 * 60 * Icm_typ / r)
        lim = cispr32_b_3m(f)
        margin = lim - dbuv(E)
        imax = max(imax, Icm_typ)
        rows.append((f, In, Vcm, dbuv(E), dbuv(E_ott), lim, margin, Icm_res, Icm_typ))
        if margin < worst[0]:
            worst = (margin, f)
    print(f"\n== {name}")
    if verbose:
        print("  f[MHz]  I_dm[mA]  V_cm[uV]  E_MREMC[dBuV/m]  E_Ott(150ohm)  limit  margin  I_cm res/typ [uA]")
        for f, In, V, E, Eo, lim, m, i1, i2 in rows[:10]:
            print(f"  {f/1e6:6.0f}  {In*1e3:7.2f}  {V*1e6:8.1f}  {E:8.1f}         {Eo:7.1f}       {lim:4.0f}  {m:6.1f}"
                  f"  {i1*1e6:6.2f}/{i2*1e6:6.2f}")
    print(f"  worst margin {worst[0]:+.1f} dB at {worst[1]/1e6:.0f} MHz; max I_cm (150 ohm) "
          f"{imax*1e6:.2f} uA vs Ott 5 uA rule ({20*math.log10(5e-6/max(imax,1e-30)):+.1f} dB)")
    return worst


def main():
    h, lt = 0.2e-3, 30e-3          # L1 over L2 GND, 30 mm clock trace
    W = 80e-3                       # board width (edge-to-edge across the trace)
    Lret = mremc_lret(h, lt, W / 2, W / 2)
    Lret_edge = mremc_lret(h, lt, 3 * h, W - 3 * h)
    Ls = slot_inductance(20e-3, 0.5e-3)
    kappa = 2.09 / 11.69            # fe_peec_plane.py: share of slot dL seen between the board-end centres
    print(f"L_ret (MREMC, centred) = {Lret*1e12:.1f} pH; trace 3h from edge = {Lret_edge*1e12:.1f} pH")
    print(f"slot 20 x 0.5 mm: loop dL = {Ls*1e9:.2f} nH; seen between board ends ~{kappa:.2f} x dL "
          f"(slot inside the board) to ~1.0 x dL (slot splits the board)")
    print("1 mV CM check: E_MREMC(1 mV, 100 MHz) = "
          f"{dbuv(fmax_factor(100e6) * 0.55 * 1e-3 * cable_factor(100e6)):.1f} dBuV/m; "
          f"I_cm = 1 mV/150 ohm = {1e-3/150*1e6:.1f} uA")

    base = dict(A=3.3, f0=50e6, tr=1e-9, Rs=33.0, C=10e-12)
    run_case("A. 50 MHz clock, 30 mm, solid plane, cables on opposite edges", L_cm=Lret, verbose=True, **base)
    run_case("A2. same, trace 3h from the board edge", L_cm=Lret_edge, **base)
    sl_in, sl_split = (Ls, kappa), (Ls, 1.0)
    run_case("B. crosses a 20 mm slot (slot inside the board), cables on opposite sides",
             L_cm=Lret, slot=sl_in, verbose=True, **base)
    run_case("B2. slot splits the board (bridge far away), cables on opposite sides",
             L_cm=Lret, slot=sl_split, **base)
    run_case("C. B + one 10 nF stitching cap at the crossing (path 1.0 nH)",
             L_cm=Lret, slot=sl_in, cap=(10e-9, 1.0e-9), **base)
    run_case("C2. B2 + one 10 nF stitching cap at the crossing (path 1.0 nH)",
             L_cm=Lret, slot=sl_split, cap=(10e-9, 1.0e-9), **base)
    run_case("C3. B2 + two caps, one each side of the trace (path 0.5 nH effective)",
             L_cm=Lret, slot=sl_split, cap=(20e-9, 0.5e-9), **base)
    run_case("C4. B2 + one cap 5 mm along the slot (path 1.0 + ~0.6 nH slot edge)",
             L_cm=Lret, slot=sl_split, cap=(10e-9, 1.6e-9), **base)
    run_case("D. B, but both cables on the same edge (PEEC: >= 40 dB less plane voltage)",
             L_cm=Lret, slot=sl_in, same_edge_db=40.0, **base)
    run_case("E. B with slew-limited driver t_r = 3 ns", L_cm=Lret, slot=sl_in, **{**base, "tr": 3e-9})
    run_case("F. B with series R raised to 100 ohm", L_cm=Lret, slot=sl_in, **{**base, "Rs": 100.0})
    run_case("G. A on a 2-layer board, h = 1.5 mm (no slot)", L_cm=mremc_lret(1.5e-3, lt, W / 2, W / 2), **base)

    # skew-driven common mode on an unshielded differential cable
    print("\n== H. Unshielded differential cable: CM from intra-pair skew, V_cm(f) = V_d(f) sin(pi f dt)")
    Vd, f0, tr = 2.0, 31.25e6, 3e-9   # 2 Vpp differential square wave, upper bound for 100BASE-TX
    for dt in (5e-12, 50e-12, 200e-12):
        worst = 1e9
        imax = 0
        for n in range(1, 33, 2):
            f = n * f0
            if f < 30e6:
                continue
            Vn = 2 * Vd * 0.5 * abs(np.sinc(n * 0.5)) * abs(np.sinc(n * tr * f0))  # Vd = p-p swing
            Vcm = Vn * abs(math.sin(math.pi * f * dt)) / 2
            E = fmax_factor(f) * 0.55 * Vcm * cable_factor(f)
            worst = min(worst, cispr32_b_3m(f) - dbuv(E))
            imax = max(imax, Vcm / 150)
        print(f"  skew {dt*1e12:5.0f} ps: worst margin {worst:+.1f} dB (before CMC/magnetics), "
              f"I_cm max {imax*1e6:.1f} uA")


if __name__ == "__main__":
    main()
