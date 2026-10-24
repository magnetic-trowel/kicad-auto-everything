# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Whole-net DC resistance between pads, all layers (venv Python).

The copper of a net (zone fills + pads + tracks + vias, from a kicad_dump.py dump) is
rasterised per copper layer; in-plane neighbours conduct 1/square, plated holes of the
net (vias, PTH pads) link the layers with a total conductance VIA_G (1/squares; a
0.3 mm via in 1.6 mm FR4 with 25 um plating is ~2 squares of 1 oz copper). Every pad of
the net is one equipotential terminal over all its layers. Returns the effective
resistance between all pad pairs (squares; inf when not connected through copper).
"""
import json
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy import ndimage as ndi

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from board import Grid, rings_to_shapely  # noqa: E402,F401

VIA_G = 0.5


def net_rasters(d, net, grid):
    layers = d["layers"]
    li = {l: k for k, l in enumerate(layers)}
    L = len(layers)
    cu = np.zeros((L,) + grid.shape, bool)
    term = np.zeros((L,) + grid.shape, np.int32)
    pads = {}
    for z in d["zones"]:
        if z["net"] != net:
            continue
        for ln, fl in z["fills"].items():
            grid.raster(fl, cu[li[ln]])
    holes_xy = []
    for it in d["items"]:
        if it["net"] != net:
            continue
        k = li[it["layer"]]
        m = grid.raster(it["poly"])
        cu[k] |= m
        if it["kind"] == "pad":
            key = (it["ref"], it["pad"])
            pads.setdefault(key, len(pads) + 1)
            term[k][m] = pads[key]
        if it["kind"] in ("pad", "via"):
            holes_xy.append((it["x"], it["y"]))
    links = np.zeros((max(L - 1, 0),) + grid.shape, np.float64)
    hx = {(round(x, 3), round(y, 3)) for x, y in holes_xy}
    for h in d["holes"]:
        if not h["plated"] or (round(h["x"], 3), round(h["y"], 3)) not in hx:
            continue
        m = grid.disc(h["x"], h["y"], max(h["d"] / 2, 0.75 * grid.g), np.zeros(grid.shape, bool))
        n = max(int(m.sum()), 1)
        for k in range(L - 1):
            both = m & cu[k] & cu[k + 1]
            links[k][both] += VIA_G * (L - 1) / n  # series over L-1 segments
    return cu, term, links, pads


def effective_resistance_3d(cu, term, links):
    """cu (L,H,W) bool conductors, term (L,H,W) int terminal ids (0 none), links
    (L-1,H,W) vertical conductances. Returns (T x T) effective resistance."""
    T = int(term.max())
    R = np.full((T, T), np.inf)
    np.fill_diagonal(R, 0.0)
    if T < 2:
        return R
    L, H, W = cu.shape
    reg = cu | (term > 0)
    # connectivity including vertical links
    struct = np.zeros((3, 3, 3), bool)
    struct[1, 1, :] = struct[1, :, 1] = True
    vl = np.zeros_like(reg)
    if L > 1:
        lk = links > 0
        vl[:-1] |= lk
        vl[1:] |= lk
    lab2d = np.zeros(reg.shape, np.int64)
    off = 0
    for k in range(L):
        l, n = ndi.label(reg[k])
        lab2d[k] = np.where(l > 0, l + off, 0)
        off += n
    # union-find over 2-D components through links and shared terminals
    parent = np.arange(off + 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    for k in range(L - 1):
        m = (links[k] > 0) & (lab2d[k] > 0) & (lab2d[k + 1] > 0)
        for a, b in set(zip(lab2d[k][m].tolist(), lab2d[k + 1][m].tolist())):
            union(a, b)
    tcomp = {}
    for t in range(1, T + 1):
        cs = np.unique(lab2d[term == t])
        cs = cs[cs > 0]
        for c in cs[1:]:
            union(cs[0], c)
        tcomp[t] = cs[0] if len(cs) else None
    roots = {}
    for t, c in tcomp.items():
        if c is not None:
            roots.setdefault(find(c), []).append(t)
    comp_root = np.array([find(a) for a in range(off + 1)])
    for root, tids in roots.items():
        if len(tids) < 2:
            continue
        sel = (lab2d > 0) & (comp_root[lab2d] == root)
        node = -np.ones(reg.shape, np.int64)
        free = sel & (term == 0)
        nf = int(free.sum())
        node[free] = np.arange(nf)
        tmap = {t: nf + k for k, t in enumerate(tids)}
        for t, k in tmap.items():
            node[sel & (term == t)] = k
        N = nf + len(tids)
        r_, c_, w_ = [], [], []
        for a, b in ((node[:, :, :-1], node[:, :, 1:]), (node[:, :-1, :], node[:, 1:, :])):
            m = (a >= 0) & (b >= 0) & (a != b)
            r_.append(a[m]); c_.append(b[m]); w_.append(np.ones(int(m.sum())))
        if L > 1:
            a, b = node[:-1], node[1:]
            m = (a >= 0) & (b >= 0) & (a != b) & (links > 0)
            r_.append(a[m]); c_.append(b[m]); w_.append(links[m])
        r = np.concatenate(r_); c = np.concatenate(c_); w = np.concatenate(w_)
        A = sp.coo_matrix((w, (r, c)), shape=(N, N)).tocsr()
        A = A + A.T
        Lp = (sp.diags(np.asarray(A.sum(1)).ravel()) - A).tocsc()
        g0 = tmap[tids[0]]
        keep = np.r_[0:g0, g0 + 1:N]
        lu = spla.splu(Lp[keep][:, keep].tocsc())
        tn = [tmap[t] for t in tids[1:]]
        rows = np.array([n if n < g0 else n - 1 for n in tn])
        Xt = np.zeros((len(tn), len(tn)))
        for c0 in range(0, len(tn), 64):
            cols = np.arange(c0, min(c0 + 64, len(tn)))
            B = np.zeros((N - 1, len(cols)))
            B[rows[cols], np.arange(len(cols))] = 1.0
            Xt[:, cols] = lu.solve(B)[rows, :]
        dg = np.diag(Xt)
        ids = np.array(tids) - 1
        R[ids[0], ids[1:]] = dg
        R[ids[1:], ids[0]] = dg
        R[np.ix_(ids[1:], ids[1:])] = dg[:, None] + dg[None, :] - 2 * Xt
    return R


def net_resistance(d, net, g=0.1, grid=None):
    grid = grid or Grid(d["bbox"], g)
    cu, term, links, pads = net_rasters(d, net, grid)
    R = effective_resistance_3d(cu, term, links)
    iu = np.triu_indices(len(pads), 1)
    rv = R[iu]
    con = np.isfinite(rv)
    return dict(pads=len(pads), pairs=int(len(rv)), connected=int(con.sum()),
                R_mean=float(rv[con].mean()) if con.any() else None,
                R_median=float(np.median(rv[con])) if con.any() else None,
                R_max=float(rv[con].max()) if con.any() else None,
                copper_mm2=float(cu.sum() * grid.g ** 2)), R, list(pads)


if __name__ == "__main__":
    d = json.load(open(sys.argv[1]))
    for n in sys.argv[2:]:
        print(n, net_resistance(d, n)[0])
