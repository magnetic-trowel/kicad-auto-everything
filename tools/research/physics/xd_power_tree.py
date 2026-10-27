# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Branching-conductor experiments borrowed from flow networks (xd).

1. Width allocation for a DC power tree at a FIXED copper area (Murray/Kelvin
   analogy): equal widths vs width ~ I (constant current density, minimizes
   total I^2R loss) vs width ~ sqrt(I) vs widths optimized for the worst-case
   IR drop (convex problem, solved numerically).
2. Star vs shared-trunk topology, with and without a per-conductor clearance
   overhead (branched transport: overhead per conductor makes trunks pay).
3. Reverse-return ("Tichelmann", Z-type manifold) vs same-end (U-type) feeding
   of N paralleled loads: current-sharing spread.
4. Linearly accumulating collector bus: tapered vs uniform width at equal area.

Run:  python tools/research/physics/xd_power_tree.py
Deterministic, < 10 s. Units: metres, amperes, ohms. 1 oz copper (35 um).
"""
import numpy as np
from scipy.optimize import minimize

RHO = 1.72e-8
T = 35e-6
K = RHO / T  # ohm per square


def tree_metrics(edges, w):
    """edges: list of (length, current, path_ids_of_loads_served).
    Returns total loss (W) and per-load drop (V)."""
    L = np.array([e[0] for e in edges]); I = np.array([e[1] for e in edges])
    R = K * L / w
    loss = float((I ** 2 * R).sum())
    return loss, R * I


def main():
    # ---------------- 1. width allocation on a comb tree -----------------
    loads = np.array([2.0, 1.0, 0.5, 0.25, 0.25])     # A, at x = 15,30,45,60,75 mm
    n = len(loads)
    trunk_I = np.array([loads[k:].sum() for k in range(n)])
    edges = [(15e-3, trunk_I[k]) for k in range(n)] + [(10e-3, loads[k]) for k in range(n)]
    L = np.array([e[0] for e in edges]); I = np.array([e[1] for e in edges])
    # path matrix: load j uses trunk 0..j and branch j
    P = np.zeros((n, 2 * n))
    for j in range(n):
        P[j, :j + 1] = 1; P[j, n + j] = 1
    A = 1.0e-3 * L.sum()  # copper area budget = equal 1 mm width everywhere

    def evaluate(w):
        R = K * L / w
        loss = (I ** 2 * R).sum()
        drops = P @ (R * I)
        return loss, drops.max()

    def scaled(shape):
        w = shape / (shape * L).sum() * A
        return w

    cands = {"equal width (1.00 mm)": scaled(np.ones_like(I)),
             "w ~ I   (Kelvin/'Murray' for loss)": scaled(I),
             "w ~ sqrt(I) (series-drop optimum)": scaled(np.sqrt(I)),
             "w ~ I^1.38 (IPC-2221 equal-dT form)": scaled(I ** 1.38)}
    # worst-drop optimum: variables u = 1/w (drops are linear in u, area is
    # convex in u); minimize t s.t. drop_j <= t and sum L/u = A (SLSQP).
    c = K * L * I
    def cons_drop(z):
        u, t = z[:-1], z[-1]
        return t - P @ (c * u)
    def cons_area(z):
        return A - (L / z[:-1]).sum()
    u0 = 1 / scaled(np.sqrt(I)); z0 = np.r_[u0, (P @ (c * u0)).max()]
    res = minimize(lambda z: z[-1], z0, method="SLSQP",
                   constraints=[{"type": "ineq", "fun": cons_drop}, {"type": "ineq", "fun": cons_area}],
                   bounds=[(1e1, 1e5)] * len(L) + [(0, 1)], options={"maxiter": 2000, "ftol": 1e-14})
    cands["optimized for worst-case drop"] = 1 / res.x[:-1]
    print("== 1. comb power tree, 5 loads (2, 1, 0.5, 0.25, 0.25 A), trunk 5x15 mm, branches 10 mm,")
    print("      1 oz Cu, fixed copper area = 1 mm everywhere")
    base = evaluate(cands["equal width (1.00 mm)"])
    for name, w in cands.items():
        loss, drop = evaluate(w)
        print(f"  {name:38s} loss {loss*1e3:6.1f} mW ({loss/base[0]*100:5.1f}%)  worst drop {drop*1e3:6.1f} mV ({drop/base[1]*100:5.1f}%)"
              f"  widths trunk {np.round(w[:n]*1e3,2)} br {np.round(w[n:]*1e3,2)} mm")

    # ---------------- 2. star vs trunk ----------------
    print("== 2. star (one conductor per load) vs shared trunk, constant current density, fixed footprint")
    xs = 15e-3 * np.arange(1, n + 1); y = 10e-3
    star_L = np.hypot(xs, y)
    trunk_edges_L = np.r_[np.full(n, 15e-3), np.full(n, 10e-3)]
    trunk_edges_I = I
    for s in (0.0, 0.3e-3, 0.6e-3):
        # footprint F = sum (w + s) L ; with w = J I: F = J sum I L + s sum L
        F = 1.0e-3 * L.sum() + s * L.sum()  # same footprint as the trunk at 1 mm + clearance
        out = []
        for label, Ls, Is in (("trunk", trunk_edges_L, trunk_edges_I), ("star", star_L, loads)):
            cu = F - s * Ls.sum()              # copper area left after clearances
            if cu <= 0:
                out.append((label, np.inf)); continue
            loss = K * (Is * Ls).sum() ** 2 / cu  # constant-J optimum: P = K (sum I L)^2 / A_cu
            out.append((label, loss))
        print(f"  clearance overhead {s*1e3:.1f} mm/conductor: " + ", ".join(f"{a} {b*1e3:.1f} mW" for a, b in out)
              + f"  (sum I*L: trunk {(trunk_edges_I*trunk_edges_L).sum()*1e3:.1f}, star {(loads*star_L).sum()*1e3:.1f} A*mm)")

    # ---------------- 3. reverse return ----------------
    print("== 3. N paralleled loads between a feed rail and a return rail")
    for N, r_seg, R_el in ((8, 1e-3, 10e-3), (8, 0.5e-3, 5e-3), (4, 0.3e-3, 3e-3)):
        res_ = {}
        for cfg in ("U same-end", "Z reverse-return"):
            # nodes: feed f0..f(N-1), return g0..g(N-1); source + at f0, - at g0 (U) or g(N-1) (Z)
            nn = 2 * N
            G = np.zeros((nn, nn))
            def add(a, b, g):
                G[a, a] += g; G[b, b] += g; G[a, b] -= g; G[b, a] -= g
            for k in range(N - 1):
                add(k, k + 1, 1 / r_seg); add(N + k, N + k + 1, 1 / r_seg)
            for k in range(N):
                add(k, N + k, 1 / R_el)
            gnd = N if cfg.startswith("U") else 2 * N - 1
            b = np.zeros(nn); b[0] = 1.0  # 1 A injected at f0
            keep = [i for i in range(nn) if i != gnd]
            v = np.zeros(nn); v[keep] = np.linalg.solve(G[np.ix_(keep, keep)], b[keep])
            Iel = (v[:N] - v[N:]) / R_el
            res_[cfg] = Iel / Iel.mean()
        print(f"  N={N}, rail segment {r_seg*1e3:.1f} mOhm, element {R_el*1e3:.0f} mOhm: " +
              "; ".join(f"{k}: max/min share {v.max()/v.min():.2f}" for k, v in res_.items()))

    # ---------------- 4. tapered collector ----------------
    print("== 4. bus collecting current uniformly along its length (I grows 0 -> I0)")
    print("  uniform width w: loss = I0^2 K L/(3w); taper w(x) ~ x at equal area: I0^2 K L/(4w) -> 25% less loss")


if __name__ == "__main__":
    main()
