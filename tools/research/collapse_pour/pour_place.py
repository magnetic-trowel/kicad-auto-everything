# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pour quality as a function of placement, and a cheap placement term for it.

`pour_score(world)` (on a tools/research/pnr World) predicts, for each net that has a
zone, the mean pad-to-pad resistance of its pour in squares:

    R_ij = [ln(d_ij / a_i) + ln(d_ij / a_j)] / (2 pi)   (two discs on an infinite sheet)
           / sum_l f_ij,l                                 (pour layers in parallel)

d_ij = pad distance, a = equivalent pad radius, f_ij,l = fraction of the band of width
`band` along the segment i-j that is free on zone layer l (inside the board and not
blocked by another net's copper halo: World.DT - own occT). Before routing only pads
block; after routing the router's tracks are in occT too. Lower is better; the score
is the sum over pour nets of the mean predicted resistance.

Driver (venv Python):  python pour_place.py OUT.json [BOARD_ID ...]
For every A/B board with zones it scores the human board (reference) and the attempt-0
boards of pnr-seq-v5 and pnr-combo-v5: the full metric is netcond.net_resistance on the
KiCad-refilled board (all layers, pads as terminals); the cheap terms are pour_score on
a World with the board's placement (pads only) and the same formula on the routed board.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PNR = os.path.join(ROOT, "tools", "research", "pnr")
sys.path.insert(0, HERE)
KPY = "/usr/bin/python3"


# ---------------------------------------------------------------- the cheap term
def predicted_resistance(centres, radii, free_layers, to_cell, band=0.5, step=None):
    """centres (n,2) mm, radii (n,) mm, free_layers: list of bool (H,W) maps,
    to_cell(x, y) -> (ix, iy) float cell coordinates. Returns dict with the mean
    predicted R, the ideal-sheet mean R and the mean free fraction over pairs."""
    n = len(centres)
    if n < 2:
        return None
    c = np.asarray(centres, float)
    a = np.maximum(np.asarray(radii, float), 0.05)
    i, j = np.triu_indices(n, 1)
    d = np.maximum(np.linalg.norm(c[i] - c[j], axis=1), a[i] + a[j])
    r0 = (np.log(d / a[i]) + np.log(d / a[j])) / (2 * np.pi)
    # free fraction along each segment, sampled on 3 parallel lines (offsets -band/2..band/2)
    H, W = free_layers[0].shape
    ff = np.zeros(len(i))
    t = np.linspace(0.0, 1.0, 33)[1:-1]
    for fl in free_layers:
        acc = np.zeros(len(i))
        for off in (-0.5 * band, 0.0, 0.5 * band):
            u = c[j] - c[i]
            nrm = np.stack([-u[:, 1], u[:, 0]], 1) / np.maximum(np.linalg.norm(u, axis=1), 1e-9)[:, None]
            P = c[i][:, None, :] + t[None, :, None] * u[:, None, :] + off * nrm[:, None, :]
            ix, iy = to_cell(P[..., 0], P[..., 1])
            ix = np.clip(np.round(ix).astype(int), 0, W - 1)
            iy = np.clip(np.round(iy).astype(int), 0, H - 1)
            acc += fl[iy, ix].mean(1)
        ff += acc / 3
    rp = r0 / np.maximum(ff, 0.05)
    return dict(R_pred=float(rp.mean()), R_ideal=float(r0.mean()), free=float(ff.mean()),
                spread_mm=float(d.mean()), pads=n)


def pour_score(world, nets=None, band=0.5):
    """Cheap pour term on a pnr World (pads and any stamped routes block). Returns
    (total, {net: {...}}); total = sum over pour nets of the predicted mean R."""
    out = {}
    names = sorted({n for n, _ in world.zone_nets}) if nets is None else nets
    g = world.g
    for name in names:
        nid = world.net_id.get(name)
        if nid is None or nid not in world.net_pins:
            continue
        layers = sorted(l for (n, l) in world.zone_nets if n == name)
        pins = [(pi, k) for pi, k in world.net_pins[nid] if pi in world.pose]
        cen, rad = [], []
        for pi, k in pins:
            cen.append(world.pad_world(pi, k))
            ncell = len(world.raster(pi)["pads"][k]["cu"])
            rad.append(math.sqrt(max(ncell, 1) * g * g / math.pi))
        free = [world.inside & ((world.DT[l] - (world.occT[nid, l] > 0)) == 0) for l in layers]
        r = predicted_resistance(cen, rad, free,
                                 lambda x, y: ((x - world.x0) / g, (y - world.y0) / g), band)
        if r:
            r["layers"] = layers
            out[name] = r
    return sum(v["R_pred"] for v in out.values()), out


def pour_term_from_dump(d, net, g=0.1, band=0.5):
    """Same formula on a KiCad dump (all copper of other nets blocks, bloated by the
    net's clearance), for the routed board."""
    from board import Grid
    G = Grid(d["bbox"], g)
    zl = sorted({l for z in d["zones"] if z["net"] == net for l in z["layers"]})
    if not zl:
        return None
    inside = G.raster(d["outline"])
    pads = {}
    for it in d["items"]:
        if it["net"] == net and it["kind"] == "pad":
            key = (it["ref"], it["pad"])
            if key not in pads:
                m = G.raster(it["poly"])
                pads[key] = ((it["x"], it["y"]), math.sqrt(max(m.sum(), 1) * g * g / math.pi))
    clr = max([d["netclass_clearance"].get(net, 0.2)] +
              [z["clearance"] or 0 for z in d["zones"] if z["net"] == net])
    free = []
    for l in zl:
        foreign = np.zeros(G.shape, bool)
        for it in d["items"]:
            if it["layer"] == l and it["net"] != net:
                G.raster(it["poly"], foreign)
        free.append(inside & ~G.dilate(foreign, clr))
    cen = [p[0] for p in pads.values()]
    rad = [p[1] for p in pads.values()]
    return predicted_resistance(cen, rad, free,
                                lambda x, y: ((x - G.x0) / g, (y - G.y0) / g), band)


# ---------------------------------------------------------------- driver
def kicad(script, *args):
    r = subprocess.run([KPY, script, *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def world_score(board_path, work):
    sys.path.insert(0, PNR)
    from world import World
    ext = os.path.join(work, "extract.json")
    kicad(os.path.join(PNR, "kicad_io.py"), "extract", board_path, ext)
    data = json.load(open(ext))
    w = World(data, g=0.1)
    for pi in range(len(w.parts)):
        w.place_original(pi)
    return pour_score(w)


def boards_with_zones():
    out = []
    for bid in sorted(os.listdir(os.path.join(ROOT, "kae-work", "results", "pnr-seq-v5",
                                              "x-pnr-seq-v5", "place"))):
        t = json.load(open(os.path.join(ROOT, "kae-work", "tasks", bid, "task.json")))
        if t["reference"]["stats"]["zones"] > 0:
            out.append(bid)
    return out


def main():
    from netcond import net_resistance
    out_path = sys.argv[1]
    ids = sys.argv[2:] or boards_with_zones()
    res = json.load(open(out_path)) if os.path.exists(out_path) else {}
    for bid in ids:
        srcs = {"human": os.path.join(ROOT, "kae-work", "tasks", bid, "reference", "board.kicad_pcb")}
        for run in ("pnr-seq-v5", "pnr-combo-v5"):
            p = os.path.join(ROOT, "kae-work", "results", run, f"x-{run}", "place", bid,
                             "attempt-0", "output", "board.kicad_pcb")
            if os.path.exists(p):
                srcs[run] = p
        for name, path in srcs.items():
            key = f"{bid}|{name}"
            if key in res:
                continue
            work = os.path.join(ROOT, "kae-work", "pour", "place", bid, name)
            os.makedirs(work, exist_ok=True)
            try:
                dj = os.path.join(work, "dump.json")
                kicad(os.path.join(HERE, "kicad_dump.py"), "dump", path, dj, "--refill")
                d = json.load(open(dj))
                tot, ws = world_score(path, work)
                nets = sorted({z["net"] for z in d["zones"] if z["net"] and z["fills"]})
                row = {}
                for n in nets:
                    full, _, _ = net_resistance(d, n, 0.1)
                    if full["pads"] < 2:
                        continue
                    row[n] = dict(full=full, world=ws.get(n), routed=pour_term_from_dump(d, n))
                res[key] = row
                print(key, {n: (round(v["full"]["R_mean"] or -1, 3),
                                round((v["world"] or {}).get("R_pred", -1), 3),
                                round((v["routed"] or {}).get("R_pred", -1), 3)) for n, v in row.items()},
                      flush=True)
            except Exception as e:  # keep going; record the failure
                res[key] = dict(error=str(e)[-500:])
                print(key, "ERROR", str(e)[-300:], flush=True)
            json.dump(res, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main()
