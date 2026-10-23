# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compiled annealing engine: the routability, legality, displacement and order terms of
kae.place.anneal with every update incremental and in numba (`kae[fast]`).

The same cost as anneal.Annealer (that class stays the reference and the fallback):

    cost = w_wl * wl_cost(HPWL / seed HPWL)  +  lam * legality / mean part area
         + w_disp * displacement             +  w_phys * physics / structures
         + w_cong * RUDY overflow            +  w_order * protection-order violation

Kept incrementally in arrays: pin coordinates; per-net bounding boxes and costs (a move
re-measures only its parts' nets, frozen ground/power nets excluded); rectangles in a bucket
hash per side (overlap of a part = the rectangles in the buckets it covers); outline cells
from the summed-area table; RUDY demand per bin (a net's box spreads its expected length
over the bins it covers, pins add escape demand at their bin; a move re-adds only what it
touched and prices the bins in between); the order rules of the moved parts.

Moves of parts that no physics term touches (and that are not macro members) run entirely
in the compiled loop (`FastAnnealer.run` hands it batches); physics parts and macro moves are
proposed in Python, priced by Terms.delta, and evaluated by the same compiled move function.
Aggressor-loop members, whose Terms.delta is the costliest, are sampled at half rate.
"""
from __future__ import annotations

import math
import random
import time
from collections import namedtuple

import numpy as np

try:
    import numba
    HAVE_NUMBA = True
except ImportError:          # pragma: no cover
    numba = None
    HAVE_NUMBA = False


def _jit(f):
    return numba.njit(cache=True)(f) if HAVE_NUMBA else f


# iparams indices
I_NCX, I_NCY, I_HX, I_HY, I_HB, I_CAP, I_HOFF, I_CX, I_CY, I_STAMP, I_NSTAMP, I_OVERFLOW, I_CONG, \
    I_WIN, I_WX0, I_WX1, I_WY0, I_WY1 = range(18)
# fparams indices
F_G, F_OX, F_OY, F_CB, F_CX0, F_CY0, F_SUP, F_TGT, F_NORM, F_A0, F_S0, F_W0, F_SLACK, F_BAR, F_WWL, F_WDISP, \
    F_WCONG, F_WORD, F_OMARGIN, F_NMOV = range(20)
# totals
T_WL, T_LEG, T_CONG, T_ORDER, T_DISP = range(5)

Eng = namedtuple("Eng", [
    "ip", "fp", "tot",
    "X", "Y", "K", "Xs", "Ys", "movable", "side", "nrot",
    "own", "gbrd", "opp_ptr", "opp_r", "brd_ptr", "brd_r",
    "part_r0", "part_rn", "r_box", "r_side", "r_owner", "r_span", "r_seen", "hcnt", "hids", "SO",
    "pin_part", "part_pin_ptr", "pin_off", "px", "py",
    "net_ptr", "net_pins", "w", "frozen", "part_net_ptr", "part_nets", "nb", "nc", "net_seen",
    "Dn", "Dp", "pin_esc", "pin_bx", "pin_by", "net_box", "net_dens", "has_box", "cw", "sc_wx", "sc_wy",
    "rule_rp", "rule_pins", "open", "part_rule_ptr", "part_rules", "rule_seen",
    "in_s", "sc_pins_x", "sc_pins_y", "sc_nets", "sc_nb", "sc_nc", "sc_box", "sc_has", "sc_dens",
    "sc_rules", "sc_open", "sc_pbx", "sc_pby", "sc_oX", "sc_oY", "sc_oK",
    "turn", "ring", "snap", "n_ortho",
])


# ============================================================================ kernels
@_jit
def _hash_span(E, rid):
    HB = E.ip[I_HB]
    off = E.ip[I_HOFF]
    HX = E.ip[I_HX]
    HY = E.ip[I_HY]
    i0 = (E.r_box[rid, 0] + off) // HB
    i1 = (E.r_box[rid, 1] - 1 + off) // HB
    j0 = (E.r_box[rid, 2] + off) // HB
    j1 = (E.r_box[rid, 3] - 1 + off) // HB
    i0 = min(max(i0, 0), HX - 1)
    i1 = min(max(i1, 0), HX - 1)
    j0 = min(max(j0, 0), HY - 1)
    j1 = min(max(j1, 0), HY - 1)
    E.r_span[rid, 0] = i0
    E.r_span[rid, 1] = i1
    E.r_span[rid, 2] = j0
    E.r_span[rid, 3] = j1


@_jit
def _hash_add(E, rid):
    _hash_span(E, rid)
    s = E.r_side[rid]
    cap = E.ip[I_CAP]
    for bi in range(E.r_span[rid, 0], E.r_span[rid, 1] + 1):
        for bj in range(E.r_span[rid, 2], E.r_span[rid, 3] + 1):
            c = E.hcnt[s, bi, bj]
            if c >= cap:
                E.ip[I_OVERFLOW] = 1
                continue
            E.hids[s, bi, bj, c] = rid
            E.hcnt[s, bi, bj] = c + 1


@_jit
def _hash_remove(E, rid):
    s = E.r_side[rid]
    for bi in range(E.r_span[rid, 0], E.r_span[rid, 1] + 1):
        for bj in range(E.r_span[rid, 2], E.r_span[rid, 3] + 1):
            c = E.hcnt[s, bi, bj]
            for m in range(c):
                if E.hids[s, bi, bj, m] == rid:
                    E.hids[s, bi, bj, m] = E.hids[s, bi, bj, c - 1]
                    E.hcnt[s, bi, bj] = c - 1
                    break


@_jit
def _place_rects(E, i):
    """Re-register part i's rectangles at its current pose."""
    X = E.X[i]
    Y = E.Y[i]
    k = E.K[i]
    r0 = E.part_r0[i]
    nr = E.part_rn[i]
    for m in range(nr):
        rid = r0 + m
        if m == 0:
            a = E.own[i, k, 0]
            b = E.own[i, k, 1]
            c = E.own[i, k, 2]
            d = E.own[i, k, 3]
        else:
            q = E.opp_ptr[i] + m - 1
            a = E.opp_r[q, k, 0]
            b = E.opp_r[q, k, 1]
            c = E.opp_r[q, k, 2]
            d = E.opp_r[q, k, 3]
        nb0 = X + a
        nb1 = X + b
        nb2 = Y + c
        nb3 = Y + d
        if nb0 == E.r_box[rid, 0] and nb1 == E.r_box[rid, 1] and nb2 == E.r_box[rid, 2] and nb3 == E.r_box[rid, 3]:
            continue
        _hash_remove(E, rid)
        E.r_box[rid, 0] = nb0
        E.r_box[rid, 1] = nb1
        E.r_box[rid, 2] = nb2
        E.r_box[rid, 3] = nb3
        _hash_add(E, rid)


@_jit
def _overlap_part(E, i, stamp_s):
    """Overlap area (cells^2) of part i's rectangles with rectangles of owners not in the
    move set (in_s == stamp_s marks the set; obstacles have owner -1)."""
    tot = 0
    r0 = E.part_r0[i]
    for m in range(E.part_rn[i]):
        rid = r0 + m
        E.ip[I_STAMP] += 1          # each rectangle counts its overlaps once (as anneal does)
        st = E.ip[I_STAMP]
        s = E.r_side[rid]
        i0 = E.r_box[rid, 0]
        i1 = E.r_box[rid, 1]
        j0 = E.r_box[rid, 2]
        j1 = E.r_box[rid, 3]
        for bi in range(E.r_span[rid, 0], E.r_span[rid, 1] + 1):
            for bj in range(E.r_span[rid, 2], E.r_span[rid, 3] + 1):
                for q in range(E.hcnt[s, bi, bj]):
                    o = E.hids[s, bi, bj, q]
                    if E.r_seen[o] == st:
                        continue
                    E.r_seen[o] = st
                    ow = E.r_owner[o]
                    if ow == i:
                        continue
                    if ow >= 0 and E.in_s[ow] == stamp_s:
                        continue
                    dx = min(i1, E.r_box[o, 1]) - max(i0, E.r_box[o, 0])
                    if dx <= 0:
                        continue
                    dy = min(j1, E.r_box[o, 3]) - max(j0, E.r_box[o, 2])
                    if dy > 0:
                        tot += dx * dy
    return tot


@_jit
def _overlap_pair(E, i, j):
    tot = 0
    for ma in range(E.part_rn[i]):
        ra = E.part_r0[i] + ma
        for mb in range(E.part_rn[j]):
            rb = E.part_r0[j] + mb
            if E.r_side[ra] != E.r_side[rb]:
                continue
            dx = min(E.r_box[ra, 1], E.r_box[rb, 1]) - max(E.r_box[ra, 0], E.r_box[rb, 0])
            dy = min(E.r_box[ra, 3], E.r_box[rb, 3]) - max(E.r_box[ra, 2], E.r_box[rb, 2])
            if dx > 0 and dy > 0:
                tot += dx * dy
    return tot


@_jit
def _outside(E, i):
    ncx = E.ip[I_NCX]
    ncy = E.ip[I_NCY]
    X = E.X[i]
    Y = E.Y[i]
    k = E.K[i]
    tot = 0
    for q in range(E.brd_ptr[i], E.brd_ptr[i + 1]):
        i0 = X + E.brd_r[q, k, 0]
        i1 = X + E.brd_r[q, k, 1]
        j0 = Y + E.brd_r[q, k, 2]
        j1 = Y + E.brd_r[q, k, 3]
        area = (i1 - i0) * (j1 - j0)
        if area <= 0:
            continue
        a0 = min(max(i0, 0), ncx)
        a1 = min(max(i1, 0), ncx)
        b0 = min(max(j0, 0), ncy)
        b1 = min(max(j1, 0), ncy)
        ins = (a1 - a0) * (b1 - b0)
        cnt = 0
        if ins > 0:
            cnt = E.SO[a1, b1] - E.SO[a0, b1] - E.SO[a1, b0] + E.SO[a0, b0]
        tot += cnt + area - ins
    return tot


@_jit
def _leg(E, S, ns, stamp_s):
    tot = 0
    for a in range(ns):
        i = S[a]
        tot += _overlap_part(E, i, stamp_s) + _outside(E, i)
        for b in range(a + 1, ns):
            tot += _overlap_pair(E, i, S[b])
    return tot


@_jit
def _update_pins(E, i):
    g = E.fp[F_G]
    x0 = E.fp[F_OX] + E.X[i] * g
    y0 = E.fp[F_OY] + E.Y[i] * g
    k = E.K[i]
    for p in range(E.part_pin_ptr[i], E.part_pin_ptr[i + 1]):
        E.px[p] = x0 + E.pin_off[k, p, 0]
        E.py[p] = y0 + E.pin_off[k, p, 1]


@_jit
def _net_measure(E, j):
    """(xmin, xmax, ymin, ymax) of net j's pins."""
    xmin = 1e300
    xmax = -1e300
    ymin = 1e300
    ymax = -1e300
    for q in range(E.net_ptr[j], E.net_ptr[j + 1]):
        p = E.net_pins[q]
        x = E.px[p]
        y = E.py[p]
        if x < xmin:
            xmin = x
        if x > xmax:
            xmax = x
        if y < ymin:
            ymin = y
        if y > ymax:
            ymax = y
    return xmin, xmax, ymin, ymax


@_jit
def _axis(lo, hi, e0, eb, nb, out):
    """Overlap lengths of [lo, hi] with bins of size eb from e0: returns (k0, n) and fills
    out[0:n]."""
    k0 = int(math.floor((lo - e0) / eb))
    k1 = int(math.ceil((hi - e0) / eb))
    if k0 < 0:
        k0 = 0
    if k0 > nb - 1:
        k0 = nb - 1
    if k1 < k0 + 1:
        k1 = k0 + 1
    if k1 > nb:
        k1 = nb
    n = k1 - k0
    for t in range(n):
        a = e0 + (k0 + t) * eb
        b = a + eb
        v = min(b, hi) - max(a, lo)
        out[t] = v if v > 0 else 0.0
    return k0, n


@_jit
def _net_box_apply(E, j, sgn, bx0, bx1, by0, by1, dens, wx, wy):
    """Add sgn * the RUDY block of a net box to Dn."""
    cb = E.fp[F_CB]
    kx, nx = _axis(bx0, bx1, E.fp[F_CX0], cb, E.ip[I_CX], wx)
    ky, ny = _axis(by0, by1, E.fp[F_CY0], cb, E.ip[I_CY], wy)
    for a in range(nx):
        va = sgn * dens * wx[a]
        for b in range(ny):
            E.Dn[kx + a, ky + b] += va * wy[b]
    return kx, kx + nx, ky, ky + ny


@_jit
def _box_bins(E, bx0, bx1, by0, by1):
    cb = E.fp[F_CB]
    nbx = E.ip[I_CX]
    nby = E.ip[I_CY]
    k0 = int(math.floor((bx0 - E.fp[F_CX0]) / cb))
    k1 = int(math.ceil((bx1 - E.fp[F_CX0]) / cb))
    k0 = min(max(k0, 0), nbx - 1)
    k1 = min(max(k1, k0 + 1), nbx)
    l0 = int(math.floor((by0 - E.fp[F_CY0]) / cb))
    l1 = int(math.ceil((by1 - E.fp[F_CY0]) / cb))
    l0 = min(max(l0, 0), nby - 1)
    l1 = min(max(l1, l0 + 1), nby)
    return k0, k1, l0, l1


@_jit
def _cong_region_cost(E, x0, x1, y0, y1):
    sup = E.fp[F_SUP]
    tgt = E.fp[F_TGT]
    tot = 0.0
    for a in range(x0, x1):
        for b in range(y0, y1):
            u = (E.Dn[a, b] + E.Dp[a, b]) / sup - tgt
            if u > 0:
                tot += u * u
    return tot


@_jit
def _pin_bin(E, p):
    cb = E.fp[F_CB]
    bx = int((E.px[p] - E.fp[F_CX0]) / cb)
    by = int((E.py[p] - E.fp[F_CY0]) / cb)
    if bx < 0:
        bx = 0
    if bx > E.ip[I_CX] - 1:
        bx = E.ip[I_CX] - 1
    if by < 0:
        by = 0
    if by > E.ip[I_CY] - 1:
        by = E.ip[I_CY] - 1
    return bx, by


@_jit
def _order_pen(E, j):
    """Penalty of order rule j: (d(conn, prot) + margin - min(d(conn, tgt), d(prot, tgt)))+ / S0."""
    cx = cy = tx = ty = ix = iy = 0.0
    for role in range(3):
        sx = 0.0
        sy = 0.0
        n = 0
        for q in range(E.rule_rp[j, role], E.rule_rp[j, role + 1]):
            p = E.rule_pins[q]
            sx += E.px[p]
            sy += E.py[p]
            n += 1
        if n == 0:
            return 0.0
        if role == 0:
            cx = sx / n
            cy = sy / n
        elif role == 1:
            tx = sx / n
            ty = sy / n
        else:
            ix = sx / n
            iy = sy / n
    d_ct = math.hypot(tx - cx, ty - cy)
    d_i = min(math.hypot(ix - cx, iy - cy), math.hypot(ix - tx, iy - ty))
    over = d_ct + E.fp[F_OMARGIN] - d_i
    return over / E.fp[F_S0] if over > 0 else 0.0


@_jit
def _wl_cost(E, wl):
    u = wl / E.fp[F_W0]
    over = u - 1.0 - E.fp[F_SLACK]
    if over > 0:
        return u + E.fp[F_BAR] * over * over
    return u


@_jit
def try_move(E, S, nX, nY, nK, ns, T, lam, extra, u, commit_always):
    """Evaluate moving parts S[:ns] to (nX, nY, nK); accept (Metropolis with uniform u, or
    always when commit_always) or revert. `extra` is a cost change priced elsewhere (physics).
    Returns (accepted, delta)."""
    E.ip[I_NSTAMP] += 1
    ss = E.ip[I_NSTAMP]
    for a in range(ns):
        E.in_s[S[a]] = ss
    # ---- before
    leg_old = _leg(E, S, ns, ss)
    disp_old = 0
    for a in range(ns):
        i = S[a]
        disp_old += abs(E.X[i] - E.Xs[i]) + abs(E.Y[i] - E.Ys[i])
    # touched nets and rules
    nn = 0
    nr = 0
    for a in range(ns):
        i = S[a]
        for q in range(E.part_net_ptr[i], E.part_net_ptr[i + 1]):
            j = E.part_nets[q]
            if E.net_seen[j] != ss:
                E.net_seen[j] = ss
                E.sc_nets[nn] = j
                nn += 1
        for q in range(E.part_rule_ptr[i], E.part_rule_ptr[i + 1]):
            j = E.part_rules[q]
            if E.rule_seen[j] != ss:
                E.rule_seen[j] = ss
                E.sc_rules[nr] = j
                nr += 1
    wl_old_nets = 0.0
    for t in range(nn):
        j = E.sc_nets[t]
        wl_old_nets += E.nc[j]
        E.sc_nb[t, 0] = E.nb[j, 0]
        E.sc_nb[t, 1] = E.nb[j, 1]
        E.sc_nb[t, 2] = E.nb[j, 2]
        E.sc_nb[t, 3] = E.nb[j, 3]
        E.sc_nc[t] = E.nc[j]
        E.sc_has[t] = E.has_box[j]
        E.sc_box[t, 0] = E.net_box[j, 0]
        E.sc_box[t, 1] = E.net_box[j, 1]
        E.sc_box[t, 2] = E.net_box[j, 2]
        E.sc_box[t, 3] = E.net_box[j, 3]
        E.sc_dens[t] = E.net_dens[j]
    ord_old = 0.0
    for t in range(nr):
        E.sc_open[t] = E.open[E.sc_rules[t]]
        ord_old += E.sc_open[t]
    # save poses and pins
    np_ = 0
    for a in range(ns):
        i = S[a]
        for p in range(E.part_pin_ptr[i], E.part_pin_ptr[i + 1]):
            E.sc_pins_x[np_] = E.px[p]
            E.sc_pins_y[np_] = E.py[p]
            E.sc_pbx[np_] = E.pin_bx[p]
            E.sc_pby[np_] = E.pin_by[p]
            np_ += 1
    oX = E.sc_oX
    oY = E.sc_oY
    oK = E.sc_oK
    for a in range(ns):
        i = S[a]
        oX[a] = E.X[i]
        oY[a] = E.Y[i]
        oK[a] = E.K[i]
    # ---- apply
    for a in range(ns):
        i = S[a]
        E.X[i] = nX[a]
        E.Y[i] = nY[a]
        E.K[i] = nK[a]
        _place_rects(E, i)
        _update_pins(E, i)
    leg_new = _leg(E, S, ns, ss)
    disp_new = 0
    for a in range(ns):
        i = S[a]
        disp_new += abs(E.X[i] - E.Xs[i]) + abs(E.Y[i] - E.Ys[i])
    wl_new_nets = 0.0
    for t in range(nn):
        j = E.sc_nets[t]
        xmin, xmax, ymin, ymax = _net_measure(E, j)
        E.nb[j, 0] = xmin
        E.nb[j, 1] = xmax
        E.nb[j, 2] = ymin
        E.nb[j, 3] = ymax
        c = E.w[j] * (xmax - xmin + ymax - ymin)
        E.nc[j] = c
        wl_new_nets += c
    ord_new = 0.0
    for t in range(nr):
        v = _order_pen(E, E.sc_rules[t])
        E.open[E.sc_rules[t]] = v
        ord_new += v
    # ---- RUDY
    d_cong = 0.0
    if E.ip[I_CONG] == 1:
        rx0 = 1 << 30
        rx1 = -1
        ry0 = 1 << 30
        ry1 = -1
        # region: old and new net boxes, old and new pin bins
        for t in range(nn):
            j = E.sc_nets[t]
            if E.sc_has[t]:
                k0, k1, l0, l1 = _box_bins(E, E.sc_box[t, 0], E.sc_box[t, 1], E.sc_box[t, 2], E.sc_box[t, 3])
                rx0 = min(rx0, k0)
                rx1 = max(rx1, k1)
                ry0 = min(ry0, l0)
                ry1 = max(ry1, l1)
            if E.cw[j] > 0 and E.net_ptr[j + 1] - E.net_ptr[j] >= 2:
                k0, k1, l0, l1 = _box_bins(E, E.nb[j, 0] - 0.2, E.nb[j, 1] + 0.2, E.nb[j, 2] - 0.2, E.nb[j, 3] + 0.2)
                rx0 = min(rx0, k0)
                rx1 = max(rx1, k1)
                ry0 = min(ry0, l0)
                ry1 = max(ry1, l1)
        q = 0
        for a in range(ns):
            i = S[a]
            if not E.movable[i]:
                continue
            for p in range(E.part_pin_ptr[i], E.part_pin_ptr[i + 1]):
                bx, by = _pin_bin(E, p)
                rx0 = min(rx0, min(bx, E.sc_pbx[q]))
                rx1 = max(rx1, max(bx, E.sc_pbx[q]) + 1)
                ry0 = min(ry0, min(by, E.sc_pby[q]))
                ry1 = max(ry1, max(by, E.sc_pby[q]) + 1)
                q += 1
        if rx1 > rx0 and ry1 > ry0:
            before = _cong_region_cost(E, rx0, rx1, ry0, ry1)
            wx = E.sc_wx
            wy = E.sc_wy
            for t in range(nn):
                j = E.sc_nets[t]
                if E.sc_has[t]:
                    _net_box_apply(E, j, -1.0, E.sc_box[t, 0], E.sc_box[t, 1], E.sc_box[t, 2], E.sc_box[t, 3],
                                   E.sc_dens[t], wx, wy)
                if E.cw[j] > 0 and E.net_ptr[j + 1] - E.net_ptr[j] >= 2:
                    b0 = E.nb[j, 0] - 0.2
                    b1 = E.nb[j, 1] + 0.2
                    c0 = E.nb[j, 2] - 0.2
                    c1 = E.nb[j, 3] + 0.2
                    W = b1 - b0
                    H = c1 - c0
                    dens = E.cw[j] * (W + H) / (W * H)
                    _net_box_apply(E, j, 1.0, b0, b1, c0, c1, dens, wx, wy)
                    E.net_box[j, 0] = b0
                    E.net_box[j, 1] = b1
                    E.net_box[j, 2] = c0
                    E.net_box[j, 3] = c1
                    E.net_dens[j] = dens
                    E.has_box[j] = True
                else:
                    E.has_box[j] = False
            q = 0
            for a in range(ns):
                i = S[a]
                if not E.movable[i]:
                    continue
                for p in range(E.part_pin_ptr[i], E.part_pin_ptr[i + 1]):
                    bx, by = _pin_bin(E, p)
                    e = E.pin_esc[p]
                    if e != 0.0:
                        E.Dp[E.sc_pbx[q], E.sc_pby[q]] -= e
                        E.Dp[bx, by] += e
                    E.pin_bx[p] = bx
                    E.pin_by[p] = by
                    q += 1
            after = _cong_region_cost(E, rx0, rx1, ry0, ry1)
            d_cong = (after - before) * E.fp[F_NORM]
    # ---- price
    wl = E.tot[T_WL]
    d_wl = wl_new_nets - wl_old_nets
    delta = (E.fp[F_WWL] * (_wl_cost(E, wl + d_wl) - _wl_cost(E, wl))
             + lam * (leg_new - leg_old) / E.fp[F_A0]
             + E.fp[F_WDISP] * (disp_new - disp_old) * E.fp[F_G] / (E.fp[F_NMOV] * E.fp[F_S0])
             + E.fp[F_WCONG] * d_cong
             + E.fp[F_WORD] * (ord_new - ord_old)
             + extra)
    if commit_always or delta <= 0 or (T > 0 and u < math.exp(-delta / T)):
        E.tot[T_WL] += d_wl
        E.tot[T_LEG] += leg_new - leg_old
        E.tot[T_CONG] += d_cong
        E.tot[T_ORDER] += ord_new - ord_old
        E.tot[T_DISP] += disp_new - disp_old
        return True, delta
    # ---- revert
    if E.ip[I_CONG] == 1:
        wx = E.sc_wx
        wy = E.sc_wy
        for t in range(nn):
            j = E.sc_nets[t]
            if E.has_box[j]:
                _net_box_apply(E, j, -1.0, E.net_box[j, 0], E.net_box[j, 1], E.net_box[j, 2], E.net_box[j, 3],
                               E.net_dens[j], wx, wy)
            if E.sc_has[t]:
                _net_box_apply(E, j, 1.0, E.sc_box[t, 0], E.sc_box[t, 1], E.sc_box[t, 2], E.sc_box[t, 3],
                               E.sc_dens[t], wx, wy)
            E.net_box[j, 0] = E.sc_box[t, 0]
            E.net_box[j, 1] = E.sc_box[t, 1]
            E.net_box[j, 2] = E.sc_box[t, 2]
            E.net_box[j, 3] = E.sc_box[t, 3]
            E.net_dens[j] = E.sc_dens[t]
            E.has_box[j] = E.sc_has[t]
        q = 0
        for a in range(ns):
            i = S[a]
            if not E.movable[i]:
                continue
            for p in range(E.part_pin_ptr[i], E.part_pin_ptr[i + 1]):
                e = E.pin_esc[p]
                if e != 0.0:
                    E.Dp[E.pin_bx[p], E.pin_by[p]] -= e
                    E.Dp[E.sc_pbx[q], E.sc_pby[q]] += e
                E.pin_bx[p] = E.sc_pbx[q]
                E.pin_by[p] = E.sc_pby[q]
                q += 1
    for t in range(nn):
        j = E.sc_nets[t]
        E.nb[j, 0] = E.sc_nb[t, 0]
        E.nb[j, 1] = E.sc_nb[t, 1]
        E.nb[j, 2] = E.sc_nb[t, 2]
        E.nb[j, 3] = E.sc_nb[t, 3]
        E.nc[j] = E.sc_nc[t]
    for t in range(nr):
        E.open[E.sc_rules[t]] = E.sc_open[t]
    q = 0
    for a in range(ns):
        i = S[a]
        E.X[i] = oX[a]
        E.Y[i] = oY[a]
        E.K[i] = oK[a]
        _place_rects(E, i)
        for p in range(E.part_pin_ptr[i], E.part_pin_ptr[i + 1]):
            E.px[p] = E.sc_pins_x[q]
            E.py[p] = E.sc_pins_y[q]
            q += 1
    return False, delta


@_jit
def _clamp(E, i, X, Y, k):
    a = E.gbrd[i, k, 0]
    b = E.gbrd[i, k, 1]
    c = E.gbrd[i, k, 2]
    d = E.gbrd[i, k, 3]
    lo_x = -a
    hi_x = E.ip[I_NCX] - b
    lo_y = -c
    hi_y = E.ip[I_NCY] - d
    if E.ip[I_WIN] == 1:
        lo_x = max(lo_x, E.ip[I_WX0] - E.own[i, k, 0])
        hi_x = min(hi_x, E.ip[I_WX1] - E.own[i, k, 1])
        lo_y = max(lo_y, E.ip[I_WY0] - E.own[i, k, 2])
        hi_y = min(hi_y, E.ip[I_WY1] - E.own[i, k, 3])
    if hi_x < lo_x:
        hi_x = lo_x
    if hi_y < lo_y:
        hi_y = lo_y
    X = min(max(X, lo_x), hi_x)
    Y = min(max(Y, lo_y), hi_y)
    return X, Y


@_jit
def seed_rng(s):
    np.random.seed(s)


@_jit
def run_batch(E, parts, swap_ptr, swap_ids, nmoves, T, lam, r, stats):
    """nmoves single-part moves (shift 62%, rotate 18%, swap 20%) of parts drawn from
    `parts` (no physics, no macro), Metropolis at temperature T with legality weight lam.
    stats[0..5] += shift tried/accepted, rotate tried/accepted, swap tried/accepted."""
    S = np.empty(2, np.int64)
    nX = np.empty(2, np.int64)
    nY = np.empty(2, np.int64)
    nK = np.empty(2, np.int64)
    npart = parts.shape[0]
    for _ in range(nmoves):
        i = parts[np.random.randint(npart)]
        u = np.random.random()
        kind = 0
        ns = 1
        S[0] = i
        if u < 0.62:
            X = E.X[i] + np.random.randint(-r, r + 1)
            Y = E.Y[i] + np.random.randint(-r, r + 1)
            X, Y = _clamp(E, i, X, Y, E.K[i])
            nX[0] = X
            nY[0] = Y
            nK[0] = E.K[i]
        elif u < 0.80 and E.nrot[i] > 1:
            kind = 1
            k0 = E.K[i]
            k1 = E.turn[i, k0, 1 + np.random.randint(3)]
            if E.nrot[i] > E.n_ortho[i]:
                v = np.random.random()
                if v < 0.3:
                    k1 = E.ring[i, k0, np.random.randint(2)]
                elif k0 >= E.n_ortho[i] and v < 0.55:
                    k1 = E.snap[i, k0]
            cx0 = E.own[i, k0, 0] + E.own[i, k0, 1]
            cy0 = E.own[i, k0, 2] + E.own[i, k0, 3]
            cx1 = E.own[i, k1, 0] + E.own[i, k1, 1]
            cy1 = E.own[i, k1, 2] + E.own[i, k1, 3]
            X = E.X[i] + (cx0 - cx1) // 2
            Y = E.Y[i] + (cy0 - cy1) // 2
            X, Y = _clamp(E, i, X, Y, k1)
            nX[0] = X
            nY[0] = Y
            nK[0] = k1
        else:
            kind = 2
            j = -1
            c0 = swap_ptr[i]
            c1 = swap_ptr[i + 1]
            if c1 - c0 > 1 and np.random.random() < 0.7:
                j = swap_ids[c0 + np.random.randint(c1 - c0)]
                if j != i:
                    ns = 2
                    S[1] = j
                    nX[0] = E.X[j]
                    nY[0] = E.Y[j]
                    nK[0] = E.K[j]
                    nX[1] = E.X[i]
                    nY[1] = E.Y[i]
                    nK[1] = E.K[i]
                else:
                    j = -1
            if j < 0:
                j = parts[np.random.randint(npart)]
                if j == i or E.side[j] != E.side[i]:
                    kind = 0
                    X = E.X[i] + np.random.randint(-r, r + 1)
                    Y = E.Y[i] + np.random.randint(-r, r + 1)
                    X, Y = _clamp(E, i, X, Y, E.K[i])
                    nX[0] = X
                    nY[0] = Y
                    nK[0] = E.K[i]
                else:
                    ns = 2
                    S[1] = j
                    ki = E.K[i]
                    kj = E.K[j]
                    cix = E.own[i, ki, 0] + E.own[i, ki, 1]
                    ciy = E.own[i, ki, 2] + E.own[i, ki, 3]
                    cjx = E.own[j, kj, 0] + E.own[j, kj, 1]
                    cjy = E.own[j, kj, 2] + E.own[j, kj, 3]
                    Xi, Yi = _clamp(E, i, E.X[j] + (cjx - cix) // 2, E.Y[j] + (cjy - ciy) // 2, ki)
                    Xj, Yj = _clamp(E, j, E.X[i] + (cix - cjx) // 2, E.Y[i] + (ciy - cjy) // 2, kj)
                    nX[0] = Xi
                    nY[0] = Yi
                    nK[0] = ki
                    nX[1] = Xj
                    nY[1] = Yj
                    nK[1] = kj
        acc, _d = try_move(E, S, nX, nY, nK, ns, T, lam, 0.0, np.random.random(), False)
        stats[2 * kind] += 1
        if acc:
            stats[2 * kind + 1] += 1
        if E.ip[I_OVERFLOW] != 0:
            return


# ============================================================================ builder
def build(ann, hash_cap=None):
    """Arrays of an anneal.Annealer's problem and current state (the Annealer supplies the
    weights, the normalizations and the frozen nets, so both price the same cost)."""
    P = ann.P
    n = len(P.parts)
    g = P.g
    nrot = np.array([len(p.rots) for p in P.parts], np.int64)
    NR = max(4, int(nrot.max()) if n else 4)
    own = np.zeros((n, NR, 4), np.int64)
    gbrd = np.zeros((n, NR, 4), np.int64)
    turn = np.zeros((n, NR, 4), np.int64)
    ring = np.zeros((n, NR, 2), np.int64)
    snap = np.zeros((n, NR), np.int64)
    n_ortho = np.array([getattr(p, "n_ortho", len(p.rots)) for p in P.parts], np.int64)
    from .anneal import snap_index
    for p in P.parts:
        for k in range(len(p.rots)):
            turn[p.i, k] = p.turn[k]
            ring[p.i, k] = p.ring[k]
            snap[p.i, k] = snap_index(p, k)
    opp_ptr = np.zeros(n + 1, np.int64)
    brd_ptr = np.zeros(n + 1, np.int64)
    opp_list, brd_list = [], []
    for p in P.parts:
        nk = len(p.rots)
        for k in range(NR):
            r = p.rots[min(k, nk - 1)]
            own[p.i, k] = r.g_own
            gbrd[p.i, k] = r.g_board
        no = len(p.rots[0].g_opp)
        nb_ = len(p.rots[0].g_boards or (p.rots[0].g_board,))
        for m in range(no):
            opp_list.append([p.rots[min(k, nk - 1)].g_opp[m] for k in range(NR)])
        for m in range(nb_):
            brd_list.append([(p.rots[min(k, nk - 1)].g_boards or (p.rots[min(k, nk - 1)].g_board,))[m]
                             for k in range(NR)])
        opp_ptr[p.i + 1] = opp_ptr[p.i] + no
        brd_ptr[p.i + 1] = brd_ptr[p.i] + nb_
    opp_r = np.array(opp_list, np.int64).reshape(-1, NR, 4) if opp_list else np.zeros((0, NR, 4), np.int64)
    brd_r = np.array(brd_list, np.int64).reshape(-1, NR, 4) if brd_list else np.zeros((0, NR, 4), np.int64)
    # rectangles: movable parts' own + far rects, then obstacles (fixed parts are obstacles)
    movable = np.array([p.movable for p in P.parts], bool)
    part_r0 = np.zeros(n, np.int64)
    part_rn = np.zeros(n, np.int64)
    R = 0
    for p in P.parts:
        if p.movable:
            part_r0[p.i] = R
            part_rn[p.i] = 1 + (opp_ptr[p.i + 1] - opp_ptr[p.i])
            R += part_rn[p.i]
    nob = len(P.obstacles)
    r_box = np.zeros((R + nob, 4), np.int64)
    r_side = np.zeros(R + nob, np.int64)
    r_owner = np.full(R + nob, -1, np.int64)
    side = np.array([0 if p.s > 0 else 1 for p in P.parts], np.int64)
    for p in P.parts:
        if not p.movable:
            continue
        r_side[part_r0[p.i]] = side[p.i]
        r_owner[part_r0[p.i]] = p.i
        for m in range(1, part_rn[p.i]):
            r_side[part_r0[p.i] + m] = 1 - side[p.i]
            r_owner[part_r0[p.i] + m] = p.i
    for t, ob in enumerate(P.obstacles):
        r_box[R + t] = ob.g
        r_side[R + t] = ob.side
    ext = 1
    for i in P.mov:
        for k in range(NR):
            a, b, c, d = own[i, k]
            ext = max(ext, -a, b, -c, d)
    HB = max(4, int(round(math.sqrt(ann.A0) * 1.5)))
    hoff = ext + HB
    HX = (P.ncx + 2 * hoff) // HB + 2
    HY = (P.ncy + 2 * hoff) // HB + 2
    if hash_cap is None:
        hash_cap = 128
    hcnt = np.zeros((2, HX, HY), np.int64)
    hids = np.zeros((2, HX, HY, hash_cap), np.int64)
    # pins
    pin_part, part_pin_ptr = [], np.zeros(n + 1, np.int64)
    for p in P.parts:
        part_pin_ptr[p.i + 1] = part_pin_ptr[p.i] + len(p.fp.pads)
        pin_part += [p.i] * len(p.fp.pads)
    NP = int(part_pin_ptr[-1])
    pin_off = np.zeros((NR, NP, 2))
    px = np.zeros(NP)
    py = np.zeros(NP)
    for p in P.parts:
        a0 = part_pin_ptr[p.i]
        nk = len(p.rots)
        for k in range(NR):
            pins = p.rots[min(k, nk - 1)].pins
            if len(pins):
                pin_off[k, a0:a0 + len(pins)] = pins
        if not p.movable:
            px[a0:a0 + len(p.fp.pads)] = p.x0 + p.rots[0].pins[:, 0] if len(p.fp.pads) else []
            py[a0:a0 + len(p.fp.pads)] = p.y0 + p.rots[0].pins[:, 1] if len(p.fp.pads) else []
    # nets (the annealer's weights and frozen set)
    nets = P.nets
    net_ptr = np.zeros(len(nets) + 1, np.int64)
    net_pins = []
    for net in nets:
        net_ptr[net.i + 1] = net_ptr[net.i] + len(net.pins)
        net_pins += [int(part_pin_ptr[i] + k) for (i, k) in net.pins]
    w = np.array(ann.net_w, float) if len(nets) else np.zeros(0)
    frozen = np.array([j in ann.frozen for j in range(len(nets))], bool)
    part_net_ptr = np.zeros(n + 1, np.int64)
    part_nets = []
    for p in P.parts:
        nl = list(ann.part_nets[p.i])
        part_net_ptr[p.i + 1] = part_net_ptr[p.i] + len(nl)
        part_nets += nl
    # congestion (beta 0 only; the annealer's Congestion supplies bins and weights)
    cong = ann.cong
    use_cong = cong is not None and (cong.beta == 0.0)
    if use_cong:
        cx, cy, cb = cong.nbx, cong.nby, cong.b
        cx0, cy0 = cong.x0, cong.y0
        sup = cong.S0
        tgt = cong.target
        norm = cong.norm
        Dn = cong.Dn.copy()
        Dp = cong.Dp.copy()
        cw = np.array(cong.w, float)
    else:
        cx = cy = 1
        cb, cx0, cy0, sup, tgt, norm = 1.0, 0.0, 0.0, 1.0, 1.0, 0.0
        Dn = np.zeros((1, 1))
        Dp = np.zeros((1, 1))
        cw = w.copy()
    pin_esc = np.zeros(NP)
    if use_cong:
        for p in P.parts:
            a0 = part_pin_ptr[p.i]
            pin_esc[a0:a0 + len(p.fp.pads)] = cong.pad_esc[p.i]
    rules = getattr(ann, "order", [])
    rule_rp = np.zeros((max(1, len(rules)), 4), np.int64)
    rule_pins = []
    part_rule = {}
    for j, rule in enumerate(rules):
        for role, (i, pads) in enumerate(rule):
            rule_rp[j, role] = len(rule_pins)
            rule_pins += [int(part_pin_ptr[i] + k) for k in pads]
            part_rule.setdefault(i, []).append(j)
        rule_rp[j, 3] = len(rule_pins)
    part_rule_ptr = np.zeros(n + 1, np.int64)
    part_rules = []
    for i in range(n):
        lst = sorted(set(part_rule.get(i, [])))
        part_rule_ptr[i + 1] = part_rule_ptr[i] + len(lst)
        part_rules += lst
    maxpins = max(1, int(np.max(np.diff(part_pin_ptr))) if n else 1) * 2 + 2
    maxnets = max(1, len(nets)) + 2
    ip = np.zeros(18, np.int64)
    if getattr(ann, "window", None) is not None:
        ip[I_WIN] = 1
        ip[I_WX0], ip[I_WX1], ip[I_WY0], ip[I_WY1] = ann.window
    ip[I_NCX], ip[I_NCY], ip[I_HX], ip[I_HY], ip[I_HB], ip[I_CAP], ip[I_HOFF] = P.ncx, P.ncy, HX, HY, HB, hash_cap, hoff
    ip[I_CX], ip[I_CY], ip[I_CONG] = cx, cy, 1 if use_cong else 0
    fp = np.zeros(20)
    fp[F_G], fp[F_OX], fp[F_OY] = g, P.ox, P.oy
    fp[F_CB], fp[F_CX0], fp[F_CY0], fp[F_SUP], fp[F_TGT], fp[F_NORM] = cb, cx0, cy0, sup, tgt, norm
    fp[F_A0], fp[F_S0], fp[F_W0] = ann.A0, ann.S0, ann.W0
    fp[F_SLACK], fp[F_BAR] = ann.wl_slack, ann.wl_barrier
    fp[F_WWL], fp[F_WDISP], fp[F_WCONG], fp[F_WORD] = (ann.w["wl"], ann.w["disp"], ann.w["cong"] if use_cong else 0.0,
                                                       ann.w["order"])
    fp[F_OMARGIN], fp[F_NMOV] = ann.order_margin, max(1, len(ann.mov))
    E = Eng(
        ip=ip, fp=fp, tot=np.zeros(5),
        X=np.array(ann.X, np.int64), Y=np.array(ann.Y, np.int64), K=np.array(ann.K, np.int64),
        Xs=np.array(ann.Xs, np.int64), Ys=np.array(ann.Ys, np.int64), movable=movable, side=side, nrot=nrot,
        own=own, gbrd=gbrd, opp_ptr=opp_ptr, opp_r=opp_r, brd_ptr=brd_ptr, brd_r=brd_r,
        part_r0=part_r0, part_rn=part_rn, r_box=r_box, r_side=r_side, r_owner=r_owner,
        r_span=np.zeros((R + nob, 4), np.int64), r_seen=np.zeros(R + nob, np.int64), hcnt=hcnt, hids=hids,
        SO=P.sat_out.astype(np.int64),
        pin_part=np.array(pin_part, np.int64), part_pin_ptr=part_pin_ptr, pin_off=pin_off, px=px, py=py,
        net_ptr=net_ptr, net_pins=np.array(net_pins, np.int64), w=w, frozen=frozen,
        part_net_ptr=part_net_ptr, part_nets=np.array(part_nets, np.int64), nb=np.zeros((max(1, len(nets)), 4)),
        nc=np.zeros(max(1, len(nets))), net_seen=np.zeros(max(1, len(nets)), np.int64),
        Dn=Dn, Dp=Dp, pin_esc=pin_esc, pin_bx=np.zeros(NP, np.int64), pin_by=np.zeros(NP, np.int64),
        net_box=np.zeros((max(1, len(nets)), 4)), net_dens=np.zeros(max(1, len(nets))),
        has_box=np.zeros(max(1, len(nets)), bool), cw=cw if len(cw) else np.zeros(1),
        sc_wx=np.zeros(cx + 2), sc_wy=np.zeros(cy + 2),
        rule_rp=rule_rp, rule_pins=np.array(rule_pins or [0], np.int64), open=np.zeros(max(1, len(rules))),
        part_rule_ptr=part_rule_ptr, part_rules=np.array(part_rules or [0], np.int64),
        rule_seen=np.zeros(max(1, len(rules)), np.int64),
        in_s=np.zeros(n, np.int64), sc_pins_x=np.zeros(NP + 2), sc_pins_y=np.zeros(NP + 2),
        sc_nets=np.zeros(maxnets, np.int64), sc_nb=np.zeros((maxnets, 4)), sc_nc=np.zeros(maxnets),
        sc_box=np.zeros((maxnets, 4)), sc_has=np.zeros(maxnets, bool), sc_dens=np.zeros(maxnets),
        sc_rules=np.zeros(max(1, len(rules)) + 2, np.int64), sc_open=np.zeros(max(1, len(rules)) + 2),
        sc_pbx=np.zeros(NP + 2, np.int64), sc_pby=np.zeros(NP + 2, np.int64),
        sc_oX=np.zeros(n + 2, np.int64), sc_oY=np.zeros(n + 2, np.int64), sc_oK=np.zeros(n + 2, np.int64),
        turn=turn, ring=ring, snap=snap, n_ortho=n_ortho,
    )
    # initial state: rects, pins, nets, RUDY boxes, rules, totals
    for i in P.mov:
        for m in range(part_rn[i]):
            rid = part_r0[i] + m
            E.r_box[rid] = (-(1 << 40), -(1 << 40) + 1, -(1 << 40), -(1 << 40) + 1)
        _place_rects_py(E, i)
        _update_pins(E, i)
    for t in range(nob):
        _hash_add(E, R + t)
    for net in nets:
        j = net.i
        if net_ptr[j + 1] - net_ptr[j] >= 1:
            E.nb[j] = _net_measure(E, j)
            E.nc[j] = w[j] * (E.nb[j, 1] - E.nb[j, 0] + E.nb[j, 3] - E.nb[j, 2]) if len(net.pins) >= 2 else 0.0
        if use_cong:
            c = cong.contrib.get(j)
            if c is not None:
                xs, ys = ann.nx[j], ann.ny[j]
                E.net_box[j] = (min(xs) - 0.2, max(xs) + 0.2, min(ys) - 0.2, max(ys) + 0.2)
                W = E.net_box[j, 1] - E.net_box[j, 0]
                H = E.net_box[j, 3] - E.net_box[j, 2]
                E.net_dens[j] = cong.w[j] * (W + H) / (W * H)
                E.has_box[j] = True
    for p in range(NP):
        if use_cong:
            E.pin_bx[p], E.pin_by[p] = _pin_bin(E, p)
    for j in range(len(rules)):
        E.open[j] = _order_pen(E, j)
    E.tot[T_WL] = ann.wl
    E.tot[T_LEG] = ann.total_leg()
    E.tot[T_CONG] = cong.total() if use_cong else 0.0
    E.tot[T_ORDER] = float(E.open[:len(rules)].sum()) if rules else 0.0
    E.tot[T_DISP] = float(sum(abs(ann.X[i] - ann.Xs[i]) + abs(ann.Y[i] - ann.Ys[i]) for i in ann.mov))
    return E


def _place_rects_py(E, i):
    """First registration of part i's rectangles (its boxes start far away)."""
    X, Y, k = E.X[i], E.Y[i], E.K[i]
    for m in range(E.part_rn[i]):
        rid = E.part_r0[i] + m
        if m == 0:
            a, b, c, d = E.own[i, k]
        else:
            a, b, c, d = E.opp_r[E.opp_ptr[i] + m - 1, k]
        E.r_box[rid] = (X + a, X + b, Y + c, Y + d)
        _hash_add(E, rid)


@_jit
def sample_uphill(E, parts, swap_ptr, swap_ids, n, lam, r, out):
    """The schedule's opening sample: n moves at zero temperature (downhill ones are kept, as
    in anneal.Annealer.run), uphill deltas written to out; returns how many."""
    stats = np.zeros(6, np.int64)
    m = 0
    S = np.empty(1, np.int64)
    nX = np.empty(1, np.int64)
    nY = np.empty(1, np.int64)
    nK = np.empty(1, np.int64)
    npart = parts.shape[0]
    for _ in range(n):
        i = parts[np.random.randint(npart)]
        S[0] = i
        X = E.X[i] + np.random.randint(-r, r + 1)
        Y = E.Y[i] + np.random.randint(-r, r + 1)
        X, Y = _clamp(E, i, X, Y, E.K[i])
        nX[0] = X
        nY[0] = Y
        nK[0] = E.K[i]
        acc, d = try_move(E, S, nX, nY, nK, 1, 1e-12, lam, 0.0, 1.0, False)
        if d > 0 and m < out.shape[0]:
            out[m] = d
            m += 1
    _ = stats
    return m


DELTA_BUDGET = 2e-4     # seconds of Terms.delta a physics part may cost per pick at the uniform rate


from .anneal import quarter_turns, turn_move  # noqa: E402  (anneal imports engine lazily)


class FastAnnealer:
    """anneal.Annealer's schedule and cost on the compiled engine.

    Construction builds a reference anneal.Annealer (its weights, normalizations, frozen nets,
    macros and physics bookkeeping) and the engine arrays from it. `run` alternates compiled
    batches of moves of the parts no physics term touches with Python-proposed moves of the
    others (physics parts, macro moves), priced by Terms.delta plus the engine. Same public
    surface as Annealer: run, write_back, cost, evaluate, terms_report, order_violations,
    report, stats, best_legal, X/Y/K."""

    def __init__(self, P, st, terms=None, macros=(), seed=0, subset=None, window=None, **kw):
        from .anneal import Annealer
        self.ann = Annealer(P, st, terms=terms, macros=macros, seed=seed, subset=subset, window=window, **kw)
        a = self.ann
        self.P, self.st, self.terms = P, st, terms
        self.rng = random.Random(seed)
        self.seed = seed
        self.log = a.log
        self.E = build(a)
        if self.E.ip[I_OVERFLOW]:
            self.E = build(a, hash_cap=1024)
        seed_rng(int(seed) & 0x7fffffff)
        # who may move: all movable parts, or a subset (a window re-placement)
        self.mov = list(a.active)
        self.window = window
        tp = set()
        if terms is not None:
            tp = {i for i in self.mov if a.uuid[i] in a.tparts}
        in_mac = set(a.macro_of)
        self.fast = np.array([i for i in self.mov if i not in tp and i not in in_mac], np.int64)
        self.slow = [i for i in self.mov if i in tp or i in in_mac]
        # equal-footprint swap classes among the fast parts
        fs = set(self.fast.tolist())
        n = len(P.parts)
        ptr = np.zeros(n + 1, np.int64)
        ids = []
        for i in range(n):
            cls = [j for j in a.swap_class.get(i, []) if j in fs] if i in fs else []
            ptr[i + 1] = ptr[i] + len(cls)
            ids += cls
        self.swap_ptr, self.swap_ids = ptr, np.array(ids or [0], np.int64)
        self.phys = a.phys
        self.poses = a.poses
        self.dt = {}                  # measured Terms.delta seconds per part (EMA)
        self.delta_budget = DELTA_BUDGET
        self.w = a.w
        self.stats = dict(moves=0, accepted=0, by_move={})
        self.best_legal = None
        self.A0, self.S0, self.W0, self.nstruct = a.A0, a.S0, a.W0, a.nstruct
        self.lam0, self.lam1 = a.lam0, a.lam1

    # ------------------------------------------------------------------ state views
    @property
    def X(self):
        return self.E.X

    @property
    def Y(self):
        return self.E.Y

    @property
    def K(self):
        return self.E.K

    @property
    def wl(self):
        return float(self.E.tot[T_WL])

    @property
    def leg_total(self):
        return int(round(self.E.tot[T_LEG]))

    def _pose(self, i):
        p = self.P.parts[i]
        g = self.P.g
        return (self.P.ox + int(self.E.X[i]) * g, self.P.oy + int(self.E.Y[i]) * g, p.rots[int(self.E.K[i])].rot, p.side)

    # ------------------------------------------------------------------ cost
    def cost(self, lam):
        E = self.E
        w = self.w
        disp = E.tot[T_DISP] * self.P.g / (max(1, len(self.ann.mov)) * self.S0)
        return (w["wl"] * float(_wl_cost(E, E.tot[T_WL])) + lam * E.tot[T_LEG] / self.A0 + w["disp"] * disp
                + w["phys"] * self.phys / self.nstruct + E.fp[F_WCONG] * E.tot[T_CONG] + w["order"] * E.tot[T_ORDER])

    def terms_report(self):
        E = self.E
        disp = E.tot[T_DISP] * self.P.g / (max(1, len(self.ann.mov)) * self.S0)
        out = dict(wl=round(E.tot[T_WL] / self.W0, 5), phys=round(self.phys / self.nstruct, 5),
                   cong=round(float(E.tot[T_CONG]), 6) if E.ip[I_CONG] else None, leg=self.leg_total,
                   disp=round(disp, 5))
        if self.ann.order:
            out.update(order=round(float(E.tot[T_ORDER]), 5), order_rules=len(self.ann.order),
                       order_violations=self.order_violations())
        return out

    def order_violations(self):
        a = self._sync_reference()
        return a.order_violations()

    def _sync_reference(self):
        """The reference annealer's positions follow the engine (for checks)."""
        from .anneal import Annealer
        st = self.st.copy()
        for i in self.ann.mov:
            st.X[i], st.Y[i], st.K[i] = int(self.E.X[i]), int(self.E.Y[i]), int(self.E.K[i])
        return Annealer(self.P, st, terms=None, w_cong=0.0, order=self.ann.order, order_margin=self.ann.order_margin)

    def evaluate(self, st):
        a = self.ann
        a.phys = self.phys
        return a.evaluate(st)

    # ------------------------------------------------------------------ Python-side moves
    def _pick_slow(self):
        """A part for a Python-side move. Parts whose Terms.delta is costly (aggressor loops,
        coupling and cable common-mode terms on big boards cost milliseconds) are sampled at
        min(1, DELTA_BUDGET / their measured delta time) of the uniform rate, so the physics
        parts share the time instead of a few of them taking it all."""
        rng = self.rng
        for _ in range(8):
            i = self.slow[rng.randrange(len(self.slow))]
            t = self.dt.get(i)
            if t is None or t <= self.delta_budget or rng.random() < self.delta_budget / t:
                return i
        return i

    def _propose_slow(self, r):
        a = self.ann
        rng = self.rng
        i = self._pick_slow()
        E = self.E
        mi = a.macro_of.get(i)
        u = rng.random()
        if mi is not None and u < 0.25:
            m = a.macros[mi]
            mem = [j for j in m.members if j in a.movset]
            if not mem:
                return None
            v = rng.random()
            if v < 0.6 or m.anchor not in a.movset:
                dX, dY = rng.randint(-r, r), rng.randint(-r, r)
                return mem, [(int(E.X[j]) + dX, int(E.Y[j]) + dY, int(E.K[j])) for j in mem], "macro_shift"
            A = m.anchor
            AX, AY = int(E.X[A]), int(E.Y[A])
            if v < 0.7 or len(m.layouts) < 2:
                q = rng.choice((1, 2, 3))
                out = []
                for j in mem:
                    dx, dy = int(E.X[j]) - AX, int(E.Y[j]) - AY
                    for _ in range(q):
                        dx, dy = dy, -dx
                    out.append((AX + dx, AY + dy, self.P.parts[j].turn[int(E.K[j])][q]))
                return mem, out, "macro_rotate"
            lay = m.layouts[rng.randrange(len(m.layouts))]
            q = quarter_turns(self.P.parts[A], int(E.K[A]), lay.offsets[A][2])
            out = []
            for j in mem:
                dx, dy, k = lay.offsets[j]
                dx -= lay.offsets[A][0]
                dy -= lay.offsets[A][1]
                for _ in range(q):
                    dx, dy = dy, -dx
                out.append((AX + dx, AY + dy, self.P.parts[j].turn[k][q]))
            return mem, out, "macro_relayout"
        if u < 0.62 or (u < 0.80 and a.nrot[i] <= 1):
            X = int(E.X[i]) + rng.randint(-r, r)
            Y = int(E.Y[i]) + rng.randint(-r, r)
            X, Y = _clamp(E, i, X, Y, int(E.K[i]))
            return [i], [(int(X), int(Y), int(E.K[i]))], "shift"
        if u < 0.80:
            k0 = int(E.K[i])
            k1, kind = turn_move(self.P.parts[i], k0, rng)
            cx0, cy0 = a._center2(i, k0)
            cx1, cy1 = a._center2(i, k1)
            X, Y = _clamp(E, i, int(E.X[i]) + (cx0 - cx1) // 2, int(E.Y[i]) + (cy0 - cy1) // 2, k1)
            return [i], [(int(X), int(Y), k1)], kind
        j = self.mov[rng.randrange(len(self.mov))]
        if j == i or a.side[j] != a.side[i]:
            X = int(E.X[i]) + rng.randint(-r, r)
            Y = int(E.Y[i]) + rng.randint(-r, r)
            X, Y = _clamp(E, i, X, Y, int(E.K[i]))
            return [i], [(int(X), int(Y), int(E.K[i]))], "shift"
        ki, kj = int(E.K[i]), int(E.K[j])
        ci, cj = a._center2(i, ki), a._center2(j, kj)
        Xi, Yi = _clamp(E, i, int(E.X[j]) + (cj[0] - ci[0]) // 2, int(E.Y[j]) + (cj[1] - ci[1]) // 2, ki)
        Xj, Yj = _clamp(E, j, int(E.X[i]) + (ci[0] - cj[0]) // 2, int(E.Y[i]) + (ci[1] - cj[1]) // 2, kj)
        return [i, j], [(int(Xi), int(Yi), ki), (int(Xj), int(Yj), kj)], "swap"

    def _try_python(self, S, newpos, T, lam, kind):
        a = self.ann
        d_phys = 0.0
        moved_u = [a.uuid[i] for i in S if a.uuid[i] in a.tparts]
        g = self.P.g
        if moved_u:
            newp = {}
            for i, (X, Y, K) in zip(S, newpos):
                p = self.P.parts[i]
                newp[a.uuid[i]] = (self.P.ox + X * g, self.P.oy + Y * g, p.rots[K].rot, p.side)
            t0 = time.perf_counter()
            d_phys = self.terms.delta(self.poses, moved_u, {u: newp[u] for u in moved_u})
            dt = time.perf_counter() - t0
            if len(S) == 1:
                i = S[0]
                self.dt[i] = dt if i not in self.dt else 0.8 * self.dt[i] + 0.2 * dt
        Sa = np.array(S, np.int64)
        nX = np.array([q[0] for q in newpos], np.int64)
        nY = np.array([q[1] for q in newpos], np.int64)
        nK = np.array([q[2] for q in newpos], np.int64)
        acc, d = try_move(self.E, Sa, nX, nY, nK, len(S), T, lam, self.w["phys"] * d_phys / self.nstruct,
                          self.rng.random(), False)
        st = self.stats
        st["moves"] += 1
        bm = st["by_move"].setdefault(kind, [0, 0])
        bm[0] += 1
        if acc:
            st["accepted"] += 1
            bm[1] += 1
            self.phys += d_phys
            for i in S:
                self.poses[a.uuid[i]] = self._pose(i)
        return acc, d

    # ------------------------------------------------------------------ schedule
    def run(self, cpu_s, moves_per_part=4000, max_moves=None, log_every=0.25, batch=2000, max_per_part=20000,
            deadline=None):
        """The reference schedule over N = moves_per_part x parts planned moves; when the
        compiled engine is fast enough to do more within cpu_s (measured on the first
        batches), N grows up to max_per_part x parts (a slower cooling at no extra time)."""
        n = len(self.mov)
        if n == 0:
            return self.report(0.0)
        N = max_moves or moves_per_part * n
        adaptive = max_moves is None
        t0 = time.process_time()
        r0 = max(2, int(0.25 * self.ann._span()))
        ups = np.zeros(400)
        m = 0
        if len(self.fast):
            m = sample_uphill(self.E, self.fast, self.swap_ptr, self.swap_ids, min(200, 20 * n), self.lam0, r0, ups)
        ups = sorted(ups[:m].tolist())
        if not ups and self.slow:
            for _ in range(min(200, 20 * n)):
                mv = self._propose_slow(r0)
                if mv is None:
                    continue
                acc, d = self._try_python(mv[0], mv[1], 1e-12, self.lam0, mv[2])
                if d > 0:
                    ups.append(d)
            ups.sort()
        T0 = ups[len(ups) // 2] / math.log(1 / 0.3) if ups else 1e-3
        T1 = T0 * 1e-4
        self.T0 = T0
        self.stats = dict(moves=0, accepted=0, by_move={})
        fstats = np.zeros(6, np.int64)
        share_fast = len(self.fast) / n
        done = 0
        next_log = log_every
        best = None
        w0 = time.monotonic()
        wall = (deadline - w0) if deadline is not None else None
        while done < N:
            # cool on whichever runs out first: planned moves, CPU budget or wall time, so a
            # run cut short by its budget still ends cold (not at a random hot state)
            frac = done / N
            el = time.process_time() - t0
            tf = el / cpu_s if cpu_s > 0 else 0.0
            if wall:
                tf = max(tf, (time.monotonic() - w0) / wall)
            if tf > frac + 0.02:          # only when a budget binds (a seeded run stays repeatable)
                frac = tf
            if frac >= 1.0:
                break
            T = T0 * (T1 / T0) ** frac
            self.T_last = T
            lam = self.lam0 * (self.lam1 / self.lam0) ** frac
            r = max(1, int(r0 * (T / T0) ** 0.5))
            nf = int(round(batch * share_fast))
            if nf and len(self.fast):
                run_batch(self.E, self.fast, self.swap_ptr, self.swap_ids, nf, T, lam, r, fstats)
                if self.E.ip[I_OVERFLOW]:
                    self._rebuild()
            for _ in range(batch - nf if self.slow else 0):
                mv = self._propose_slow(r)
                if mv is None:
                    continue
                self._try_python(mv[0], mv[1], T, lam, mv[2])
            done += batch
            if adaptive and done == 4 * batch:
                el = time.process_time() - t0
                if el > 0:
                    N = int(max(N, min(max_per_part * n, 0.85 * (done / el) * cpu_s)))
            if self.leg_total == 0:
                c = self.cost(lam)
                if best is None or c < best[0]:
                    best = (c, self.E.X.copy(), self.E.Y.copy(), self.E.K.copy())
            if done / N >= next_log:
                next_log += log_every
                self.log(f"anneal {100 * done / N:.0f}% T={T:.2e} lam={lam:.1f} r={r} wl={self.wl:.1f} "
                         f"phys={self.phys:.3f} leg={self.leg_total}")
        # a run whose budget went to overheads before it could cool ends with a short quench
        if getattr(self, "T_last", T0) > 10 * T1:
            self.T_last = T1
            for _ in range(5):
                nf = int(round(batch * share_fast))
                if nf and len(self.fast):
                    run_batch(self.E, self.fast, self.swap_ptr, self.swap_ids, nf, T1, self.lam1, 1, fstats)
                for _ in range(min(200, batch - nf) if self.slow else 0):
                    mv = self._propose_slow(1)
                    if mv is not None:
                        self._try_python(mv[0], mv[1], T1, self.lam1, mv[2])
                done += batch
        for k, name in enumerate(("shift", "rotate", "swap")):
            bm = self.stats["by_move"].setdefault(name, [0, 0])
            bm[0] += int(fstats[2 * k])
            bm[1] += int(fstats[2 * k + 1])
        self.stats["moves"] += int(fstats[0] + fstats[2] + fstats[4])
        self.stats["accepted"] += int(fstats[1] + fstats[3] + fstats[5])
        self.final_lam = self.lam0 * (self.lam1 / self.lam0) ** min(1.0, done / N)
        self.best_legal = best
        return self.report(time.process_time() - t0, planned=N, done=done)

    def _rebuild(self):
        """Hash bucket overflow: rebuild the engine from the current state with room to spare."""
        a = self.ann
        for i in a.mov:
            a.X[i], a.Y[i], a.K[i] = int(self.E.X[i]), int(self.E.Y[i]), int(self.E.K[i])
        cap = int(self.E.ip[I_CAP]) * 4
        tot = self.E.tot.copy()
        Xs, Ys = self.E.Xs.copy(), self.E.Ys.copy()
        self.E = build(a, hash_cap=cap)
        self.E.Xs[:] = Xs
        self.E.Ys[:] = Ys
        _ = tot

    def report(self, cpu, planned=0, done=0):
        return dict(cpu_s=round(cpu, 2), planned_moves=planned, moves=done,
                    moves_per_s=round(done / cpu) if cpu > 0 else None,
                    accept=round(self.stats["accepted"] / max(1, self.stats["moves"]), 3),
                    by_move={k: dict(tried=v[0], accepted=v[1]) for k, v in self.stats["by_move"].items()},
                    hpwl=round(self.wl, 2), physics=round(self.phys, 4), leg_cells=self.leg_total,
                    T0=getattr(self, "T0", None), engine="compiled",
                    fast_parts=int(len(self.fast)), python_parts=len(self.slow))

    def write_back(self, use_best_legal=False):
        X, Y, K = self.E.X, self.E.Y, self.E.K
        if use_best_legal and self.best_legal is not None:
            _, X, Y, K = self.best_legal
        for i in self.ann.mov:
            self.st.X[i], self.st.Y[i], self.st.K[i] = int(X[i]), int(Y[i]), int(K[i])
