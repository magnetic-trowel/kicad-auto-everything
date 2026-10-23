# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compiled kernels of the greedy legalizer (kae.place.legalize.greedy), used when numba is
installed (`kae[fast]`); the numpy window search in legalize.py is the fallback.

Occupancy lives in one summed-area table per side over the grid padded by `pad` cells
(courtyards may overhang the board). A rectangle query is O(1); placing a part updates the
table in place (O(cells after the rectangle)). The nearest free origin is found by walking
L1 rings outwards from the wanted origin, so a part that fits nearby costs a few hundred
queries.
"""
from __future__ import annotations

import numpy as np

try:
    import numba
    HAVE_NUMBA = True
except ImportError:          # pragma: no cover - exercised without kae[fast]
    numba = None
    HAVE_NUMBA = False


def _jit(f):
    return numba.njit(cache=True)(f) if HAVE_NUMBA else f


@_jit
def sat_add_rect(S, i0, i1, j0, j1, v):
    """Add v to every cell of [i0, i1) x [j0, j1) (padded coordinates) in the summed-area
    table S (S[i, j] = sum of cells [0, i) x [0, j))."""
    ni = S.shape[0] - 1
    nj = S.shape[1] - 1
    if i0 < 0:
        i0 = 0
    if j0 < 0:
        j0 = 0
    if i1 > ni:
        i1 = ni
    if j1 > nj:
        j1 = nj
    if i1 <= i0 or j1 <= j0:
        return
    for i in range(i0 + 1, ni + 1):
        wi = (i if i < i1 else i1) - i0
        for j in range(j0 + 1, nj + 1):
            wj = (j if j < j1 else j1) - j0
            S[i, j] += v * wi * wj


@_jit
def _q(S, i0, i1, j0, j1):
    """Cells of [i0, i1) x [j0, j1) in S's table (clipped: cells beyond count as empty)."""
    ni = S.shape[0] - 1
    nj = S.shape[1] - 1
    if i0 < 0:
        i0 = 0
    if j0 < 0:
        j0 = 0
    if i1 > ni:
        i1 = ni
    if j1 > nj:
        j1 = nj
    if i1 <= i0 or j1 <= j0:
        return 0
    return S[i1, j1] - S[i0, j1] - S[i1, j0] + S[i0, j0]


@_jit
def _outside(SO, ncx, ncy, i0, i1, j0, j1):
    """Cells of [i0, i1) x [j0, j1) (board grid) not inside the outline; cells beyond the
    grid count as outside."""
    area = (i1 - i0) * (j1 - j0)
    if area <= 0:
        return 0
    a0 = min(max(i0, 0), ncx)
    a1 = min(max(i1, 0), ncx)
    b0 = min(max(j0, 0), ncy)
    b1 = min(max(j1, 0), ncy)
    inside = (a1 - a0) * (b1 - b0)
    cnt = 0
    if inside > 0:
        cnt = SO[a1, b1] - SO[a0, b1] - SO[a1, b0] + SO[a0, b0]
    return cnt + (area - inside)


@_jit
def _fits(T0, T1, SO, ncx, ncy, pad, si, X, Y, k, own, opp, opp_n, brd, brd_n):
    """Part at origin (X, Y), rotation k: board rectangles inside the outline, own rectangle
    free in its side's table and far rectangles free in the other side's (T0 front, T1 back)."""
    for m in range(brd_n[k]):
        if _outside(SO, ncx, ncy, X + brd[k, m, 0], X + brd[k, m, 1], Y + brd[k, m, 2], Y + brd[k, m, 3]) > 0:
            return False
    A = T0 if si == 0 else T1
    B = T1 if si == 0 else T0
    if _q(A, X + own[k, 0] + pad, X + own[k, 1] + pad, Y + own[k, 2] + pad, Y + own[k, 3] + pad) > 0:
        return False
    for m in range(opp_n[k]):
        if _q(B, X + opp[k, m, 0] + pad, X + opp[k, m, 1] + pad, Y + opp[k, m, 2] + pad, Y + opp[k, m, 3] + pad) > 0:
            return False
    return True


@_jit
def nearest_spot(S0, S1, SO, ncx, ncy, pad, si, X0, Y0, K0, w_rot, own, opp, opp_n, brd, brd_n, max_d):
    """Nearest origin (L1 + w_rot when turning) where the part fits: (cost, X, Y, k), cost
    -1 when none within max_d."""
    nk = own.shape[0]
    best_c = -1.0
    bx = by = bk = 0
    for d in range(max_d + 1):
        if best_c >= 0 and d > best_c:
            break
        for dx in range(-d, d + 1):
            rem = d - abs(dx)
            for sgn in range(2):
                if sgn == 1 and rem == 0:
                    break
                dy = rem if sgn == 0 else -rem
                X = X0 + dx
                Y = Y0 + dy
                for k in range(nk):
                    c = d + (w_rot if k != K0 else 0.0)
                    if best_c >= 0 and c >= best_c:
                        continue
                    if _fits(S0, S1, SO, ncx, ncy, pad, si, X, Y, k, own, opp, opp_n, brd, brd_n):
                        best_c = c
                        bx = X
                        by = Y
                        bk = k
    return best_c, bx, by, bk


@_jit
def ripup_spot(H0, H1, C0, C1, SO, ncx, ncy, pad, si, X0, Y0, K0, w_rot, w_cost, own, opp, opp_n, brd, brd_n,
               max_d):
    """Origin minimizing L1 + turning + w_cost x cells of evictable parts (tables C) the
    own rectangle covers, among origins free in the hard tables H: (cost, X, Y, k), -1 when
    none within max_d."""
    nk = own.shape[0]
    best_c = -1.0
    bx = by = bk = 0
    for d in range(max_d + 1):
        if best_c >= 0 and d > best_c:
            break
        for dx in range(-d, d + 1):
            rem = d - abs(dx)
            for sgn in range(2):
                if sgn == 1 and rem == 0:
                    break
                dy = rem if sgn == 0 else -rem
                X = X0 + dx
                Y = Y0 + dy
                for k in range(nk):
                    c0 = d + (w_rot if k != K0 else 0.0)
                    if best_c >= 0 and c0 >= best_c:
                        continue
                    if not _fits(H0, H1, SO, ncx, ncy, pad, si, X, Y, k, own, opp, opp_n, brd, brd_n):
                        continue
                    C = C0 if si == 0 else C1
                    cov = _q(C, X + own[k, 0] + pad, X + own[k, 1] + pad, Y + own[k, 2] + pad, Y + own[k, 3] + pad)
                    c = c0 + w_cost * cov
                    if best_c < 0 or c < best_c:
                        best_c = c
                        bx = X
                        by = Y
                        bk = k
    return best_c, bx, by, bk


def part_arrays(p):
    """(own (nk, 4), opp (nk, m, 4), opp_n (nk,), brd (nk, m, 4), brd_n (nk,)) int64 arrays
    of a Problem part's grid rectangles per rotation."""
    nk = len(p.rots)
    mo = max(1, max(len(r.g_opp) for r in p.rots))
    mb = max(1, max(len(r.g_boards or (r.g_board,)) for r in p.rots))
    own = np.zeros((nk, 4), np.int64)
    opp = np.zeros((nk, mo, 4), np.int64)
    opp_n = np.zeros(nk, np.int64)
    brd = np.zeros((nk, mb, 4), np.int64)
    brd_n = np.zeros(nk, np.int64)
    for k, r in enumerate(p.rots):
        own[k] = r.g_own
        for m, o in enumerate(r.g_opp):
            opp[k, m] = o
        opp_n[k] = len(r.g_opp)
        bs = r.g_boards or (r.g_board,)
        for m, b in enumerate(bs):
            brd[k, m] = b
        brd_n[k] = len(bs)
    return own, opp, opp_n, brd, brd_n
