# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cost and accuracy of physics evaluators per fidelity tier (workstream 3, solver ladder).

Each section times a small, representative kernel on this machine (numpy/scipy,
1 thread unless BLAS threads) and prints accuracy against a finer reference:

  zo    microstrip Z0: Hammerstad-Jensen (H-J) and IPC-2141 closed forms vs a 2-D
        finite-difference Laplace solve (zero-thickness strip, FR-4 er=4.3);
        FD grid convergence vs cost.
  via   via inductance: Goldfarb-Pucel vs the Johnson rule (values only).
  cav   plane-pair cavity model Z11(f) (double modal sum): cost per sweep.
  ir    2.5-D DC IR drop on a copper pour raster (finite volume, SuperLU):
        cost vs grid, and incremental re-solve after a local edit (slot cut)
        using the stale LU factor as a CG preconditioner.
  fdtd  3-D Yee FDTD throughput in numpy (Mcell-updates/s), for scaling
        published openEMS / GPU numbers to PCB regions.
  vf    scikit-rf vector fitting of the cavity Z11 into a rational macromodel.

Run:  python tools/research/physics/sl_tier_costs.py [zo|via|cav|ir|fdtd|vf|all]
Deterministic; 'all' takes ~3 min (the 'zo' FD reference dominates). Needs numpy, scipy, scikit-rf (vf only).
"""

import math
import sys
import time

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

MU0 = 4e-7 * math.pi
EPS0 = 8.8541878128e-12
C0 = 299792458.0
ETA0 = MU0 * C0


def tic():
    return time.perf_counter()


# ------------------------------------------------------------------ microstrip
def hj_z0(w, h, er):
    """Hammerstad-Jensen 1980, zero thickness: returns (Z0, eps_eff)."""
    u = w / h
    f = 6 + (2 * math.pi - 6) * math.exp(-((30.666 / u) ** 0.7528))
    z01 = ETA0 / (2 * math.pi) * math.log(f / u + math.sqrt(1 + (2 / u) ** 2))
    a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    return z01 / math.sqrt(ee), ee


def ipc2141_z0(w, h, er, t=0.0):
    return 87 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))


def fd_microstrip(w, h, er, cells_per_h=20, side=8.0, top=8.0):
    """2-D FD/FV Laplace, zero-thickness strip at y=h, shielded box. Returns (Z0, eps_eff, n, secs)."""
    d = h / cells_per_h
    nx = int(round((w + 2 * side * h) / d)) + 1
    ny = int(round((h + top * h) / d)) + 1
    jh = cells_per_h
    x = np.arange(nx) * d - (w / 2 + side * h)
    strip = (np.abs(x) <= w / 2 + 1e-12)

    def cap(eps_cells):
        # node unknowns: all interior nodes except strip nodes; boundary phi=0
        idx = -np.ones((ny, nx), dtype=np.int64)
        fixed = np.zeros((ny, nx), dtype=bool)
        fixed[0, :] = fixed[-1, :] = fixed[:, 0] = fixed[:, -1] = True
        fixed[jh, strip] = True
        val = np.zeros((ny, nx))
        val[jh, strip] = 1.0
        free = ~fixed
        idx[free] = np.arange(free.sum())
        # edge permittivities: horizontal edge between (j,i)-(j,i+1) sees cells (j-1,i),(j,i)
        ec = np.pad(eps_cells, 1, mode="edge")  # (ny+1, nx+1) padded cell grid, cell (j,i) -> ec[j+1? ]
        # cell (j,i) spans nodes j..j+1, i..i+1, defined for j<ny-1, i<nx-1
        eh = 0.5 * (ec[0:ny, 1:nx] + ec[1:ny + 1, 1:nx])  # horizontal edges (ny, nx-1)
        ev = 0.5 * (ec[1:ny, 0:nx] + ec[1:ny, 1:nx + 1])  # vertical edges (ny-1, nx)
        rows, cols, vals = [], [], []
        rhs = np.zeros(free.sum())
        def add(ja, ia, jb, ib, g):
            a, b = idx[ja, ia], idx[jb, ib]
            fa, fb = a >= 0, b >= 0
            m = fa & fb
            rows.extend([a[m], b[m], a[m], b[m]])
            cols.extend([a[m], b[m], b[m], a[m]])
            vals.extend([g[m], g[m], -g[m], -g[m]])
            m2 = fa & ~fb
            rows.append(a[m2]); cols.append(a[m2]); vals.append(g[m2])
            np.add.at(rhs, a[m2], g[m2] * val[jb, ib][m2])
            m3 = ~fa & fb
            rows.append(b[m3]); cols.append(b[m3]); vals.append(g[m3])
            np.add.at(rhs, b[m3], g[m3] * val[ja, ia][m3])
        J, I = np.mgrid[0:ny, 0:nx - 1]
        add(J, I, J, I + 1, eh)
        J, I = np.mgrid[0:ny - 1, 0:nx]
        add(J, I, J + 1, I, ev)
        A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(free.sum(), free.sum()))
        phi = val.copy()
        phi[free] = spla.spsolve(A.tocsc(), rhs)
        e = (eh * np.diff(phi, axis=1) ** 2).sum() + (ev * np.diff(phi, axis=0) ** 2).sum()
        return EPS0 * e, free.sum()

    eps = np.ones((ny - 1, nx - 1))
    eps[:jh, :] = er
    t0 = tic()
    c1, n = cap(eps)
    c0, _ = cap(np.ones_like(eps))
    secs = tic() - t0
    z0 = 1 / (C0 * math.sqrt(c1 * c0))
    return z0, c1 / c0, n, secs


def sec_zo():
    print("== microstrip Z0, FR-4 er=4.3, zero thickness. FD reference = 2-D Laplace in a 16h box,")
    print("   Richardson-extrapolated from 10 and 20 cells/h (Z = 2*Z20 - Z10; first-order edge singularity)")
    er = 4.3
    print(f"{'w/h':>5s} {'FD Z0':>7s} {'FD eeff':>7s} {'H-J':>7s} {'err':>6s} {'H-J eeff':>8s} {'IPC-2141':>8s} {'err':>7s}")
    for u in (0.2, 0.5, 1.0, 1.9, 3.0, 6.0):
        z10, e10, _, _ = fd_microstrip(u, 1.0, er, cells_per_h=10, side=16, top=16)
        z20, e20, _, _ = fd_microstrip(u, 1.0, er, cells_per_h=20, side=16, top=16)
        zf, ef = 2 * z20 - z10, 2 * e20 - e10
        zh, eh = hj_z0(u, 1.0, er)
        zi = ipc2141_z0(u, 1.0, er)
        print(f"{u:5.2f} {zf:7.2f} {ef:7.3f} {zh:7.2f} {100*(zh/zf-1):5.1f}% {eh:8.3f} {zi:8.2f} {100*(zi/zf-1):6.1f}%")
    print("FD grid convergence at w/h = 1.9, box 8h (cells per h -> Z0, unknowns, seconds for 2 solves)")
    for c in (5, 10, 20, 40):
        zf, ef, n, s = fd_microstrip(1.9, 1.0, er, cells_per_h=c)
        print(f"  {c:3d} cells/h: Z0 {zf:7.3f}  eps_eff {ef:6.3f}  n={n:7d}  {s*1e3:8.1f} ms")
    n = 200000
    t0 = tic()
    for i in range(n):
        hj_z0(0.5 + (i % 50) * 0.05, 1.0, er)
    print(f"  H-J closed form: {(tic()-t0)/n*1e6:.2f} us per call (pure Python); "
          "vectorized numpy is ~0.05 us per element")


# ------------------------------------------------------------------ via
def sec_via():
    print("== via inductance (isolated barrel, no return via): Goldfarb-Pucel vs Johnson rule")
    for h_mm, d_mm in ((0.2, 0.2), (0.4, 0.3), (1.6, 0.3), (1.6, 0.6)):
        h, r = h_mm * 1e-3, d_mm * 1e-3 / 2
        gp = MU0 / (2 * math.pi) * (h * math.log((h + math.sqrt(r * r + h * h)) / r)
                                     + 1.5 * (r - math.sqrt(r * r + h * h)))
        hi, di = h_mm / 25.4, d_mm / 25.4
        jo = 5.08 * hi * (math.log(4 * hi / di) + 1) * 1e-9
        rosa = MU0 * h / (2 * math.pi) * (math.log(2 * h / r) - 1)  # straight-wire partial L, HF limit
        print(f"  h={h_mm} mm d={d_mm} mm: Goldfarb-Pucel {gp*1e9:.3f} nH, Rosa partial (HF) {rosa*1e9:.3f} nH,"
              f" Johnson 5.08h[ln(4h/d)+1] {jo*1e9:.3f} nH")
    print("  (a via's loop inductance depends on where its return flows; both are partial-L numbers)")


# ------------------------------------------------------------------ cavity
def cavity_z11(f, a, b, d, er, tand, x, y, wp, M=60, N=60, sigma=5.8e7):
    w = 2 * math.pi * f
    ds = np.sqrt(2 / (w * MU0 * sigma))
    k = w * np.sqrt(MU0 * EPS0 * er) * np.sqrt(1 - 1j * (tand + ds / d))
    m = np.arange(M)[:, None]
    n = np.arange(N)[None, :]
    kx, ky = m * math.pi / a, n * math.pi / b
    chi = np.where(m == 0, 1, 2) * np.where(n == 0, 1, 2)
    sx = np.sinc(kx * wp / 2 / math.pi)
    sy = np.sinc(ky * wp / 2 / math.pi)
    g = chi * (np.cos(kx * x) * np.cos(ky * y) * sx * sy) ** 2
    kmn2 = (kx ** 2 + ky ** 2)[None]
    s = (g[None] / (kmn2 - k[:, None, None] ** 2)).sum(axis=(1, 2))
    return 1j * w * MU0 * d / (a * b) * s


def sec_cav():
    print("== plane-pair cavity model, 50x40 mm, d=0.1 mm, FR-4, port at (10,12) mm")
    f = np.logspace(6, np.log10(3e9), 600)
    for M in (20, 40, 80):
        t0 = tic()
        z = cavity_z11(f, 0.05, 0.04, 0.1e-3, 4.3, 0.02, 0.01, 0.012, 0.5e-3, M=M, N=M)
        s = tic() - t0
        fr = f[1:-1][(np.abs(z[1:-1]) > np.abs(z[:-2])) & (np.abs(z[1:-1]) > np.abs(z[2:]))]
        print(f"  {M}x{M} modes, {len(f)} freqs: {s*1e3:7.1f} ms; first peaks (MHz): "
              + ", ".join(f"{v/1e6:.0f}" for v in fr[:3]))
    return f, z


# ------------------------------------------------------------------ IR drop
def pour_mask(nx, ny, d):
    X, Y = np.meshgrid((np.arange(nx) + 0.5) * d, (np.arange(ny) + 0.5) * d)
    m = np.ones((ny, nx), bool)
    m &= ~((X > 0.015) & (X < 0.022) & (Y > 0.008) & (Y < 0.022))  # cut-out
    for cx in np.arange(0.004, 0.040, 0.0025):  # rows of via antipads
        for cy in (0.004, 0.026):
            m &= (X - cx) ** 2 + (Y - cy) ** 2 > (0.35e-3) ** 2
    return m


def build_ir(mask, d, rs, sinks, src_cols=2):
    ny, nx = mask.shape
    idx = -np.ones(mask.shape, np.int64)
    idx[mask] = np.arange(mask.sum())
    g = 1 / rs  # conductance between edge-adjacent square cells
    rows, cols, vals = [], [], []
    for (dj, di) in ((0, 1), (1, 0)):
        a = idx[: ny - dj, : nx - di]
        b = idx[dj:, di:]
        m = (a >= 0) & (b >= 0)
        a, b = a[m], b[m]
        rows += [a, b, a, b]
        cols += [a, b, b, a]
        vals += [np.full(a.size, g)] * 2 + [np.full(a.size, -g)] * 2
    n = mask.sum()
    # source: left columns tied to 0 V through a large conductance
    src = idx[:, :src_cols][mask[:, :src_cols]]
    rows.append(src); cols.append(src); vals.append(np.full(src.size, 1e6))
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    b = np.zeros(n)
    for (j, i), cur in sinks:
        b[idx[j, i]] -= cur
    return A.tocsc(), b, idx


def sec_ir():
    print("== 2.5-D DC IR drop, 40x30 mm pour, 1 oz Cu (0.49 mOhm/sq), 16 x 0.5 A sinks, SuperLU")
    rs = 1.72e-8 / 35e-6
    for d in (0.2e-3, 0.1e-3, 0.05e-3):
        nx, ny = int(0.04 / d), int(0.03 / d)
        mask = pour_mask(nx, ny, d)
        sinks = [((int(cy / d), int(cx / d)), 0.5) for cx in (0.030, 0.032, 0.034, 0.036)
                 for cy in (0.011, 0.013, 0.015, 0.017)]
        A, b, idx = build_ir(mask, d, rs, sinks)
        t0 = tic()
        lu = spla.splu(A)
        tf = tic() - t0
        t0 = tic()
        v = lu.solve(b)
        ts = tic() - t0
        print(f"  cell {d*1e3:.2f} mm: n={A.shape[0]:7d}  factor {tf*1e3:7.1f} ms  solve {ts*1e3:6.1f} ms"
              f"  max drop {-v.min()*1e3:.2f} mV")
        if d < 0.15e-3:
            incremental_edit(A, b, lu, v, mask, idx, d, rs, sinks, tf + ts)
            if d > 0.07e-3:
                adjoint_screen(v, mask, idx, d, rs, sinks)


def adjoint_screen(v, mask, idx, d, rs, sinks):
    """First-order (adjoint) estimate of the loss change for removing copper, vs exact re-solve.

    DC loss P = sum g*dV^2 is self-adjoint, so dP/dg_e = -dV_e^2: removing a cell raises P by
    about the power its edges carried. One solve prices every cell at once.
    """
    V = np.full(mask.shape, np.nan)
    V[mask] = v[idx[mask]]
    g = 1 / rs
    px = g * np.nan_to_num(np.diff(V, axis=1)) ** 2
    py = g * np.nan_to_num(np.diff(V, axis=0)) ** 2
    E = np.zeros(mask.shape)
    E[:, :-1] += px / 2
    E[:, 1:] += px / 2
    E[:-1, :] += py / 2
    E[1:, :] += py / 2
    edits = {"0.5 mm hole": (0.0145, 0.015, 0.026, 0.0265), "2x2 mm cut-out": (0.013, 0.015, 0.026, 0.028),
             "6 mm slot across a band": (0.0, 0.006, 0.018, 0.018 + 2 * d)}
    A, b, _ = build_ir(mask, d, rs, sinks)
    P0 = b @ v
    for name, (y0, y1, x0, x1) in edits.items():
        j0, j1, i0, i1 = int(round(y0 / d)), int(round(y1 / d)), int(round(x0 / d)), int(round(x1 / d))
        m2 = mask.copy()
        m2[j0:j1, i0:i1] = False
        A2, b2, idx2 = build_ir(m2, d, rs, sinks)
        v2 = spla.splu(A2).solve(b2)
        est = 2 * E[j0:j1, i0:i1][mask[j0:j1, i0:i1]].sum()
        print(f"    adjoint screen, {name:24s}: loss +{(b2 @ v2 - P0)*1e3:7.3f} mW exact vs"
              f" +{est*1e3:7.3f} mW first-order (total {P0*1e3:.1f} mW)")


def incremental_edit(A, b, lu, v, mask, idx, d, rs, sinks, t_full):
    """Cut a 6 mm slot across the lower current band, then re-solve two ways."""
    m2 = mask.copy()
    i0 = int(0.018 / d)
    m2[: int(0.006 / d), i0:i0 + 2] = False
    A2, b2, idx2 = build_ir(m2, d, rs, sinks)
    both = (idx2 >= 0) & (idx >= 0)
    new_i, old_i = idx2[both], idx[both]
    x0 = np.zeros(A2.shape[0])
    x0[new_i] = v[old_i]
    t0 = tic()
    v2 = spla.splu(A2).solve(b2)
    tfull = tic() - t0
    z = np.zeros(A.shape[0])

    def prec(r):  # old factor restricted to the surviving cells (SPD), removed cells left out
        z[:] = 0.0
        z[old_i] = r[new_i]
        out = np.empty_like(r)
        out[new_i] = lu.solve(z)[old_i]
        return out
    M = spla.LinearOperator(A2.shape, matvec=prec)
    it = [0]
    t0 = tic()
    v3, info = spla.cg(A2, b2, x0=x0, M=M, rtol=1e-9, callback=lambda xk: it.__setitem__(0, it[0] + 1))
    tpcg = tic() - t0
    print(f"    local edit (6 mm slot, cell {d*1e3:.2f} mm): max drop {-v.min()*1e3:.2f} -> {-v2.min()*1e3:.2f} mV;"
          f" refactor+solve {tfull*1e3:.0f} ms vs stale-LU-preconditioned CG {tpcg*1e3:.0f} ms"
          f" ({it[0]} iterations, max err {np.abs(v3-v2).max()*1e6:.3f} uV)")


# ------------------------------------------------------------------ FDTD
def sec_fdtd():
    print("== 3-D Yee FDTD in numpy (float32, PEC box), throughput")
    for n in (64, 128):
        Ex, Ey, Ez = (np.zeros((n, n, n), np.float32) for _ in range(3))
        Hx, Hy, Hz = (np.zeros((n, n, n), np.float32) for _ in range(3))
        ce, ch = np.float32(0.5), np.float32(0.5)
        steps = 30
        t0 = tic()
        for s in range(steps):
            Hx[:, :-1, :-1] -= ch * ((Ez[:, 1:, :-1] - Ez[:, :-1, :-1]) - (Ey[:, :-1, 1:] - Ey[:, :-1, :-1]))
            Hy[:-1, :, :-1] -= ch * ((Ex[:-1, :, 1:] - Ex[:-1, :, :-1]) - (Ez[1:, :, :-1] - Ez[:-1, :, :-1]))
            Hz[:-1, :-1, :] -= ch * ((Ey[1:, :-1, :] - Ey[:-1, :-1, :]) - (Ex[:-1, 1:, :] - Ex[:-1, :-1, :]))
            Ex[:, 1:, 1:] += ce * ((Hz[:, 1:, 1:] - Hz[:, :-1, 1:]) - (Hy[:, 1:, 1:] - Hy[:, 1:, :-1]))
            Ey[1:, :, 1:] += ce * ((Hx[1:, :, 1:] - Hx[1:, :, :-1]) - (Hz[1:, :, 1:] - Hz[:-1, :, 1:]))
            Ez[1:, 1:, :] += ce * ((Hy[1:, 1:, :] - Hy[:-1, 1:, :]) - (Hx[1:, 1:, :] - Hx[1:, :-1, :]))
            Ez[n // 2, n // 2, n // 2] += np.float32(math.sin(0.1 * s))
        s = tic() - t0
        print(f"  {n}^3 cells x {steps} steps: {n**3*steps/s/1e6:.0f} Mcell-updates/s")


# ------------------------------------------------------------------ vector fitting
def sec_vf():
    import warnings

    import skrf
    from skrf.vectorFitting import VectorFitting
    warnings.filterwarnings("ignore")
    print("== scikit-rf vector fitting: 1-port PDN = 50x40 mm cavity + 10 x 100 nF + 2 x 22 uF MLCC,")
    print("   S11 referenced to 1 ohm, 600 points 100 kHz-3 GHz")
    f = np.logspace(5, np.log10(3e9), 600)
    w = 2 * np.pi * f
    z = cavity_z11(f, 0.05, 0.04, 0.1e-3, 4.3, 0.02, 0.01, 0.012, 0.5e-3, M=40, N=40)
    zc = 0.01 + 1j * w * 0.5e-9 + 1 / (1j * w * 100e-9)
    zb = 0.005 + 1j * w * 2e-9 + 1 / (1j * w * 22e-6)
    zt = 1 / (1 / z + 10 / zc + 2 / zb)
    s11 = (zt - 1.0) / (zt + 1.0)
    ntw = skrf.Network(frequency=skrf.Frequency.from_f(f, unit="Hz"), s=s11.reshape(-1, 1, 1), z0=1.0)
    for nc in (6, 9):
        vf = VectorFitting(ntw)
        t0 = tic()
        vf.vector_fit(n_poles_real=2, n_poles_cmplx=nc)
        s = tic() - t0
        print(f"  {nc} complex + 2 real poles: fit {s*1e3:6.0f} ms, rms error {vf.get_rms_error():.2e},"
              f" passive={vf.is_passive()}")
    print("  (on the undamped bare cavity, S11 ~ 1 everywhere: 10-30 poles took 6-76 s, rms 1-2e-2,"
          " non-passive, and passivity_enforce() failed at default settings)")


SECTIONS = {"zo": sec_zo, "via": sec_via, "cav": sec_cav, "ir": sec_ir, "fdtd": sec_fdtd, "vf": sec_vf}

if __name__ == "__main__":
    which = sys.argv[1:] or ["all"]
    for k, fn in SECTIONS.items():
        if "all" in which or k in which:
            fn()
            print()
