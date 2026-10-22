# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast scalar loop inductance for the annealer's inner loop (pure Python, a few us).

Same physics as `kernels.loop_L` (partial inductances with PEC images, Hammerstad-Jensen
self terms for strips), specialised for loops made of horizontal straight segments at
known heights plus vertical segments (vias, part terminations):

  L = sum_k S_k + 2 sum_{j<k} [M(j, k) + M(j, img k)] + vertical terms

* S_k: `kernels.strip_self` (thin-filament form with an effective image distance that
  reproduces L'(w, h)); free-space Rosa form when there is no plane (h = inf).
* Parallel pairs: Grover's exact form. Pairs sharing a corner: Grover's exact form for
  two filaments meeting at a point. Other oblique pairs: the second segment projected on
  the first's direction at its mean distance (exact when parallel; validated against
  quadrature in tests). Pairs closer to perpendicular than `PERP_COS` are skipped
  (perpendicular filaments do not couple).
* Images: a horizontal segment at height h images at -h reversed; vertical segments
  image with the same direction.
Heights are measured above the reference plane; h = inf means no plane.
"""
from __future__ import annotations

import math

from .kernels import gmd_rect, lprime_hj

MU = 0.1            # mu0 / 4 pi, nH/mm
PERP_COS = 0.05     # skip pairs with |cos| below this
INF = float('inf')

_asinh = math.asinh
_sqrt = math.sqrt
_log = math.log
_hyp = math.hypot


def _G(u, d):
    return u * _asinh(u / d) - _sqrt(u * u + d * d)


def m_par(l1, l2, s, d):
    """Grover: parallel co-directed filaments, 1 on [0, l1], 2 on [s, s+l2], distance d."""
    if d < 1e-9:
        d = 1e-9
    return MU * (_G(s + l2, d) - _G(s + l2 - l1, d) - _G(s, d) + _G(s - l1, d))


def m_self(ln, d):
    """m_par(ln, ln, 0, d) in closed form: 0.2 (ln asinh(ln/d) - sqrt(ln^2 + d^2) + d)."""
    if d < 1e-9:
        d = 1e-9
    return 2.0 * MU * (ln * _asinh(ln / d) - _sqrt(ln * ln + d * d) + d)


_STRIP = {}


def strip_consts(w, h):
    """(a, d_eff) of a strip of width w at height h (cached)."""
    key = (round(w, 4), round(h, 4) if h != INF else INF)
    v = _STRIP.get(key)
    if v is None:
        a = gmd_rect(w)
        if h == INF:
            v = (a, INF)
        else:
            v = (a, a * math.exp(lprime_hj(w, h) / (2.0 * MU)))
        if len(_STRIP) < 200000:
            _STRIP[key] = v
    return v


def strip_self(ln, w, h):
    a, de = strip_consts(w, h)
    if de == INF:
        return m_self(ln, a)
    return m_self(ln, a) - m_self(ln, de)


def m_corner(l1, l2, cosang, R):
    """Two coplanar filaments meeting at a point; cosang = cos of the angle between their
    directions taken both pointing away from the vertex; R = distance between far ends.
    Grover: M = (mu0/4pi) 2 cos e [l1 atanh(l2/(l1+R)) + l2 atanh(l1/(l2+R))]; at e = 180
    degrees it reduces to the collinear form."""
    a = l2 / (l1 + R)
    b = l1 / (l2 + R)
    a = min(a, 1.0 - 1e-12)
    b = min(b, 1.0 - 1e-12)
    return MU * cosang * (l1 * _log((1 + a) / (1 - a)) + l2 * _log((1 + b) / (1 - b)))


def m_hh(ax, ay, bx, by, cx, cy, dx, dy, dz, adjacent, dmin=0.0):
    """Mutual (nH) of horizontal filaments A->B and C->D whose planes are dz apart.

    adjacent: B == C (consecutive in a loop, same height) -> exact corner form, used for
    corners between 45 and 135 degrees; sharper corners use the projected form with the
    distance floored at dmin (strips cannot come closer than their GMD without merging)."""
    ux, uy = bx - ax, by - ay
    l1 = _hyp(ux, uy)
    vx, vy = dx - cx, dy - cy
    l2 = _hyp(vx, vy)
    if l1 < 1e-9 or l2 < 1e-9:
        return 0.0
    ux /= l1
    uy /= l1
    vx /= l2
    vy /= l2
    c = ux * vx + uy * vy
    if -PERP_COS < c < PERP_COS:
        return 0.0
    if adjacent and dz < 1e-12 and -0.7 < c < 0.7:
        # both pointing away from the shared vertex B=C: -u and v
        R = _hyp(dx - ax, dy - ay)
        return -m_corner(l1, l2, -c, R)
    # project C, D on the A->B axis
    s0 = (cx - ax) * ux + (cy - ay) * uy
    s1 = (dx - ax) * ux + (dy - ay) * uy
    p0 = (cx - ax) * uy - (cy - ay) * ux
    p1 = (dx - ax) * uy - (dy - ay) * ux
    dperp = 0.5 * abs(p0 + p1)
    d = _sqrt(dperp * dperp + dz * dz)
    if d < dmin:
        d = dmin
    if s1 >= s0:
        m = m_par(l1, s1 - s0, s0, d)
    else:
        m = m_par(l1, s0 - s1, s1, d)
    return m if c > 0 else -m


def loop_fast(H, V=()):
    """Loop inductance (nH).

    H: list of horizontal segments (x0, y0, x1, y1, w, h) in loop order (current from
       (x0, y0) to (x1, y1)); h = height above the reference plane (inf: no plane).
    V: vertical segments (x, y, z0, z1, r): current from height z0 to z1 (heights above the
       plane; z < 0 not allowed), r = radius or GMD.
    Consecutive horizontal segments that share an end point at the same height use the
    exact corner formula."""
    L = 0.0
    n = len(H)
    for k in range(n):
        x0, y0, x1, y1, w, h = H[k]
        L += strip_self(_hyp(x1 - x0, y1 - y0), w, h)
    for j in range(n):
        ax, ay, bx, by, wj, hj = H[j]
        for k in range(j + 1, n):
            cx, cy, dx, dy, wk, hk = H[k]
            same = abs(hj - hk) < 1e-9
            adj_jk = same and abs(bx - cx) < 1e-9 and abs(by - cy) < 1e-9
            adj_kj = same and abs(dx - ax) < 1e-9 and abs(dy - ay) < 1e-9
            if adj_jk:
                m = m_hh(ax, ay, bx, by, cx, cy, dx, dy, 0.0, True)
            elif adj_kj:
                m = m_hh(cx, cy, dx, dy, ax, ay, bx, by, 0.0, True)
            else:
                m = m_hh(ax, ay, bx, by, cx, cy, dx, dy, abs(hj - hk) if hj != INF else 0.0, False)
            if hj != INF and hk != INF:
                # image of k: at -hk, reversed
                m -= m_hh(ax, ay, bx, by, cx, cy, dx, dy, hj + hk, False)
            L += 2.0 * m
    if V:
        L += _vertical_terms(H, V)
    return L


def _vertical_terms(H, V):
    """Self and mutual terms of vertical segments (with same-direction images)."""
    L = 0.0
    nv = len(V)
    for a in range(nv):
        xa, ya, za0, za1, ra = V[a]
        la = abs(za1 - za0)
        if la < 1e-12:
            continue
        sa = 1.0 if za1 > za0 else -1.0
        lo_a = min(za0, za1)
        # self + mutual with own image (collinear, image spans [-hi, -lo], same direction)
        L += m_self(la, ra)
        L += _collinear(la, la, 2.0 * lo_a)    # own image spans [-hi, -lo]: gap 2 lo
        for b in range(a + 1, nv):
            xb, yb, zb0, zb1, rb = V[b]
            lb = abs(zb1 - zb0)
            if lb < 1e-12:
                continue
            sb = 1.0 if zb1 > zb0 else -1.0
            lo_b = min(zb0, zb1)
            d = _hyp(xa - xb, ya - yb)     # 0 for stacked collinear segments: m_par stays finite
            m = m_par(la, lb, lo_b - lo_a, d)
            # b's image spans [-(lo_b+lb), -lo_b], same direction
            m += m_par(la, lb, -(lo_b + lb) - lo_a, d)
            L += 2.0 * sa * sb * m
    return L


def _collinear(l1, l2, g):
    """Mutual of two collinear co-directed filaments of lengths l1, l2 with a gap g >= 0
    between them (end to end)."""
    def f(x):
        return x * _log(x) if x > 1e-12 else 0.0
    return MU * (f(l1 + l2 + g) - f(l1 + g) - f(l2 + g) + f(g))


def pair_mut(ax, ay, bx, by, cx, cy, dx, dy, hj, hk, adjacent, cos_min, dmin):
    """2 [M(j, k) - M(j, image k)] for horizontal segments j = A->B at height hj and
    k = C->D at height hk over a plane (inf = no plane: no image term). Returns 0 for pairs
    closer to perpendicular than cos_min. The projection is shared by the direct and image
    terms; Grover's G(u, d) = u asinh(u/d) - sqrt(u^2 + d^2) is inlined."""
    ux = bx - ax
    uy = by - ay
    l1 = _sqrt(ux * ux + uy * uy)
    vx = dx - cx
    vy = dy - cy
    l2 = _sqrt(vx * vx + vy * vy)
    if l1 < 1e-9 or l2 < 1e-9:
        return 0.0
    ux /= l1
    uy /= l1
    c = (ux * vx + uy * vy) / l2
    if -cos_min < c < cos_min:
        return 0.0
    noplane = hj == INF or hk == INF
    qx = cx - ax
    qy = cy - ay
    rx = dx - ax
    ry = dy - ay
    s0 = qx * ux + qy * uy
    s1 = rx * ux + ry * uy
    dp = 0.5 * abs(qx * uy - qy * ux + rx * uy - ry * ux)
    if s1 >= s0:
        lo, e1 = s0, s1
    else:
        lo, e1 = s1, s0
    e2 = e1 - l1
    e3 = lo - l1
    asinh = _asinh
    sqrt = _sqrt
    if adjacent and -0.7 < c < 0.7:
        R = _hyp(dx - ax, dy - ay)
        a = min(l2 / (l1 + R), 1.0 - 1e-12)
        b = min(l1 / (l2 + R), 1.0 - 1e-12)
        m = c * (l1 * _log((1 + a) / (1 - a)) + l2 * _log((1 + b) / (1 - b)))
    else:
        dz = 0.0 if noplane else abs(hj - hk)
        d = sqrt(dp * dp + dz * dz)
        if d < dmin:
            d = dmin
        dd = d * d
        m = (e1 * asinh(e1 / d) - sqrt(e1 * e1 + dd)) - (e2 * asinh(e2 / d) - sqrt(e2 * e2 + dd)) \
            - (lo * asinh(lo / d) - sqrt(lo * lo + dd)) + (e3 * asinh(e3 / d) - sqrt(e3 * e3 + dd))
        if c < 0:
            m = -m
    if not noplane:
        d = sqrt(dp * dp + (hj + hk) ** 2)
        dd = d * d
        mi = (e1 * asinh(e1 / d) - sqrt(e1 * e1 + dd)) - (e2 * asinh(e2 / d) - sqrt(e2 * e2 + dd)) \
            - (lo * asinh(lo / d) - sqrt(lo * lo + dd)) + (e3 * asinh(e3 / d) - sqrt(e3 * e3 + dd))
        m -= mi if c > 0 else -mi
    return 2.0 * MU * m
