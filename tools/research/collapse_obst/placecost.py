# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Obstruction measures as functions of placement, for use inside a placer.

    import sys; sys.path.insert(0, ".../tools/research/collapse_obst")
    from placecost import capacity_overflow, bus_lds, bus_pairs

    capacity_overflow(world)                  # world: pnr World with parts placed
    bus_pairs(world)                          # [(part_a, part_b, n_nets), ...]
    bus_lds(world, a, b, rot_a=90, rot_b=None)

capacity_overflow: for rectangular rings around every part (through each pad row and
outward) and circles on a grid, nets with pads strictly on both sides must cross; each
crossing takes w + c of free cut length on some layer (pads block their own layers).
Returns the worst local demand in layers (1.0 = the cut needs one full layer of
tracks) and the total overflow in mm of track pitch against the board's layer count.

bus_lds: pins of the two-pin nets joining two parts, ordered across the axis between
the parts. In the strip between two facing pin rows, via-free routing needs LDS layers
(longest decreasing subsequence of the pin permutation), and 2 layers fit
lambda_1 + lambda_2 nets (Greene); the rest need vias. Rotations are tried about each
footprint origin with positions fixed.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import obst  # noqa: E402

ROTS = (0.0, 90.0, 180.0, 270.0)
_CACHE = {}


# ------------------------------------------------------------------ board adapters
def board_from_world(world):
    """obst.Board for a pnr World, re-posed to the world's current part poses. The
    pad geometry is computed once per World data and cached."""
    key = id(world.data)
    B = _CACHE.get(key)
    if B is None:
        B = obst.Board(world.data)
        _CACHE[key] = B
    poses = {}
    for pi, (cx, cy, ri) in world.pose.items():
        x, y = world.xy(cx, cy)
        fx, fy = world.frac.get(pi, (0.0, 0.0))
        p = world.parts[pi]
        rot = p.rot0 if ri >= len(ROTS) else ROTS[ri]
        poses[pi] = (x + fx, y + fy, rot)
    B.set_poses(poses)
    return B


# ------------------------------------------------------------------ capacity
def capacity_board(B, layers=None, circles=True, spacing=None, key="all"):
    """Capacity measures for an obst.Board at its current poses.
    key: 'all' nets or 'nopour' (nets owning a zone left to planes)."""
    L = layers or B.layers
    recs = obst.part_rings(B)
    if circles:
        recs += obst.circle_cuts(B, spacing=spacing)
    worst, wdesc, over, nover, ncuts = 0.0, None, 0.0, 0, 0
    alld, allL = [], []
    for desc, ev in recs:
        e = ev[key]
        d = np.where(np.isfinite(e["d"]), e["d"], 1e3)
        alld.append(d)
        allL.append(e["L"])
        if len(d):
            i = int(np.argmax(d))
            if d[i] > worst:
                where = list(desc[:-1]) + [float(np.asarray(desc[-1])[i])]
                worst, wdesc = float(d[i]), dict(where=where, n=int(e["n"][i]))
        need = e["n"] * B.p_lb
        cap = e["fF"] + (e["fB"] if L >= 2 else 0) + max(L - 2, 0) * e["fI"]
        ex = np.maximum(need - cap, 0)
        over += float(ex.sum())
        nover += int((ex > 0).sum())
        ncuts += len(ex)
    alld = np.concatenate(alld) if alld else np.zeros(1)
    allL = np.concatenate(allL) if allL else np.ones(1)
    # L_bound: forced layers from the worst cut; cuts_d50: cuts needing half a layer or more
    return dict(max_demand=worst, worst=wdesc, overflow_mm=over, cuts_over=nover, cuts=ncuts,
                L_bound=float(allL.max()), cuts_d50=int((alld >= 0.5).sum()),
                p99_demand=float(np.quantile(alld, 0.99)))


def capacity_overflow(world, layers=None, circles=True, spacing=None, key="all"):
    """Placement cost: capacity measures of a pnr World at its current poses.
    Rings only (circles=False) is ~10x cheaper; use it inside tight loops."""
    return capacity_board(board_from_world(world), layers, circles, spacing, key)


# ------------------------------------------------------------------ bus LDS
def _lds_stats(sa, sb):
    order = np.argsort(sa, kind="stable")
    rank_b = np.argsort(np.argsort(np.asarray(sb)[order], kind="stable"), kind="stable")
    shape = obst.rsk_shape(list(rank_b))
    n = len(sa)
    return dict(nets=n, lds=len(shape), fit2=sum(shape[:2]), forced_2layer=n - sum(shape[:2]))


def bus_nets(B, fa, fb):
    """(pad index on fa, pad index on fb) for two-pin nets joining footprints fa, fb."""
    out = []
    for n in range(B.nn):
        idx = B.ci[B.net[B.ci] == n]
        if len(idx) != 2:
            continue
        a, b = idx
        if B.fp[a] == fb and B.fp[b] == fa:
            a, b = b, a
        if B.fp[a] == fa and B.fp[b] == fb:
            out.append((a, b))
    return out


def pairs_board(B, min_nets=4):
    cnt = {}
    for n in range(B.nn):
        idx = B.ci[B.net[B.ci] == n]
        if len(idx) == 2 and B.fp[idx[0]] != B.fp[idx[1]]:
            k = tuple(sorted((int(B.fp[idx[0]]), int(B.fp[idx[1]]))))
            cnt[k] = cnt.get(k, 0) + 1
    return sorted([(a, b, c) for (a, b), c in cnt.items() if c >= min_nets], key=lambda t: -t[2])


def lds_board(B, fa, fb, rot_a=None, rot_b=None, mirror_a=False, mirror_b=False, nets=None):
    """LDS stats of the bus between footprints fa, fb with optional rotation override
    (degrees, about the footprint origin) and mirror (part flipped to the other side)."""
    nets = nets if nets is not None else bus_nets(B, fa, fb)
    if not nets:
        return None
    ia = np.array([a for a, _ in nets])
    ib = np.array([b for _, b in nets])

    def pos(fi, idx, rot, mirror):
        f = B.fps[fi]
        lx = -B.lx[idx] if mirror else B.lx[idx]
        r = f["rot"] if rot is None else rot
        x, y = obst.kicad_rot(lx, B.ly[idx], r)
        return x + f["x"], y + f["y"]

    xa, ya = pos(fa, ia, rot_a, mirror_a)
    xb, yb = pos(fb, ib, rot_b, mirror_b)
    u = np.array([B.fps[fb]["x"] - B.fps[fa]["x"], B.fps[fb]["y"] - B.fps[fa]["y"]])
    if np.hypot(*u) == 0:
        return None
    perp = np.array([-u[1], u[0]]) / np.hypot(*u)
    return _lds_stats(xa * perp[0] + ya * perp[1], xb * perp[0] + yb * perp[1])


def bus_pairs(world, min_nets=4):
    """[(part_a, part_b, n_two_pin_nets)] for part pairs joined by >= min_nets nets."""
    return pairs_board(board_from_world(world), min_nets)


def bus_lds(world, part_a, part_b, rot_a=None, rot_b=None, mirror_a=False, mirror_b=False):
    """Via-free layers (LDS) and forced 2-layer jumpers of the bus between two parts of
    a pnr World; rot_* overrides the current orientation (degrees)."""
    return lds_board(board_from_world(world), part_a, part_b, rot_a, rot_b, mirror_a, mirror_b)


def best_orientations(B, fa, fb, mirror=False):
    """LDS for every rotation pair (and mirror, if asked); returns (current, best, table)."""
    nets = bus_nets(B, fa, fb)
    cur = lds_board(B, fa, fb, nets=nets)
    if cur is None:  # coincident footprint origins: no axis between the parts
        return None
    table = []
    for ma in ((False, True) if mirror else (False,)):
        for mb in ((False, True) if mirror else (False,)):
            for ra in ROTS:
                for rb in ROTS:
                    s = lds_board(B, fa, fb, ra, rb, ma, mb, nets=nets)
                    table.append(((ra, rb, ma, mb), s["lds"], s["forced_2layer"]))
    best = min(table, key=lambda t: (t[1], t[2]))
    return cur, best, table
