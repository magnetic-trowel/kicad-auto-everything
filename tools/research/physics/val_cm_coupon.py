# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered predictions for the board-world common-mode coupon (validation program, coupon CM).

Used by docs/topics/physics/validation-coupons.md. Lens CT derived the one-cable common-mode
current from charge conservation on a surface around the board, I_CM = -j w sum_i C_i,ext V_i,
and showed that a heatsink bond moves a displacement edge inside or outside that surface:
in its lumped example a 10 nH strap to DC- instead of to the chassis gave -39 dB at 30 MHz but
only -20 dB at 100 MHz. Round 1's rule (DR28) says "bond the heatsink to DC-"; common practice
says "bond the heatsink to chassis/earth". The coupon measures which, and where the strap stops
working.

Coupon: an 80 x 60 mm 4-layer board (GND on L2) with a 10 x 10 mm "switch-node" pad on L1 fed
by an SMA (centre to the pad, body to GND); a 40 x 40 mm aluminium plate (the heatsink) on
0.25 mm Kapton over the pad; the board on 6 mm standoffs (nylon or metal) over a 300 x 200 mm
aluminium plate (the chassis and reference ground); a 1 m two-wire cable from the board GND
and +12 V pads to a LISN bonded to the plate (CM 25 ohm); a clamp-on CM current probe on the
cable 50 mm from the board. NanoVNA S21 from the pad drive to the probe. Variants (jumpers
and screws): V1 heatsink floating; V2 heatsink strapped to the chassis; V3 strapped to board
GND (10 mm wire); V4 V3 plus a 4.7 nF Y-capacitor GND-chassis at a mounting hole; V5 V1 with
metal standoffs (board GND bonded to the chassis at four holes).

Model: the lumped extended graph of ct_cut_topology.py (section cm), with the cable as a
transmission line over the plate (Z_c, length, er_eff) loaded by the LISN, so its input
impedance has the 1 m cable resonances. Registered: the variant ratios |I_CM(Vk)/I_CM(V2)|
in dB at 3-200 MHz, with 5-95 % intervals from a Monte Carlo over the parasitics (ranges in
PARAMS). Absolute levels depend on the probe's transfer impedance and are not registered.

Run:  python tools/research/physics/val_cm_coupon.py      (numpy, ~5 s)
"""
import math
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np  # noqa: E402

EPS0, C0 = 8.854e-12, 2.998e8
FREQS = np.array([3e6, 10e6, 30e6, 60e6, 100e6, 150e6, 200e6])
N_MC = 4000
# parameter: (low, high), sampled log-uniformly
PARAMS = {
    "C_tab": (10e-12, 16e-12),      # pad 100 mm^2 under 0.25 mm Kapton (er 3.4) = 12 pF, plus fringe
    "C_sw_ch": (0.3e-12, 1.5e-12),  # pad's own capacitance to the chassis plate
    "C_n_ch": (6e-12, 15e-12),      # board (80 x 60 mm, 6 mm up) to the plate: 7 pF parallel plate, plus fringe
    "C_hs_ch": (2e-12, 8e-12),      # 40 x 40 mm plate ~8 mm above the chassis
    "L_strap": (7e-9, 15e-9),       # 10 mm wire plus terminations
    "L_bond": (3e-9, 10e-9),        # four metal standoffs in parallel
    "L_y": (2e-9, 5e-9),            # Y-capacitor ESL and leads
    "Z_c": (150.0, 300.0),          # cable CM line over the plate (2-5 cm high)
    "len": (0.95, 1.05),            # cable length (m)
    "er_eff": (1.0, 1.4),           # cable insulation
}
VARIANTS = ("V1 floating", "V2 to chassis", "V3 to board GND", "V4 V3 + 4.7 nF Y-cap", "V5 V1 + metal standoffs")


def cable_zin(f, zc, length, er_eff, zl=25.0):
    beta = 2 * math.pi * f * math.sqrt(er_eff) / C0
    t = np.tan(beta * length)
    return zc * (zl + 1j * zc * t) / (zc + 1j * zl * t)


def icm(f, p, variant):
    """CM current into the cable per volt of switch-node drive. Nodes: N (board GND), SW, HS; chassis = 0 V."""
    w = 2 * math.pi * f
    Y = np.zeros((3, 3), complex)
    N, SW, HS = 0, 1, 2

    def add(a, b, y):
        for i in (a, b):
            if i is not None:
                Y[i, i] += y
        if a is not None and b is not None:
            Y[a, b] -= y
            Y[b, a] -= y
    zin = cable_zin(f, p["Z_c"], p["len"], p["er_eff"])
    add(N, None, 1 / zin)
    add(SW, HS, 1j * w * p["C_tab"])
    add(SW, None, 1j * w * p["C_sw_ch"])
    add(N, None, 1j * w * p["C_n_ch"])
    if variant.startswith("V2"):
        add(HS, None, 1 / (1j * w * p["L_strap"]))
    else:
        add(HS, None, 1j * w * p["C_hs_ch"])
    if variant.startswith(("V3", "V4")):
        add(HS, N, 1 / (1j * w * p["L_strap"]))
    if variant.startswith("V4"):
        add(N, None, 1 / (1 / (1j * w * 4.7e-9) + 1j * w * p["L_y"]))
    if variant.startswith("V5"):
        add(N, None, 1 / (1j * w * p["L_bond"]))
    G = 1e6                                   # stiff 1 V source SW-N (Norton), as in ct_cut_topology
    add(SW, N, G)
    I = np.zeros(3, complex)
    I[SW], I[N] = G, -G
    V = np.linalg.solve(Y, I)
    return V[N] / zin


def sample(rng):
    return {k: math.exp(rng.uniform(math.log(lo), math.log(hi))) for k, (lo, hi) in PARAMS.items()}


def main():
    rng = np.random.default_rng(7)
    nominal = {k: math.sqrt(lo * hi) for k, (lo, hi) in PARAMS.items()}
    print("== CM coupon: CM current into the 1 m cable per volt on the switch-node pad (lumped extended graph)")
    print("   nominal |I_CM| (uA per V):")
    print("   variant                      " + "".join(f"{f/1e6:8.0f}MHz" for f in FREQS))
    for v in VARIANTS:
        print(f"   {v:28s} " + "".join(f"{abs(icm(f, nominal, v))*1e6:11.3f}" for f in FREQS))
    print("\n   registered ratios |I_CM(V)/I_CM(V2 heatsink to chassis)| in dB: nominal [5 %, 95 %]")
    draws = [sample(rng) for _ in range(N_MC)]
    for v in VARIANTS:
        if v.startswith("V2"):
            continue
        cells = []
        for f in FREQS:
            r = np.array([20 * math.log10(abs(icm(f, p, v)) / abs(icm(f, p, "V2 to chassis"))) for p in draws])
            nom = 20 * math.log10(abs(icm(f, nominal, v)) / abs(icm(f, nominal, "V2 to chassis")))
            cells.append(f"{nom:+6.1f} [{np.percentile(r, 5):+.0f},{np.percentile(r, 95):+.0f}]")
        print(f"   {v:28s} " + "  ".join(cells))
    print("   frequencies: " + ", ".join(f"{f/1e6:.0f}" for f in FREQS) + " MHz")
    # where the DC- strap stops working: frequency at which V3 is only 10 dB below V2
    fs = np.logspace(6, 8.5, 300)
    r = np.array([20 * math.log10(abs(icm(f, nominal, "V3 to board GND")) / abs(icm(f, nominal, "V2 to chassis")))
                  for f in fs])
    i = int(np.argmax(r > -10))
    print(f"\n   the strap to board GND keeps >= 10 dB of advantage up to about {fs[i]/1e6:.0f} MHz (nominal);"
          f" its own reactance w L_strap equals the cable's CM impedance near the strap-to-cable crossover")
    print("   competing predictions: 'bond the heatsink to chassis' (common practice) makes V2 the best variant;")
    print("   CT/DR28 make V3/V4 better by 20-40 dB below ~30 MHz, and V4's Y-cap extends it upward.")


if __name__ == "__main__":
    main()
