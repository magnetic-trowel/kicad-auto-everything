# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Coarse streamline trees -> fine (0.1 mm) cell paths for the pnr engine, with
line-of-sight shortcutting against the net's foreign halos (string pulling)."""
import numpy as np
from numba import njit


@njit(cache=True)
def _line_free(l, y0, x0, y1, x1, net, blockT, DT, occT):
    n = max(abs(y1 - y0), abs(x1 - x0))
    for i in range(n + 1):
        t = i / n if n > 0 else 0.0
        y = int(round(y0 + (y1 - y0) * t))
        x = int(round(x0 + (x1 - x0) * t))
        if blockT[l, y, x]:
            return False
        if DT[l, y, x] - (1 if occT[net, l, y, x] > 0 else 0) > 0:
            return False
    return True


def _line(l, y0, x0, y1, x1):
    n = max(abs(y1 - y0), abs(x1 - x0))
    if n == 0:
        return np.array([[l, y0, x0]], np.int32)
    t = np.arange(n + 1) / n
    ys = np.round(y0 + (y1 - y0) * t).astype(np.int32)
    xs = np.round(x0 + (x1 - x0) * t).astype(np.int32)
    return np.stack([np.full(n + 1, l, np.int32), ys, xs], 1)


def _nearest_term(terms, l, y, x):
    tl = terms[terms[:, 0] == l]
    if len(tl) == 0:
        tl = terms
    d = (tl[:, 1] - y) ** 2 + (tl[:, 2] - x) ** 2
    return tl[int(np.argmin(d))]


def tree_to_fine(w, F, net, tree, pins, src, shortcut=True):
    """tree: list (one per sink pin, src skipped) of coarse node arrays or None."""
    s = F.s
    terms = []
    for pi, k in w.net_pins[net]:
        if pi not in w.pose:
            continue
        t = np.array(w.terminals(pi, k), np.int32).reshape(-1, 3)
        t = t[(t[:, 1] >= 0) & (t[:, 2] >= 0) & (t[:, 1] < w.H) & (t[:, 2] < w.W)]
        if len(t):
            terms.append(t)
    sinks = [i for i in range(len(pins)) if i != src]
    src_set = set(pins[src].tolist())
    out = []
    for i, nodes in zip(sinks, tree):
        if nodes is None:
            out.append(None)
            continue
        l, y, x = F.unravel(nodes)
        cy = np.minimum(y * s + s // 2, w.H - 1)
        cx = np.minimum(x * s + s // 2, w.W - 1)
        pts = [tuple(_nearest_term(terms[i], l[0], cy[0], cx[0]))]
        for j in range(len(nodes)):
            pts.append((int(l[j]), int(cy[j]), int(cx[j])))
        if int(nodes[-1]) in src_set:
            pts.append(tuple(_nearest_term(terms[src], l[-1], cy[-1], cx[-1])))
        pts = [tuple(int(v) for v in p) for p in pts]
        if shortcut:
            pts = _pull(pts, net, w)
        segs = []
        for a, b in zip(pts[:-1], pts[1:]):
            if a[0] != b[0]:  # via: change layer at a's (y, x), then go on
                seg = np.array([[a[0], a[1], a[2]], [b[0], a[1], a[2]]], np.int32)
                seg = np.concatenate([seg, _line(b[0], a[1], a[2], b[1], b[2])[1:]])
            else:
                seg = _line(a[0], a[1], a[2], b[1], b[2])
            segs.append(seg if not segs else seg[1:])
        p = np.concatenate(segs) if segs else np.array([pts[0]], np.int32)
        # drop consecutive duplicates
        keep = np.r_[True, np.any(np.diff(p, axis=0) != 0, axis=1)]
        out.append(np.ascontiguousarray(p[keep], np.int32))
    return out


def _pull(pts, net, w):
    """Greedy line-of-sight: from each kept point jump to the farthest later point on the
    same layer (before the next layer change) reachable by a free straight line."""
    out = [pts[0]]
    i = 0
    n = len(pts)
    while i < n - 1:
        j_best = i + 1
        lay = pts[i][0]
        j = i + 1
        while j < n and pts[j][0] == lay:
            if _line_free(lay, pts[i][1], pts[i][2], pts[j][1], pts[j][2], net, w.blockT, w.DT, w.occT):
                j_best = j
            j += 1
        out.append(pts[j_best])
        i = j_best
    return out
