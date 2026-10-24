# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the obstruction bounds on every prepared task (human placement).

    python run_all.py extract            # kicad_io extract per task (KiCad python, serial)
    python run_all.py bounds [ids...]    # bounds -> kae-work/collapse_obst/bounds/<id>.json
    python run_all.py buses              # add via-free facing-bus permutation stats
    python run_all.py heat id [id...]    # heat-map PNGs -> heatmaps/<id>.png
    python run_all.py report             # tables printed as markdown

Single process throughout (the machine is shared).
"""
import json
import math
import os
import subprocess
import sys
import time

import numpy as np
import shapely
from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
TASKS = os.path.join(ROOT, "kae-work/tasks")
WORK = os.path.join(ROOT, "kae-work/collapse_obst")
EXT = os.path.join(WORK, "ext")
OUT = os.path.join(WORK, "bounds")
sys.path.insert(0, HERE)
import obst  # noqa: E402


def task_ids():
    return sorted(i for i in os.listdir(TASKS) if os.path.exists(os.path.join(TASKS, i, "task.json")))


def load(tid):
    task = json.load(open(os.path.join(TASKS, tid, "task.json")))
    d = json.load(open(os.path.join(EXT, tid + ".json")))
    pcb = os.path.join(TASKS, tid, "reference/board.kicad_pcb")
    return task, obst.Board(d, pcb, task["reference"]["stats"])


def plane_layers(B):
    """Inner copper layers on which one net's zone outlines cover >= 60% of the board."""
    cover = {}
    for z in B.d.get("zones", []):
        if not z["net"]:
            continue
        g = shapely.unary_union([Polygon(p).buffer(0) for p in z["poly"] if len(p) >= 3])
        for lay in z["layers"]:
            k = (lay, z["net"])
            cover[k] = g if k not in cover else cover[k].union(g)
    best = {}
    for (lay, net), g in cover.items():
        f = g.intersection(B.geom).area / B.area if B.area else 0
        best[lay] = max(best.get(lay, 0), f)
    # planes: inner layers (KiCad 10 ids: F.Cu 0, B.Cu 2) mostly covered by one net's zones.
    # Outer-layer pours on 2-layer boards are fill around signals, not planes.
    planes = sum(1 for lay, f in best.items() if f >= 0.6 and lay not in (0, 2))
    return planes, {str(k): round(v, 2) for k, v in best.items()}


def bounds(tid):
    t0 = time.time()
    task, B = load(tid)
    st = task["reference"]["stats"]
    r = dict(id=tid, split=task["split"], L=st["copper_layers"], pads=st["pads"], nets=B.nn,
             pour_nets=int(B.pour.sum()), board_mm2=round(B.area, 1), w_lb=B.w_lb, w_src=B.w_src,
             outline=B.outline_src, c_lb=B.c_lb, p_lb=round(B.p_lb, 4), w_routed=B.w_routed, sides=sorted(B.sides),
             track_mm=st.get("track_length_mm"), vias=st.get("vias"))
    r["planes"], r["plane_cover"] = plane_layers(B)
    r["side_L"] = 2 if len(B.sides) == 2 else 1
    S = obst.straight_cuts(B)
    lines = [((("line", th), t), ev) for th, t, _, ev in S]
    circ = obst.circle_cuts(B)
    rings = obst.part_rings(B)
    for name, recs in (("line", lines), ("circle", circ), ("ring", rings)):
        for key in ("all", "nopour"):
            L, dmax, where = obst.best_of(recs, key, "L")
            Ln, _, wn = obst.best_of(recs, key, "Lnom")
            # max fractional demand (lower-bound pitch and nominal pitch)
            dd = max((np.nanmax(np.where(np.isfinite(ev[key]["d"]), ev[key]["d"], np.nan))
                      for _, ev in recs if len(ev[key]["d"])), default=0.0)
            dn = max((np.nanmax(np.where(np.isfinite(ev[key]["dnom"]), ev[key]["dnom"], np.nan))
                      for _, ev in recs if len(ev[key]["dnom"])), default=0.0)
            r[f"cut_{name}_{key}"] = dict(L=L, Lnom=Ln, d=float(dd), dnom=float(dn), where=where,
                                          where_nom=wn)
    r["escape"] = obst.escape(B)
    r["area"] = obst.area_bound(B)
    r["topo"] = obst.topology(B, time_limit=20)
    r["secs"] = round(time.time() - t0, 1)
    return r


def summarize(r, key):
    cut = max(r[f"cut_{k}_{key}"]["L"] for k in ("line", "circle", "ring"))
    cutn = max(r[f"cut_{k}_{key}"]["Lnom"] for k in ("line", "circle", "ring"))
    esc = max([e[key]["L"] for e in r["escape"]], default=1)
    area = r["area"][key]["L"]
    tA = r["topo"][key]
    topo_via = 1 if tA["A_peel"] == 1 else 2  # with vias any netlist fits on 2 layers
    parts = dict(side=r["side_L"], topo=topo_via, cut=cut, escape=esc, area=area)
    pred = max(parts.values())
    parts_nom = dict(parts, cut=cutn)
    pred_nom = max(parts_nom.values())
    return pred, parts, pred_nom, parts_nom


def demand_grid(B, key="all", bounds=None, res=None):
    """Local layer demand map: max fractional demand over the local cuts (circles on a
    grid, rings around parts) passing through each cell."""
    minx, miny, maxx, maxy = bounds or B.bounds
    h = res or max(maxx - minx, maxy - miny) / 160
    nx_, ny_ = int((maxx - minx) / h) + 1, int((maxy - miny) / h) + 1
    H = np.zeros((ny_, nx_))

    def paint(px, py, inb, ev):
        i = np.clip(((py - miny) / h).astype(int), 0, ny_ - 1)
        j = np.clip(((px - minx) / h).astype(int), 0, nx_ - 1)
        d = np.where(np.isfinite(ev[key]["d"]), ev[key]["d"], 0)
        val = np.broadcast_to(d[:, None], px.shape)
        np.maximum.at(H, (i[inb], j[inb]), val[inb])

    obst.circle_cuts(B, spacing=max(maxx - minx, maxy - miny) / 80, paint=paint)
    obst.part_rings(B, paint=paint)
    return H


def heat_panels(panels, title, out):
    """panels: [(Board, key, label)]. Writes one PNG with a shared colour scale."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    B0 = panels[0][0]
    minx, miny, maxx, maxy = B0.bounds
    grids = [demand_grid(B, key, B0.bounds) for B, key, _ in panels]
    ramp = ["#ffffff", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
    cmap = LinearSegmentedColormap.from_list("blue", ramp)
    n = len(panels)
    fig, axs = plt.subplots(1, n, figsize=(6 * n, 5.4 * (maxy - miny) / max(maxx - minx, 1e-3) + 1.2))
    axs = np.atleast_1d(axs)
    vmax = max(1.0, max(float(g.max()) for g in grids))
    for ax, (B, key, label), H in zip(axs, panels, grids):
        im = ax.imshow(H, origin="upper", extent=(minx, maxx, maxy, miny), cmap=cmap, vmin=0, vmax=vmax,
                       interpolation="nearest")
        for r in B.rings_outer + B.rings_hole:
            ax.plot(r[:, 0], r[:, 1], color="#555555", lw=0.8)
        ax.scatter(B.x, B.y, s=0.3, color="#888888", linewidths=0)
        ax.set_aspect("equal")
        ax.set_xlim(minx, maxx); ax.set_ylim(maxy, miny)
        ax.set_title(f"{label}: max {H.max():.2f}", fontsize=10, color="#333333")
        ax.tick_params(labelsize=7, colors="#666666")
        for sp in ax.spines.values():
            sp.set_color("#bbbbbb")
    cb = fig.colorbar(im, ax=list(axs), shrink=0.8)
    cb.set_label("local layer demand (crossing nets x pitch / free cut length)", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    fig.suptitle(title, fontsize=10, color="#333333")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(out)


def heat(tid):
    task, B = load(tid)
    L = task["reference"]["stats"]["copper_layers"]
    heat_panels([(B, "all", "all nets"), (B, "nopour", "pour nets removed")],
                f"{tid}  ({L} copper layers, human placement)",
                os.path.join(HERE, "heatmaps", tid + ".png"))


def main():
    op = sys.argv[1]
    if op == "extract":
        os.makedirs(EXT, exist_ok=True)
        for tid in task_ids():
            out = os.path.join(EXT, tid + ".json")
            if os.path.exists(out):
                continue
            subprocess.run(["/usr/bin/python3", os.path.join(ROOT, "tools/research/pnr/kicad_io.py"), "extract",
                            os.path.join(TASKS, tid, "reference/board.kicad_pcb"), out],
                           stderr=subprocess.DEVNULL, check=False)
    elif op == "bounds":
        os.makedirs(OUT, exist_ok=True)
        ids = sys.argv[2:] or task_ids()
        ids.sort(key=lambda i: json.load(open(os.path.join(TASKS, i, "task.json")))["reference"]["stats"]["pads"])
        for tid in ids:
            out = os.path.join(OUT, tid + ".json")
            if os.path.exists(out) and len(sys.argv) == 2:
                continue
            try:
                r = bounds(tid)
            except Exception as e:  # keep going; report the failure
                r = dict(id=tid, error=repr(e))
            json.dump(r, open(out, "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
            print(tid, r.get("secs"), r.get("error", ""), flush=True)
    elif op == "buses":
        for tid in task_ids():
            out = os.path.join(OUT, tid + ".json")
            r = json.load(open(out))
            if "error" in r:
                continue
            _, B = load(tid)
            r["buses"] = obst.facing_buses(B)
            json.dump(r, open(out, "w"))
    elif op == "heat":
        for tid in sys.argv[2:]:
            heat(tid)
    elif op == "report":
        import report
        report.main()


if __name__ == "__main__":
    main()
