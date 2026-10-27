# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Eddy currents in a copper plane under a power inductor (the "copper under the inductor" rule).

Workstream 4 (power). Model: the inductor's winding as coaxial filament loops
(an air-coil equivalent of its external field) above an infinite copper sheet of
thickness T (one PCB copper layer). The impedance change of the coil follows the
Dodd and Deeds (1968) spectral solution:

    dZ = j w mu0 pi sum_ij a_i a_j Int_0^inf J1(k a_i) J1(k a_j) exp(-k (z_i + z_j)) G(k) dk
    G(k) = (k^2 - b^2)(1 - exp(-2 b T)) / ((k + b)^2 - (k - b)^2 exp(-2 b T)),  b = sqrt(k^2 + j w mu0 sigma)

G -> -1 for a perfect conductor (image), G -> 0 for no plate. Re(dZ) is the eddy
loss resistance referred to the winding, Im(dZ)/w the inductance change.

A real inductor puts only a fraction f_ext of its magnetic energy outside the
core where the plane can reach it, so the air-coil numbers are scaled by f_ext
(an assumption, tagged [I] in the docs: ~0.3-0.5 drum/unshielded, ~0.05-0.1
semi-shielded, ~0.005-0.02 shielded/molded). The script prints the air-coil
fractions and the scaled losses for a representative 5 A buck.

Run:  python pw_eddy.py      (numpy + scipy, deterministic, a few seconds)
"""
import math

import numpy as np
from scipy.integrate import quad
from scipy.special import ellipe, ellipk, j1

MU0 = 4e-7 * math.pi
SIG = 5.8e7
mm = 1e-3


def gamma(k, f, T, sigma=SIG):
    b = np.sqrt(k * k + 1j * 2 * math.pi * f * MU0 * sigma)
    e = np.exp(-2 * b * T)
    return (k * k - b * b) * (1 - e) / ((k + b) ** 2 - (k - b) ** 2 * e)


def pair_integral(ai, aj, zsum, f, T, perfect=False):
    def integrand(k, part):
        g = -1.0 if perfect else gamma(k, f, T)
        v = j1(k * ai) * j1(k * aj) * np.exp(-k * zsum) * g
        return v.real if part == 0 else v.imag
    kmax = 60.0 / zsum
    re = quad(integrand, 0, kmax, args=(0,), limit=400)[0]
    im = 0.0 if perfect else quad(integrand, 0, kmax, args=(1,), limit=400)[0]
    return re + 1j * im


def mutual_coax(a, b, d):
    """Exact mutual inductance of two coaxial filament loops (Maxwell, elliptic integrals)."""
    k2 = 4 * a * b / ((a + b) ** 2 + d * d)
    k = math.sqrt(k2)
    return MU0 * math.sqrt(a * b) * ((2 / k - k) * ellipk(k2) - 2 / k * ellipe(k2))


def coil(a_in, a_out, z_bot, z_top, nr=3, nz=4):
    """Filament loops filling a winding cross-section (radii a_in..a_out, heights z_bot..z_top above the plane)."""
    rs = np.linspace(a_in, a_out, nr)
    zs = np.linspace(z_bot, z_top, nz)
    return [(r, z) for r in rs for z in zs]


def self_L(loops, wire_r=0.2 * mm):
    """Air-coil inductance: sum of mutuals, self-terms with a wire radius (current spread over the turns)."""
    L = 0.0
    for i, (ai, zi) in enumerate(loops):
        for j, (aj, zj) in enumerate(loops):
            d = abs(zi - zj)
            if i == j:
                L += MU0 * ai * (math.log(8 * ai / wire_r) - 2)
            else:
                L += mutual_coax(ai, aj, max(d, 1e-9) if ai != aj or d > 0 else wire_r)
    return L


def dZ(loops, f, T, perfect=False):
    tot = 0j
    for ai, zi in loops:
        for aj, zj in loops:
            tot += ai * aj * pair_integral(ai, aj, zi + zj, f, T, perfect)
    return 1j * 2 * math.pi * f * MU0 * math.pi * tot


def main():
    print("== check: perfect-conductor image vs exact coaxial mutual (a = 2.5 mm loop at h above the plane)")
    for h in (0.5 * mm, 2 * mm):
        m_spec = MU0 * math.pi * 2.5e-3 ** 2 * pair_integral(2.5e-3, 2.5e-3, 2 * h, 1e6, 35e-6, perfect=True).real
        print(f"  h = {h/mm:.1f} mm: spectral {m_spec*1e9:.4f} nH vs Maxwell M(2h) {mutual_coax(2.5e-3, 2.5e-3, 2*h)*1e9:.4f} nH")
    print("== air-coil equivalent: winding radii 1.5-3.0 mm, 0.5-3.5 mm above the board surface, N turns scale out")
    print("   (fractions are per unit N^2; the plane is the top-copper pour (gap 0), L2 (0.1-0.2 mm) or bottom (1.6 mm))")
    print("  plane depth   f       T      dL/L_air   R_eddy/(w L_air)  [loss tangent]")
    rows = []
    for depth in (0.0, 0.1 * mm, 0.2 * mm, 1.6 * mm):
        loops = coil(1.5 * mm, 3.0 * mm, 0.5 * mm + depth, 3.5 * mm + depth)
        L0 = self_L(loops)
        for f in (1e5, 5e5, 2e6):
            for T in (35e-6, 70e-6):
                z = dZ(loops, f, T)
                w = 2 * math.pi * f
                dl = z.imag / w / L0
                tan = z.real / (w * L0)
                rows.append((depth, f, T, dl, tan))
                print(f"  {depth/mm:4.1f} mm   {f:7.0e} {T*1e6:3.0f}um   {dl*100:+6.2f}%     {tan:8.4f}")
        zp = dZ(loops, 1e6, 35e-6, perfect=True)
        print(f"  {depth/mm:4.1f} mm   perfect-conductor limit dL/L_air = {zp.imag/(2*math.pi*1e6)/L0*100:+6.2f}%")
    # worked example: 5 A buck, 500 kHz, L = 3.3 uH, ripple 1.5 A p-p (triangle)
    print("== worked example: L = 3.3 uH, f_sw = 500 kHz, ripple 1.5 A p-p (triangle), plane = L2 at 0.1 mm")
    loops = coil(1.5 * mm, 3.0 * mm, 0.6 * mm, 3.6 * mm)
    L0 = self_L(loops)
    dI = 1.5
    tot = 0.0
    for n in range(1, 40, 2):
        In = 4 * dI / (math.pi ** 2 * n * n)  # amplitude of odd harmonics of a symmetric triangle (p-p = dI)
        z = dZ(loops, n * 5e5, 35e-6)
        tan = z.real / (2 * math.pi * n * 5e5 * L0)
        R_eddy = tan * 2 * math.pi * n * 5e5 * 3.3e-6   # referred to the real inductor, before f_ext
        tot += 0.5 * In * In * R_eddy
        if n in (1, 3, 5):
            print(f"  harmonic {n}: amplitude {In:5.3f} A, loss tangent {tan:6.4f}, R_eddy(air-coil-fraction x 3.3 uH) {R_eddy*1e3:7.1f} mOhm")
    print(f"  loss if ALL of the inductor's energy were external (f_ext = 1): {tot*1e3:7.1f} mW")
    for name, fe in (("unshielded drum (f_ext ~ 0.4)", 0.4), ("semi-shielded (~0.07)", 0.07), ("shielded / molded (~0.01)", 0.01)):
        print(f"  {name:32s}: eddy loss ~ {tot*fe*1e3:6.2f} mW; dL/L ~ {rows[[r[0] for r in rows].index(0.1*mm)][3]*fe*100:+5.2f}% (500 kHz row x f_ext)")
    print("  compare: inductor DCR loss at 5 A with 20 mOhm DCR = 500 mW; converter loss ~ 1-2 W")


if __name__ == "__main__":
    main()
