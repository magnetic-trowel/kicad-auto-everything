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
        self.holes = np.zeros(G.shape, bool)
        hc = d["rules"]["hole_clearance"] or 0.0
        for h in d["holes"]:
            G.disc(h["x"], h["y"], h["d"] / 2 + hc, self.holes)
        self.clear = {}
        for n in self.nets:
            zc = [z["clearance"] or 0 for z in self.zones if z["net"] == n]
            self.clear[n] = max([d["rules"]["min_clearance"] or 0,
                                 d["netclass_clearance"].get(n, 0)] + zc)
        self.minw = {n: max([z["min_width"] for z in self.zones if z["net"] == n] + [0])
                     for n in self.nets}

    def human_fill(self, dump=None):
        d = dump or self.d
        out = {}
        for z in d["zones"]:
            if self.layer in z["layers"] and z["net"] in self.nets:
                m = out.setdefault(z["net"], np.zeros(self.grid.shape, bool))
                self.grid.raster(z["fills"].get(self.layer, []), m)
        return out

    def setup(self):
        """Phases, allowed masks, pinned cells for the MBO solver."""
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
            bad = G.dilate(foreign, self.clear[n] + 0.5 * G.g) | (self.holes & ~own)
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
        pos = {n: (n if n < g0 else n - 1) for n in tn}
        B = np.zeros((N - 1, len(tn)))
        for k, n in enumerate(tn):
            B[pos[n], k] = 1.0
        X = lu.solve(B)
        Xt = X[[pos[n] for n in tn], :]
        ids = [t - 1 for t in tids]
        R[ids[0], ids[0]] = 0
        for k, t in enumerate(tids[1:]):
            R[ids[0], t - 1] = R[t - 1, ids[0]] = Xt[k, k]
        for a in range(len(tn)):
            for b in range(a + 1, len(tn)):
                v = Xt[a, a] + Xt[b, b] - 2 * Xt[a, b]
                R[tids[a + 1] - 1, tids[b + 1] - 1] = R[tids[b + 1] - 1, tids[a + 1] - 1] = v
    return R


def score_layer(L, fills, label=""):
    """fills: net -> bool mask of zone fill. Copper = fill | own copper on layer."""
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
        out[n] = dict(area_mm2=float(cu.sum() * G.g ** 2), fill_mm2=float(f.sum() * G.g ** 2),
                      terminals=T, pairs=int(len(rv)), pairs_connected=int(con.sum()),
                      R_mean_sq=float(rv[con].mean()) if con.any() else None,
                      R_median_sq=float(np.median(rv[con])) if con.any() else None,
                      R_max_sq=float(rv[con].max()) if con.any() else None,
                      fill_components=int(nfl), islands=int(isl),
                      edge_mm=float(edge.sum() * G.g * np.pi / 4),
                      split_mm=float(split.sum() * G.g * np.pi / 4))
    return out


# ---------------------------------------------------------------- MBO on a layer
def run_mbo(L, targets, kernel, s_mm=(1.5, 0.35), n=(30, 60), init=None, log=print):
    P, alive, allowed, pinned = L.setup()
    G = L.grid
    s0, s1 = s_mm[0] / G.g, s_mm[1] / G.g
    tgt = np.array(list(targets) + [np.nan])
    tgt[-1] = np.nan
    # free phase: volume constraint too (rest of the alive cells) when pours are constrained
    nalive = int((alive).sum())
    tgt[-1] = max(nalive - np.nansum(tgt[:-1]), 0)
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
            connect=connect)
    t = time.time()
    lab = m.run(lab, schedule(s0, s1, n[0], n[1]), log=log)
    log(f"  mbo {kernel}: {time.time() - t:.1f}s, counts {np.bincount(lab[lab >= 0], minlength=P)}"
        f" target {np.round(tgt).astype(int)}")
    return lab, m


def zone_outlines(L, lab, shrink=None):
    """Partition -> per-net shapely outlines. Pour cells plus their share (nearest
    label) of the in-board cells no pour may use, minus half the clearance."""
    G = L.grid
    P = len(L.nets) + 1
    lab = lab.copy()
    lab[~L.inboard] = -1
    known = lab >= 0
    blocked = L.inboard & ~known
    if blocked.any():
        _, ind = ndi.distance_transform_edt(~known, return_indices=True)
        lab[blocked] = lab[ind[0], ind[1]][blocked]
    # grow slightly beyond the board edge so outlines cover the edge band
    edge = ndi.binary_dilation(L.inboard, iterations=3) & ~L.inboard
    _, ind = ndi.distance_transform_edt(lab < 0, return_indices=True)
    lab[edge] = lab[ind[0], ind[1]][edge]
    out = {}
    for p, n in enumerate(L.nets):
        geom = G.to_polys(lab == p)
        c = L.clear[n] if shrink is None else shrink
        geom = geom.buffer(-(0.5 * c + 0.02), join_style=2).buffer(0)
        out[n] = geom
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
                    "--refill-zones", "--schematic-parity" if False else "--units", "mm",
                    "-o", out, board_path], capture_output=True, text=True)
    try:
        d = json.load(open(out))
    except Exception:
        return None
    from collections import Counter
    c = Counter(v["type"] for v in d.get("violations", []))
    c.update({"unconnected_items": len(d.get("unconnected_items", []))})
    return dict(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("layers", nargs="+")
    ap.add_argument("--g", type=float, default=0.1)
    ap.add_argument("--kernel", default="both")
    ap.add_argument("--mode", default="iso_area")
    ap.add_argument("--tag", default="v1")
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
    labs = {k: {} for k in kernels}
    layers = {}
    for ln in a.layers:
        L = Layer(d, ln, a.g)
        layers[ln] = L
        hf = L.human_fill()
        hs = score_layer(L, hf)
        print(f"[{bid} {ln}] nets {L.nets} grid {L.grid.shape}", flush=True)
        if a.mode == "iso_area":
            tg = [hf[n].sum() + 0 for n in L.nets]
        else:
            tot = sum(hf[n].sum() for n in L.nets)
            w = np.array([max(ndi.label(L.term.get(n, np.zeros(1)))[1], 1) for n in L.nets], float)
            tg = list(tot * w / w.sum())
        # own copper is counted as pinned area; the fill target is the human fill
        P, alive, allowed, pinned = L.setup()
        tg = [int(t + (pinned == p).sum() - (hf[n] & (pinned == p)).sum())
              for p, (n, t) in enumerate(zip(L.nets, tg))]
        results["layers"][ln] = dict(nets=L.nets, human=hs, clear=L.clear, targets_cells=tg)
        for k in kernels:
            lab, m = run_mbo(L, tg, k)
            labs[k][ln] = lab
            results["layers"][ln][f"lam_{k}"] = m.lam.tolist()
    with open(os.path.join(out_dir, "grid_results.json"), "w") as f:
        json.dump(results, f, indent=1)
    np.savez_compressed(os.path.join(out_dir, "labels.npz"),
                        **{f"{k}|{ln}": v for k in labs for ln, v in labs[k].items()})
    if a.no_kicad:
        return
    # write back to KiCad (one board per kernel, all requested layers replaced)
    for k in kernels:
        spec = dict(replace=[], zones=[])
        for ln, L in layers.items():
            geoms, _ = zone_outlines(L, labs[k][ln])
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
        dm = json.load(open(dj))
        results[f"drc_{k}"] = drc(ob)
        for ln, L in layers.items():
            mf = L.human_fill(dm)
            results["layers"][ln][f"mbo_{k}"] = score_layer(L, mf)
            results["layers"][ln][f"_fill_{k}"] = mf
    # human DRC (same command on a copy of the reference)
    hdir = os.path.join(WORK, bid, "human_board")
    if not os.path.exists(os.path.join(hdir, "board.kicad_pcb.drc.json")):
        os.makedirs(hdir, exist_ok=True)
        shutil.copy(ref, hdir)
        shutil.copy(os.path.join(TASKS, bid, "reference", "board.kicad_pro"), hdir)
    results["drc_human"] = drc(os.path.join(hdir, "board.kicad_pcb"))
    for ln, L in layers.items():
        panels = [("human (KiCad fill)", L.human_fill())]
        for k in kernels:
            panels.append((f"MBO {k} (KiCad fill)", results["layers"][ln].pop(f"_fill_{k}")))
        figp = os.path.join(HERE, "fig", f"{bid[:40]}_{ln}_{a.tag}.png")
        plot_layer(L, panels, figp)
        results["layers"][ln]["figure"] = os.path.relpath(figp, HERE)
    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    print_summary(results)


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
    for k in res:
        if k.startswith("drc_"):
            print(k, res[k])


if __name__ == "__main__":
    main()
