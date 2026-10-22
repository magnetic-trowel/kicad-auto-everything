# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Least dissipation and fluctuation-dissipation on the board: where loss sits, what it costs, what it adds.

Round-2 lens TH (thermodynamics, dissipation, noise, irreversibility),
docs/topics/physics/lens-th.md.

  equipartition  Thomson's principle near a small feed: the potential is logarithmic,
           and the current through every equipotential band is the whole current, so
           each e-fold of radius dissipates the same power, I^2 R_s / (2 pi), per feed.
           Checked on round 1's pour (pw_sheet.py `pour`: 2 x 2 mm pads 30 mm apart in a
           44 x 30 mm region): fraction of loss within r of the feeds vs ln(r/a)/(pi N_sq)
           (a = 0.59 x side, the log capacity of a square), and the feed law
           dN_sq = -(ln 2)/pi when both feeds double in size.
  transfer Rayleigh monotonicity holds for self quantities (a source's own resistance or
           temperature) but not for transfer quantities (foreign voltage across sense taps,
           a victim's temperature). (i) Sheet: aggressor A -> B under a moat, sense taps C,
           D above it: moat present, bridged at the centre, filled. (ii) Board (60 x 40 mm,
           top copper only): 1 W source and a victim 20 mm away, with and without a 2 mm moat
           in the top copper between them.
  fdt      Fluctuation-dissipation numbers for layout (closed forms):
           (a) dielectric loss at a high-impedance input: S_i = 4kT w C_d tan(d), against
               the shot noise of 20 fA bias and a 1 Tohm feedback resistor; the 1/f voltage
               noise it makes at a capacitive node; guarding removes the signal current
               through C_d but not this noise current;
           (b) loss ahead of the first gain stage, T_add = (L - 1) T, and the noise
               temperature of an antenna with radiation efficiency eta,
               T_A = eta T_sky + (1 - eta) T_phys (GNSS example);
           (c) thermal magnetic noise of copper layers near a magnetometer (non-magnetic
               infinite plate, Lee and Romalis 2008: dB = mu0 sqrt(kT sigma t)/(sqrt(8 pi) a));
           (d) series copper resistance in front of low-impedance sources (negligible).

Run:  python tools/research/physics/th_dissipation_noise.py [equipartition|transfer|fdt|all]
numpy + scipy; about 15 s on one core.
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pw_sheet as ps  # noqa: E402
import tm_board_thermal_fv as tb  # noqa: E402

KB = 1.380649e-23
QE = 1.602177e-19
MU0 = 4e-7 * math.pi
T0 = 296.0


def exp_equipartition():
    print("== equipartition: loss per e-fold of radius near a feed is I^2 R_s/(2 pi), whatever the pour")
    dx, wd, hd = 0.1, 44.0, 30.0
    ny, nx = int(hd / dx), int(wd / dx)
    yy, xx = np.mgrid[0:ny, 0:nx]
    x = (xx + 0.5) * dx - 7.0
    y = (yy + 0.5) * dx - hd / 2
    full = np.ones((ny, nx), bool)

    def pads(s):
        return ((np.abs(x) <= s / 2) & (np.abs(y) <= s / 2), (np.abs(x - 30) <= s / 2) & (np.abs(y) <= s / 2))

    A, B = pads(2.0)
    V, I = ps.solve(full, [(A, 1.0), (B, 0.0)])
    nsq = 1 / I[0]
    P = ps.jmag(full, V) ** 2
    ptot = P.sum()
    a_eq = 0.5902 * 2.0
    print(f"  full 44 x 30 mm region, 2 x 2 mm feeds 30 mm apart: N_sq = {nsq:.3f}; log law per e-fold, both feeds:"
          f" 1/(pi N_sq) = {1/(math.pi*nsq)*100:.1f}% of the loss")
    ra, rb = np.hypot(x, y), np.hypot(x - 30, y)
    for r in (1.5, 2, 3, 4, 5, 6):
        fr = (P[ra <= r].sum() + P[rb <= r].sum()) / ptot
        print(f"    within r = {r:3.1f} mm of the feed centres: {fr*100:5.1f}%   log law ln(r/a)/(pi N_sq): "
              f"{math.log(r/a_eq)/(math.pi*nsq)*100:5.1f}%")
    redge = np.minimum(np.hypot(np.maximum(np.abs(x) - 1, 0), np.maximum(np.abs(y) - 1, 0)),
                       np.hypot(np.maximum(np.abs(x - 30) - 1, 0), np.maximum(np.abs(y) - 1, 0)))
    print(f"    within 3 mm of the pad edges (round 1's definition): {P[redge <= 3].sum()/ptot*100:4.1f}% (round 1: 31%)")
    prev = None
    for s in (1.0, 2.0, 4.0):
        A, B = pads(s)
        _, I = ps.solve(full, [(A, 1.0), (B, 0.0)])
        n = 1 / I[0]
        extra = "" if prev is None else f"; change {n-prev:+.3f} sq (law -(ln 2)/pi = {-math.log(2)/math.pi:+.3f})"
        print(f"    feeds {s:3.1f} x {s:3.1f} mm: N_sq {n:.3f}{extra}")
        prev = n


def exp_transfer():
    print("== transfer: adding copper lowers self quantities (Rayleigh) but can raise transfer quantities")
    dx, wd, hd = 0.1, 40.0, 24.0
    ny, nx = int(hd / dx), int(wd / dx)
    yy, xx = np.mgrid[0:ny, 0:nx]
    x = (xx + 0.5) * dx
    y = (yy + 0.5) * dx
    A = (np.abs(x - 8) <= 1) & (np.abs(y - 5) <= 1)
    B = (np.abs(x - 32) <= 1) & (np.abs(y - 5) <= 1)
    moat = (np.abs(y - 12) <= 0.5) & (x >= 2) & (x <= 38)
    bridge = (np.abs(x - 20) <= 1) & (np.abs(y - 12) <= 0.5)
    c, d = (int(20 / dx), int(15 / dx)), (int(20 / dx), int(25 / dx))
    print("  (i) sheet 40 x 24 mm: aggressor pads A (8,5), B (32,5); 1 mm moat at y = 12 from x = 2 to 38;"
          " sense taps C (15,20), D (25,20)")
    for name, mask in (("moat (2 mm necks at the ends)", ~moat), ("moat + 2 mm bridge at x = 20", ~moat | bridge),
                       ("moat filled", np.ones((ny, nx), bool))):
        V, I = ps.solve(mask, [(A, 1.0), (B, 0.0)])
        print(f"    {name:30s}: self R_AB {1/I[0]:6.3f} sq; foreign drop V_CD/I {(V[c]-V[d])/I[0]*1e3:7.1f} milli-sq")
    print("    (the centre bridge lies on the aggressor's symmetry equipotential, so it carries ~no current)")
    print("  (ii) board 60 x 40 mm, 1.6 mm FR-4, top copper only (1 oz), h 10 per side; 1 W in 3 x 3 mm at (15,20),"
          " victim 3 x 3 mm at (35,20); moat 2 x 32 mm at x = 25")
    for name in ("moat", "moat filled"):
        b = tb.Board(60e-3, 40e-3, 0.5e-3, [35e-6, 35e-6], [1.53e-3], 10.0, 10.0)
        b.cov[0][:] = True
        if name == "moat":
            b.cov[0][b.rect(24e-3, 4e-3, 26e-3, 36e-3)] = False
        src = b.rect(13.5e-3, 18.5e-3, 16.5e-3, 21.5e-3)
        vic = b.rect(33.5e-3, 18.5e-3, 36.5e-3, 21.5e-3)
        b.add_power(src, 1.0)
        T = b.solve()
        print(f"    {name:12s}: source rise {T[0][src].mean():5.1f} K, victim rise {T[0][vic].mean():5.1f} K")


def exp_fdt():
    print("== fdt (a): dielectric-loss noise current of 1 pF of board dielectric at a high-impedance node, fA/rtHz")
    cd = 1e-12
    freqs = (1, 10, 100, 1000)
    print("    material (tan d)      " + "".join(f"{f:>9d} Hz" for f in freqs))
    for name, td in (("FR-4 (0.02)", 0.02), ("Rogers 4350B (0.0037)", 0.0037), ("PTFE (0.0002)", 0.0002)):
        print(f"    {name:22s}" + "".join(f"{math.sqrt(4*KB*T0*2*math.pi*f*cd*td)*1e15:12.3f}" for f in freqs))
    print(f"    floors: shot noise of 20 fA bias {math.sqrt(2*QE*20e-15)*1e15:.3f}; 1 Tohm resistor"
          f" {math.sqrt(4*KB*T0/1e12)*1e15:.3f}; 10 Gohm {math.sqrt(4*KB*T0/1e10)*1e15:.2f} fA/rtHz")
    for R in (1e12, 1e10):
        print(f"    1 pF of FR-4 out-noises a {R:.0e} ohm resistor above {1/(2*math.pi*R*cd*0.02):6.1f} Hz")
    ctot = 5e-12
    print("    as voltage noise at a node of 5 pF total (1 pF of it FR-4): "
          + "; ".join(f"{math.sqrt(4*KB*T0*0.02*cd/(2*math.pi*f*ctot**2))*1e9:6.0f} nV/rtHz at {f} Hz" for f in (0.1, 1, 10))
          + "  (1/f)")
    print("    guard driven at the node's potential: signal current through C_d -> 0, noise current sqrt(4kT w C_d tan d)"
          " unchanged (it is a source between node and guard)")
    print("== fdt (b): loss before the first gain stage adds (L - 1) T; antenna efficiency adds (1 - eta) T_phys")
    for ldb in (0.1, 0.3, 1.0):
        L = 10 ** (ldb / 10)
        tadd = (L - 1) * T0
        nf = 10 * math.log10(1 + (tadd + L * 75) / 290)
        print(f"    {ldb:3.1f} dB at {T0:.0f} K: +{tadd:5.1f} K; system NF with a 75 K (1.0 dB) LNA: {nf:4.2f} dB")
    for eta in (0.9, 0.7, 0.5):
        ta = eta * 60 + (1 - eta) * T0
        noise_db = 10 * math.log10((ta + 75) / (60 + 75))
        print(f"    GNSS, sky 60 K, LNA 75 K, efficiency {eta:.1f}: T_A {ta:5.1f} K; C/N0 loss {noise_db + 10*math.log10(1/eta):4.2f} dB,"
              f" of which added noise {noise_db:4.2f} dB")
    print("== fdt (c): thermal magnetic noise of copper layers (normal component, f below the sheet's eddy cut-off)")
    for t, name in ((35e-6, "one 1 oz plane"), (4 * 35e-6, "four 1 oz planes")):
        cells = [f"{a*1e3:3.0f} mm {MU0*math.sqrt(KB*T0*5.8e7*t)/(math.sqrt(8*math.pi)*a)*1e15:6.1f}" for a in (2e-3, 5e-3, 10e-3, 20e-3)]
        print(f"    {name:16s} (fT/rtHz): " + "; ".join(cells))
    print("    optically pumped magnetometers reach ~10-20 fT/rtHz, fluxgates ~5-20 pT/rtHz")
    print("== fdt (d): 20 mOhm of series copper in front of low-impedance sources (noise power increase)")
    for rs, name in ((10.0, "10 ohm (MC cartridge)"), (100.0, "100 ohm (RTD)"), (350.0, "350 ohm (bridge)")):
        print(f"    {name:22s}: +{10*math.log10(1+0.02/rs)*1e3:5.2f} mdB; copper e_n {math.sqrt(4*KB*T0*0.02)*1e12:4.0f} pV/rtHz")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in (("equipartition", exp_equipartition), ("transfer", exp_transfer), ("fdt", exp_fdt)):
        if which in (name, "all"):
            fn()
