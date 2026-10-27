# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tombstoning physics: torque balance vs package size, and a lumped
transient model of two pads of a chip part passing through liquidus.

1  Torque ratio R = (surface-tension torque of the first molten fillet) /
   (gravity torque of the part) ~ gamma*W*H / (m*g*L/2). R scales as 1/L^2,
   so small parts are dominated by surface tension; what holds them down is
   the unmelted paste and wetting under the other end, i.e. timing.
2  Capillary time sqrt(rho*l^3/gamma): how fast a molten fillet can act.
3  Lumped reflow model (Euler-free, scipy solve_ivp). Nodes: gas (ramp),
   local board area under the part, a plane region (with or without a heavy
   part such as a 10x10x5 mm inductor), pad A (linked to the plane by a
   solid connection, 4-spoke relief, or a narrow neck) and pad B (local
   only). Reports the temperature difference between the pads when the
   first one reaches 217 C and the time lag between them. Per-area board
   time constant tau = rho*c*t/(2h) is the same everywhere, so pads only
   desynchronise when the plane is tied to something with a different time
   constant (heavy parts, shadowed areas, rails). Lag ~ ramp_rate * dtau.

Run (numpy, scipy):

    python tools/research/physics/tm_solder_reflow.py
"""
import math

import numpy as np
from scipy.integrate import solve_ivp

GAMMA = 0.5        # N/m molten SAC with flux (0.4-0.55)
RHO_SOLDER = 7400.0
OZ = 34.8e-6


def section_1():
    print("1  tombstoning torque ratio (surface tension / gravity), MLCC density 5.8 g/cm^3")
    parts = {"01005": (0.4, 0.2, 0.2), "0201": (0.6, 0.3, 0.3), "0402": (1.0, 0.5, 0.5),
             "0603": (1.6, 0.8, 0.8), "0805": (2.0, 1.25, 0.85), "1206": (3.2, 1.6, 1.0)}
    for name, (L, W, H) in parts.items():
        L, W, H = L * 1e-3, W * 1e-3, H * 1e-3
        m = 5800 * L * W * H
        t_st = GAMMA * W * H
        t_g = m * 9.81 * L / 2
        print(f"    {name:5s} mass {m*1e6:6.2f} mg  T_gamma {t_st*1e9:6.1f} nN*m  T_grav {t_g*1e9:7.3f} nN*m"
              f"  ratio {t_st/t_g:6.0f}")
    for l in (0.1e-3, 0.3e-3):
        print(f"    capillary time for a {l*1e3:.1f} mm fillet: {math.sqrt(RHO_SOLDER*l**3/GAMMA)*1e3:.2f} ms")


def run(link_G, heavy=True, ramp=1.5, h=80.0, plane_area=20e-3 * 20e-3):
    """Return (dT_pads at first liquidus crossing, time lag s)."""
    rc_board = 1850 * 1100 * 1.6e-3 + 3.45e6 * OZ          # J/(m^2 K)
    a_loc = 3e-3 * 3e-3
    C_loc, G_loc_gas = rc_board * a_loc, 2 * h * a_loc
    C_pl, G_pl_gas = rc_board * plane_area, 2 * h * plane_area
    # heavy part: 10x10x5 mm ferrite/copper ~ 3.5e6 J/m^3K, exposed area 3e-4 m^2, pads tie it to the plane
    C_hv, G_hv_gas, G_hv_pl = (3.5e6 * 5e-7, h * 3e-4, 0.5) if heavy else (0.0, 0.0, 0.0)
    # pads: 0402 pad + termination + paste
    a_pad = 0.5e-3 * 0.6e-3
    C_pad = 3.45e6 * a_pad * 35e-6 + 7400 * 230 * a_pad * 0.05e-3 + 3e6 * 0.5e-3 * 0.5e-3 * 0.25e-3
    G_pad_loc = 0.3 / 0.3e-3 * a_pad          # through ~0.3 mm of FR-4 to the local board
    G_pad_gas = h * a_pad
    T0 = 150.0

    def gas(t):
        # 60 s soak at 170 C, then ramp to 245 C
        if t < 60:
            return min(170.0, T0 + 0.5 * t + 20)
        return min(245.0, 170.0 + ramp * (t - 60))

    def rhs(t, y):
        Tl, Tp, Th, Ta, Tb = y
        Tg = gas(t)
        dTl = (G_loc_gas * (Tg - Tl) + G_pad_loc * (Tb - Tl)) / C_loc
        dTp = (G_pl_gas * (Tg - Tp) + G_hv_pl * (Th - Tp) + link_G * (Ta - Tp)) / C_pl
        dTh = (G_hv_gas * (Tg - Th) + G_hv_pl * (Tp - Th)) / C_hv if heavy else 0.0
        dTa = (G_pad_gas * (Tg - Ta) + G_pad_loc * (Tl - Ta) + link_G * (Tp - Ta)) / C_pad
        dTb = (G_pad_gas * (Tg - Tb) + G_pad_loc * (Tl - Tb)) / C_pad
        return [dTl, dTp, dTh, dTa, dTb]
    y0 = [T0] * 5
    sol = solve_ivp(rhs, (0, 200), y0, max_step=0.05, method="LSODA", dense_output=True)
    t = np.linspace(0, 200, 40001)
    Y = sol.sol(t)
    Ta, Tb = Y[3], Y[4]

    def cross(T):
        i = np.argmax(T >= 217.0)
        return t[i] if T[i] >= 217.0 else float("nan")
    ta, tb = cross(Ta), cross(Tb)
    i = int(np.argmax((Ta >= 217) | (Tb >= 217)))
    return Tb[i] - Ta[i], ta - tb


def section_3():
    print("3  lumped reflow, 0402 pad A on a 20x20 mm plane, pad B local only; h = 80 W/m^2K")
    links = [("solid (plane spreading only)", 0.031), ("4 spokes 0.25x0.25", 1 / (1 / 0.054 + 1 / 0.031)),
             ("2 spokes 0.15x0.5", 1 / (1 / (2 * 390 * 0.15e-3 * OZ / 0.5e-3) + 1 / 0.031)),
             ("neck 0.15 x 2 mm trace", 390 * 0.15e-3 * OZ / 2e-3), ("no link (symmetric)", 0.0)]
    for heavy in (False, True):
        for ramp in (1.0, 2.5):
            print(f"    heavy part on plane: {heavy}, ramp {ramp} K/s")
            for name, G in links:
                dT, lag = run(G, heavy, ramp)
                print(f"      {name:30s} G_link {G*1e3:6.2f} mW/K  dT(B-A) at liquidus {dT:5.2f} K  lag {lag:5.2f} s")


if __name__ == "__main__":
    section_1()
    section_3()
