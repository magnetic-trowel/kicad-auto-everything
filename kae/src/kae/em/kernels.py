# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Partial inductances of the raster's conductors, in SI units (m, H).

- `bar_mutual`: exact mutual partial inductance of two parallel rectangular bars carrying
  uniform current along x (Hoer and Love, J. Res. NBS 69C, 1965), as the 64-term difference
  of a sixfold antiderivative of 1/r. Exact for any separation, including self (equal bars).
  Its terms grow as r^5 while the result falls as 1/r, so it is used for near pairs only.
- `fil_mutual`: two parallel line filaments (Neumann, closed form). Used beyond NEAR cells,
  where the bars' finite cross-sections change the result by < (w/d)^2 / 12.
- `tube_self`: thin-walled tube (a via barrel): the GMD of a circle to itself is its radius.
"""
from __future__ import annotations

import numpy as np

MU0 = 4e-7 * np.pi
K = MU0 / (4 * np.pi)
NEAR = 6            # in-plane cell offsets (Chebyshev) evaluated exactly


def _f(x, y, z):
    """Hoer-Love antiderivative: d2/dx2 d2/dy2 d2/dz2 f = 1/sqrt(x^2+y^2+z^2)."""
    x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
    x2, y2, z2 = x * x, y * y, z * z
    r = np.sqrt(x2 + y2 + z2)
    out = (x2 * x2 + y2 * y2 + z2 * z2 - 3 * x2 * y2 - 3 * y2 * z2 - 3 * z2 * x2) * r / 60.0
    with np.errstate(divide="ignore", invalid="ignore"):
        for a, b2, c2 in ((x, y2, z2), (y, x2, z2), (z, x2, y2)):
            coef = (b2 * c2 / 4 - b2 * b2 / 24 - c2 * c2 / 24) * a
            den = np.sqrt(b2 + c2)
            lg = np.log((a + r) / den)
            ok = (coef != 0) & (den > 0) & np.isfinite(lg)
            out = out + np.where(ok, coef * np.where(ok, lg, 0.0), 0.0)
        for a, b, c in ((z, x, y), (y, x, z), (x, y, z)):
            # - x y z^3/6 atan(xy/(z r)),  - x y^3 z/6 atan(xz/(y r)),  - x^3 y z/6 atan(yz/(x r))
            coef = a * a * a * b * c / 6
            ok = (coef != 0) & (r > 0)
            at = np.arctan(np.where(ok, b * c / np.where(ok, a * r, 1.0), 0.0))
            out = out - np.where(ok, coef * at, 0.0)
    return out


def bar_mutual(b1, b2):
    """Mutual partial inductance (H) of bars b = (x0, x1, y0, y1, z0, z1) (m), both carrying
    uniform current along x. Arrays broadcast over the leading dimensions of b1 and b2."""
    b1 = [np.asarray(v, float) for v in b1]
    b2 = [np.asarray(v, float) for v in b2]
    tot = 0.0
    # per axis: integral over u in [a0,a1], v in [c0,c1] of g(u-v) -> G(a1-c0) - G(a1-c1) - G(a0-c0) + G(a0-c1)
    def diffs(a0, a1, c0, c1):
        return ((a1 - c0, 1), (a1 - c1, -1), (a0 - c0, -1), (a0 - c1, 1))
    dx = diffs(b1[0], b1[1], b2[0], b2[1])
    dy = diffs(b1[2], b1[3], b2[2], b2[3])
    dz = diffs(b1[4], b1[5], b2[4], b2[5])
    for ux, sx in dx:
        for uy, sy in dy:
            for uz, sz in dz:
                tot = tot + (sx * sy * sz) * _f(ux, uy, uz)
    area = (b1[3] - b1[2]) * (b1[5] - b1[4]) * (b2[3] - b2[2]) * (b2[5] - b2[4])
    return K * tot / area


def _G(u, d):
    """d2G/du2 = 1/sqrt(u^2 + d^2)."""
    return u * np.arcsinh(u / d) - np.sqrt(u * u + d * d)


def fil_mutual(a0, a1, c0, c1, d):
    """Two parallel filaments along one axis, spans [a0,a1] and [c0,c1] (m), lateral distance d > 0."""
    return K * (_G(a1 - c0, d) - _G(a1 - c1, d) - _G(a0 - c0, d) + _G(a0 - c1, d))


def tube_self(length, radius):
    """Partial self inductance of a thin-walled tube (via barrel)."""
    return fil_mutual(0.0, length, 0.0, length, radius)


def xbar_kernel(p, z1, t1, z2, t2, ny, nx, near=NEAR):
    """Table K[dy, dx] (H), dy in -(ny-1)..ny-1, dx in -(nx-1)..nx-1 (index + n-1): the mutual of an
    x-directed bar p x p x t1 at the origin (bottom z1) and one offset by (dx p, dy p) at bottom z2,
    thickness t2. Exact (Hoer-Love) within `near` cells, filaments of the bars' centre lines beyond.
    The y-directed table is this one transposed (square cells)."""
    jy = np.arange(-(ny - 1), ny)[:, None].astype(float)
    ix = np.arange(-(nx - 1), nx)[None, :].astype(float)
    zc1, zc2 = z1 + t1 / 2, z2 + t2 / 2
    dz = zc2 - zc1
    # centre-line distance; for collinear bars (d = 0) the filaments sit at the cross-section's
    # self-GMD apart (0.2235 (w + t)), which changes far terms by < (w/d)^2 / 12
    g = 0.2235 * (p + (t1 + t2) / 2)
    d = np.sqrt((jy * p) ** 2 + dz * dz + (g * g if abs(dz) < 1e-15 else 0.0) * (jy == 0))
    Kt = np.empty((2 * ny - 1, 2 * nx - 1))
    far = (np.abs(jy) > near) | (np.abs(ix) > near)
    far = np.broadcast_to(far, Kt.shape)
    dd = np.broadcast_to(d, Kt.shape)
    xs = np.broadcast_to(ix * p, Kt.shape)
    with np.errstate(divide="ignore", invalid="ignore"):
        Kt[...] = np.where(far, fil_mutual(-p / 2, p / 2, xs - p / 2, xs + p / 2, np.where(far, dd, 1.0)), 0.0)
    m = int(near)
    sl_y = slice(ny - 1 - min(m, ny - 1), ny + min(m, ny - 1))
    sl_x = slice(nx - 1 - min(m, nx - 1), nx + min(m, nx - 1))
    J, I = np.meshgrid(np.arange(-(ny - 1), ny)[sl_y], np.arange(-(nx - 1), nx)[sl_x], indexing="ij")
    b1 = (-p / 2, p / 2, -p / 2, p / 2, z1, z1 + t1)
    b2 = (I * p - p / 2, I * p + p / 2, J * p - p / 2, J * p + p / 2, np.full(I.shape, z2), np.full(I.shape, z2 + t2))
    Kt[sl_y, sl_x] = bar_mutual(b1, b2)
    return Kt
