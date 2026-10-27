# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team test of the candidate principle 'a conductor is invisible to first order when its
characteristic impedance equals the circuit impedance it carries; then its only effect is delay'
(round-3 context point 5; lens LS P2, lens VP D6, round-1 PW2).

Sections (python rt_impedance_match.py [twoport|capload|range|energy|all]):
  twoport  Exact transfer of a lossless line (electrical length theta) between resistive Z_S and
           Z_L, relative to no line: H/H0 = 1 / (cos theta + j kappa sin theta),
           kappa = (Z0 + Z_S Z_L / Z0) / (Z_S + Z_L). First order is a pure phase for EVERY Z0;
           the second-order amplitude error -(kappa^2 - 1) theta^2 / 2 vanishes at Z0 = Z_S or
           Z0 = Z_L, and is a GAIN when Z0 lies between unequal terminations (transformer).
  capload  Source R_S driving a capacitive load C_L through a line: overshoot of the step
           response vs Z0 for a fixed delay. 'Matched to the circuit impedance' is ill-defined
           (R_S at one end, 1/(w C_L) at the other); the delay-only line is Z0 = R_S.
  range    Circuit impedance levels vs realisable PCB Z0 (0.3-170 ohm): which nets can be
           matched at all, and the size of eps_L = theta Z0/Z and eps_C = theta Z/Z0 at 1 and
           100 MHz for 30 mm of copper.
  energy   Switching-cell copper: per-cycle stored energy 1/2 L I^2 + 1/2 C V^2 is minimal at
           Z0 = V/I (AM-GM), but adding the I_rms^2 R term (PW2's own case) moves the optimum
           width 2.3x; 'matching' here is a loss optimum, not invisibility.

Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_impedance_match.py   (seconds)
"""
import math
import sys

import numpy as np

MU0 = 4e-7 * math.pi
EPS0 = 8.854e-12
C0 = 299792458.0
ETA0 = MU0 * C0


def h_ratio(theta, zs, zl, z0):
    kappa = (z0 + zs * zl / z0) / (zs + zl)
    return 1.0 / (np.cos(theta) + 1j * kappa * np.sin(theta)), kappa


def sec_twoport():
    print("== twoport: short lossless line between resistive terminations, theta = 0.1 rad")
    th = 0.1
    print("   Z_S    Z_L    Z0    kappa   |H/H0|-1 (exact)  -(k^2-1)th^2/2   phase/theta")
    for zs, zl in ((50, 50), (10, 10), (25, 1e4), (0.1, 0.1), (1e3, 1e3)):
        for z0 in sorted({zs, zl, math.sqrt(zs * zl), 50.0, 0.5, 150.0}):
            r, k = h_ratio(th, zs, zl, z0)
            print(f"   {zs:6g} {zl:6g} {z0:6.3g}  {k:7.3f}    {abs(r)-1:+.5f}          {-(k*k-1)*th*th/2:+.5f}"
                  f"        {-np.angle(r)/th:6.3f}")
    print("   -> first-order effect is a pure delay kappa*T_d for any Z0; matching (Z0 = Z_S or Z_L) removes the")
    print("      second-order amplitude error and makes kappa = 1; Z0 between unequal ends gives |H| > |H0| (a transformer).")


def step_overshoot(rs, cl, z0, td, nseg=400, tmax_factor=40.0):
    """Lossless line (LC ladder, nseg sections) from a step source with R_S into C_L; returns overshoot of V_load."""
    L = z0 * td / nseg
    C = td / (z0 * nseg)
    # states: inductor currents i_k (nseg), capacitor voltages v_k (nseg), last capacitor includes C_L
    n = nseg
    caps = np.full(n, C)
    caps[-1] += cl
    dt = min(td / nseg / 4, rs * C / 4 if rs > 0 else td / nseg / 4)
    tmax = tmax_factor * max(td, rs * cl, z0 * cl)
    steps = int(tmax / dt)
    i = np.zeros(n)
    v = np.zeros(n)
    vmax = 0.0
    for _ in range(steps):
        # source node: V_s = 1 through R_S into node 0 (first capacitor) via first inductor? use: node0 fed by R_S
        vin = np.concatenate([[1.0 - 0.0], v[:-1]])  # voltage driving each inductor from the left
        # first inductor driven by source through R_S: v_left = 1 - R_S * i0
        vin[0] = 1.0 - rs * i[0]
        i += dt * (vin - v) / L
        iin = i
        iout = np.concatenate([i[1:], [0.0]])
        v += dt * (iin - iout) / caps
        vmax = max(vmax, v[-1])
    return vmax - 1.0


def sec_capload():
    print("== capload: step through R_S and a line (delay T_d) into C_L; overshoot of the load voltage")
    rs, cl = 30.0, 5e-12
    for td in (0.2e-9, 0.5e-9):
        cells = []
        for z0 in (15.0, 30.0, 50.0, 100.0, 150.0):
            ov = step_overshoot(rs, cl, z0, td, nseg=120, tmax_factor=12.0)
            cells.append(f"Z0 {z0:5.0f}: {ov*100:5.1f}%")
        tau = rs * cl
        print(f"   R_S 30 ohm, C_L 5 pF (R_S C_L = {tau*1e12:.0f} ps), T_d {td*1e12:.0f} ps: " + "; ".join(cells))
    print("   -> the delay-only line is Z0 = R_S (series termination); the load's |1/(w C_L)| is no 'circuit")
    print("      impedance' to match; a single Z = V/I does not exist for reactive terminations.")


def sec_range():
    print("== range: circuit impedance vs realisable PCB Z0 (about 0.3-170 ohm); 30 mm of copper")
    l = 30e-3
    v = C0 / math.sqrt(4.3)
    rows = [("hot loop (12 V / 10 A)", 1.2, 0.3), ("PDN target (1 V, 5% of 10 A)", 0.005, 0.3),
            ("PDN target (3.3 V, 2% of 0.5 A)", 0.13, 0.3), ("CMOS driver output", 30.0, 30.0),
            ("RF / SI line", 50.0, 50.0), ("op-amp feedback node", 1e4, 150.0), ("sensor 1 MOhm", 1e6, 170.0),
            ("electrometer 1 TOhm", 1e12, 170.0)]
    print("   net                               Z (ohm)   best Z0   m=Z0/Z     eps_L/eps_C at 1 MHz   at 100 MHz")
    for name, z, z0 in rows:
        cells = []
        for f in (1e6, 100e6):
            th = 2 * math.pi * f * l / v
            cells.append(f"{th*z0/z:8.2e}/{th*z/z0:8.2e}")
        print(f"   {name:34s} {z:9.3g} {z0:8.3g}  {z0/z:9.2e}   " + "   ".join(cells))
    print("   -> only ~1-170 ohm nets can be matched; elsewhere the principle reduces to 'minimise L' (Z << Z0)")
    print("      or 'minimise C' (Z >> Z0), i.e. round 1's principle 2, with eps_L/eps_C as the regime variables.")


def sec_energy():
    print("== energy: switching-cell copper width, cost = a L + b C + g R (PW2: a = I^2 f/2, b = V^2 f/2, g = I_rms^2)")
    eps = EPS0 * 4.3
    rho, t = 1.72e-8, 35e-6
    for name, V, I, f, irms, h in (("12 V / 10.5 A / 500 kHz, I_rms 5.5 A (g 30)", 12.0, 10.5, 5e5, math.sqrt(30), 0.1e-3),
                                    ("48 V / 20 A / 1 MHz, g 200", 48.0, 20.0, 1e6, math.sqrt(200), 0.1e-3)):
        a, b, g = 0.5 * I * I * f, 0.5 * V * V * f, irms ** 2
        w_lc = math.sqrt(a * MU0 * h / (b * eps / h))
        w_all = math.sqrt((a * MU0 * h + g * rho / t) / (b * eps / h))
        z0 = lambda w: ETA0 * h / (w * math.sqrt(4.3))  # noqa: E731
        print(f"   {name}: L-C only w* {w_lc*1e3:5.1f} mm (Z0 {z0(w_lc):.2f} ohm = V/I {V/I:.2f}); with R: "
              f"w* {w_all*1e3:5.1f} mm (Z0 {z0(w_all):.2f} ohm)")
    print("   -> the equipartition optimum holds only when the I^2 R term is negligible; it is a loss optimum")
    print("      (both stored energies are dissipated each hard-switched cycle), not a statement of invisibility.")


SECTIONS = {"twoport": sec_twoport, "capload": sec_capload, "range": sec_range, "energy": sec_energy}

if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    for name, fn in SECTIONS.items():
        if "all" in which or name in which:
            fn()
            print()
