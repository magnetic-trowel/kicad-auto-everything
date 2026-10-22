# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The R-L crossover as a relaxation spectrum, not one frequency (round-2 lens VP).

Between DC (current minimises dissipation, Thomson) and HF (current minimises magnetic
energy, Maxwell) the return current is the stationary point of R[I] + j*w*L[I]. Its
transition is governed by the generalised eigenvalues of the pair (R, L) restricted to
zero-net-current eddy patterns: each eddy mode k relaxes at rate lambda_k = R_k/L_k and
moves inductance c_k^2 from the DC value toward the HF value around f_k = lambda_k/2pi.
For a thin sheet, Maxwell's receding-image theory gives lambda(k) = 2 R_s |k| / mu0 for a
pattern of wavenumber k, so a return confined within +-l needs f >~ R_s / (pi mu0 l).
Round 1 used one boundary f_x = R_s/(2 pi mu0 h); this script tests whether the relevant
scale is h or the distance l that matters to a victim.

Model: 2-D (per unit length) quasi-static PEEC cross-section, as in vo_return_spread.py:
one trace (w x t) at height h above a plane of width W (1 oz, thin-sheet strips), log
kernel, GMD self terms, conductor groups with common voltage and prescribed net current.

Sections (python vp_rl_band.py [spectrum|contain|damper|all]):
  spectrum  eddy-mode relaxation spectrum (generalised eigenproblem of R and L on the
            zero-net-current subspace of the plane) and the share of the DC->HF
            inductance drop carried by each mode; band edges f10/f50/f90 vs
            f_x = R_s/(2 pi mu0 h) and R_s/(pi mu0 l) for l = h, W/2; Foster-form check
            against the direct solve.
  contain   frequency f50(l) at which half the return current lies within +-l of the
            trace, for several h and l: is f50 * l constant (independent of h)?
  damper    a resistive film between a trace and its solid return plane: film loss
            peaks where the film's eddy mode relaxes at the ring frequency; Q of the
            loop vs film sheet resistance at 200 MHz, and the bound Q >= 2/k^2 - 1.

Deterministic, numpy/scipy only, about 1-2 minutes in total.
"""
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402
import scipy.linalg as sla  # noqa: E402

MU0 = 4e-7 * math.pi
RHO = 1.72e-8
T_CU = 35e-6
RS = RHO / T_CU


def plane_edges(width, h, n_fine=160, n_coarse=140, fine_half=8.0):
    fine = np.linspace(-fine_half * h, fine_half * h, n_fine + 1)
    half = width / 2
    outer = np.geomspace(fine_half * h, half, n_coarse // 2 + 1)
    return np.concatenate([-outer[::-1], fine[1:-1], outer])


def _f1(u):
    """F with F'' = ln|u| (F(0) = 0): F(u) = u^2/2 ln|u| - 3u^2/4."""
    au = np.abs(u)
    return np.where(au > 0, 0.5 * u * u * np.log(np.where(au > 0, au, 1.0)) - 0.75 * u * u, 0.0)


def mean_log_same_plane(x, a):
    """Exact mean of ln|s - t| over two coplanar zero-thickness strips (Galerkin, PD kernel)."""
    dd = x[None, :] - x[:, None]
    s = (a[:, None] + a[None, :]) / 2
    df = (a[:, None] - a[None, :]) / 2
    return (_f1(dd + s) + _f1(dd - s) - _f1(dd + df) - _f1(dd - df)) / (a[:, None] * a[None, :])


def mean_log_cross(xi, ai, xj, aj, dz, nq=8):
    """Mean of ln sqrt((s - t)^2 + dz^2) over strips in parallel planes (Gauss-Legendre)."""
    g, wq = np.polynomial.legendre.leggauss(nq)
    si = xi[:, None] + 0.5 * ai[:, None] * g[None, :]          # (ni, nq)
    tj = xj[:, None] + 0.5 * aj[:, None] * g[None, :]          # (nj, nq)
    du = si[:, None, :, None] - tj[None, :, None, :]           # (ni, nj, nq, nq)
    val = 0.5 * np.log(du * du + dz * dz)
    return np.einsum("ijab,a,b->ij", val, wq, wq) / 4.0


def build(h, w, width, n_tr=8, film=None):
    """Zero-thickness sheet strips. Groups: 0 trace (z = h), 1 plane (z = 0), 2 film.
    Returns strip centres, group ids, resistance per metre and the 2-D partial-inductance
    matrix (H/m, up to a constant that cancels for zero total current)."""
    xs, as_, zs, rs, gs = [], [], [], [], []
    xe = np.linspace(-w / 2, w / 2, n_tr + 1)
    xs.append((xe[1:] + xe[:-1]) / 2)
    as_.append(np.diff(xe))
    zs.append(h)
    rs.append(RS / np.diff(xe))
    gs.append(0)
    e = plane_edges(width, h)
    xs.append((e[1:] + e[:-1]) / 2)
    as_.append(np.diff(e))
    zs.append(0.0)
    rs.append(RS / np.diff(e))
    gs.append(1)
    if film is not None:
        zf, rs_f, wf = film                       # height of the film, sheet R, film width
        ef = plane_edges(wf, h, n_fine=100, n_coarse=40, fine_half=min(8.0, 0.999 * wf / 2 / h))
        xs.append((ef[1:] + ef[:-1]) / 2)
        as_.append(np.diff(ef))
        zs.append(zf)
        rs.append(rs_f / np.diff(ef))
        gs.append(2)
    n = sum(len(v) for v in xs)
    lm = np.zeros((n, n))
    off = np.cumsum([0] + [len(v) for v in xs])
    for i in range(len(xs)):
        for j in range(len(xs)):
            si, sj = slice(off[i], off[i + 1]), slice(off[j], off[j + 1])
            if i == j:
                ml = mean_log_same_plane(xs[i], as_[i])
            elif j < i:
                continue
            else:
                ml = mean_log_cross(xs[i], as_[i], xs[j], as_[j], abs(zs[i] - zs[j]))
            lm[si, sj] = -(MU0 / (2 * math.pi)) * ml
            if i != j:
                lm[sj, si] = lm[si, sj].T
    x = np.concatenate(xs)
    grp = np.concatenate([np.full(len(v), g) for v, g in zip(xs, gs)])
    r = np.concatenate(rs)
    return x, grp, r, lm


def solve(f, x, grp, r, lmat, net):
    """Direct solve; net = {group: net current}. Returns filament currents and group voltages."""
    n = len(r)
    groups = sorted(net)
    m = len(groups)
    z = np.diag(r).astype(complex) + 1j * 2 * math.pi * f * lmat
    a = np.zeros((n + m, n + m), complex)
    rhs = np.zeros(n + m, complex)
    a[:n, :n] = z
    for j, g in enumerate(groups):
        a[:n, n + j] = -(grp == g).astype(float)
        a[n + j, :n] = (grp == g).astype(float)
        rhs[n + j] = net[g]
    sol = np.linalg.solve(a, rhs)
    return sol[:n], dict(zip(groups, sol[n:]))


def loop_z(f, x, grp, r, lmat, net):
    cur, v = solve(f, x, grp, r, lmat, net)
    return v[0] - v[1], cur


def eddy_spectrum(x, grp, r, lmat):
    """Modes of the plane on its zero-net-current subspace, driven by the trace with its DC
    (uniform) current shape and the plane's DC distribution. Returns rates, weights c_k^2."""
    tp, pp = np.flatnonzero(grp == 0), np.flatnonzero(grp == 1)
    s = (1 / r[tp]) / np.sum(1 / r[tp])                     # DC split across the trace
    idc = -(1 / r[pp]) / np.sum(1 / r[pp])                  # DC split across the plane
    q = sla.null_space(np.ones((1, len(pp))))
    lt = q.T @ lmat[np.ix_(pp, pp)] @ q
    rt = q.T @ np.diag(r[pp]) @ q
    lam, v = sla.eigh(rt, lt)                               # v' lt v = I
    gvec = q.T @ (lmat[np.ix_(pp, pp)] @ idc + lmat[np.ix_(pp, tp)] @ s)
    c = v.T @ gvec
    zdc = lambda f: (s @ (np.diag(r[tp]) + 1j * 2 * math.pi * f * lmat[np.ix_(tp, tp)]) @ s  # noqa: E731
                     + idc @ (np.diag(r[pp]) + 1j * 2 * math.pi * f * lmat[np.ix_(pp, pp)]) @ idc
                     + 2 * 1j * 2 * math.pi * f * (s @ lmat[np.ix_(tp, pp)] @ idc) * 1.0)
    return lam, c ** 2, zdc


def band_edges(lam, wgt, levels=(0.1, 0.5, 0.9)):
    o = np.argsort(lam)
    cw = np.cumsum(wgt[o]) / wgt.sum()
    fk = lam[o] / (2 * math.pi)
    return [fk[np.searchsorted(cw, lv)] for lv in levels]


def sec_spectrum():
    print("== spectrum: eddy relaxation spectrum of the return plane (1 oz, R_s = %.3f mOhm)" % (RS * 1e3))
    print("   h mm  w mm  W mm | f10      f50      f90      | f_x=Rs/(2pi mu0 h) | Rs/(pi mu0 W/2) | Rs/(pi mu0 h) "
          "| L_DC  L_HF nH/mm")
    for h, w, width in ((0.1e-3, 0.3e-3, 50e-3), (0.2e-3, 0.3e-3, 50e-3), (1.6e-3, 0.3e-3, 50e-3),
                        (0.1e-3, 2e-3, 50e-3), (0.1e-3, 0.3e-3, 100e-3), (0.2e-3, 0.3e-3, 20e-3)):
        x, grp, r, lm = build(h, w, width, n_tr=1 if w < 1e-3 else 8)
        lam, wgt, zdc = eddy_spectrum(x, grp, r, lm)
        f10, f50, f90 = band_edges(lam, wgt)
        ldc = (zdc(1.0).imag / (2 * math.pi)) * 1e6
        lhf = ldc - wgt.sum() * 1e6
        print(f"   {h * 1e3:4.1f}  {w * 1e3:4.1f}  {width * 1e3:4.0f} | {f10:8.3g} {f50:8.3g} {f90:8.3g} |"
              f" {RS / (2 * math.pi * MU0 * h):10.3g}         | {RS / (math.pi * MU0 * width / 2):10.3g}      |"
              f" {RS / (math.pi * MU0 * h):10.3g}    | {ldc:5.3f} {lhf:5.3f}")
    # Foster-form check against the direct solve (trace as one filament so its shape is fixed)
    x, grp, r, lm = build(0.2e-3, 0.3e-3, 50e-3, n_tr=1)
    lam, wgt, zdc = eddy_spectrum(x, grp, r, lm)
    print("   Foster check (h 0.2, w 0.3, W 50 mm): f, L direct vs modal sum (nH/mm), R direct vs modal (mOhm/mm)")
    for f in (1e3, 1e4, 1e5, 1e6, 1e7):
        w_ = 2 * math.pi * f
        zf = zdc(f) + np.sum(w_ ** 2 * wgt / (lam + 1j * w_))
        zd, _ = loop_z(f, x, grp, r, lm, {0: 1.0, 1: -1.0})
        print(f"     {f:8.0e} Hz: L {zd.imag / w_ * 1e6:.4f} vs {zf.imag / w_ * 1e6:.4f};"
              f"  R {zd.real * 1e3 * 1e-3:.4f} vs {zf.real * 1e3 * 1e-3:.4f}")


def contained(cur, x, grp, ell):
    pp = grp == 1
    return abs(np.sum(cur[pp & (np.abs(x) <= ell)]))


def f50(h, ell, w=0.3e-3, width=100e-3, level=0.5):
    x, grp, r, lm = build(h, w, width, n_tr=1)
    fs = np.logspace(1, 8, 36)
    fr = []
    for f in fs:
        _, cur = loop_z(f, x, grp, r, lm, {0: 1.0, 1: -1.0})
        fr.append(contained(cur, x, grp, ell))
    fr = np.array(fr)
    i = int(np.argmax(fr >= level))
    if fr[i] < level or i == 0:
        return float("nan"), fr
    a, b = math.log10(fs[i - 1]), math.log10(fs[i])
    return 10 ** (a + (level - fr[i - 1]) * (b - a) / (fr[i] - fr[i - 1])), fr


def sec_contain():
    print("== contain: f50(l) = frequency at which 50% of the return lies within +-l (trace 0.3 mm, plane 100 mm)")
    print("   receding-image scale: l_c(f) = R_s / (pi mu0 f);  f50 * l is constant if the law holds")
    print("   h mm |  l mm  |  f50 Hz    | f50 * l (Hz m) | f50 / f_x | f50 / [R_s/(pi mu0 l)]")
    for h in (0.1e-3, 0.2e-3, 0.5e-3, 1.6e-3):
        fx = RS / (2 * math.pi * MU0 * h)
        for ell in (3 * h, 1e-3, 3e-3, 10e-3):
            if ell < 2.5 * h and ell != 3 * h:
                continue
            fv, _ = f50(h, ell)
            print(f"   {h * 1e3:4.1f} | {ell * 1e3:6.2f} | {fv:10.4g} | {fv * ell:10.4g}     | {fv / fx:7.3f}   |"
                  f" {fv / (RS / (math.pi * MU0 * ell)):6.3f}", flush=True)


def sec_damper():
    print("== damper: resistive film halfway between a 1.5 mm trace and its solid plane (h = 0.2 mm), f = 200 MHz")
    h, w, width, f = 0.2e-3, 1.5e-3, 20e-3, 200e6
    wr = 2 * math.pi * f
    x, grp, r, lm = build(h, w, width, n_tr=10)
    z0, _ = loop_z(f, x, grp, r, lm, {0: 1.0, 1: -1.0})
    # reference: solid copper plane at 0.1 mm (the film position) instead of 0.2 mm
    x1, g1, r1, l1 = build(0.1e-3, w, width, n_tr=10)
    z1, _ = loop_z(f, x1, g1, r1, l1, {0: 1.0, 1: -1.0})
    print(f"   no film: L' {z0.imag / wr * 1e6:.4f} nH/mm (plane at 0.2 mm); copper plane at 0.1 mm instead: "
          f"{z1.imag / wr * 1e6:.4f} nH/mm")
    k2 = 1 - (z1.imag / wr) / (z0.imag / wr)
    print(f"   coupling of the film mode k^2 ~ 1 - L(0.1)/L(0.2) = {k2:.3f}; bound Q_film >= 2/k^2 - 1 = {2 / k2 - 1:.2f}")
    print("   film R_s (ohm/sq) | L' nH/mm | R'_film mOhm/mm | Q_film = wL/R_film")
    best = (1e9, None)
    for rs_f in (0.01, 0.03, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0, 20.0, 100.0):
        xf, gf, rf, lf = build(h, w, width, n_tr=10, film=(h / 2, rs_f, 3 * w))
        zz, _ = loop_z(f, xf, gf, rf, lf, {0: 1.0, 1: -1.0, 2: 0.0})
        dr = zz.real - z0.real
        q = zz.imag / dr if dr > 0 else float("inf")
        best = min(best, (q, rs_f))
        print(f"   {rs_f:8.2f}          | {zz.imag / wr * 1e6:.4f}   | {dr * 1e3 * 1e-3:10.4f}      | {q:7.2f}")
    print(f"   best Q_film {best[0]:.2f} at R_s = {best[1]} ohm/sq (film width 3w; copper's own Q is 30-170, round 1)")


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("spectrum", "all"):
        sec_spectrum()
    if which in ("contain", "all"):
        sec_contain()
    if which in ("damper", "all"):
        sec_damper()


if __name__ == "__main__":
    main()
