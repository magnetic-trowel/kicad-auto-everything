# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pricing a copper edit from one solve: energy density vs polarization tensor (lens VP).

Round 1 (sl_tier_costs.py `ir`) priced copper removals with the self-adjoint first-order
estimate "removing a cell costs about twice the power its edges carried" and found it
good for compact holes but 30x low for a 6 mm slot (0.27 mW vs 8.1 mW).

Variational reading: the first-order change of the minimum dissipation when a small
insulating inclusion B is cut into a sheet carrying local current density K is
    dP = R_s * K' M(B) K,
where M is the inclusion's 2-D polarization tensor. For a disc M = 2*area*I, which is
exactly round 1's factor 2. For an ellipse with semi-axis b across the current and a
along it, M = pi*b*(a+b): a slit of length l across the flow has M = pi*l^2/4 (Griffith's
energy release; the stream-function law dP = (pi/4) R_s dpsi^2 of XD2), and a slit along
the flow has M -> 0. A slit from an insulating edge is half of a slit of twice the length
(mirror image), i.e. twice an interior slit of the same length. So the area estimate is
wrong for slits by about (a+b)/(2a) ~ l/(2w) (interior) or l/w (edge): 30 for 6/0.2 mm.

This script re-uses round 1's 40 x 30 mm, 1 oz pour (16 x 0.5 A sinks, via-antipad rows,
a cut-out) and compares, for each edit, the exact re-solve with
  (a) round 1's area estimate (2 x energy of the removed cells), and
  (b) the polarization estimate R_s * (M_nn <K_n>^2 + M_tt <K_t>^2), with <K_n> taken as
      the current crossing the slit's centreline divided by its length (dpsi / l).

Run: python vp_edit_pricing.py [--d 0.1]   (about 1-2 minutes; numpy/scipy only)
"""
import argparse
import math
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sl_tier_costs as st  # noqa: E402

RS = 1.72e-8 / 35e-6


def setup(d):
    nx, ny = int(round(0.04 / d)), int(round(0.03 / d))
    mask = st.pour_mask(nx, ny, d)
    sinks = [((int(cy / d), int(cx / d)), 0.5) for cx in (0.030, 0.032, 0.034, 0.036)
             for cy in (0.011, 0.013, 0.015, 0.017)]
    return mask, sinks


def solve(mask, d, sinks):
    a, b, idx = st.build_ir(mask, d, RS, sinks)
    v = spla.splu(a).solve(b)
    vv = np.full(mask.shape, np.nan)
    vv[mask] = v[idx[mask]]
    return b @ v, vv


def cell_energy(vv):
    """Round 1's per-cell power share (half of each adjacent edge's g*dV^2)."""
    g = 1 / RS
    px = g * np.nan_to_num(np.diff(vv, axis=1)) ** 2
    py = g * np.nan_to_num(np.diff(vv, axis=0)) ** 2
    e = np.zeros(vv.shape)
    e[:, :-1] += px / 2
    e[:, 1:] += px / 2
    e[:-1, :] += py / 2
    e[1:, :] += py / 2
    return e


def face_currents(vv):
    """Currents through cell faces (A): ix[j, i] from cell (j,i) to (j,i+1); iy[j, i] to (j+1,i)."""
    g = 1 / RS
    ix = -g * np.nan_to_num(np.diff(vv, axis=1))
    iy = -g * np.nan_to_num(np.diff(vv, axis=0))
    return ix, iy


def price(name, rect, kind, base, mask, d, sinks):
    """rect = (y0, y1, x0, x1) in m (cells removed); kind: 'edge-y' slit from y=0, 'slit', 'hole'."""
    p0, vv, e, ix, iy = base
    y0, y1, x0, x1 = rect
    j0, j1, i0, i1 = (int(round(y0 / d)), int(round(y1 / d)), int(round(x0 / d)), int(round(x1 / d)))
    m2 = mask.copy()
    m2[j0:j1, i0:i1] = False
    p2, _ = solve(m2, d, sinks)
    exact = p2 - p0
    area_est = 2 * e[j0:j1, i0:i1][mask[j0:j1, i0:i1]].sum()
    ly, lx = (j1 - j0) * d, (i1 - i0) * d
    jm, im = (j0 + j1) // 2, (i0 + i1) // 2
    if kind == "hole":
        # disc of equal area: M = 2 * area; K from the mean energy density of the cells
        kk = e[j0:j1, i0:i1][mask[j0:j1, i0:i1]].mean() / (d * d) / RS
        pol = RS * 2 * lx * ly * kk
    else:
        if ly >= lx:     # slit along y: normal current = x-component crossing the centre column
            dpsi = abs(ix[j0:j1, im - 1 if im > 0 else im][mask[j0:j1, im]].sum())
            dtan = abs(iy[jm - 1, i0:i1].sum()) if jm > 0 else 0.0
            ln, wd = ly, lx
        else:            # slit along x
            dpsi = abs(iy[jm - 1, i0:i1][mask[jm, i0:i1]].sum())
            dtan = abs(ix[j0:j1, im - 1].sum())
            ln, wd = lx, ly
        kn, kt = dpsi / ln, dtan / wd
        b, a = ln / 2, wd / 2
        mnn, mtt = math.pi * b * (a + b), math.pi * a * (a + b)
        if kind == "edge-y":    # mirror image: half of an interior slit of twice the length
            b2 = ln
            mnn, mtt = 0.5 * math.pi * b2 * (a + b2), 0.5 * math.pi * a * (a + b2)
        pol = RS * (mnn * kn * kn + mtt * kt * kt)
    print(f"  {name:34s} exact {exact * 1e3:8.3f} mW | area est {area_est * 1e3:8.3f} ({area_est / exact:5.3f}x)"
          f" | polarization {pol * 1e3:8.3f} ({pol / exact:5.3f}x)", flush=True)
    return exact, area_est, pol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--d", type=float, default=0.1, help="cell size, mm")
    d = ap.parse_args().d * 1e-3
    mask, sinks = setup(d)
    p0, vv = solve(mask, d, sinks)
    e = cell_energy(vv)
    ix, iy = face_currents(vv)
    base = (p0, vv, e, ix, iy)
    print(f"== edit pricing on round 1's 40x30 mm pour (cell {d * 1e3:.2f} mm): total loss {p0 * 1e3:.1f} mW")
    print("   estimate / exact: 1.0 is perfect")
    edits = [("round-1 0.5 mm hole", (0.0145, 0.015, 0.026, 0.0265), "hole"),
             ("round-1 2x2 mm cut-out", (0.013, 0.015, 0.026, 0.028), "hole"),
             ("round-1 6 mm edge slit, w 0.2", (0.0, 0.006, 0.018, 0.018 + 2 * d), "edge-y")]
    for ell in (0.001, 0.002, 0.004, 0.006, 0.008):
        for wcells in (2, 4):
            edits.append((f"edge slit l {ell * 1e3:.0f} mm, w {wcells * d * 1e3:.1f}",
                          (0.0, ell, 0.012, 0.012 + wcells * d), "edge-y"))
    edits += [("interior slit across flow 2 mm", (0.0010, 0.0030, 0.010, 0.010 + 2 * d), "slit"),
              ("interior slit across flow 3 mm", (0.0045, 0.0075, 0.010, 0.010 + 2 * d), "slit"),
              ("interior slit along flow 4 mm", (0.0060, 0.0060 + 2 * d, 0.008, 0.012), "slit")]
    for name, rect, kind in edits:
        price(name, rect, kind, base, mask, d, sinks)


if __name__ == "__main__":
    main()
