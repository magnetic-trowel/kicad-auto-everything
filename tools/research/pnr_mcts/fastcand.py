# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast candidate poses: same result as `Kit.candidates`, without the FFT legal map.

`Kit.candidates` builds a full legality map per orientation (FFT correlation, ~50 ms on a
500x350 grid) and then takes the k cheapest legal origins. Here the cost map (HPWL is
separable, so it is cheap) is partially sorted and origins are tested for legality one by
one in cost order (a few microseconds each in numba) until k spread-out legal origins are
found; only if that runs long do we fall back to the full map.
"""
import numpy as np
from numba import njit

from placekit import corr


@njit(cache=True)
def _scan(order, start, nk, W, H, occ, okstat, keep, k, nms, out):
    """Walk flat origin indices order[start:]; keep legal ones at least `nms` cells apart
    (Chebyshev) from the nk already kept in `out`. Returns the number kept (<= k)."""
    for t in range(start, order.shape[0]):
        f = order[t]
        cy = f // W
        cx = f - cy * W
        if not okstat[cy, cx]:
            continue
        skip = False
        for j in range(nk):
            g = out[j]
            gy = g // W
            gx = g - gy * W
            if abs(cx - gx) < nms and abs(cy - gy) < nms:
                skip = True
                break
        if skip:
            continue
        ok = True
        for i in range(keep.shape[0]):  # (plane, dx, dy); off-grid keep-out is fine
            x = cx + keep[i, 1]
            y = cy + keep[i, 2]
            if x >= 0 and y >= 0 and x < W and y < H and occ[keep[i, 0], y, x] > 0:
                ok = False
                break
        if ok:
            out[nk] = f
            nk += 1
            if nk >= k:
                break
    return nk


def candidates(kit, pi, rots=range(4), k=8, cost_extra=None, nms_cells=None):
    """Drop-in for Kit.candidates (no legal_extra): top-k legal poses per orientation by
    HPWL (+ cost_extra), spread by non-maximum suppression, sorted by cost."""
    w = kit.w
    part = w.parts[pi]
    nms = nms_cells or max(3, int(1.0 / w.g))
    occ = w.court
    out = []
    buf = np.zeros(k, np.int64)
    cache = part.cache.setdefault("_fast", {})
    n = w.H * w.W
    for ri in rots:
        if ri not in cache:
            rr = w.part_raster(part, ri)
            rng = np.random.default_rng(0)  # random offset order: overlaps are rejected fast
            keep = np.concatenate([np.concatenate([np.full((len(c), 1), pl, np.int32), c], 1)
                                   for pl, c in rr["keep"]]).astype(np.int32)
            # static part of legality (pad copper inside the edge clearance), once per pose
            okstat = (corr(~w.ok_cu, rr["cu"]) < 0.5) if len(rr["cu"]) else np.ones((w.H, w.W), bool)
            cache[ri] = (np.ascontiguousarray(keep[rng.permutation(len(keep))]), okstat)
        keep, okstat = cache[ri]
        c = kit.hpwl_map(pi, ri)
        if cost_extra is not None:
            c = c + cost_extra(pi, ri)
        flat = c.ravel()
        m = min(n, 4096 * max(1, k // 2))
        lo = 0
        nk = 0
        while True:
            if m >= n:
                order = np.argsort(flat, kind="stable")
            else:
                part_idx = np.argpartition(flat, m)[:m]
                order = part_idx[np.argsort(flat[part_idx], kind="stable")]
            # the first `lo` entries are the same cells as last round (ties aside)
            nk = _scan(order.astype(np.int64), lo, nk, w.W, w.H, occ, okstat, keep, k, nms, buf)
            if nk >= k or m >= n:
                break
            lo = m
            m = min(n, m * 4)
        for j in range(nk):
            f = int(buf[j])
            cy, cx = divmod(f, w.W)
            out.append((float(flat[f]), cx, cy, ri))
    out.sort()
    return out
