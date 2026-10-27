# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnostics of the collapse terms on finished boards.

    python diag.py OUT.json RUN_DIR[:attempts] [RUN_DIR ...] [--suite kae-work/ab33.txt]

For every board of each run (output board of attempt N, extracted with KiCad's Python):
per bus, the forced-via count at the board's orientations, the minimum over the 16
rotation pairs of the two parts (positions kept), and the routed vias on the bus nets;
per board, total fv, straight-line crossings, capacity overflow and routed vias.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/research/pnr"))
sys.path.insert(0, str(HERE))

from terms import CollapseTerms, bus_fv_cyclic  # noqa: E402
from world import World  # noqa: E402

KICAD_PY = os.environ.get("KAE_KICAD_PYTHON", "/usr/bin/python3")
CACHE = Path(os.environ.get("CPLACE_CACHE", str(ROOT / "kae-work/cplace/ext")))


def extract(pcb, key):
    out = CACHE / f"{key}.json"
    if not out.exists():
        r = subprocess.run([KICAD_PY, str(ROOT / "tools/research/pnr/kicad_io.py"), "extract", str(pcb), str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None
    return json.loads(out.read_text())


def vias_by_net(pcb):
    txt = Path(pcb).read_text()
    out = {}
    for m in re.finditer(r"\(via\b.*?\(net \"?([^\")]*)\"?\)", txt, re.S):
        out[m.group(1)] = out.get(m.group(1), 0) + 1
    return out


def board_diag(data, pcb):
    w = World(data)
    for i in range(len(w.parts)):
        w.place_original(i)
    t = CollapseTerms(w, w_x=1.0)
    ev = t.evaluate(t.poses)
    vn = vias_by_net(pcb)
    xy, _ = t.pad_xy(t.poses)
    buses = []
    for bi, bu in enumerate(t.buses):
        a, b = bu["a"], bu["b"]
        fv, lds = t.bus_fv(bi, xy)
        best = None
        for ra in range(4):
            for rb in range(4):
                poses = {a: w.pose[a][:2] + (ra,), b: w.pose[b][:2] + (rb,)}
                xy2, _ = t.pad_xy(poses)
                f2 = t.bus_fv(bi, xy2)[0]
                best = f2 if best is None else min(best, f2)
        ca = xy[t.part_pads[a]].mean(0)
        cb = xy[t.part_pads[b]].mean(0)
        fvc = bus_fv_cyclic(xy[bu["pa"]], xy[bu["pb"]], ca, cb, bu["L"])
        nets = {t.pad_net[j] for j in bu["pa"]}
        rv = sum(vn.get(w.net_names[n], 0) for n in nets)
        buses.append(dict(a=w.parts[a].ref, b=w.parts[b].ref, n=len(bu["pa"]), L=bu["L"], fv=fv, lds=lds,
                          fv_min=best, fv_cyc=fvc, routed_vias=rv))
    return dict(fv=ev["fv"], x=ev["x"], ovf=ev["ovf"], vias=sum(vn.values()), buses=buses)


def main():
    args = sys.argv[1:]
    out = Path(args.pop(0))
    suite = ROOT / "kae-work/ab33.txt"
    if "--suite" in args:
        i = args.index("--suite")
        suite = Path(args[i + 1])
        del args[i:i + 2]
    ids = suite.read_text().split()
    res = json.loads(out.read_text()) if out.exists() else {}
    for spec in args:
        run, _, att = spec.partition(":")
        atts = [int(a) for a in att.split(",")] if att else [0]
        name = Path(run).name
        for bid in ids:
            for a in atts:
                key = f"{name}/{bid}/{a}"
                if key in res:
                    continue
                pcbs = list(Path(run).glob(f"*/*/{bid}/attempt-{a}/output/board.kicad_pcb"))
                if not pcbs:
                    continue
                data = extract(pcbs[0], f"{name}__{bid}__{a}")
                if data is None:
                    continue
                try:
                    res[key] = board_diag(data, pcbs[0])
                except Exception as e:  # noqa: BLE001
                    res[key] = dict(error=str(e)[:200])
                print(key, {k: v for k, v in res[key].items() if k != "buses"}, flush=True)
                out.write_text(json.dumps(res, indent=1, default=int))


if __name__ == "__main__":
    main()
