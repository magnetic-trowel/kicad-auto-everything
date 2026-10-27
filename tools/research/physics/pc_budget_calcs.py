#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Back-of-envelope numbers behind docs/topics/physics/physics-critics*.md (workstream 9).

Each block prints one table of closed-form estimates used to set critic thresholds
and to judge whether a planted fault matters. Formulas are textbook (Hammerstad
microstrip, plane-pair spreading, quarter-wave stub, cavity modes, sheet resistance,
Hockanson/Hubing-style return-plane inductance). They are screening numbers, not
sign-off: each critic doc row says how to calibrate them.

Run:  python3 -I pc_budget_calcs.py        (numpy and scipy only; deterministic)
"""
import math

import numpy as np
from scipy.optimize import curve_fit

MU0 = 4e-7 * math.pi
C0 = 299792458.0


def lprime(w, h):
    """Microstrip loop inductance per length (H/m); w, h in any common unit."""
    u = w / h
    if u <= 1:
        return MU0 / (2 * math.pi) * math.log(8 / u + u / 4)
    return MU0 / (u + 1.393 + 0.667 * math.log(u + 1.444))


def section(t):
    print(f"\n## {t}")


section("1. Return-current spread under a microstrip: share within +-x of the centreline")
for x in (1, 2, 3, 5, 10):
    print(f"x = {x:>2} h : {200 / math.pi * math.atan(x):5.1f} %")

section("2. Decap ground via moved away: extra series L of the connecting trace")
for w, h in ((0.25, 0.1), (0.25, 0.2), (0.5, 0.2)):
    for d in (1, 2, 5):
        l_add = lprime(w, h) * d * 1e-3
        print(f"w={w} mm h={h} mm d={d} mm : +{l_add * 1e9:.2f} nH, "
              f"|Z| at 100 MHz +{2 * math.pi * 1e8 * l_add * 1e3:.0f} mOhm")
c, esl, mount = 100e-9, 0.4e-9, 0.6e-9
for extra in (0, lprime(0.25, 0.1) * 5e-3):
    lt = esl + mount + extra
    print(f"100 nF, L_total {lt * 1e9:.2f} nH -> f_srf {1 / (2 * math.pi * math.sqrt(lt * c)) / 1e6:.1f} MHz, "
          f"|Z(100 MHz)| {abs(2 * math.pi * 1e8 * lt - 1 / (2 * math.pi * 1e8 * c)) * 1e3:.0f} mOhm")

section("3. Hot-loop partial inductance (current sheet over a plane) and overshoot")
for length, w, h in ((6, 3, 0.1), (6, 3, 0.2), (12, 3, 0.2), (12, 3, 1.0), (20, 2, 1.5)):
    lh = MU0 * h * length / (w + 2 * h) * 1e-3  # parallel-plate with fringing width w+2h [I]
    print(f"path {length} mm, width {w} mm, plane depth {h} mm: L ~ {lh * 1e9:.2f} nH -> "
          f"overshoot {lh * 1e9:.2f} V per A/ns; at 5 A/ns {5 * lh * 1e9:.1f} V")

section("4. Crosstalk coupling factor K = 1/(1+(D/H)^2), aggressor 3.3 V")
for dh in (1, 2, 3, 5):
    k = 1 / (1 + dh * dh)
    print(f"D/H = {dh}: K = {k:.3f} -> {3300 * k:.0f} mV (before the min(1, 2T/tr) length factor)")

section("5. Via stub quarter-wave resonance f = c/(4 L sqrt(er)), er = 4.2")
nyq = {"USB2 HS": 0.24, "USB3 Gen1": 2.5, "PCIe Gen3": 4.0, "PCIe Gen4": 8.0, "PCIe Gen5": 16.0}
for stub in (0.2, 0.5, 0.8, 1.4):
    f = C0 / (4 * stub * 1e-3 * math.sqrt(4.2)) / 1e9
    worry = [k for k, v in nyq.items() if f < 3 * v]
    print(f"stub {stub} mm: f_res {f:5.1f} GHz; below 3x Nyquist for: {', '.join(worry) or 'none'}")

section("6. Plane cavity and stitching: first mode c/(2 sqrt(er) d), er = 4.5")
for d in (100, 50, 20, 10, 5):
    print(f"d = {d:>3} mm: {C0 / (2 * math.sqrt(4.5) * d * 1e-3) / 1e9:5.2f} GHz")
for tr in (1e-9, 0.5e-9, 0.1e-9):
    fk = 0.35 / tr
    lam = C0 / math.sqrt(4.5) / fk
    print(f"t_r {tr * 1e9:.1f} ns: f_knee {fk / 1e9:.2f} GHz, lambda/20 in FR-4 {lam / 20 * 1e3:.1f} mm")

section("7. Pour neck: sheet resistance, drop and current density (copper, 20 C)")
for oz, t in ((1, 0.035), (2, 0.070)):
    rsq = 1.72e-8 / (t * 1e-3)
    for w, l, i in ((1.0, 5.0, 5.0), (2.0, 5.0, 5.0), (0.5, 2.0, 2.0)):
        r = rsq * l / w
        print(f"{oz} oz neck {w} x {l} mm at {i} A: {r * 1e3:.2f} mOhm, {i * r * 1e3:.1f} mV, "
              f"{i * i * r * 1e3:.0f} mW, J = {i / (w * t):.0f} A/mm^2")

section("8. Ott slot data (10 MHz trace, 3 ns edges): fit dV = a*l*ln(l/l0)")
slot_in = np.array([0.25, 0.5, 1.0, 1.5])
dv_mv = np.array([20, 26, 49, 75]) - 15.0  # plane voltage minus the no-slot 15 mV
(a, l0), _ = curve_fit(lambda l, a, l0: a * l * np.log(l / l0), slot_in, dv_mv, p0=(30, 0.05),
                       bounds=([0, 1e-4], [1e4, 0.24]))
for li, dv in zip(slot_in, dv_mv):
    print(f'slot {li}": measured +{dv:.0f} mV, fit +{a * li * math.log(li / l0):.1f} mV')
print(f"a = {a:.1f} mV/in, l0 = {l0:.3f} in; a pure linear fit would miss by 2-3x across the range")
zs, v = 100.0, C0 / math.sqrt((4.5 + 1) / 2)
print(f"shorted-slotline model, centred 1\" slot: L ~ {zs / v * 12.7e-3 / 2 * 1e9:.1f} nH (Z_slot 100 Ohm assumed)")

section("9. Return-plane inductance and common-mode voltage (Hockanson/Hubing, MREMC form)")
for edge_mm in (25.0, 5.0, 1.0):
    t, lt, d1 = 0.1e-3, 50e-3, edge_mm * 1e-3
    d2 = 50e-3 - d1
    we, off = d1 + d2, abs(d1 - d2) / 2
    lret = MU0 / math.pi * t * lt / we / math.sqrt(max(1e-9, 1 - 4 * (1 - 2 * t / we) * off ** 2 / we ** 2))
    f, i_h = 75e6, 3.3 * 2 / (3 * math.pi) * 2 * math.pi * 75e6 * 8e-12  # 3rd harmonic into 8 pF
    print(f"50 mm trace, h 0.1 mm, {edge_mm:>4} mm from the edge of a 50 mm board: L_ret {lret * 1e12:.1f} pH, "
          f"V_cm at 75 MHz ({i_h * 1e3:.1f} mA) {2 * math.pi * f * lret * i_h * 1e6:.1f} uV (1 mV line, 100 uV strict)")

section("10. Reference change through a bridging cap: mu0*t/pi*ln(D/r) + 1 nH mounting")
for t_mm in (0.2, 1.0):
    for dmm in (2, 5, 10, 20):
        lx = MU0 * t_mm * 1e-3 / math.pi * math.log(dmm / 0.15) + 1e-9
        print(f"plane gap {t_mm} mm, cap at {dmm:>2} mm: +{lx * 1e9:.2f} nH")

section("11. Shorted-slot-line VOID proxy (used by pc_refplane.py) vs the in-repo PEEC")
# Reference values: tools/research/physics/fe_peec_plane.py (workstream 5), section "Slot crossing",
# nH per mm of h for a trace (w = 2h) crossing the centre of a slot of length l and width g.
peec = {(10, 0.5): 0.714, (25, 0.5): 1.960, (50, 0.5): 3.945, (100, 0.5): 7.670,
        (10, 2.0): 1.421, (25, 2.0): 3.409, (50, 2.0): 6.376, (100, 2.0): 11.690}
zs_over_v = 100.0 / (C0 / math.sqrt((4.5 + 1) / 2)) * 1e6  # nH per mm
for (l_h, g_h), ref in peec.items():
    proxy = zs_over_v * l_h / 4  # centred slot: two shorted stubs of l/2 in parallel -> Z_s/v * l/4
    print(f"l/h {l_h:>3}, g/h {g_h}: proxy {proxy:5.2f}, PEEC {ref:5.2f} nH per mm of h -> ratio {proxy / ref:.2f}")
