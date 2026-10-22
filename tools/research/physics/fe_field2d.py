# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""2-D electrostatic finite-difference field solver for PCB cross-sections.

Used by docs/topics/physics/fields-si-emi.md and rf-geometry.md ([C] numbers).
Solves div(eps grad phi) = 0 on a uniform grid; conductors are fixed-potential
rectangles; ground plane(s) are Dirichlet boundaries. Capacitance matrices come
from the discrete Gauss law; inductance from the air-filled solve, L = mu0 eps0 C0^-1.

Prints:
  1. single microstrip Z0 vs the Hammerstad-Jensen closed form (validation);
  2. coupled microstrip and stripline: K_L, K_C, saturated NEXT = (K_L+K_C)/4,
     FEXT coefficient (K_L-K_C)/2 (multiply by coupled delay / t_r), vs
     Johnson's bound 1/(1+(D/h)^2): shows microstrip decays ~ 1/D^2 and
     stripline ~ exp(-pi D / b), and stripline FEXT = 0;
  3. coplanar ground pour next to a 50-ohm microstrip: Z0 vs gap (when does
     "ground fill" or CPWG change the impedance);
  4. edge-coupled 100-ohm pairs: trace width needed vs spacing (tight vs loose
     coupling) and the resulting conductor-loss ratio;
  5. an 0402-size pad (0.5 mm wide) on a 50-ohm line: impedance over the
     adjacent plane vs over a voided adjacent plane (reference one layer deeper).
Run:  python tools/research/physics/fe_field2d.py     (about 1-3 min)
"""
import math

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

EPS0 = 8.854e-12
MU0 = 4e-7 * math.pi
C0 = 2.998e8


def solve_caps(X, Y, dx, layers, conductors, top_plane=None, gnd_rects=()):
    """Return Maxwell C matrix (F/m) for conductors over a ground plane at y=0.

    layers: list of (y0, y1, er); conductors: list of (x0, x1, y0, y1);
    top_plane: y of a second ground plane (stripline) or None (open top, far box);
    gnd_rects: extra grounded rectangles (coplanar pours, reference islands)."""
    nx, ny = int(round(2 * X / dx)) + 1, int(round(Y / dx)) + 1
    xs = -X + dx * np.arange(nx)
    ys = dx * np.arange(ny)
    # permittivity per cell (cell (i,j) spans x[i]..x[i+1], y[j]..y[j+1])
    xc = 0.5 * (xs[:-1] + xs[1:])
    yc = 0.5 * (ys[:-1] + ys[1:])
    er = np.ones((nx - 1, ny - 1))
    for y0, y1, e in layers:
        er[:, (yc >= y0) & (yc < y1)] = e
    fixed = np.zeros((nx, ny), dtype=bool)
    val = np.zeros((nx, ny))
    fixed[0, :] = fixed[-1, :] = True
    fixed[:, 0] = True
    fixed[:, -1] = True
    if top_plane is not None:
        fixed[:, ys >= top_plane - 1e-12] = True
    X2, Y2 = np.meshgrid(xs, ys, indexing="ij")
    for (x0, x1, y0, y1) in gnd_rects:
        fixed |= (X2 >= x0 - 1e-12) & (X2 <= x1 + 1e-12) & (Y2 >= y0 - 1e-12) & (Y2 <= y1 + 1e-12)
    cmask = []
    for (x0, x1, y0, y1) in conductors:
        m = (X2 >= x0 - 1e-12) & (X2 <= x1 + 1e-12) & (Y2 >= y0 - 1e-12) & (Y2 <= y1 + 1e-12)
        cmask.append(m)
        fixed |= m
    # edge permittivities
    ex = np.zeros((nx - 1, ny))  # edge between (i,j) and (i+1,j)
    ex[:, 1:-1] = 0.5 * (er[:, :-1] + er[:, 1:])
    ex[:, 0], ex[:, -1] = er[:, 0], er[:, -1]
    ey = np.zeros((nx, ny - 1))
    ey[1:-1, :] = 0.5 * (er[:-1, :] + er[1:, :])
    ey[0, :], ey[-1, :] = er[0, :], er[-1, :]
    idx = -np.ones((nx, ny), dtype=int)
    free = ~fixed
    idx[free] = np.arange(free.sum())
    n = free.sum()
    rows, cols, vals = [], [], []
    diag = np.zeros((nx, ny))
    diag[:-1, :] += ex; diag[1:, :] += ex
    diag[:, :-1] += ey; diag[:, 1:] += ey
    fi = np.nonzero(free)
    rows.append(idx[fi]); cols.append(idx[fi]); vals.append(diag[fi])
    nbrs = []
    for (di, dj, e_arr, sl_self, sl_nb) in (
            (1, 0, ex, (slice(0, -1), slice(None)), (slice(1, None), slice(None))),
            (-1, 0, ex, (slice(1, None), slice(None)), (slice(0, -1), slice(None))),
            (0, 1, ey, (slice(None), slice(0, -1)), (slice(None), slice(1, None))),
            (0, -1, ey, (slice(None), slice(1, None)), (slice(None), slice(0, -1)))):
        a_idx, b_idx = idx[sl_self], idx[sl_nb]
        e = e_arr
        m = (a_idx >= 0) & (b_idx >= 0)
        rows.append(a_idx[m]); cols.append(b_idx[m]); vals.append(-e[m])
        nbrs.append((sl_self, sl_nb, e))
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    solver = spla.factorized(A.tocsc())
    nc = len(conductors)
    Cm = np.zeros((nc, nc))
    for i in range(nc):
        val[:] = 0.0
        val[cmask[i]] = 1.0
        rhs = np.zeros((nx, ny))
        for sl_self, sl_nb, e in nbrs:
            contrib = np.zeros((nx, ny))
            contrib[sl_self] = e * val[sl_nb]
            rhs += contrib * free
        phi = val.copy()
        phi[free] = solver(rhs[free])
        # charge on each conductor: sum over its nodes of eps*(phi_n - phi_m)
        for j in range(nc):
            q = 0.0
            for sl_self, sl_nb, e in nbrs:
                d = np.zeros((nx, ny))
                d[sl_self] = e * (phi[sl_self] - phi[sl_nb])
                q += d[cmask[j]].sum()
            Cm[i, j] = EPS0 * q
    return Cm


def line_params(Cd, Ca):
    L = MU0 * EPS0 * np.linalg.inv(Ca)
    return L, Cd


def hj_microstrip(w, h, er):
    u = w / h
    a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
    bb = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    ee = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * bb)
    f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
    z = 60 / math.sqrt(ee) * math.log(f / u + math.sqrt(1 + (2 / u) ** 2))
    return z, ee


def main():
    er, h, t = 4.3, 0.1e-3, 0.035e-3
    dx = 0.0125e-3
    X, Y = 2.0e-3, 2.0e-3
    lay = [(0, h, er)]
    # 1. validation
    w = 0.19e-3
    cond = [(-w / 2, w / 2, h, h + t)]
    Cd = solve_caps(X, Y, dx, lay, cond)
    Ca = solve_caps(X, Y, dx, [], cond)
    z0 = math.sqrt((MU0 * EPS0 / Ca[0, 0]) / Cd[0, 0])
    eeff = Cd[0, 0] / Ca[0, 0]
    zhj, ehj = hj_microstrip(w + 0.5 * t, h, er)  # rough thickness correction
    print(f"1. microstrip w={w*1e3:.3f} h={h*1e3:.2f} t={t*1e3:.3f} mm er={er}: FD Z0={z0:.1f} ohm eeff={eeff:.2f};"
          f" Hammerstad-Jensen (w+t/2) Z0={zhj:.1f} eeff={ehj:.2f}")
    print(f"   C'={Cd[0,0]*1e12/1e3:.4f} pF/mm  L'={MU0*EPS0/Ca[0,0]*1e9/1e3:.4f} nH/mm")

    # 2. coupled lines
    print("\n2. Coupled 50-ohm lines, D = centre-to-centre; Johnson bound 1/(1+(D/h)^2) (h = nearest plane)")
    print("   type        D/h   K_L     K_C     NEXTsat  FEXTcoef(K_L-K_C)/2  Johnson")
    for kind in ("microstrip", "stripline"):
        if kind == "microstrip":
            wl, layers, top, hh = w, lay, None, h
        else:
            # symmetric stripline, planes at 0 and b = 2h + t, Z0 ~ 50 ohm needs narrower trace
            b = 2 * h + t
            wl, layers, top, hh = 0.06e-3, [(0, b, er)], b, h
        for Dh in (2, 3, 4, 6, 10):
            D = Dh * hh
            cond = [(-D / 2 - wl / 2, -D / 2 + wl / 2, hh, hh + t), (D / 2 - wl / 2, D / 2 + wl / 2, hh, hh + t)]
            Cd = solve_caps(X, Y, dx, layers, cond, top_plane=top)
            Ca = solve_caps(X, Y, dx, [], cond, top_plane=top)
            L = MU0 * EPS0 * np.linalg.inv(Ca)
            KL = L[0, 1] / L[0, 0]
            KC = -Cd[0, 1] / Cd[0, 0]
            print(f"   {kind:10s}  {Dh:4.1f}  {KL:.4f}  {KC:.4f}  {(KL+KC)/4:.4f}   {(KL-KC)/2:+.4f}"
                  f"               {1/(1+Dh**2):.4f}")
        if kind == "stripline":
            z0s = math.sqrt(L[0, 0] / Cd[0, 0])
            print(f"   (stripline w={wl*1e3:.3f} mm in b={b*1e3:.3f} mm: Z0 ~ {z0s:.1f} ohm)")

    # 3. coplanar ground pour next to a microstrip
    print("\n3. Coplanar ground pour (same layer, both sides) next to the 50-ohm microstrip: Z0 vs gap g")
    for gh in (0.5, 1.0, 2.0, 3.0, 5.0, None):
        if gh is None:
            gr = ()
        else:
            g = gh * h
            gr = ((-X, -w / 2 - g, h, h + t), (w / 2 + g, X, h, h + t))
        cond = [(-w / 2, w / 2, h, h + t)]
        Cd = solve_caps(X, Y, dx, lay, cond, gnd_rects=gr)
        Ca = solve_caps(X, Y, dx, [], cond, gnd_rects=gr)
        zz = math.sqrt((MU0 * EPS0 / Ca[0, 0]) / Cd[0, 0])
        print(f"   gap = {('inf' if gh is None else f'{gh:.1f} h'):>6s}: Z0 = {zz:5.1f} ohm")

    # 4. 100-ohm differential pairs, tight vs loose
    print("\n4. Edge-coupled microstrip pair, Zdiff = 100 ohm: width needed vs gap s")
    for sg in (0.1e-3, 0.2e-3, 0.4e-3, 0.8e-3):
        lo, hi = 0.05e-3, 0.4e-3
        for _ in range(9):
            wm = 0.5 * (lo + hi)
            cond = [(-sg / 2 - wm, -sg / 2, h, h + t), (sg / 2, sg / 2 + wm, h, h + t)]
            Cd = solve_caps(X, Y, dx, lay, cond)
            Ca = solve_caps(X, Y, dx, [], cond)
            L = MU0 * EPS0 * np.linalg.inv(Ca)
            Lo, Co = L[0, 0] - L[0, 1], Cd[0, 0] - Cd[0, 1]
            zd = 2 * math.sqrt(Lo / Co)
            if zd > 100:
                lo = wm
            else:
                hi = wm
        Le, Ce = L[0, 0] + L[0, 1], Cd[0, 0] + Cd[0, 1]
        print(f"   gap s = {sg*1e3:.2f} mm ({sg/h:.0f} h): w = {wm*1e3:.3f} mm, Zdiff = {zd:.1f}, "
              f"Zcomm = {0.5*math.sqrt(Le/Ce):.1f} ohm, K_L = {L[0,1]/L[0,0]:.3f}; "
              f"conductor loss ~ 1/(w+t): {1/(wm+t)*1e-3:.2f} /mm")

    # 5. pad discontinuity and voided reference
    print("\n5. 0.5 mm wide pad (0402-size) on a 50-ohm line, h = 0.1 mm to L2, L3 0.235 mm below L2:")
    h3 = h + t + 0.2e-3   # pad height above L3 when L2 is voided under it
    l2y0, l2y1 = h3 - h - t, h3 - h
    cases = (("over L2 (no void)", h, ()),
             ("L2 voided 60% of pad width (|x|<0.15 mm)", h3,
              ((-X, -0.15e-3, l2y0, l2y1), (0.15e-3, X, l2y0, l2y1))),
             ("L2 voided full pad width (|x|<0.25 mm)", h3,
              ((-X, -0.25e-3, l2y0, l2y1), (0.25e-3, X, l2y0, l2y1))),
             ("L2 voided pad width + 0.1 mm (|x|<0.35 mm)", h3,
              ((-X, -0.35e-3, l2y0, l2y1), (0.35e-3, X, l2y0, l2y1))),
             ("L2 removed entirely, reference L3", h3, ()))
    for label, hh, gr in cases:
        layers = [(0, hh, er)]
        cond = [(-0.25e-3, 0.25e-3, hh, hh + t)]
        Cd = solve_caps(X, Y, dx, layers, cond, gnd_rects=gr)
        Ca = solve_caps(X, Y, dx, [], cond, gnd_rects=gr)
        zz = math.sqrt((MU0 * EPS0 / Ca[0, 0]) / Cd[0, 0])
        print(f"   {label:44s}: Z_pad = {zz:5.1f} ohm, C' = {Cd[0,0]*1e9:.3f} pF/mm")


if __name__ == "__main__":
    main()
