# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Manufacturing and mechanical physics behind common PCB DFM rules.

Sections (all printed; inputs are stated next to each result):
  A  etching: JLCPCB min space vs copper thickness (linear fit), etch-factor
     trapezoid and its resistance penalty
  B  through-hole plating: throwing power from a 1-D electrolyte/polarisation
     transmission-line model, TP = 1/cosh(L/(2*Lambda)),
     Lambda = sqrt(R_p*d/(4*rho_e)) (secondary current distribution only)
  C  warpage: Timoshenko bilayer curvature for unbalanced copper and for an
     asymmetric resin-rich layer; bow % over 100 mm vs the IPC 0.75 % limit
  F  via-in-pad solder theft: open barrel volume vs printed solder volume
  G  thermal relief: electrical R, partial L and thermal conductance of
     spokes vs a solid connection
  H  mechanics: 3-point-bend surface strain (AEC-Q200 flex test, a screw
     boss), first plate mode of a board, Steinberg displacement limit
  I  drill wander: probability of breakout at the trace junction vs annular
     ring and position sigma, with and without a teardrop
  J  defect-limited yield: critical area of parallel conductors with a
     1/x^3 defect-size distribution, A = L*x0^2/s (shorts), L*x0^2/w (opens)

Run (numpy, scipy):

    python tools/research/physics/tm_mfg_physics.py
"""
import math

import numpy as np
from scipy.stats import norm

OZ = 34.8e-6
RHO_CU = 1.72e-8
MU0 = 4e-7 * math.pi


def section_a():
    print("A  etching")
    data = [(1, 0.10), (2, 0.16), (2.5, 0.20), (3.5, 0.25), (4.5, 0.30)]   # JLCPCB 2L, oz -> mm
    t = np.array([d[0] * OZ * 1e3 for d in data])
    s = np.array([d[1] for d in data])
    b, a = np.polyfit(t, s, 1)
    print(f"    JLCPCB 2L min space ~ {a*1e3:.0f} um + {b:.2f} x copper thickness  (fit to 1-4.5 oz)")
    for ef in (2.0, 3.0, 4.0):
        for w in (0.10e-3, 0.20e-3):
            tc = OZ
            u = tc / ef
            wt = w - 2 * u
            area = tc * (w + wt) / 2
            print(f"    EF={ef:.0f}, 1 oz, drawn base {w*1e3:.2f} mm: undercut {u*1e6:4.1f} um/side, top {wt*1e3:.3f} mm,"
                  f" R +{(tc*w/area-1)*100:4.1f} % vs rectangle")


def section_b():
    print("B  through-hole plating throwing power (centre/surface thickness), 1-D model")
    rho_e = 0.02          # ohm*m, acid copper bath ~0.5 S/cm
    for rp_ohm_cm2 in (2.0, 5.0, 20.0):
        rp = rp_ohm_cm2 * 1e-4   # ohm*m^2
        cells = []
        for L, d in ((1.6e-3, 0.4e-3), (1.6e-3, 0.2e-3), (1.6e-3, 0.15e-3), (2.4e-3, 0.2e-3), (3.2e-3, 0.2e-3)):
            lam = math.sqrt(rp * d / (4 * rho_e))
            tp = 1 / math.cosh(L / (2 * lam))
            cells.append(f"AR {L/d:4.1f}:{tp*100:3.0f}%")
        print(f"    R_p={rp_ohm_cm2:4.0f} ohm*cm^2  " + "  ".join(cells))
    print("    (additives raise R_p, i.e. the Wagner number, which is why 'high-throw' baths work;"
          " mass transport into the hole is ignored)")


def timoshenko_kappa(E1, h1, E2, h2, deps):
    num = 6 * E1 * E2 * (h1 + h2) * h1 * h2 * deps
    den = (E1 ** 2 * h1 ** 4 + 4 * E1 * E2 * h1 ** 3 * h2 + 6 * E1 * E2 * h1 ** 2 * h2 ** 2
           + 4 * E1 * E2 * h1 * h2 ** 3 + E2 ** 2 * h2 ** 4)
    return num / den


def section_c():
    print("C  warpage (bilayer estimate, bow = kappa*L^2/8 over L = 100 mm; IPC limit 0.75 %)")
    E_cu, E_fr4 = 110e9, 22e9
    L = 0.1
    for imbalance in (0.2, 0.5, 0.8):
        for dalpha, dT in ((3e-6, 150), (6e-6, 150)):
            h1 = OZ * imbalance
            k = timoshenko_kappa(E_cu, h1, E_fr4, 1.6e-3, dalpha * dT)
            print(f"    outer-copper imbalance {imbalance*100:3.0f}% of 1 oz, d_alpha {dalpha*1e6:.0f} ppm/K, dT {dT} K:"
                  f" bow {k*L*L/8/L*100:6.3f} %")
    for thick in (0.05e-3, 0.1e-3):
        k = timoshenko_kappa(8e9, thick, E_fr4, 1.6e-3, 20e-6 * 150)
        print(f"    resin-rich asymmetric layer {thick*1e3:.2f} mm, E 8 GPa, d_alpha 20 ppm/K, dT 150 K: "
              f"bow {k*L*L/8/L*100:6.3f} %")
    for d_asym in (0.1e-3, 0.2e-3):
        # unequal dielectric: model the extra prepreg as a layer with d_alpha 5 ppm/K (resin vs core) and E 15 GPa
        k = timoshenko_kappa(15e9, d_asym, E_fr4, 1.6e-3, 5e-6 * 150)
        print(f"    asymmetric dielectric (+{d_asym*1e3:.1f} mm prepreg on one side, d_alpha 5 ppm/K): "
              f"bow {k*L*L/8/L*100:6.3f} %")


def section_f():
    print("F  via-in-pad solder theft: open-via volume / printed solder volume (paste 50 % metal by volume)")
    cases = [
        ("0402 pad 0.5x0.6, stencil 0.10, one 0.20 mm via (finished 0.15), 1.6 mm", 0.5 * 0.6 * 0.10, 1, 0.15, 1.6),
        ("QFN EP 3x3, 60 % paste, stencil 0.12, 9 x 0.30 mm vias (0.25), 1.6 mm", 9 * 0.6 * 0.12, 9, 0.25, 1.6),
        ("QFN EP 3x3, 60 % paste, stencil 0.12, 9 x 0.20 mm vias (0.15), 1.6 mm", 9 * 0.6 * 0.12, 9, 0.15, 1.6),
        ("BGA 0.5 mm pitch pad 0.25, stencil 0.10, open 0.10 mm microvia 0.075 deep", math.pi * 0.125 ** 2 * 0.10, 1, 0.10, 0.075),
    ]
    for name, paste_mm3, n, dfin, L in cases:
        solder = paste_mm3 * 0.5
        via = n * math.pi * (dfin / 2) ** 2 * L
        print(f"    {name:78s} ratio {via/solder:5.2f}")


def spoke_L_nH(l_mm, w_mm, t_mm):
    """Partial self-inductance of a rectangular bar (Grover/Ruehli approximation)."""
    return 0.2 * l_mm * (math.log(2 * l_mm / (w_mm + t_mm)) + 0.5 + 0.2235 * (w_mm + t_mm) / l_mm)


def section_g():
    print("G  thermal relief (1 oz, 4 spokes, spoke length = relief gap)")
    t = OZ
    for w, gap in ((0.25e-3, 0.25e-3), (0.25e-3, 0.5e-3), (0.15e-3, 0.3e-3)):
        r1 = RHO_CU * gap / (w * t)
        L1 = spoke_L_nH(gap * 1e3, w * 1e3, t * 1e3)
        g1 = 390 * w * t / gap
        print(f"    spokes {w*1e3:.2f} mm x {gap*1e3:.2f} mm: R(4 par) {r1/4*1e3:5.3f} mOhm,"
              f" L(4 par, no mutual) {L1/4:5.3f} nH, G_th(4) {4*g1*1e3:5.1f} mW/K")
    for a in (0.3e-3, 0.8e-3):
        for b in (a + 0.25e-3,):
            gsol = 2 * math.pi * 390 * t / math.log(b / a)
            print(f"    solid ring from pad radius {a*1e3:.1f} mm to {b*1e3:.2f} mm: G_th {gsol*1e3:5.1f} mW/K")
    gspread = 2 * math.pi * 390 * t / math.log(8e-3 / 0.5e-3)
    print(f"    plane spreading 0.5 -> 8 mm (in series with either): {gspread*1e3:4.1f} mW/K;"
          f" a 0402 pad's own convective + local-FR4 coupling ~0.1 mW/K")


def section_h():
    print("H  board mechanics")
    for name, t, d, L in (("AEC-Q200 flex test, 2 mm over 90 mm span", 1.6e-3, 2e-3, 90e-3),
                          ("AEC-Q200 flex test, 5 mm over 90 mm (soft termination)", 1.6e-3, 5e-3, 90e-3),
                          ("screw pulls board 0.1 mm over a 10 mm local span", 1.6e-3, 0.1e-3, 10e-3),
                          ("same, 0.8 mm board", 0.8e-3, 0.1e-3, 10e-3),
                          ("ICT fixture 0.5 mm over 60 mm", 1.6e-3, 0.5e-3, 60e-3)):
        eps = 6 * t * d / L ** 2
        print(f"    {name:55s} peak surface strain {eps*1e6:6.0f} ue")
    E, nu, rho = 22e9, 0.15, 1900.0
    for a, b, t, extra in ((100e-3, 80e-3, 1.6e-3, 1.0), (100e-3, 80e-3, 1.6e-3, 2.0),
                           (160e-3, 100e-3, 1.6e-3, 2.0), (100e-3, 80e-3, 0.8e-3, 2.0)):
        D = E * t ** 3 / (12 * (1 - nu ** 2))
        m = rho * t * extra
        f = math.pi / 2 * (1 / a ** 2 + 1 / b ** 2) * math.sqrt(D / m)
        print(f"    plate {a*1e3:.0f}x{b*1e3:.0f}x{t*1e3:.1f} mm, mass x{extra:.0f} (parts), simply supported: f1 = {f:5.0f} Hz")
    print("    Steinberg: allowed board displacement Z = 0.00022*B/(c*t*r*sqrt(L)) in; r = 1 at the board"
          " centre, 0.5 at quarter span -> heavy/long parts near supports, long axis along B")


def section_i():
    print("I  drill-position breakout at the trace junction: P = Q(ring/sigma) per hole")
    for sigma in (0.025e-3, 0.04e-3):
        for ring in (0.075e-3, 0.10e-3, 0.15e-3):
            p = norm.sf(ring / sigma)
            ptd = norm.sf((ring + 0.15e-3) / sigma)
            pall = math.exp(-ring ** 2 / (2 * sigma ** 2))
            print(f"    sigma {sigma*1e3:5.3f} mm, ring {ring*1e3:4.2f} mm: junction breakout {p:8.1e}"
                  f" (with 0.15 mm teardrop {ptd:8.1e}); breakout anywhere {pall:8.1e}; per 1000 holes {1000*p:7.2f}")


def section_j():
    print("J  critical area (defects ~ 1/x^3 above x0): A_short = L*x0^2/s, A_open = L*x0^2/w")
    x0 = 0.025e-3
    for s in (0.1e-3, 0.15e-3, 0.2e-3, 0.3e-3):
        a = 1.0 * x0 ** 2 / s
        print(f"    1 m of parallel run at spacing {s*1e3:.2f} mm: short critical area {a*1e6:6.2f} mm^2"
              f"  (relative {0.1e-3/s:4.2f})")
    print("    yield Y = exp(-D0 * sum A); spreading a 0.1 mm gap to 0.2 mm halves its short risk")


if __name__ == "__main__":
    section_a()
    section_b()
    section_c()
    section_f()
    section_g()
    section_h()
    section_i()
    section_j()
