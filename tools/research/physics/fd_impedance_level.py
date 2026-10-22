# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test of the candidate principle "a conductor is invisible to first order when Z0 equals the
circuit impedance it carries" (round-3 foundations, docs/topics/physics/foundations.md).

A piece of copper with its reference is a two-conductor structure: L = Z0 T, C = T / Z0,
T = l/v its delay.  Carrying a current swing dI and a voltage swing dV (to its reference) it
stores 1/2 L dI^2 + 1/2 C dV^2 >= dV dI T, with equality iff Z0 = dV/dI (AM-GM); between equal
resistive terminations its first-order perturbations are eps_L = theta Z0/Z and eps_C =
theta Z/Z0 (lens LS).  Five parts:

  cascade  Matching is local: a line with sqrt(L_tot/C_tot) = Z built from sections k Z and
           Z/k is not a delay; (sum L)(sum C) >= T^2 (Cauchy-Schwarz), and the first-order
           phase grows by (k + 1/k)/2.
  buck     12 V / 10 A, t_r 2 ns, L1 over L2 GND at h = 0.1 mm.  Per piece: carried impedance
           dV/dI, the width that minimises the piece's parasitic field energy, and how that
           energy compares with the parts' (C_oss, package L) and with the piece's external
           dipole (interaction), which the theorem does not cover.
  pdn      (a) constant-resistance network: (R + jwL) || (R + 1/jwC) = R for all w iff
           R = sqrt(L/C); (b) plane-pair cavity (th_damping_ledger / fe_cavity model,
           100 x 80 mm): bare peaks vs Q_mn * Z0_mn, matched edge terminations vs Z0_mn;
           (c) Z0_mn is proportional to d: the spacing a target impedance needs.
  line50   +-10 % Z0 between 50 ohm terminations; Bode-Fano limit for a 50 ohm || C receiver.
  highz    A high-impedance node: eps_C and eps_L for three stackups, and the capacitive-node
           form eps = C_trace / C_node.

Run:  python tools/research/physics/fd_impedance_level.py [cascade|buck|pdn|line50|highz|all]
numpy only (pdn reuses th_damping_ledger.py / fe_cavity.py); about 1 minute on one core.
Closed forms and lumped or modal models, uncalibrated against measurement.
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 299792458.0
ETA0 = 376.73
ER = 4.3
mm = 1e-3


def ms_z0(w, h, er=ER):
    """Hammerstad-Jensen microstrip Z0 and eps_eff (zero thickness), as in ls_regime_map.py."""
    u = w / h
    ee = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 / u)
    if u <= 1:
        z = 60 / math.sqrt(ee) * math.log(8 / u + u / 4)
    else:
        z = 120 * math.pi / math.sqrt(ee) / (u + 1.393 + 0.667 * math.log(u + 1.444))
    return z, ee


def lc_per_m(w, h):
    z, ee = ms_z0(w, h)
    v = C0 / math.sqrt(ee)
    return z / v, 1 / (z * v), z, v


# --------------------------------------------------------------------------------- cascade
def abcd_line(z0, th):
    return np.array([[math.cos(th), 1j * z0 * math.sin(th)], [1j * math.sin(th) / z0, math.cos(th)]])


def transfer(abcd, zs, zl):
    a, b, c, d = abcd[0, 0], abcd[0, 1], abcd[1, 0], abcd[1, 1]
    return zl / (a * zl + b + c * zs * zl + d * zs)


def cascade():
    print("== cascade: matching is local (Z = 50 ohm terminations, total delay theta split in two)")
    Z = 50.0
    for k in (1.0, 1.5, 2.0, 4.0):
        Ltot = (k * Z + Z / k) / 2      # in units of T (each half has delay T/2)
        Ctot = (1 / (k * Z) + k / Z) / 2
        print(f"  sections {k*Z:6.1f} / {Z/k:6.1f} ohm: sqrt(Ltot/Ctot) = {math.sqrt(Ltot/Ctot):5.1f} ohm,"
              f" Ltot*Ctot/T^2 = {Ltot*Ctot:5.3f}, first-order phase factor {(k+1/k)/2:5.3f}")
        row = []
        for th in (0.05, 0.2, 0.5, 1.0):
            m = abcd_line(k * Z, th / 2) @ abcd_line(Z / k, th / 2)
            H = transfer(m, Z, Z) / 0.5
            row.append(f"th {th:4.2f}: |H|-1 {abs(H)-1:+.2e}, phase/th {-np.angle(H)/th:5.3f}")
        print("     " + "; ".join(row))


# ------------------------------------------------------------------------------------ buck
def buck():
    print("== buck: per-piece impedance level, 12 V / 10 A, t_r = 2 ns, L1 over L2 GND, h = 0.1 mm")
    V, I, tr, h = 12.0, 10.0, 2e-9, 0.1 * mm
    fe = 1 / (math.pi * tr)
    w_e = 2 * math.pi * fe
    esl, esr = 0.15e-9, 1.5e-3               # 2 x 10 uF MLCC, 0.3 nH and 3 mOhm each incl. mounting
    zcin = abs(esr + 1j * w_e * esl)
    cpar_l = 10e-12                          # inductor inter-winding capacitance (assumed)
    di_sw = cpar_l * V / tr
    pieces = [
        ("VIN pour, CIN+ to HS drain", 4 * mm, I, I * zcin, "dV = I |Z_CIN(f_e)|: the cap holds VIN"),
        ("SW inside commutation loop", 2 * mm, I, V, "dV = V, dI = I"),
        ("SW to output inductor", 6 * mm, di_sw, V, "dI = C_par,L dV/dt only"),
    ]
    widths = [0.15, 0.3, 0.5, 1, 2, 4, 8, 15]
    print(f"  edge band f_e = 1/(pi t_r) = {fe/1e6:.0f} MHz; |Z_CIN(f_e)| = {zcin*1e3:.0f} mOhm;"
          f" SW-to-L current swing {di_sw*1e3:.0f} mA")
    for name, ln, dI, dV, note in pieces:
        zc = dV / dI
        Es = []
        for wmm in widths:
            Lp, Cp, z0, v = lc_per_m(wmm * mm, h)
            E = 0.5 * Lp * ln * dI ** 2 + 0.5 * Cp * ln * dV ** 2
            Es.append((E, wmm, z0))
        Emin, wbest, zbest = min(Es)
        _, _, _, v = lc_per_m(1 * mm, h)
        floor = dV * dI * ln / v
        print(f"  {name}: Z_carried = {zc:8.3f} ohm ({note})")
        print("     width mm:  " + "".join(f"{w:>8.2f}" for w in widths))
        print("     Z0 ohm:    " + "".join(f"{e[2]:>8.2f}" for e in Es))
        print("     E nJ:      " + "".join(f"{e[0]*1e9:>8.3f}" for e in Es))
        print(f"     best in range w = {wbest} mm (Z0 {zbest:.2f} ohm), E = {Emin*1e9:.3f} nJ;"
              f" equipartition floor dV dI T = {floor*1e9:.3f} nJ")
    coss, lpkg = 300e-12, 0.5e-9
    print(f"  part energies per edge: 1/2 C_oss V^2 = {0.5*coss*V*V*1e9:.1f} nJ (C_oss 300 pF),"
          f" 1/2 L_pkg I^2 = {0.5*lpkg*I*I*1e9:.1f} nJ (0.5 nH)")
    # interaction: external dipole of SW copper, p = 2 eps0 * integral(V dA) (lens SY D1, w >> h)
    for wmm in (2, 15):
        area = wmm * mm * 2 * mm
        print(f"  SW-in-loop piece at w = {wmm:2d} mm: area {area/mm**2:4.0f} mm^2 -> external dipole"
              f" 2 eps0 V A = {2*EPS0*V*area*1e15:.2f} fC*m (scales with area, not with h)")


# ------------------------------------------------------------------------------------- pdn
def pdn():
    print("== pdn (a): constant-resistance network (R + jwL) || (R + 1/jwC), L = 1 nH, C = 1 uF")
    L, C = 1e-9, 1e-6
    z0 = math.sqrt(L / C)
    w = 2 * math.pi * np.logspace(3, 10, 2001)
    for r in (0.1, 0.3, 1.0, 3.0):
        R = r * z0
        z = 1 / (1 / (R + 1j * w * L) + 1 / (R + 1 / (1j * w * C)))
        print(f"  R = {r:3.1f} Z0 ({R*1e3:5.1f} mOhm): max |Z|/R = {np.max(np.abs(z))/R:7.3f},"
              f" min |Z|/R = {np.min(np.abs(z))/R:6.3f}")
    print("  (|Z| <= R at every w iff sqrt(L/C) <= R; |Z| = R exactly iff sqrt(L/C) = R)")
    print("== pdn (b): 100 x 80 mm PWR-GND cavity, probe (12, 9) mm, FR-4 tan d 0.02 (th_damping_ledger model)")
    import fe_cavity as fc
    import th_damping_ledger as th
    a, b = th.CAV_A, th.CAV_B
    freqs = np.linspace(0.3e9, 2.5e9, 441)
    eps = EPS0 * fc.ER
    for d in (0.025e-3, 0.1e-3, 0.4e-3):
        fc.TAND = 0.02
        cav = fc.Cavity(a, b, d, 24, 24)
        phi = cav.phi(th.PROBE)[0]
        wmn = np.sqrt(cav.k2) / math.sqrt(MU0 * eps)
        sel = (wmn > 2 * math.pi * 0.3e9) & (wmn < 2 * math.pi * 2.5e9)
        z0mn = d * phi[sel] ** 2 / (a * b * eps * wmn[sel])
        delta = np.sqrt(2 / (wmn[sel] * MU0 * 5.8e7))
        q = 1 / (0.02 + delta / d)
        pred = np.max(q * z0mn)
        bare = th.peak_of(th.cavity_curve(d, 0.02, freqs))
        pts = th.edge_points(10e-3)
        rm = ETA0 * d / (math.sqrt(fc.ER) * 10e-3)
        zt = th.cavity_curve(d, 0.02, freqs, (pts, rm, 0.0, 10e-9))
        k = int(np.argmax(zt))
        k1 = int(np.argmin(np.abs(freqs - 1e9)))
        slope = math.log(zt[-1] / zt[-41]) / math.log(freqs[-1] / freqs[-41])
        i = int(np.argmax(q * z0mn))
        print(f"  d = {d*1e3:5.3f} mm: max_mn Q*Z0_mn = {pred:7.3f} ohm (Q {q[i]:4.1f}, Z0_mn {z0mn[i]*1e3:6.1f} mOhm)"
              f" vs bare peak {bare:7.3f} ohm")
        print(f"     matched edge terminations R_m = eta d/p = {rm:5.2f} ohm (p = 10 mm): max |Z| {zt[k]:6.3f} ohm"
              f" at {freqs[k]/1e9:4.2f} GHz (band edge), |Z|(1 GHz) {zt[k1]:6.3f} ohm, d ln|Z|/d ln f near 2.5 GHz"
              f" {slope:4.2f}: no resonant peak left, an inductive rise proportional to d")
    print("== pdn (c): Z0 of the (1,0) mode at a corner, 2 eta d/(pi b), vs spacing; d for a target")
    eta = ETA0 / math.sqrt(ER)
    for d in (0.01e-3, 0.025e-3, 0.1e-3, 0.4e-3, 1.5e-3):
        print(f"  d = {d*1e3:5.3f} mm: Z0_10 = {2*eta*d/(math.pi*b)*1e3:7.2f} mOhm")
    for zt in (0.1, 0.02):
        print(f"  target {zt*1e3:4.0f} mOhm: Z0_10 <= target needs d <= {zt*math.pi*b/(2*eta)*1e6:5.1f} um on this"
              f" board; otherwise decaps with ESR ~ target must carry the band (part a, one-sided form)")


# ---------------------------------------------------------------------------------- line50
def line50():
    print("== line50: lossless line between 50 ohm terminations, any length")
    for z0 in (45.0, 55.0, 60.0, 75.0):
        m = z0 / 50
        f = (m + 1 / m) / 2
        gam = abs((z0 - 50) / (z0 + 50))
        print(f"  Z0 = {z0:4.0f} ohm: |Gamma| per end {gam:5.3f} ({20*math.log10(gam):6.1f} dB),"
              f" worst |H|/|H_matched| = {1/f:6.4f} ({-20*math.log10(f):+6.3f} dB)")
    print("  Bode-Fano, receiver 50 ohm || C over 0..f_max: best flat |Gamma| = exp(-pi/(R C 2 pi f_max))")
    for cpf in (0.3, 1.0, 2.0):
        cells = []
        for fmax in (5e9, 16e9):
            g = math.exp(-math.pi / (50 * cpf * 1e-12 * 2 * math.pi * fmax))
            cells.append(f"{fmax/1e9:4.0f} GHz: |Gamma| >= {g:5.3f} ({20*math.log10(g):6.1f} dB)")
        print(f"  C = {cpf:3.1f} pF: " + "; ".join(cells))


# ----------------------------------------------------------------------------------- highz
def highz():
    print("== highz: 15 mm x 0.15 mm trace on a high-impedance node")
    ln, w = 15 * mm, 0.15 * mm
    cases = [("over L2 GND, h = 0.1 mm", 0.1 * mm), ("L2 voided, L3 at 1.3 mm", 1.3 * mm),
             ("2-layer, h = 1.6 mm", 1.6 * mm)]
    for R, f in ((1e6, 10e3), (100e3, 100e3)):
        wo = 2 * math.pi * f
        print(f"  node R = {R/1e3:6.0f} kOhm at {f/1e3:4.0f} kHz:")
        for name, h in cases:
            Lp, Cp, z0, _ = lc_per_m(w, h)
            Ct, Lt = Cp * ln, Lp * ln
            print(f"     {name:26s} Z0 {z0:5.0f} ohm (m = Z0/Z = {z0/R:.1e}): C {Ct*1e12:4.2f} pF,"
                  f" eps_C = w C R = {wo*Ct*R:6.3f}, eps_L = w L/R = {wo*Lt/R:.1e},"
                  f" C/C_node(3 pF) = {Ct/3e-12:4.2f}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for nm, fn in (("cascade", cascade), ("buck", buck), ("pdn", pdn), ("line50", line50), ("highz", highz)):
        if which in (nm, "all"):
            fn()
