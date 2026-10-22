# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Back-of-envelope thermal and electro-thermal checks for PCB layout.

Sections (all printed):
  A  per-via thermal resistance R = L/(k*A_barrel) for drill, plating, board
     thickness and fill; checks TI SNVA419's 261 C/W, the 150 C/W calculator
     figure and the SLVA959 5.73 C/W error
  B  heat-transfer coefficients: natural convection (vertical and horizontal
     plate correlations) and linearised radiation 4*eps*sigma*T^3
  C  15.3 cm^2/W: isothermal-plate area 1/(2*h*dT), and the fin length
     lambda = sqrt(G_sheet/h_total) for common stackups
  D  trace self-heating: line source on a board fin vs IPC-2221
     (I = k*dT^0.44*A^0.725), with and without a plane 0.2 mm below
  E  copper TCR feedback: dT = dT0/(1 - alpha*dT0); runaway at dT0 = 1/alpha
  F  Arrhenius: electrolytic life vs temperature (10 K doubling) and the
     implied activation energy
  G  thermocouple error of a 2-terminal part in a gradient from a 1 W source

Run (numpy, scipy):

    python tools/research/physics/tm_thermal_analytic.py
"""
import math

from scipy.optimize import brentq

K_CU = 390.0
RHO_CU = 1.72e-8      # ohm*m at 20 C (annealed; ED foil 1.7-1.9e-8)
ALPHA_CU = 0.00393    # 1/K at 20 C
SIGMA = 5.670e-8
OZ = 34.8e-6


def via_r(drill, plating, length, fill_k=0.0, k=K_CU):
    """Barrel conduction only; drill = plated barrel outer diameter."""
    a = math.pi * plating * (drill - plating)
    core = math.pi * (drill / 2 - plating) ** 2
    return length / (k * a + fill_k * core)


def section_a():
    print("A  per-via thermal resistance (barrel conduction, k_Cu = 390 W/mK)")
    rows = [
        ("TI SNVA419 case: 12 mil, 0.5 oz (17.5 um) wall, 1.6 mm", 0.3048e-3, 17.5e-6, 1.6e-3, 0),
        ("0.3 mm, 25 um, 1.6 mm (IPC class 2/3 typical)", 0.3e-3, 25e-6, 1.6e-3, 0),
        ("0.3 mm, 20 um, 1.6 mm", 0.3e-3, 20e-6, 1.6e-3, 0),
        ("0.2 mm, 20 um, 1.6 mm", 0.2e-3, 20e-6, 1.6e-3, 0),
        ("0.3 mm, 25 um, 0.2 mm (L1->L2 of a 4-layer)", 0.3e-3, 25e-6, 0.2e-3, 0),
        ("0.3 mm, 25 um, 1.6 mm, epoxy filled (k 0.3)", 0.3e-3, 25e-6, 1.6e-3, 0.3),
        ("0.3 mm, 25 um, 1.6 mm, conductive-paste fill (k 5)", 0.3e-3, 25e-6, 1.6e-3, 5.0),
        ("0.3 mm, 25 um, 1.6 mm, solder filled (k 55)", 0.3e-3, 25e-6, 1.6e-3, 55.0),
        ("0.3 mm, 25 um, 1.6 mm, copper filled (k 390)", 0.3e-3, 25e-6, 1.6e-3, 390.0),
    ]
    for name, d, t, L, kf in rows:
        print(f"    {name:55s} {via_r(d, t, L, kf):7.1f} K/W")
    a_fr4 = 1e-3 * 1e-3
    print(f"    FR-4 column 1x1 mm (via pitch cell), 1.6 mm, k_z 0.3: {1.6e-3/(0.3*a_fr4):7.0f} K/W")
    r_ti = 5.73
    a_needed = 1.6e-3 / (K_CU * r_ti)
    print(f"    SLVA959's 5.73 K/W would need {a_needed*1e6:.2f} mm^2 of copper = a solid "
          f"{2*math.sqrt(a_needed/math.pi)*1e3:.2f} mm rod (physically wrong for a 0.3 mm via)")


def h_conv_vertical(dT, L):
    """Laminar natural convection, vertical plate, air ~ 300-350 K (simplified)."""
    return 1.42 * (dT / L) ** 0.25


def h_conv_horizontal_up(dT, L):
    return 1.32 * (dT / L) ** 0.25


def h_conv_horizontal_down(dT, L):
    return 0.59 * (dT / L) ** 0.25


def h_rad(Ts, Ta, eps=0.9):
    return eps * SIGMA * (Ts ** 2 + Ta ** 2) * (Ts + Ta)


def section_b():
    print("B  heat-transfer coefficients (W/m^2K), board 50 mm, ambient 25 C")
    for dT in (10, 20, 40, 60):
        Ts, Ta = 298.15 + dT, 298.15
        hv = h_conv_vertical(dT, 0.05)
        hu = h_conv_horizontal_up(dT, 0.05)
        hd = h_conv_horizontal_down(dT, 0.05)
        hr = h_rad(Ts, Ta)
        print(f"    dT={dT:3d} K  conv vertical {hv:4.1f}  horiz-up {hu:4.1f}  horiz-down {hd:4.1f}"
              f"  radiation(eps .9) {hr:4.1f}  -> vertical total {hv+hr:4.1f}")
    print("    forced air ~1-2 m/s: h ~ 20-50 (laminar flat plate, 50 mm)")


def section_c():
    print("C  copper area per watt and the spreading length lambda")
    for h in (8.2, 10, 14):
        print(f"    isothermal two-sided plate, h={h:4.1f}/side, dT 40 K: A = {1/(2*h*40)*1e4:5.1f} cm^2/W")
    print("    SNVA419's 500 C*cm^2/W = 1/(2h) with h = 10 W/m^2K exactly; 15.3 cm^2/W ~ h = 8.2/side"
          " or 12.5 cm^2 plus spreading/theta_JC")
    stacks = {
        "2L 1 oz/1 oz, 1.6 mm": [OZ, OZ],
        "2L 2 oz/2 oz, 1.6 mm": [2 * OZ, 2 * OZ],
        "4L 1/0.5/0.5/1 oz planes": [OZ, OZ / 2, OZ / 2, OZ],
        "6L 1/1/1/1/1/1 oz planes": [OZ] * 6,
        "bare FR-4 1.6 mm (k_xy 0.8)": [],
    }
    for name, layers in stacks.items():
        gs = sum(K_CU * t for t in layers) + 0.8 * 1.6e-3
        for htot in (20.0, 60.0):
            lam = math.sqrt(gs / htot)
            print(f"    {name:28s} G_s={gs*1e3:5.1f} mW/K  h_tot={htot:4.0f}  lambda={lam*1e3:5.1f} mm"
                  f"  log-term P/(2 pi G_s)={1/(2*math.pi*gs):5.2f} K per W per e-fold")


def section_d():
    print("D  trace self-heating: physics line-source model vs IPC-2221 (external, 1 oz)")
    t = OZ
    htot = 20.0
    g_fr4 = 0.8 * 1.6e-3                  # bare board fin sheet conductance

    def g_line_bare(w):
        return 2 * math.sqrt(g_fr4 * htot) + htot * w  # fin both directions + own top/bottom

    def g_line_plane(w, hd=0.2e-3):
        gs_plane = 0.8 * 1.6e-3 + K_CU * OZ
        g_diel = 0.3 * (w + 2 * hd) / hd     # spreading through dielectric (crude)
        g_plane = 2 * math.sqrt(gs_plane * htot)
        return 1 / (1 / g_diel + 1 / g_plane) + 10.0 * w

    def ipc2221(I, dT):
        a_mil2 = (I / (0.048 * dT ** 0.44)) ** (1 / 0.725)
        return a_mil2 * (25.4e-6) ** 2 / t     # width in m

    for I in (0.5, 1.0, 2.0, 5.0):
        for dT_target in (10.0,):
            w_ipc = ipc2221(I, dT_target)

            def dT_bare(w):
                rp = RHO_CU / (w * t)
                dt0 = I * I * rp / g_line_bare(w)
                return dt0 / (1 - ALPHA_CU * dt0) if ALPHA_CU * dt0 < 1 else 1e9

            def dT_plane(w):
                rp = RHO_CU / (w * t)
                dt0 = I * I * rp / g_line_plane(w)
                return dt0 / (1 - ALPHA_CU * dt0) if ALPHA_CU * dt0 < 1 else 1e9
            w_bare = brentq(lambda w: dT_bare(w) - dT_target, 1e-5, 0.1)
            w_pl = brentq(lambda w: dT_plane(w) - dT_target, 1e-6, 0.1)
            print(f"    {I:3.1f} A, 10 K: IPC-2221 width {w_ipc*1e3:5.2f} mm | line-source bare board "
                  f"{w_bare*1e3:5.2f} mm | with plane 0.2 mm below {w_pl*1e3:5.2f} mm")


def section_e():
    print("E  copper TCR feedback on a current-driven conductor: dT = dT0/(1 - alpha*dT0)")
    for dt0 in (10, 40, 100, 200, 250):
        x = ALPHA_CU * dt0
        print(f"    constant-R estimate {dt0:4d} K -> self-consistent "
              + (f"{dt0/(1-x):6.1f} K" if x < 1 else "no steady state (fuses)"))
    print(f"    runaway threshold dT0 = 1/alpha = {1/ALPHA_CU:.0f} K; resistance +{ALPHA_CU*100:.2f} %/K")


def section_f():
    print("F  Arrhenius life of Al-electrolytics: L = L0 * 2^((T0 - T)/10)")
    k = 8.617e-5
    T1, T2 = 358.15, 368.15
    ea = math.log(2) * k * T1 * T2 / 10
    print(f"    10 K doubling at 85-95 C implies Ea = {ea:.2f} eV")
    for dT in (5, 10, 20, 35):
        print(f"    +{dT:2d} K from a neighbour -> life x {2**(-dT/10):.2f}")


def section_g():
    print("G  thermocouple error of a 2-terminal part near a 1 W source (2L 1 oz planes)")
    gs = 2 * K_CU * OZ + 0.8 * 1.53e-3
    for r in (3e-3, 5e-3, 10e-3, 20e-3):
        grad = 1 / (2 * math.pi * gs * r)      # K/m, near-field log region
        for coef, name in ((3e-6, "Cu-SnPb/SAC solder ~3 uV/K"),
                           (35e-6, "Cu-Kovar ~35 uV/K"), (5e-6, "thick-film R ~5 uV/K")):
            span = 1.6e-3                       # 0603 terminal spacing (aligned with gradient)
            dv = coef * grad * span
            print(f"    r={r*1e3:4.0f} mm grad {grad/1e3:5.2f} K/mm  {name:28s} 0603 along gradient: "
                  f"{dv*1e6:6.2f} uV  (rotated 90 deg: ~0)")


if __name__ == "__main__":
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f()
    section_g()
