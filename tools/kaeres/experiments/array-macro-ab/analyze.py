#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""array-macro-ab: the mechanism's own metric from each run's output board (KiCad DRC run here; KAE_KICAD_WRAP).

    analyze.py EXPERIMENT CONTROL_METHOD ARRAY_METHOD [--base ~/kae-baselines] > table

For every board and arm: open connections on the array's own nets (matrix rows and columns, bus nets; the nets the
detector finds on the control's output, since the netlist is the same), total opens, and the array lattice deviation:
rms distance of each array part from the best-fit grid in millimetres (0 is a perfect lattice, parts rotated together).
"""
import argparse
import glob
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np


def detected(board):
    from kae.place import arrays as A
    from kae.place.problem import net_class_guess
    fps = [f for f in board.footprints if not f.locked and f.pads]
    pins = {}
    for f in board.footprints:
        for p in f.pads:
            if p.net:
                pins[p.net] = pins.get(p.net, 0) + 1
    kinds = {k: net_class_guess(k, v, max(1, len(board.footprints))) for k, v in pins.items()}
    mats = A.matrices(fps, kinds)
    taken = {u for g in mats for u in g.cells}
    return mats + A.buses(fps, kinds, exclude=taken)


def nets_of(board, groups):
    by = {f.uuid: f for f in board.footprints}
    return {p.net for g in groups for u in g.cells for p in by[u].pads if p.net}


def lattice_rms(board, group):
    by = {f.uuid: f for f in board.footprints}
    u = list(group.cells)
    rc = np.array([group.cells[x] for x in u], float)
    xy = np.array([(by[x].x, by[x].y) for x in u], float)
    A = np.c_[np.ones(len(rc)), rc]
    res = xy - A @ np.linalg.lstsq(A, xy, rcond=None)[0]
    return float(np.sqrt((res ** 2).sum(axis=1).mean()))


def open_nets(pcb):
    """{net: open items} from kicad-cli DRC on a stored output board (zones refilled; the run's report is not kept)."""
    out, tmp = {}, tempfile.mkdtemp(prefix="array-drc-", dir=os.environ.get("TMPDIR"))
    try:
        rep = os.path.join(tmp, "drc.json")
        subprocess.run(os.environ["KAE_KICAD_WRAP"].split() + ["kicad-cli", "pcb", "drc", "--format", "json", "--refill-zones",
                       "--severity-error", "--output", rep, pcb], check=False, capture_output=True, timeout=1800)
        for it in json.load(open(rep)).get("unconnected_items", []):
            nets = {m for x in it.get("items", []) for m in re.findall(r"\[(.+?)\]", x.get("description", ""))}
            for n in nets:
                out[n] = out.get(n, 0) + 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exp"), ap.add_argument("control"), ap.add_argument("array")
    ap.add_argument("--base", default=os.path.expanduser("~/kae-baselines"))
    a = ap.parse_args()
    from kae.board.kicad_file import load
    exp = json.load(open(f"{a.base}/experiments/{a.exp}/experiment.json"))
    ids = {m["name"]: m["id"] for m in exp["methods"]}
    print("board\tarm\tarray_nets\tarray_open\ttotal_open\tlattice_rms")
    for b in [x.strip() for x in open(f"{a.base}/experiments/{a.exp}/boards.txt")]:
        row = {}
        for arm, name in (("control", a.control), ("array", a.array)):
            d = f"{a.base}/boards/{b}/runs/*.{ids[name][:8]}.a0"
            found = glob.glob(d)
            if not found or not os.path.exists(found[0] + "/output.kicad_pcb.gz"):
                continue
            t = tempfile.mkdtemp(prefix="array-out-", dir=os.environ.get("TMPDIR"))
            p = f"{t}/b.kicad_pcb"
            with open(p, "wb") as h:
                h.write(gzip.open(found[0] + "/output.kicad_pcb.gz").read())
            row[arm] = (load(p), p, t)
        if len(row) < 2:
            continue
        groups = detected(row["control"][0])
        if not groups:
            continue
        nets = nets_of(row["control"][0], groups)
        for arm, (bd, p, t) in row.items():
            op = open_nets(p)
            rms = max(lattice_rms(bd, g) for g in groups)
            print(f"{b}\t{arm}\t{len(nets)}\t{sum(v for n, v in op.items() if n in nets)}\t{sum(op.values())}\t{rms:.3f}")
            shutil.rmtree(t, ignore_errors=True)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
