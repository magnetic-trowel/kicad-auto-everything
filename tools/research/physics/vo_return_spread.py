# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where does the return current flow in a plane under a trace, versus frequency?

Used by docs/topics/physics/vocabulary.md ("Regime") as a [C] check that the
rule "return current flows directly under the trace" is a frequency regime,
with a geometry-dependent boundary, not a law.

Model (2D, per unit length, quasi-static PEEC):
* one trace (w x t) at height h above a plane of width W and thickness t;
* the plane is cut into N strips (fine near the trace, coarse far away);
* each conductor k has resistance R_k = rho / (width_k * t) per metre;
* 2D partial inductance per metre between filaments i, j:
  L_ij = -(mu0 / 2 pi) ln(d_ij), self term with the rectangle GMD
  0.2235 (a + b) (Grover). The ln constant cancels because sum(I) = 0;
* plane strips are in parallel (same voltage drop per metre); the trace
  carries +1 A and the plane carries -1 A in total.
Skin effect inside the 35 um copper is ignored (fine below ~3 MHz; above that
the lateral distribution is already at its high-frequency limit).

Output: fraction of the return current within +-3h of the trace centre, and
the frequencies at which 50 % and 70 % of the return lies within +-3h. The
high-frequency limit is checked against the closed form (2/pi) atan(3) = 0.795
(Adamczyk's "80 % within +-3h" for microstrip).

A closed-form estimate of the boundary is also printed: the plane's sheet
resistance equals the reactance of a strip of plane one h wide,
f_x ~ R_sheet / (2 pi mu0 h). It tracks the 50-70 % points of the full model.

Run:  python vo_return_spread.py      (numpy only, deterministic, ~1 min)
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numpy as np  # noqa: E402

MU0 = 4e-7 * np.pi
RHO_CU = 1.72e-8  # ohm m at 20 C


def strips(width, h, n_fine=200, n_coarse=120):
    """Plane strip edges: uniform +-8h fine region, geometric growth outside."""
    fine = np.linspace(-8 * h, 8 * h, n_fine + 1)
    half = width / 2
    outer = np.geomspace(8 * h, half, n_coarse // 2 + 1)
    edges = np.concatenate([-outer[::-1], fine[1:-1], outer])
    return edges


def solve(f, h=0.2e-3, w=0.3e-3, t=35e-6, width=50e-3):
    edges = strips(width, h)
    xc = 0.5 * (edges[:-1] + edges[1:])
    dx = np.diff(edges)
    n = len(xc)
    # conductor list: index 0 = trace, 1..n = plane strips
    x = np.concatenate([[0.0], xc])
    y = np.concatenate([[h + t], np.zeros(n)])
    a = np.concatenate([[w], dx])
    r = RHO_CU / (a * t)
    d = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    gmd = 0.2235 * (a + t)
    np.fill_diagonal(d, gmd)
    lmat = -(MU0 / (2 * np.pi)) * np.log(d)
    z = np.diag(r) + 1j * 2 * np.pi * f * lmat
    # unknowns: plane currents I_1..I_n and plane drop V
    a_sys = np.zeros((n + 1, n + 1), complex)
    b = np.zeros(n + 1, complex)
    a_sys[:n, :n] = z[1:, 1:]
    a_sys[:n, n] = -1.0
    b[:n] = -z[1:, 0] * 1.0  # trace current = 1 A
    a_sys[n, :n] = 1.0
    b[n] = -1.0
    sol = np.linalg.solve(a_sys, b)
    i_plane = sol[:n]
    within = np.abs(xc) <= 3 * h
    frac = np.abs(i_plane[within].sum()) / 1.0
    return frac


def sweep(width, h=0.2e-3):
    freqs = np.logspace(3, 7, 25)  # 1 kHz .. 10 MHz
    fr = np.array([solve(f, h=h, width=width) for f in freqs])
    return freqs, fr


def crossing(freqs, fr, level):
    idx = np.argmax(fr >= level)
    if fr[idx] < level:
        return float("nan")
    if idx == 0:
        return freqs[0]
    f0, f1 = np.log10(freqs[idx - 1]), np.log10(freqs[idx])
    y0, y1 = fr[idx - 1], fr[idx]
    return 10 ** (f0 + (level - y0) * (f1 - f0) / (y1 - y0))


if __name__ == "__main__":
    print("closed-form HF limit within +-3h: %.3f" % (2 / np.pi * np.arctan(3)))
    r_sheet = RHO_CU / 35e-6
    for width, h in ((20e-3, 0.2e-3), (100e-3, 0.2e-3), (50e-3, 0.1e-3), (50e-3, 1.6e-3)):
        freqs, fr = sweep(width, h)
        print("\nplane width %.0f mm, h = %.2f mm, trace 0.3 mm, 1 oz" % (width * 1e3, h * 1e3))
        print("  DC-limit share within +-3h (uniform) ~ %.3f" % min(1.0, 6 * h / width))
        for f in (1e3, 1e4, 1e5, 1e6, 1e7):
            print("  f = %8.0f Hz : %.3f within +-3h" % (f, solve(f, h=h, width=width)))
        print("  50%% reached at ~%.3g Hz; 70%% at ~%.3g Hz; f_x = R_sheet/(2 pi mu0 h) = %.3g Hz"
              % (crossing(freqs, fr, 0.5), crossing(freqs, fr, 0.7), r_sheet / (2 * np.pi * MU0 * h)))
