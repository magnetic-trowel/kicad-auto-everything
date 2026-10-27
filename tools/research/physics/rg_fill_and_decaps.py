# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Two rule-of-thumb checks used in docs/topics/physics/rule-genealogy-*.md.

1. Same-layer ground fill beside a microstrip: change of Z0 as the fill gap s
   shrinks, from a small 2-D finite-difference electrostatic solve (the
   conformal-mapping CPWG closed form overstates the effect at s >> h, so it is
   not used). Answers "how close can a pour come before it matters" in units of
   the dielectric height h.
2. Decoupling: impedance of three capacitor values with equal mounting
   inductance (the "0.1 uF + 1 nF + 10 uF" habit) against the same count of
   one value, to show the anti-resonance peaks the myth produces.

Run (numpy, scipy):

    python tools/research/physics/rg_fill_and_decaps.py   # ~5 s
"""
import math

import numpy as np
from scipy.sparse import csr_matrix, diags
from scipy.sparse.linalg import spsolve

ER = 4.3


def cross_section_c(w_h, s_h, er, n=12, width=30, height=12):
    """2-D finite-difference electrostatics of a microstrip cross-section, lengths in units of h.

    Ground plane at y=0, strip (one cell thick) at y=h, optional same-layer fill
    beyond a gap s_h, grounded box of width x height. Returns C/eps0 per unit length.
    """
    dx = 1.0 / n
    nx, ny = int(width * n), int(height * n)
    x = (np.arange(nx) - nx / 2 + 0.5) * dx
    y = np.arange(ny) * dx
    _, yy = np.meshgrid(x, y)
    fixed = np.zeros((ny, nx), bool)
    val = np.zeros((ny, nx))
    fixed[0, :] = fixed[-1, :] = True
    fixed[:, 0] = fixed[:, -1] = True
    strip = np.abs(x) <= w_h / 2
    fixed[n, strip] = True
    val[n, strip] = 1.0
    if s_h is not None:
        fixed[n, np.abs(x) >= w_h / 2 + s_h] = True
    eps = np.where(yy < 1.0 - 1e-9, er, 1.0)
    ids = np.arange(nx * ny).reshape(ny, nx)
    rows, cols, data = [], [], []
    diag = np.zeros(nx * ny)
    for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        j0 = slice(max(0, -dj), ny - max(0, dj))
        i0 = slice(max(0, -di), nx - max(0, di))
        j1 = slice(max(0, dj), ny - max(0, -dj))
        i1 = slice(max(0, di), nx - max(0, -di))
        a, c = ids[j0, i0].ravel(), ids[j1, i1].ravel()
        e = 0.5 * (eps[j0, i0] + eps[j1, i1]).ravel()
        rows.append(a)
        cols.append(c)
        data.append(-e)
        np.add.at(diag, a, e)
    mat = csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
                     shape=(nx * ny, nx * ny)) + diags(diag)
    f, v = fixed.ravel(), val.ravel()
    free = ~f
    phi = v.copy()
    phi[free] = spsolve(mat[free][:, free].tocsc(), -mat[free][:, f] @ v[f])
    phi = phi.reshape(ny, nx)
    ex, ey = np.diff(phi, axis=1) / dx, np.diff(phi, axis=0) / dx
    epx, epy = 0.5 * (eps[:, 1:] + eps[:, :-1]), 0.5 * (eps[1:, :] + eps[:-1, :])
    return (np.sum(epx * ex ** 2) + np.sum(epy * ey ** 2)) * dx * dx


def z0_fd(w_h, s_h, er=ER):
    c, ca = cross_section_c(w_h, s_h, er), cross_section_c(w_h, s_h, 1.0)
    return 1 / (2.998e8 * 8.854e-12 * math.sqrt(c * ca))


def fill_check():
    print("== 1. Same-layer ground fill at gap s beside a ~50-ohm microstrip (w = 2h), 2-D FD solve")
    z_ref = z0_fd(2.0, None)
    print(f"no fill: Z0 = {z_ref:.1f} ohm (Hammerstad gives ~50 for w/h = 1.96)")
    for s_h in (0.25, 0.5, 1, 2, 3, 5):
        z = z0_fd(2.0, s_h)
        print(f"   s = {s_h:4.2f} h: Z0 = {z:5.1f} ohm ({(z/z_ref-1)*100:+5.1f} %)")
    print("(scale-free: s in units of h; checked against a 1/20 h grid to within 1 point of %)")


def decap_check():
    print("\n== 2. Equal-ESL decoupling: 3 values vs 3 x one value (ESL incl. mounting 1.0 nH each)")
    f = np.logspace(5, 9, 4001)
    w = 2 * np.pi * f

    def zcap(c, esr, esl):
        return esr + 1j * w * esl + 1 / (1j * w * c)

    def par(*zs):
        return 1 / sum(1 / z for z in zs)

    esl = 1.0e-9
    mixed = par(zcap(10e-6, 5e-3, esl), zcap(100e-9, 20e-3, esl), zcap(1e-9, 100e-3, esl))
    same = par(*(zcap(10e-6, 5e-3, esl) for _ in range(3)))
    for name, z in (("10u+100n+1n", mixed), ("3 x 10u", same)):
        mag = np.abs(z)
        # local maxima above 1 MHz
        peaks = [(f[i], mag[i]) for i in range(1, len(f) - 1) if mag[i] > mag[i - 1] and mag[i] > mag[i + 1] and f[i] > 1e6]
        at = {fx: mag[np.argmin(abs(f - fx))] for fx in (10e6, 50e6, 100e6, 300e6)}
        ptxt = ", ".join(f"{p/1e6:.0f} MHz: {m*1e3:.0f} mOhm" for p, m in peaks) or "none"
        print(f"{name:12s} |Z| @10/50/100/300 MHz = " + " / ".join(f"{v*1e3:.0f}" for v in at.values())
              + f" mOhm; anti-resonance peaks: {ptxt}")


if __name__ == "__main__":
    fill_check()
    decap_check()
