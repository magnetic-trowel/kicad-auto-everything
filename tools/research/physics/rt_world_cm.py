# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Red-team check of lens CT's board-world identity and round 1's 'cables on one edge buy ~40 dB'.

(1) identity  I_CM = -j w sum_i C_i,ext V_i is exact when V_i are potentials relative to the outside
    world. A layout tool knows circuit voltages V_i^c (relative to board ground); the board's own
    potential V_g relative to the world is set by the external CM impedance Z_A (cable antenna,
    LISN). Charge conservation on the board gives
        I_A = -j w sum_i c_i V_i^c / (1 + j w C_tot Z_A),   C_tot = sum_i c_i (ground included),
    so the naive formula with circuit voltages over-predicts by |1 + j w C_tot Z_A|; for Z_A >>
    1/(w C_tot) it becomes Shim & Hubing's V_cm = V C_part / C_tot instead.
(2) same_edge fe_emi_budget.py case D subtracts a fixed 40 dB (an input: 'PEEC: >= 40 dB less plane
    voltage' between the two cable points). With both cables on one edge the board itself becomes
    the other antenna arm: the plane voltage dV = j w L_ret I between the cable edge and the far part
    of the board drives charge onto the far region's capacitance to the world. Using the identity
    above with a two-region board (near region at the cable, far region at dV):
        I_same ~ w c_far dV / |1 + j w C_tot Z_A|     vs     I_opp ~ dV / Z_cm,
    for a trace running away from the cable edge (worst orientation) and for a trace parallel to
    it with the cables off-centre by a fraction of the board width (better orientation).

Lumped and quasi-static; C values are free-space plate estimates (a 80 x 60 mm plane is ~3-4 pF).
Run: OMP_NUM_THREADS=1 python tools/research/physics/rt_world_cm.py   (instant)
"""
import math

EPS0 = 8.854e-12


def naive_over_true(f, c_tot, z_a):
    w = 2 * math.pi * f
    return abs(1 + 1j * w * c_tot * z_a)


def sec_identity():
    print("== identity: naive I_CM (circuit voltages) / true I_CM (world-referenced), = |1 + j w C_tot Z_A|, in dB")
    print("   C_tot   Z_A     3 MHz   30 MHz  100 MHz  300 MHz")
    for c_tot in (5e-12, 30e-12):
        for z_a in (25.0, 150.0, 500.0):
            cells = [f"{20*math.log10(naive_over_true(f, c_tot, z_a)):6.1f}" for f in (3e6, 30e6, 100e6, 300e6)]
            print(f"   {c_tot*1e12:3.0f} pF {z_a:5.0f} ohm " + "  ".join(cells))
    print("   (CT's own D2 table is correct because it solves the lumped circuit including the LISN; the identity")
    print("    fed with circuit voltages over-predicts by up to 5 dB for a small free board (5 pF) to 300 MHz, and by")
    print("    10-29 dB at 100-300 MHz for a board with 30 pF to its surroundings and a 150-500 ohm cable)")


def plate_c(area_m2):
    """Free-space capacitance of a thin square-ish plate of the given area: C ~ 0.367 * 4 pi eps0 * side."""
    return 0.367 * 4 * math.pi * EPS0 * math.sqrt(area_m2)


def sec_same_edge():
    print("== same_edge: cables on one edge vs opposite edges; ratio of cable CM current I_same / I_opp (dB)")
    lb, wb = 80e-3, 60e-3
    c_tot = plate_c(lb * wb)
    print(f"   board {lb*1e3:.0f} x {wb*1e3:.0f} mm: free-space C_tot ~ {c_tot*1e12:.1f} pF (doubles near a ground plane)")
    for c_scale in (1.0, 3.0):
        ct = c_tot * c_scale
        for z_cm in (36.0, 150.0):
            cells = []
            for f in (100e6, 150e6, 300e6, 450e6):
                w = 2 * math.pi * f
                # worst orientation: trace runs away from the cable edge, far half of the board at dV
                c_far = 0.5 * ct
                i_same = w * c_far / abs(1 + 1j * w * ct * z_cm)
                i_opp = 1.0 / z_cm
                # better orientation: trace parallel to the cable edge, cables 25% of the width off-centre:
                # regions left/right at +-dV/2, net driving charge ~ (imbalance 0.25) * c_half * dV
                i_par = w * 0.25 * 0.5 * ct * 0.5 / abs(1 + 1j * w * ct * z_cm)
                cells.append(f"{f/1e6:4.0f} MHz {20*math.log10(i_same/i_opp):+6.1f} / {20*math.log10(i_par/i_opp):+6.1f}")
            print(f"   C_tot {ct*1e12:4.1f} pF, Z_cm {z_cm:4.0f} ohm (worst / parallel, off-centre): " + "; ".join(cells))
    print("   -> moving both cables to one edge removes the inter-cable voltage (PEEC 43-63 dB) but leaves the")
    print("      board-vs-cable mode: 6-30 dB of benefit in the worst orientation (6-17 dB at 300-450 MHz),")
    print("      24-48 dB when the return voltage runs parallel to the cable edge; 40 dB is not a constant.")


if __name__ == "__main__":
    sec_identity()
    print()
    sec_same_edge()
