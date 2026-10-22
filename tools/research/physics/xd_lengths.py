# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Characteristic lengths and closed-form checks borrowed from other fields (xd).

1. Thermal fin/spreading length of a board, lambda = sqrt(sum(k t) / h)
   (heat-transfer fin theory) and how much pour radius is worth having.
2. PDN "decap screening length" (Debye-length analogy): a plane pair with
   inductance mu0*d per square and n decaps per m^2 of mounting inductance Lc
   obeys a screened Laplace equation with lambda = sqrt(Lc / (mu0 d n)).
   Checked against a lattice-of-decaps grid model.
3. Paralleled copper layers above a return plane: AC current split (the
   proximity effect of planar magnetics, lumped 1D inductance model).
4. Adiabatic fault withstand of a trace (IEC 60949 k-factor form) in A^2 s.
5. DC "step voltage" in a ground pour near a high-current injection
   (substation grounding analogy) vs an ADC LSB.

Run:  python tools/research/physics/xd_lengths.py
Deterministic, < 30 s.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.special import i0, i1, k0, k1

MU0 = 4e-7 * np.pi
RHO = 1.72e-8
K_CU = 390.0     # W/m/K
K_FR4 = 0.3      # in-plane FR-4, W/m/K (order of magnitude)


def thermal():
    print("== 1. thermal spreading (fin) length lambda = sqrt(sum k*t / h_total)")
    stacks = {"2-layer 1.6 mm, 1 oz both sides": 2 * 35e-6,
              "4-layer 1.6 mm, 1 oz x4": 4 * 35e-6,
              "4-layer, 2 oz planes + 1 oz outer": 2 * 70e-6 + 2 * 35e-6}
    for name, tcu in stacks.items():
        kt = K_CU * tcu + K_FR4 * 1.6e-3
        for h_side, cond in ((10.0, "still air"), (40.0, "light forced air")):
            h = 2 * h_side
            lam = np.sqrt(kt / h)
            m = 1 / lam
            r0 = 2.5e-3  # 5 mm source footprint
            # annular fin r0..R, insulated rim: conductance vs infinite plate
            def G(R):
                num = k1(m * r0) * i1(m * R) - i1(m * r0) * k1(m * R)
                den = k0(m * r0) * i1(m * R) + i0(m * r0) * k1(m * R)
                return 2 * np.pi * kt * m * r0 * num / den
            Ginf = 2 * np.pi * kt * m * r0 * k1(m * r0) / k0(m * r0)
            Rs = np.linspace(r0 * 1.01, 10 * lam, 4000)
            g = np.array([G(R) for R in Rs])
            r90 = Rs[np.argmax(g >= 0.9 * Ginf)]
            print(f"  {name:36s} {cond:16s} kt={kt:.4f} W/K, lambda={lam*1e3:5.1f} mm, "
                  f"R_th(plate, 5 mm source)={1/Ginf:5.1f} K/W, pour radius for 90% of it: {r90*1e3:5.1f} mm")


def pdn_screening():
    print("== 2. decap screening length lambda = sqrt(Lc/(mu0 d n))  (all-inductive regime)")
    for d in (0.1e-3, 0.2e-3, 1.0e-3):
        for a in (5e-3, 10e-3):
            Lc = 0.7e-9
            n = 1 / a ** 2
            lam = np.sqrt(Lc / (MU0 * d * n))
            print(f"  plane spacing d={d*1e3:.1f} mm, decap pitch {a*1e3:.0f} mm, Lc={Lc*1e9:.1f} nH: lambda={lam*1e3:6.1f} mm")
    # numerical check: grid h=0.5 mm, 120 x 120 mm plane pair, decaps on a lattice
    h = 0.5e-3; N = 240; d = 0.2e-3; a_cells = 20; Lc = 0.7e-9
    Ls = MU0 * d  # H per square
    # "conductance" = 1/L (we solve the inductive network as a resistive one)
    n = N * N
    idx = np.arange(n).reshape(N, N)
    rows, cols, vals = [], [], []
    g = 1 / Ls
    for A, B in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
        A = A.ravel(); B = B.ravel()
        rows += [A, B, A, B]; cols += [A, B, B, A]
        vals += [np.full(A.size, g)] * 2 + [np.full(A.size, -g)] * 2
    caps = idx[a_cells // 2::a_cells, a_cells // 2::a_cells].ravel()
    rows.append(caps); cols.append(caps); vals.append(np.full(caps.size, 1 / Lc))
    G = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    load = idx[N // 2, N // 2]
    b = np.zeros(n); b[load] = 1.0
    v = spla.spsolve(G.tocsc(), b)
    Lin = v[load]
    # share of current supplied by decaps vs distance
    capI = v[caps] / Lc
    yy, xx = np.divmod(caps, N)
    r = np.hypot(yy - N // 2, xx - N // 2) * h
    lam = np.sqrt(Lc / (MU0 * d / (a_cells * h) ** 2))
    order = np.argsort(r)
    cum = np.cumsum(capI[order]) / capI.sum()
    def share_within(R):
        return cum[np.searchsorted(r[order], R, side="right") - 1]
    print(f"  grid check (d=0.2 mm, decaps every {a_cells*h*1e3:.0f} mm, load midway between 4 decaps): lambda={lam*1e3:.1f} mm")
    print(f"   input inductance seen by the load: {Lin*1e12:.0f} pH (one decap alone would be >= {Lc*1e12:.0f} pH)")
    for R in (0.5 * lam, lam, 2 * lam, 3 * lam):
        x = R / lam
        print(f"   share of load current from decaps within {R*1e3:5.1f} mm ({x:.1f} lambda): {share_within(R)*100:5.1f}%"
              f"  (continuum 1 - x K1(x): {(1 - x * k1(x))*100:5.1f}%)")


def paralleled_layers():
    print("== 3. paralleled same-net layers above one return plane: current split vs frequency")
    # 4-layer 1.6 mm: L1 at -0.2 mm, L2 = return (0), L3 at +1.2 mm, L4 at +1.4 mm.
    # forward net on L1, L3, L4 (paralleled at both ends); 1 oz; width w = 10 mm, length 20 mm
    w, length, t = 10e-3, 20e-3, 35e-6
    hgt = np.array([0.2e-3, 1.2e-3, 1.4e-3])   # distance of each forward layer from the return
    sides = np.array([-1, 1, 1])               # L1 is on the other side of the return
    R = RHO * length / (t * w) * np.eye(3)
    Lm = np.zeros((3, 3))
    for i in range(3):
        for j in range(3):
            same = sides[i] == sides[j]
            Lm[i, j] = MU0 * length / w * (min(hgt[i], hgt[j]) if same else 0.0)
    for f in (0, 1e4, 1e5, 3e5, 1e6, 1e7):
        Z = R + 1j * 2 * np.pi * f * Lm
        I = np.linalg.solve(Z, np.ones(3))
        I = np.abs(I / I.sum())
        print(f"   f={f:9.0f} Hz: share L1 (0.2 mm from return) {I[0]*100:5.1f}%, L3 {I[1]*100:5.1f}%, L4 {I[2]*100:5.1f}%")
    print("   (skin depth in Cu at 1 MHz = %.0f um; intra-layer skin effect ignored)" % (np.sqrt(RHO / (np.pi * 1e6 * MU0)) * 1e6))


def fault():
    print("== 4. adiabatic fault withstand of a trace, I^2 t = (k S)^2, k = 226 sqrt(ln((Tf+234.5)/(Ti+234.5)))")
    for Tf in (180.0, 300.0):
        k = 226 * np.sqrt(np.log((Tf + 234.5) / (25 + 234.5)))
        cells = []
        for wmm in (0.2, 0.5, 1.0, 3.0):
            S = wmm * 0.035  # mm^2 at 1 oz
            cells.append(f"{wmm} mm: {(k*S)**2:7.2f} A^2s")
        print(f"   Ti=25 C -> Tf={Tf:.0f} C (k={k:.0f}); 1 oz traces " + ", ".join(cells))


def step_voltage():
    print("== 5. DC ground-pour 'step voltage' near a high-current return injection")
    Rs = RHO / 35e-6
    for I, r, span in ((10.0, 10e-3, 5e-3), (3.0, 10e-3, 5e-3), (10.0, 30e-3, 5e-3)):
        dV = Rs * I / (2 * np.pi) * np.log((r + span / 2) / (r - span / 2))
        lsb = 3.3 / 2 ** 16
        print(f"   {I:4.0f} A entering a 1 oz pour, {span*1e3:.0f} mm-wide ADC footprint centred {r*1e3:.0f} mm away, radial: "
              f"{dV*1e6:6.0f} uV = {dV/lsb:4.1f} LSB (16 bit, 3.3 V); tangential (on an equipotential): ~0")


if __name__ == "__main__":
    thermal(); pdn_screening(); paralleled_layers(); fault(); step_voltage()
