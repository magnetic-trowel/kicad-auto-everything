# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pour partitions on real boards (venv Python; KiCad steps call kicad_dump.py).

    python board.py BOARD_ID LAYER [LAYER ...] [--g 0.1] [--kernel iso|oct|both]
                    [--mode iso_area|demand] [--tag TAG]

For each layer: the pour nets are the nets with human zone fill there. Phases = those
nets + "free". Human placement, tracks, vias and pads stay as obstacles (foreign copper
bloated by the zone clearance, holes by the hole clearance, the edge band); the
pour's own pads/vias/tracks on that layer are pinned to its phase and are its
terminals. Targets: the human copper area per net (iso_area) or the human total split
in proportion to terminal count (demand). The MBO partition is written back as KiCad
zones (each clones the human zone's settings), refilled by KiCad, and the human
(refilled) and MBO fills are scored by the same code: copper area, fill islands,
split-boundary length and effective resistance between terminals (Laplace on the
copper, sheet resistance units = squares).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import contourpy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
from shapely.geometry import MultiPolygon, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mbo import MBO, schedule  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TASKS = os.path.join(ROOT, "kae-work", "tasks")
WORK = os.path.join(ROOT, "kae-work", "pour")
KPY = "/usr/bin/python3"


def kicad(*args):
    r = subprocess.run([KPY, os.path.join(HERE, "kicad_dump.py"), *args],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- rasterization
class Grid:
    def __init__(self, bbox, g, margin=0.5):
        self.g = g
        self.x0, self.y0 = bbox[0] - margin, bbox[1] - margin
        self.W = int(np.ceil((bbox[2] - bbox[0] + 2 * margin) / g))
        self.H = int(np.ceil((bbox[3] - bbox[1] + 2 * margin) / g))
        self.shape = (self.H, self.W)

    def raster(self, polys, out=None):
        """polys: [[outer, hole, ...], ...] -> bool mask (cell centres inside)."""
        m = np.zeros(self.shape, bool) if out is None else out
        g = self.g
        for rings in polys:
            o = np.asarray(rings[0])
            if len(o) < 3:
                continue
            i0 = max(int((o[:, 0].min() - self.x0) / g) - 1, 0)
            i1 = min(int((o[:, 0].max() - self.x0) / g) + 2, self.W)
            j0 = max(int((o[:, 1].min() - self.y0) / g) - 1, 0)
            j1 = min(int((o[:, 1].max() - self.y0) / g) + 2, self.H)
            if i1 <= i0 or j1 <= j0:
                continue
            xs = self.x0 + (np.arange(i0, i1) + 0.5) * g
            ys = self.y0 + (np.arange(j0, j1) + 0.5) * g
            X, Y = np.meshgrid(xs, ys)
            P = np.c_[X.ravel(), Y.ravel()]
            ins = Path(o).contains_points(P)
            for h in rings[1:]:
                if len(h) >= 3:
                    ins ^= Path(np.asarray(h)).contains_points(P)
            m[j0:j1, i0:i1] |= ins.reshape(X.shape)
        return m

    def disc(self, x, y, r, out):
        g = self.g
        i0, i1 = int((x - r - self.x0) / g) - 1, int((x + r - self.x0) / g) + 2
        j0, j1 = int((y - r - self.y0) / g) - 1, int((y + r - self.y0) / g) + 2
        i0, j0 = max(i0, 0), max(j0, 0)
        xs = self.x0 + (np.arange(i0, i1) + 0.5) * g
        ys = self.y0 + (np.arange(j0, j1) + 0.5) * g
        X, Y = np.meshgrid(xs, ys)
        out[j0:j1, i0:i1] |= (X - x) ** 2 + (Y - y) ** 2 <= r * r
        return out

    def dilate(self, m, r):
        if r <= 0:
            return m
        return ndi.distance_transform_edt(~m) * self.g <= r

    def to_polys(self, mask, simplify=0.03):
        """bool mask -> shapely (Multi)Polygon in mm via filled contours at 0.5."""
        z = np.pad(mask.astype(float), 1)
        gen = contourpy.contour_generator(z=z, fill_type="OuterOffset")
        polys = []
        pts_list, offs_list = gen.filled(0.5, 2.0)
        for pts, offs in zip(pts_list, offs_list):
            rings = [pts[offs[k]:offs[k + 1]] for k in range(len(offs) - 1)]
            rings = [np.c_[self.x0 + (r[:, 0] - 1 + 0.5) * self.g,
                           self.y0 + (r[:, 1] - 1 + 0.5) * self.g] for r in rings]
            if len(rings[0]) < 3:
                continue
            p = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3]).buffer(0)
            polys.append(p)
        u = unary_union(polys)
        return u.simplify(simplify) if simplify else u


def shapely_to_rings(geom):
    out = []
    gs = [geom] if isinstance(geom, Polygon) else list(getattr(geom, "geoms", []))
    for p in gs:
        if p.is_empty or p.area < 1e-4:
            continue
        out.append([list(map(list, p.exterior.coords[:-1]))] +
                   [list(map(list, r.coords[:-1])) for r in p.interiors])
    return out


def rings_to_shapely(polys):
    ps = []
    for r in polys:
        if len(r[0]) >= 3:
            ps.append(Polygon(r[0], [h for h in r[1:] if len(h) >= 3]).buffer(0))
    return unary_union(ps) if ps else Polygon()


# ---------------------------------------------------------------- layer model
class Layer:
    def __init__(self, d, layer, g):
        self.d, self.layer = d, layer
        self.grid = G = Grid(d["bbox"], g)
        self.inboard = G.raster(d["outline"])
        ec = d["rules"]["edge_clearance"] or 0.0
        self.alive = self.inboard & ~G.dilate(~self.inboard, ec)
        for k in d["keepouts"]:
            if layer in k["layers"] and k.get("zones", True):
                self.alive &= ~G.raster(k["poly"])
        self.zones = [z for z in d["zones"] if layer in z["layers"] and z["net"]]
        area = {}
        for z in self.zones:
            a = rings_to_shapely(z["fills"].get(layer, [])).area
            area[z["net"]] = area.get(z["net"], 0) + a
        self.nets = sorted([n for n, a in area.items() if a > 1.0], key=lambda n: -area[n])
        self.copper = {}      # net -> mask of copper on this layer
        self.term = {}        # net -> mask of pads + vias (terminals)
        for it in d["items"]:
            if it["layer"] != layer:
                continue
            m = self.copper.setdefault(it["net"], np.zeros(G.shape, bool))
            G.raster(it["poly"], m)
            if it["kind"] in ("pad", "via") and it["net"] in self.nets:
                t = self.term.setdefault(it["net"], np.zeros(G.shape, bool))
                G.raster(it["poly"], t)
        hc = d["rules"]["hole_clearance"] or 0.0
        self.hole_list = [(h["x"], h["y"], h["d"] / 2 + hc) for h in d["holes"]]
        self.clear = {}
        for n in self.nets:
            zc = [z["clearance"] or 0 for z in self.zones if z["net"] == n]
            self.clear[n] = max([d["rules"]["min_clearance"] or 0,
                                 d["netclass_clearance"].get(n, 0)] + zc)
        self.minw = {n: max([z["min_width"] for z in self.zones if z["net"] == n] + [0])
                     for n in self.nets}

    def human_fill(self, dump=None, geoms=False):
        """Zone fills of the pour nets on this layer: net -> mask (and shapely)."""
        d = dump or self.d
        out, gs = {}, {}
        for z in d["zones"]:
            if self.layer in z["layers"] and z["net"] in self.nets:
                fl = z["fills"].get(self.layer, [])
                m = out.setdefault(z["net"], np.zeros(self.grid.shape, bool))
                self.grid.raster(fl, m)
                gs.setdefault(z["net"], []).append(rings_to_shapely(fl))
        gs = {n: unary_union(v) for n, v in gs.items()}
        return (out, gs) if geoms else out

    def setup(self):
        """Phases, allowed masks, pinned cells for the MBO solver (cached; bridge cells
        added by `repair_connectivity` are extra pins)."""
        if getattr(self, "_setup", None) is None:
            self._setup = self._setup_base()
        P, alive, allowed, pinned = self._setup
        allowed, pinned = allowed.copy(), pinned.copy()
        for p, n in enumerate(self.nets):
            ex = getattr(self, "extra_pins", {}).get(n)
            if ex is not None:
                ex = ex & allowed[p] & (pinned < 0)
                pinned[ex] = p
        allowed[P - 1] = self.alive & (pinned < 0)
        return P, alive, allowed, pinned

    def _setup_base(self):
        G, nets = self.grid, self.nets
        P = len(nets) + 1
        allowed = np.zeros((P,) + G.shape, bool)
        pinned = -np.ones(G.shape, int)
        allcu = np.zeros(G.shape, bool)
        for m in self.copper.values():
            allcu |= m
        for p, n in enumerate(nets):
            own = self.copper.get(n, np.zeros(G.shape, bool))
            foreign = allcu & ~own
            holes = np.zeros(G.shape, bool)
            for (x, y, r) in self.hole_list:
                i, j = int((x - G.x0) / G.g), int((y - G.y0) / G.g)
                if 0 <= j < G.H and 0 <= i < G.W and own[j, i]:
                    continue  # plated hole of the pour's own pad/via
                G.disc(x, y, r, holes)
            bad = G.dilate(foreign, self.clear[n] + 0.5 * G.g) | holes
            allowed[p] = self.alive & ~bad
        for p, n in enumerate(nets):  # pins last so own copper wins
            own = self.copper.get(n, np.zeros(G.shape, bool)) & self.inboard
            pinned[own] = p
            allowed[p] |= own
        allowed[P - 1] = self.alive & (pinned < 0)
        alive = self.alive | (pinned >= 0)
        return P, alive, allowed, pinned


# ---------------------------------------------------------------- metrics
def effective_resistance(region, terminals):
    """region: bool mask of conducting cells; terminals: int label map (0 = none,
    1..T) of equipotential terminal cells. Returns (T x T) effective resistance in
    squares (inf for disconnected pairs)."""
    T = int(terminals.max())
    R = np.full((T, T), np.inf)
    np.fill_diagonal(R, 0.0)
    if T < 2:
        return R
    reg = region | (terminals > 0)
    cc, ncc = ndi.label(reg)
    H, W = reg.shape
    for c in range(1, ncc + 1):
        comp = cc == c
        tids = np.unique(terminals[comp & (terminals > 0)])
        if len(tids) < 2:
            continue
        # node index: terminal cells collapse to one node each
        node = -np.ones((H, W), int)
        free = comp & (terminals == 0)
        nf = int(free.sum())
        node[free] = np.arange(nf)
        tmap = {t: nf + k for k, t in enumerate(tids)}
        for t, k in tmap.items():
            node[comp & (terminals == t)] = k
        N = nf + len(tids)
        rows, cols = [], []
        for a, b in ((node[:, :-1], node[:, 1:]), (node[:-1, :], node[1:, :])):
            m = (a >= 0) & (b >= 0) & (a != b)
            rows.append(a[m])
            cols.append(b[m])
        r = np.concatenate(rows)
        cl = np.concatenate(cols)
        A = sp.coo_matrix((np.ones(len(r)), (r, cl)), shape=(N, N)).tocsr()
        A = A + A.T
        L = sp.diags(np.asarray(A.sum(1)).ravel()) - A
        g0 = tmap[tids[0]]
        keep = np.r_[0:g0, g0 + 1:N]
        Lr = L[keep][:, keep].tocsc()
        lu = spla.splu(Lr)
        tn = [tmap[t] for t in tids[1:]]
        rowsel = np.array([n if n < g0 else n - 1 for n in tn])
        Xt = np.zeros((len(tn), len(tn)))
        for c0 in range(0, len(tn), 64):
            cols_ = np.arange(c0, min(c0 + 64, len(tn)))
            B = np.zeros((N - 1, len(cols_)))
            B[rowsel[cols_], np.arange(len(cols_))] = 1.0
            Xt[:, cols_] = lu.solve(B)[rowsel, :]
        dg = np.diag(Xt)
        sub = dg[:, None] + dg[None, :] - 2 * Xt
        ids = np.array(tids) - 1
        R[ids[0], ids[1:]] = dg
        R[ids[1:], ids[0]] = dg
        R[np.ix_(ids[1:], ids[1:])] = sub
    return R


def score_layer(L, fills, geoms=None):
    """fills: net -> bool mask of zone fill (geoms: net -> shapely fill). Copper =
    fill | own copper on layer. Lengths from the fill polygons when given."""
    G = L.grid
    out = {}
    others = {n: m for n, m in fills.items()}
    for n in L.nets:
        f = fills.get(n, np.zeros(G.shape, bool))
        own = L.copper.get(n, np.zeros(G.shape, bool))
        cu = f | own
        tl, T = ndi.label(L.term.get(n, np.zeros(G.shape, bool)))
        R = effective_resistance(cu, tl)
        iu = np.triu_indices(T, 1)
        rv = R[iu]
        con = np.isfinite(rv)
        fl, nfl = ndi.label(f)
        # islands: fill components that touch no terminal and no own copper
        touch = np.unique(fl[ndi.binary_dilation(own) & (fl > 0)])
        isl = nfl - len(touch)
        # split boundary: fill edge cells adjacent (within 2*clearance) to other pours
        edge = f & ~ndi.binary_erosion(f)
        near_other = np.zeros(G.shape, bool)
        for m2n, m2 in others.items():
            if m2n != n:
                near_other |= m2
        near_other = G.dilate(near_other, 2 * L.clear[n] + G.g)
        split = edge & near_other
        if geoms is not None and n in geoms:
            gn = geoms[n]
            oth = unary_union([v for k, v in geoms.items() if k != n] or [Polygon()])
            edge_mm = gn.boundary.length
            split_mm = gn.boundary.intersection(oth.buffer(2 * L.clear[n] + 0.05)).length
        else:
            edge_mm = float(edge.sum() * G.g)
            split_mm = float(split.sum() * G.g)
        Gp = np.where(con & (rv > 0), 1.0 / np.maximum(rv, 1e-12), 0.0)
        gm = float(Gp.mean()) if len(Gp) else 0.0
        big = int(np.isfinite(R).sum(1).max()) if T else 0
        out[n] = dict(area_mm2=float(cu.sum() * G.g ** 2), fill_mm2=float(f.sum() * G.g ** 2),
                      G_mean=gm, R_eff=(1.0 / gm) if gm > 0 else None,
                      disconnected_terminals=int(T - big),
                      terminals=T, pairs=int(len(rv)), pairs_connected=int(con.sum()),
                      R_mean_sq=float(rv[con].mean()) if con.any() else None,
                      R_median_sq=float(np.median(rv[con])) if con.any() else None,
                      R_max_sq=float(rv[con].max()) if con.any() else None,
                      fill_components=int(nfl), islands=int(isl),
                      edge_mm=float(edge_mm), split_mm=float(split_mm))
    return out


# ---------------------------------------------------------------- MBO on a layer
def run_mbo(L, targets, kernel, s_mm=(4.0, 0.35), n=(40, 60), init=None, log=print,
            fill=False, repair=True):
    """fill=False: every phase has a cell target (free = the rest). fill=True: free has
    no target and a large penalty (it only takes cells no pour may use or reach), the
    largest pour (index 0) takes all the remaining cells, the others keep targets."""
    P, alive, allowed, pinned = L.setup()
    G = L.grid
    s0, s1 = s_mm[0] / G.g, s_mm[1] / G.g
    tgt = np.array(list(targets) + [np.nan], float)
    reward = np.zeros(P)
    if fill:
        tgt[0] = np.nan
        reward[-1] = -10.0
    else:
        tgt[-1] = max(int(alive.sum()) - np.nansum(tgt[:-1]), 0)
    if init is None:
        # Voronoi of pinned cells restricted to allowed; else free
        dist, ind = ndi.distance_transform_edt(pinned < 0, return_indices=True)
        lab = pinned[ind[0], ind[1]]
        bad = ~allowed[np.clip(lab, 0, P - 1), np.arange(G.H)[:, None], np.arange(G.W)[None, :]]
        lab[bad | (lab < 0)] = P - 1
    else:
        lab = init.copy()
    connect = np.r_[np.ones(P - 1, bool), False]
    m = MBO(alive, P, kernel=kernel, allowed=allowed, pinned=pinned, target=tgt,
            connect=connect, reward=reward)
    t = time.time()
    lab = m.run(lab, schedule(s0, s1, n[0], n[1]), log=log)
    log(f"  mbo {kernel}: {time.time() - t:.1f}s, counts {np.bincount(lab[lab >= 0], minlength=P)}"
        f" target {np.round(tgt).astype(int)}")
    if repair and getattr(L, "hgroups", None) is not None:
        for rep in range(4):
            added = repair_connectivity(L, lab, allowed, log)
            if not added:
                break
            lab, m = run_mbo(L, targets, kernel, s_mm=(s_mm[1] * 2, s_mm[1]), n=(5, 20),
                             init=lab, log=log, fill=fill, repair=False)
    return lab, m


def human_groups(L, hf):
    """net -> int map: label of the human copper component (fill | own copper) under
    each terminal cell; terminals the human pour connects must stay connected."""
    out = {}
    for n in L.nets:
        cu = hf.get(n, np.zeros(L.grid.shape, bool)) | L.copper.get(n, np.zeros(L.grid.shape, bool))
        lab, _ = ndi.label(cu)
        out[n] = lab
    return out


def repair_connectivity(L, lab, allowed, log=print):
    """Bridge MBO components of a pour that hold terminals the human pour connects:
    cheapest path through cells the pour may use (cost 0.02 on its own cells, 1
    elsewhere), widened to the zone min width, becomes extra pinned cells."""
    from scipy.sparse.csgraph import dijkstra
    G = L.grid
    L.extra_pins = getattr(L, "extra_pins", {})
    added = 0
    for p, n in enumerate(L.nets):
        term = L.term.get(n)
        if term is None:
            continue
        tl, T = ndi.label(term)
        if T < 2:
            continue
        cc, _ = ndi.label(lab == p)
        hg = L.hgroups[n]
        groups = {}
        for t in range(1, T + 1):
            m = tl == t
            h = np.bincount(hg[m]).argmax() if m.any() else 0
            c = np.bincount(cc[m]).argmax() if m.any() else 0
            if h > 0:
                groups.setdefault(h, set()).add(c)
        need = [cs for cs in groups.values() if len(cs) > 1 or 0 in cs]
        if not need:
            continue
        ok = allowed[p]
        idx = -np.ones(G.shape, np.int64)
        idx[ok] = np.arange(int(ok.sum()))
        cost = np.where(lab == p, 0.02, 1.0)[ok]
        rows, cols, w = [], [], []
        for a, b in ((idx[:, :-1], idx[:, 1:]), (idx[:-1, :], idx[1:, :])):
            mm = (a >= 0) & (b >= 0)
            rows += [a[mm], b[mm]]
            cols += [b[mm], a[mm]]
            w += [cost[b[mm]], cost[a[mm]]]
        import scipy.sparse as sps
        A = sps.csr_matrix((np.concatenate(w), (np.concatenate(rows), np.concatenate(cols))),
                           shape=(int(ok.sum()),) * 2)
        flat_y, flat_x = np.nonzero(ok)
        bridge = np.zeros(G.shape, bool)
        for cs in need:
            cs = [c for c in cs if c > 0]
            if len(cs) < 2:
                continue
            sizes = {c: int((cc == c).sum()) for c in cs}
            main = max(cs, key=sizes.get)
            src = idx[(cc == main) & ok]
            src = src[src >= 0]
            dist, pred, _ = dijkstra(A, indices=src, min_only=True, return_predecessors=True)
            for c in cs:
                if c == main:
                    continue
                tgt = idx[(cc == c) & ok]
                tgt = tgt[tgt >= 0]
                if not len(tgt):
                    continue
                k = tgt[np.argmin(dist[tgt])]
                if not np.isfinite(dist[k]):
                    continue
                while k >= 0:
                    bridge[flat_y[k], flat_x[k]] = True
                    k = pred[k]
        if bridge.any():
            r = 2 * max(L.minw.get(n, 0.25), 0.25) + 0.3
            bridge = G.dilate(bridge, r) & ok
            prev = L.extra_pins.get(n, np.zeros(G.shape, bool))
            new = bridge & ~prev
            L.extra_pins[n] = prev | bridge
            added += int(new.sum())
    if added:
        log(f"  repair: pinned {added} bridge cells")
    return added


def zone_outlines(L, lab, shrink=None):
    """Partition -> per-net shapely outlines. Cells no pour may use (clearance rings,
    holes, edge band) are handed to the nearest pour/free cell so KiCad's own clearance
    rules shape the copper there; outlines of two pours are pulled back from each
    other by half the clearance each."""
    G = L.grid
    P, alive, allowed, pinned = L.setup()
    lab = lab.copy()
    lab[~allowed[:P - 1].any(0)] = -1
    lab[~L.inboard] = -1
    known = lab >= 0
    grow = (L.inboard | ndi.binary_dilation(L.inboard, iterations=3)) & ~known
    if grow.any() and known.any():
        _, ind = ndi.distance_transform_edt(~known, return_indices=True)
        lab[grow] = lab[ind[0], ind[1]][grow]
    raw = {n: G.to_polys(lab == p) for p, n in enumerate(L.nets)}
    out = {}
    for n, gm in raw.items():
        c = L.clear[n] if shrink is None else shrink
        others = [v for k, v in raw.items() if k != n and not v.is_empty]
        if others:
            gm = gm.difference(unary_union(others).buffer(0.5 * c + 0.02, join_style=2))
        out[n] = gm.buffer(0)
    return out, lab


def plot_layer(L, panels, path):
    fig, axs = plt.subplots(1, len(panels), figsize=(5 * len(panels), 5 * L.grid.H / L.grid.W + 0.8))
    axs = np.atleast_1d(axs)
    cmap = plt.get_cmap("tab10")
    for ax, (title, fills) in zip(axs, panels):
        img = np.ones(L.grid.shape + (3,))
        img[~L.inboard] = 0.85
        allcu = np.zeros(L.grid.shape, bool)
        for m in L.copper.values():
            allcu |= m
        img[allcu] = 0.3
        for k, n in enumerate(L.nets):
            f = fills.get(n)
            if f is not None:
                img[f] = cmap(k)[:3]
            own = L.copper.get(n)
            if own is not None:
                img[own] = np.array(cmap(k)[:3]) * 0.55
        ax.imshow(img, interpolation="nearest")
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    handles = [plt.Rectangle((0, 0), 1, 1, color=cmap(k)) for k in range(len(L.nets))]
    fig.legend(handles, L.nets, loc="lower center", ncol=min(6, len(L.nets)), fontsize=8)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=100)
    plt.close(fig)


def drc(board_path):
    out = board_path + ".drc.json"
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-error",
                    "--refill-zones", "--units", "mm", "-o", out, board_path],
                   capture_output=True, text=True)
    try:
        d = json.load(open(out))
    except Exception:
        return None
    from collections import Counter
    c = Counter(v["type"] for v in d.get("violations", []))
    c.update({"unconnected_items": len(d.get("unconnected_items", []))})
    return dict(c)


def write_and_dump(bid, ref, layers, labs, out_dir, k):
    spec = dict(replace=[], zones=[])
    for ln, L in layers.items():
        geoms, _ = zone_outlines(L, labs[ln])
        for n, gm in geoms.items():
            spec["replace"].append([n, ln])
            rings = shapely_to_rings(gm)
            if rings:
                spec["zones"].append(dict(net=n, layer=ln, template=[n, ln], polys=rings))
    sp_path = os.path.join(out_dir, f"zones_{k}.json")
    json.dump(spec, open(sp_path, "w"))
    bdir = os.path.join(out_dir, f"board_{k}")
    os.makedirs(bdir, exist_ok=True)
    ob = os.path.join(bdir, "board.kicad_pcb")
    shutil.copy(os.path.join(TASKS, bid, "reference", "board.kicad_pro"), bdir)
    kicad("write", ref, sp_path, ob)
    dj = os.path.join(bdir, "dump.json")
    kicad("dump", ob, dj)
    return ob, json.load(open(dj))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("layers", nargs="+")
    ap.add_argument("--g", type=float, default=0.1)
    ap.add_argument("--kernel", default="both")
    ap.add_argument("--mode", default="iso_area")
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--calib", type=int, default=2, help="area calibration rounds")
    ap.add_argument("--no-kicad", action="store_true")
    a = ap.parse_args()
    bid = a.board
    out_dir = os.path.join(WORK, bid, a.tag)
    os.makedirs(out_dir, exist_ok=True)
    ref = os.path.join(TASKS, bid, "reference", "board.kicad_pcb")
    hum_json = os.path.join(WORK, bid, "human.json")
    if not os.path.exists(hum_json):
        kicad("dump", ref, hum_json, "--refill")
    d = json.load(open(hum_json))
    kernels = ["iso", "oct"] if a.kernel == "both" else [a.kernel]
    results = dict(board=bid, g=a.g, mode=a.mode, layers={})
    layers, targets, hfill = {}, {}, {}
    for ln in a.layers:
        L = Layer(d, ln, a.g)
        layers[ln] = L
        hf, hg = L.human_fill(geoms=True)
        hfill[ln] = hf
        L.hgroups = human_groups(L, hf)
        print(f"[{bid} {ln}] nets {L.nets} grid {L.grid.shape}", flush=True)
        P, alive, allowed, pinned = L.setup()
        if a.mode == "iso_area":
            tg = [hf[n].sum() for n in L.nets]
        elif a.mode == "fill":  # max copper: smaller pours keep the human area
            tg = [hf[n].sum() for n in L.nets]
        else:
            tot = sum(hf[n].sum() for n in L.nets)
            w = np.array([max(ndi.label(L.term.get(n, np.zeros(1)))[1], 1) for n in L.nets], float)
            tg = list(tot * w / w.sum())
        targets[ln] = np.array([t + (pinned == p).sum() - (hf[n] & (pinned == p)).sum()
                                for p, (n, t) in enumerate(zip(L.nets, tg))], float)
        results["layers"][ln] = dict(nets=L.nets, human=score_layer(L, hf, hg), clear=L.clear)
    pour_nets = sorted({n for L in layers.values() for n in L.nets})
    if a.no_kicad:
        for k in kernels:
            for ln, L in layers.items():
                run_mbo(L, targets[ln], k)
        return
    results["net_human"] = {n: netcond_net(d, n, a.g) for n in pour_nets}
    for k in kernels:
        for L in layers.values():
            L.extra_pins = {}
        tg = {ln: t.copy() for ln, t in targets.items()}
        labs = {}
        for rnd in range((a.calib if a.mode == "iso_area" else 0) + 1):
            for ln, L in layers.items():
                labs[ln], m = run_mbo(L, tg[ln], k, init=labs.get(ln), fill=a.mode == "fill")
                results["layers"][ln][f"lam_{k}"] = m.lam.tolist()
            ob, dm = write_and_dump(bid, ref, layers, labs, out_dir, k)
            dev = []
            for ln, L in layers.items():
                mf = L.human_fill(dm)
                for p, n in enumerate(L.nets):
                    deficit = hfill[ln][n].sum() - mf.get(n, np.zeros(1, bool)).sum()
                    dev.append(f"{ln}:{n}:{deficit * L.grid.g ** 2:+.1f}mm2")
                    if a.mode == "iso_area":
                        tg[ln][p] += deficit
            print(f"  {k} round {rnd}: fill deficit vs human {' '.join(dev)}", flush=True)
        np.savez_compressed(os.path.join(out_dir, f"labels_{k}.npz"), **labs)
        results[f"drc_{k}"] = drc(ob)
        for ln, L in layers.items():
            mf, mg = L.human_fill(dm, geoms=True)
            results["layers"][ln][f"mbo_{k}"] = score_layer(L, mf, mg)
            results["layers"][ln][f"_fill_{k}"] = mf
        results[f"net_mbo_{k}"] = {n: netcond_net(dm, n, a.g) for n in pour_nets}
    hdir = os.path.join(WORK, bid, "human_board")
    os.makedirs(hdir, exist_ok=True)
    if not os.path.exists(os.path.join(hdir, "board.kicad_pcb")):
        shutil.copy(ref, hdir)
        shutil.copy(os.path.join(TASKS, bid, "reference", "board.kicad_pro"), hdir)
    results["drc_human"] = drc(os.path.join(hdir, "board.kicad_pcb"))
    for ln, L in layers.items():
        panels = [("human (KiCad fill)", hfill[ln])]
        for k in kernels:
            panels.append((f"MBO {k} (KiCad fill)", results["layers"][ln].pop(f"_fill_{k}")))
        figp = os.path.join(HERE, "fig", f"{bid[:40]}_{ln}_{a.tag}.png")
        plot_layer(L, panels, figp)
        results["layers"][ln]["figure"] = os.path.relpath(figp, HERE)
    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print_summary(results)


def netcond_net(d, n, g):
    from netcond import net_resistance
    return net_resistance(d, n, g)[0]


def print_summary(res):
    for ln, r in res["layers"].items():
        print(f"== {res['board']} {ln}")
        keys = [k for k in r if k.startswith("mbo_")]
        for n in r["nets"]:
            h = r["human"][n]
            line = f"  {n[:18]:18s} T={h['terminals']:3d} human A={h['area_mm2']:7.1f} R={h['R_mean_sq'] or float('nan'):6.2f} conn={h['pairs_connected']}/{h['pairs']} isl={h['islands']} split={h['split_mm']:.0f}"
            for k in keys:
                m = r[k][n]
                line += f" | {k} A={m['area_mm2']:7.1f} R={m['R_mean_sq'] or float('nan'):6.2f} conn={m['pairs_connected']} isl={m['islands']} split={m['split_mm']:.0f}"
            print(line)
    for n, h in res.get("net_human", {}).items():
        f = lambda v: "inf" if v is None else f"{v:.3f}"  # noqa: E731
        line = (f"  NET {n[:18]:18s} pads={h['pads']} human Reff={f(h.get('R_eff'))} "
                f"Rconn={f(h['R_mean'])} disc={h.get('disconnected_pads')} Cu={h['copper_mm2']:.0f}")
        for k in res:
            if k.startswith("net_mbo_"):
                m = res[k][n]
                line += (f" | {k[8:]} Reff={f(m.get('R_eff'))} Rconn={f(m['R_mean'])} "
                         f"disc={m.get('disconnected_pads')} Cu={m['copper_mm2']:.0f}")
        print(line)
    for k in res:
        if k.startswith("drc_"):
            print(k, res[k])


if __name__ == "__main__":
    main()
