# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Electro-thermal coupling as one dissipative system: stability modes, AC kernels, Peltier, exchange rates.

Round-2 lens TH (thermodynamics, dissipation, noise, irreversibility),
docs/topics/physics/lens-th.md. Uses the round-1 finite-volume board solver
(tm_board_thermal_fv.py: 2 layers, 1 oz, FR-4, h = 10 W/m^2K per side) for the thermal
resistance matrix Theta (theta_ij = mean rise over part j per watt in part i; symmetric
by reciprocity of the heat equation).

  runaway  Four 3 x 3 mm dissipators (theta_jc 1.5 K/W) on a 60 x 40 mm board, clustered
           (8 mm pitch) or spread to the corners. Loss rises with temperature,
           dP_i/dT_i = alpha P_i (MOSFET R_DS(on) ~ +0.6 %/K). Linearised:
           dT = (I - Theta D)^-1 Theta P0. Stability margin 1 - g with
           g = rho(D^1/2 Theta D^1/2) (Perron eigenvalue). Compared with the board-floor
           estimate g_floor = sum_i alpha_i P_i / (h_tot A).
  hogging  Two paralleled parts whose current RISES with temperature at fixed voltage
           (BJT/diode: dlnI/dT ~ 2 mV/K / V_T ~ 0.077/K; linear-mode MOSFETs below
           their zero-TC point behave alike). The unstable mode is differential: loop
           gain P phi_eff (theta11 - theta12) < 1, phi_eff = phi / (1 + I R_E/V_T).
           theta_jc 15 K/W (SOT-223 class); separation 4-32 mm; vs emitter ballast and
           a dual-die package.
  ackernel Periodic power at period T_p on an infinite 2-layer 1 oz sheet: the same
           screened-Laplace kernel with complex screening, Lambda = sqrt(G_s/(h_tot +
           j w c_s)). Ratio of the temperature SWING at distance r to the source's own
           swing (fatigue) vs the ratio of MEAN rises (Arrhenius ageing). Valid for
           periods >~ 30 s (the lumped areal heat capacity needs through-thickness
           equilibrium: 1.5 mm of FR-4 takes ~15 s).
  peltier  Onsager/Kelvin (Pi = S T) plus Wiedemann-Franz (k = L0 sigma T) for a
           metal-alloy shunt between copper terminals: the Peltier-Seebeck apparent
           resistance R_P = S^2 T R_th,diff, bounded by R * S^2 / L0 when the element is
           the only heat path; board paths from each pad reduce it. Joule-asymmetry
           EMF (pads with unequal thermal resistance): an offset proportional to I^2.
  exchange Material exchange rates between electrical and thermal conductance:
           metals R_th = R_el / (L T) (copper: 0.15 K/W per micro-ohm); dielectrics
           G_th / C = k / eps. Checked against round 1's via (261 K/W) and TIM-pad
           (1.7 K/W) numbers.

Run:  python tools/research/physics/th_electrothermal.py [runaway|hogging|ackernel|peltier|exchange|all]
numpy + scipy; about 10 s on one core.
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402
from scipy.special import kv  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tm_board_thermal_fv as tb  # noqa: E402

L0 = 2.44e-8          # Sommerfeld Lorenz number, W Ohm / K^2
T_AMB = 300.0
RHO_CU, K_CU = 1.72e-8, 390.0
EPS0 = 8.854e-12


def theta_matrix(lx, ly, srcs, h=10.0, fp=3e-3):
    """Thermal resistance matrix (K/W) between square footprints on a 2-layer 1 oz board with full planes."""
    b = tb.two_layer(lx=lx, ly=ly, dx=0.5e-3, h=h)
    b.cov[:] = True
    masks = [b.rect(x - fp / 2, y - fp / 2, x + fp / 2, y + fp / 2) for (x, y) in srcs]
    th = np.zeros((len(srcs), len(srcs)))
    for i, m in enumerate(masks):
        p = np.zeros_like(b.p)
        p[0][m] = 1.0 / m.sum()
        T = b.solve(p)
        for j, mj in enumerate(masks):
            th[j, i] = T[0][mj].mean()
    return th


def exp_runaway():
    print("== runaway: 4 dissipators, theta_jc 1.5 K/W, on a 60 x 40 mm 2-layer 1 oz board (h 10 per side)")
    lx, ly = 60e-3, 40e-3
    layouts = (("clustered, 8 mm pitch", [(26e-3, 16e-3), (34e-3, 16e-3), (26e-3, 24e-3), (34e-3, 24e-3)]),
               ("spread to the corners", [(10e-3, 10e-3), (50e-3, 10e-3), (10e-3, 30e-3), (50e-3, 30e-3)]))
    for name, srcs in layouts:
        th = theta_matrix(lx, ly, srcs) + 1.5 * np.eye(4)
        asym = np.abs(th - th.T).max() / th.max()
        print(f"  {name}: theta_self {th[0,0]:.1f} K/W, theta_mutual {th[0,1]:.1f}-{th[0,3]:.1f} K/W,"
              f" reciprocity |theta - theta^T|/max = {asym:.1e}")
        for P in (0.25, 0.5, 0.75):
            alpha = 0.006
            D = np.diag([alpha * P] * 4)
            Ds = np.sqrt(D)
            g = max(np.linalg.eigvalsh(Ds @ ((th + th.T) / 2) @ Ds))
            cold = th @ np.full(4, P)
            hot = np.linalg.solve(np.eye(4) - th @ D, cold)
            gfl = 4 * alpha * P / (20.0 * lx * ly)
            print(f"    {P:4.2f} W each (alpha 0.6 %/K): g = {g:4.2f} (board floor alone {gfl:4.2f});"
                  f" hottest rise {cold.max():5.1f} K cold -> {hot.max():5.1f} K self-consistent (x{hot.max()/cold.max():4.2f})")
    print("  copper alone (alpha 0.39 %/K): runaway when alpha * dT0 = 1, dT0 = 254 K (round 1, TM16) is the N = 1 case")


def exp_hogging():
    print("== hogging: two paralleled parts with current rising at fixed V (phi = 2 mV/K / V_T = 0.077/K), theta_jc 15 K/W")
    lx, ly = 60e-3, 40e-3
    phi = 0.002 / 0.02585
    for d in (4e-3, 8e-3, 16e-3, 32e-3):
        srcs = [(30e-3 - d / 2, 20e-3), (30e-3 + d / 2, 20e-3)]
        th = theta_matrix(lx, ly, srcs)
        t11, t12 = th[0, 0] + 15.0, th[0, 1]
        cells = [f"ballast I R_E/V_T = {bal:4.1f}: P_max {1/(phi/(1+bal)*(t11-t12)):5.2f} W" for bal in (0.0, 4.0, 10.0)]
        print(f"  separation {d*1e3:4.0f} mm: theta11 {t11:5.1f}, theta12 {t12:5.1f} K/W; differential {t11-t12:5.1f},"
              f" common {t11+t12:5.1f} K/W; " + "; ".join(cells))
    print(f"  dual-die package (theta11 - theta12 ~ 3 K/W), no ballast: P_max {1/(phi*3.0):4.2f} W per device")
    print("  -> the two modes want opposite layouts: proximity raises the common-mode (total) rise but stabilises sharing")


def exp_ackernel():
    print("== ackernel: periodic power on a 2-layer 1 oz sheet (G_s, h_tot 20 W/m^2K, areal heat capacity c_s)")
    gs = 2 * K_CU * 35e-6 + 0.8 * 1.53e-3
    cs = 1.53e-3 * 2.0e6 + 70e-6 * 3.45e6
    h = 20.0
    lam = math.sqrt(gs / h)
    a = 1.7e-3          # radius of a disc with the area of a 3 x 3 mm source
    print(f"  G_s {gs*1e3:.1f} mW/K, c_s {cs:.0f} J/m^2K, board time constant c_s/h = {cs/h:.0f} s, lambda_dc {lam*1e3:.1f} mm")
    rs = (5e-3, 10e-3, 20e-3, 40e-3)
    print("  period  |Lambda|   swing(r)/own swing at r = 5, 10, 20, 40 mm  | mean(r)/own mean")
    for per in (30, 60, 600, 3600):
        w = 2 * math.pi / per
        L = np.sqrt(gs / (h + 1j * w * cs))
        sw = [abs(kv(0, r / L)) / abs(kv(0, a / L)) for r in rs]
        mn = [kv(0, r / lam) / kv(0, a / lam) for r in rs]
        print(f"  {per:5d} s {abs(L)*1e3:6.1f} mm   " + "  ".join(f"{s:5.3f}" for s in sw) + "   | " + "  ".join(f"{m:5.3f}" for m in mn))
    print("  -> for minute-scale power cycling the swing (fatigue driver) is local (~2|Lambda|), while the mean rise")
    print("     (Arrhenius driver) is board-wide (~2 lambda): two keep-out radii from one solver with complex h")


def exp_peltier():
    print("== peltier: Peltier-Seebeck apparent resistance of an alloy shunt between copper terminals")
    print("  bound (element is the only heat path): R_P/R = S^2/L0 (Harman ZT with Wiedemann-Franz)")
    alloys = (("manganin (-1.0 uV/K vs Cu, datasheet)", 1.0e-6), ("NiCr-type alloy (assume 5 uV/K)", 5e-6),
              ("constantan (Cu-CuNi type T, 40.6 uV/K)", 40.6e-6))
    for name, s in alloys:
        print(f"    {name:42s}: S^2/L0 = {s*s/L0*1e6:9.1f} ppm")
    print("  with board paths: junctions J1, J2 each to the board through R_a; element R_e = R/(L0 T) split in two")
    print("  halves with its Joule heat at the midpoint; Peltier +/- S T I at J1/J2; EMF = S (T1 - T2)")
    for R, I in ((1e-3, 10.0), (10e-3, 3.0)):
        re = R / (L0 * T_AMB)
        for ra1, ra2 in ((40.0, 40.0), (25.0, 80.0)):
            for name, s in alloys[::2]:
                # nodes: J1, M, J2 ; conductances
                g1, g2, ge = 1 / ra1, 1 / ra2, 2 / re
                G = np.array([[g1 + ge, -ge, 0.0], [-ge, 2 * ge, -ge], [0.0, -ge, g2 + ge]])
                q_pel = np.array([s * T_AMB * I, 0.0, -s * T_AMB * I])
                q_joule = np.array([0.0, I * I * R, 0.0])
                tp = np.linalg.solve(G, q_pel)
                tj = np.linalg.solve(G, q_joule)
                e_p = s * (tp[0] - tp[2]) / (I * R)
                e_j = s * (tj[0] - tj[2]) / (I * R)
                print(f"    {R*1e3:4.0f} mOhm at {I:4.1f} A, R_e {re:5.0f} K/W, pads {ra1:.0f}/{ra2:.0f} K/W, {name.split(' ')[0]:10s}:"
                      f" Peltier gain error {e_p*1e6:9.1f} ppm (linear in I), Joule-asymmetry {e_j*1e6:9.1f} ppm (prop. to I)")
    print("  -> the Peltier term is a positive resistance (second law: it cannot be cancelled by symmetry) with the")
    print("     thermal time constant of the pads; the asymmetry term is even in I and vanishes with symmetric pad copper")


def exp_exchange():
    print("== exchange: electrical <-> thermal exchange rates fixed by materials")
    lcu = K_CU * RHO_CU / 293.0
    print(f"  copper Lorenz ratio k/(sigma T) = {lcu:.3e} W Ohm/K^2 (L0 = {L0:.2e}); R_th = R_el/(L T) = {1/(lcu*293):.3g} K/W per ohm"
          f" = {1e-6/(lcu*293):.3f} K/W per micro-ohm")
    d, tp, length = 0.305e-3, 17.5e-6, 1.6e-3
    r_el = RHO_CU * length / (math.pi * tp * (d - tp))
    print(f"  12 mil via, 17.5 um plating, 1.6 mm: R_el {r_el*1e3:.2f} mOhm -> R_th {r_el/(lcu*293):.0f} K/W (round 1 / TI: 261 K/W)")
    r_tr = RHO_CU / 35e-6 * 10
    print(f"  1 oz trace, 10 squares: R_el {r_tr*1e3:.2f} mOhm -> R_th {r_tr/(lcu*293):.0f} K/W along the copper")
    for name, k, er in (("FR-4", 0.3, 4.3), ("thermal prepreg 3 W/mK", 3.0, 5.0), ("silicone TIM pad k 3", 3.0, 5.0),
                        ("AlN", 170.0, 8.8)):
        print(f"  {name:24s}: G_th/C = k/eps = {k/(EPS0*er):9.2e} (W/K)/F -> 1 K/W of it costs {EPS0*er/k*1e12:7.2f} pF")
    print("  round 1: TIM pad 0.5 mm, 10 x 10 mm, 1.7 K/W -> C =", f"{EPS0*5.0*1e-4/0.5e-3*1e12:.1f} pF;",
          "SW pad 1 cm^2 over 0.1 mm FR-4: 3.3 K/W and 38 pF")
    print("  -> every heat path is also an electrical element: a metal path is a conductance (a bond), a dielectric")
    print("     path is a capacitance (a coupling). Thermal design decisions belong in the electrical ledger too.")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("runaway", exp_runaway), ("hogging", exp_hogging), ("ackernel", exp_ackernel),
                     ("peltier", exp_peltier), ("exchange", exp_exchange)):
        if which in (name, "all"):
            fn()
