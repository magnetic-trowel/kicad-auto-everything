# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sensitivity-derived hot-loop inductance budgets for a switching cell.

What it computes
----------------
A hard-switched half-bridge cell: input cap (ideal V_in) -> commutation-loop
inductance L and resistance R -> high-side switch -> switch node with the
low-side Coss (C) and body diode to PGND; the output inductor is a constant
current I_L over the edge.  The high-side switch's drain-source voltage
collapses as a Gaussian (erf) edge with 10-90 % time t_sw.  R is set from an
assumed ring quality factor Q (R = sqrt(L/C)/Q).

For a sweep of L it reports switch-node peak, overshoot, ring frequency, and
compares the ODE result with the closed form for an erf-driven LC:
    overshoot / V_in ~= exp(-(2*pi*sigma/T)^2 / 2) * exp(-pi/(2Q)),
    sigma = t_sw / 2.563,  T = 2*pi*sqrt(L*C)
which inverts to an inductance budget for an allowed overshoot fraction a:
    L_max ~= sigma^2 / (2*C*ln(1/a'))   with a' = a * exp(+pi/(2Q)).
It then shows (1) how a first-order (linearised) sensitivity budget compares
with the exact nonlinear one, and (2) a square-root allocation of L_max across
loop sub-structures: L_i proportional to sqrt(k_i/s_i), the minimiser of
sum(k_i/L_i) subject to sum(s_i*L_i) = budget (k_i = cost of squeezing part i).

Two cases: a 12 V -> 3.3 V integrated buck (fast edges, small Coss) and a
48 V discrete half-bridge (slow edges, large Coss).  Reverse recovery and
nonlinear Coss are not modelled, so absolute overshoot is indicative only.

Run:  python dr_switch_cell_budget.py        (numpy + scipy, ~10 s, deterministic)
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp
from scipy.special import erf

K_RISE = 2.563  # 10-90 % time of an erf edge = 2.563 sigma


def simulate(L, C, V_in, I_L, t_sw, Q):
    sigma = t_sw / K_RISE
    Z0 = np.sqrt(L / C)
    R = Z0 / Q
    T_ring = 2 * np.pi * np.sqrt(L * C)
    t0 = 4 * sigma
    t_end = t0 + 4 * sigma + 6 * T_ring
    V_d, G_d = 0.7, 50.0

    def v_hs(t):  # high-side V_DS collapsing from V_in to ~0
        return V_in * 0.5 * (1 - erf((t - t0) / (np.sqrt(2) * sigma)))

    def f(t, y):
        i, v = y
        i_d = G_d * max(0.0, -V_d - v)
        return [(V_in - v_hs(t) - v - R * i) / L, (i - I_L + i_d) / C]

    v0 = -V_d - I_L / G_d
    sol = solve_ivp(f, (0.0, t_end), [0.0, v0], method="LSODA",
                    max_step=min(sigma, T_ring) / 40, rtol=1e-7, atol=1e-9)
    return sol.t, sol.y[1]


def peak_and_ring(t, v, V_in):
    k = int(np.argmax(v))
    x, tt = v[k:] - V_in, t[k:]
    zc = tt[1:][np.sign(x[1:]) != np.sign(x[:-1])]
    f_ring = 1.0 / (2 * np.mean(np.diff(zc[:6]))) if len(zc) > 3 else float("nan")
    return v[k], f_ring


def closed_form_overshoot(L, C, t_sw, Q):
    sigma = t_sw / K_RISE
    T = 2 * np.pi * np.sqrt(L * C)
    return np.exp(-0.5 * (2 * np.pi * sigma / T) ** 2) * np.exp(-np.pi / (2 * Q))


def closed_form_budget(a, C, t_sw, Q):
    sigma = t_sw / K_RISE
    a_eff = a * np.exp(np.pi / (2 * Q))
    if a_eff >= 1:
        return float("inf")
    return sigma ** 2 / (2 * C * np.log(1 / a_eff))


def exact_budget(c, v_allow, n_grid=40, iters=14):
    """First L at which the simulated peak exceeds v_allow.  The scan stops at
    L_cap = V_in*t_sw/I_L: beyond it the loop inductance itself limits di/dt
    (current commutation takes longer than the edge) and this voltage-driven
    switch model no longer applies.  Returns (L_max, L_cap); L_max = inf when
    overshoot never binds below L_cap."""
    def pk(L):
        return peak_and_ring(*simulate(L, c["C"], c["V_in"], c["I_L"], c["t_sw"], c["Q"]),
                             c["V_in"])[0]
    L_cap = c["V_in"] * c["t_sw"] / c["I_L"]
    grid = np.geomspace(0.05e-9, L_cap, n_grid)
    prev = grid[0]
    for L in grid:
        if pk(L) > v_allow:
            lo, hi = prev, L
            for _ in range(iters):
                mid = np.sqrt(lo * hi)
                lo, hi = (lo, mid) if pk(mid) > v_allow else (mid, hi)
            return np.sqrt(lo * hi), L_cap
        prev = L
    return float("inf"), L_cap


def sqrt_allocation(budget, fixed, free):
    """fixed: [(name, L)]; free: [(name, s_i, k_i)] -> list of (name, L_i)."""
    rem = budget - sum(L for _, L in fixed)
    w = np.array([np.sqrt(k / s) for _, s, k in free])
    s = np.array([s for _, s, _ in free])
    L_i = rem * w / np.sum(s * w)
    return [(n, L, "fixed") for n, L in fixed] + \
           [(n, Li, f"{100 * si * Li / budget:.0f}%") for (n, si, _), Li in zip(free, L_i)]


CASES = {
    "buck_12V": dict(V_in=13.2, C=120e-12, I_L=2.0, t_sw=1.5e-9, Q=8, V_abs=20.0,
                     derate=0.85, L_nom=0.8e-9,
                     sweep=[0.25e-9, 0.5e-9, 1e-9, 2e-9, 4e-9], pkg=0.3e-9),
    "halfbridge_48V": dict(V_in=54.0, C=700e-12, I_L=20.0, t_sw=15e-9, Q=8, V_abs=100.0,
                           derate=0.8, L_nom=10e-9,
                           sweep=[2e-9, 5e-9, 10e-9, 20e-9, 40e-9], pkg=5e-9),
}


def main():
    for name, c in CASES.items():
        print(f"\n== {name}: V_in={c['V_in']} V, Coss={c['C']*1e12:.0f} pF, I_L={c['I_L']} A, "
              f"t_sw(10-90)={c['t_sw']*1e9:.1f} ns, Q={c['Q']}")
        print(f"{'L nH':>6} {'V_pk V':>7} {'ovs % ODE':>9} {'ovs % closed':>12} {'f_ring MHz':>10}")
        for L in c["sweep"]:
            v_pk, f_r = peak_and_ring(*simulate(L, c["C"], c["V_in"], c["I_L"], c["t_sw"], c["Q"]),
                                      c["V_in"])
            cf = closed_form_overshoot(L, c["C"], c["t_sw"], c["Q"])
            print(f"{L*1e9:6.2f} {v_pk:7.2f} {100*(v_pk-c['V_in'])/c['V_in']:9.1f} "
                  f"{100*cf:12.1f} {(f'{f_r/1e6:10.0f}' if np.isfinite(f_r) else '         -')}")
        v_allow = c["derate"] * c["V_abs"]
        a = (v_allow - c["V_in"]) / c["V_in"]
        L_ex, L_cap = exact_budget(c, v_allow)
        L_cf = closed_form_budget(a, c["C"], c["t_sw"], c["Q"])
        dL = 0.05 * c["L_nom"]
        pk = [peak_and_ring(*simulate(L, c["C"], c["V_in"], c["I_L"], c["t_sw"], c["Q"]),
                            c["V_in"])[0] for L in (c["L_nom"] - dL, c["L_nom"], c["L_nom"] + dL)]
        s = (pk[2] - pk[0]) / (2 * dL)
        L_lin = c["L_nom"] + (v_allow - pk[1]) / s
        print(f"allowed peak {c['derate']} x {c['V_abs']:.0f} V = {v_allow:.1f} V "
              f"(overshoot a = {100*a:.0f} %)")
        ex = f"{L_ex*1e9:.2f} nH" if np.isfinite(L_ex) else f"not binding up to {L_cap*1e9:.0f} nH"
        print(f"budget: exact {ex} | closed form {L_cf*1e9:.2f} nH | "
              f"linearised at L_nom={c['L_nom']*1e9:.1f} nH (V_pk {pk[1]:.1f} V, "
              f"dV/dL {s*1e-9:.2f} V/nH): {L_lin*1e9:.2f} nH")
        if np.isfinite(L_ex) and L_ex > c["pkg"]:
            alloc = sqrt_allocation(L_ex, [("device package (fixed)", c["pkg"])],
                                    [("C_IN ESL + pads", 1.0, 1.0),
                                     ("vias to return plane", 1.0, 0.5),
                                     ("lateral loop over plane", 1.0, 2.0)])
            print("  sqrt allocation, k = relative cost to squeeze (1, 0.5, 2):")
            for n, Li, note in alloc:
                print(f"    {n:26s} {Li*1e9:6.2f} nH  {note}")


if __name__ == "__main__":
    main()
