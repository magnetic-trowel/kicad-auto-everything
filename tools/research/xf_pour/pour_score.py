# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pour resistance of run outputs (collapse_pour/netcond.py on the KiCad-refilled board).

    python pour_score.py OUT.json RUN [RUN ...] [--suite kae-work/ab33.txt] [-j 8]
    python pour_score.py --table OUT.json BASE_RUN RUN [...]

For every board of the suite whose reference has zones, every seed's output board (and
the human reference) is dumped by collapse_pour/kicad_dump.py with --refill, and each
filled zone net gets netcond.net_resistance (all layers, pads as terminals, squares):
R_eff = 1 / mean over pad pairs of 1/R (disconnected pairs count 0). --table prints
gmean ratios: per (board, net), the gmean over seeds of R_eff, then the gmean over
(board, net) of run / base and run / human, on the (board, net) both have.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CP = ROOT / "tools" / "research" / "collapse_pour"
XF_WORK = Path(os.environ.get("XF_WORK", ROOT / "kae-work2"))
RES = XF_WORK / "results"
TASKS = XF_WORK / "tasks"


def _stub_plotting():
    """collapse_pour/board.py imports matplotlib and contourpy (absent from the venv) at
    module level; netcond only needs Grid.raster, i.e. matplotlib.path.Path.contains_points.
    Provide that with shapely (cell centres strictly inside / on the ring)."""
    import types
    if "matplotlib" in sys.modules:
        return
    import numpy as np
    import shapely
    from shapely.geometry import Polygon

    class Path:
        def __init__(self, verts):
            self.poly = Polygon(np.asarray(verts, float)).buffer(0)

        def contains_points(self, P):
            P = np.asarray(P, float)
            return shapely.contains_xy(self.poly, P[:, 0], P[:, 1])

    mpl = types.ModuleType("matplotlib")
    mpl.use = lambda *a, **k: None
    mpath = types.ModuleType("matplotlib.path")
    mpath.Path = Path
    mpl.path = mpath
    plt = types.ModuleType("matplotlib.pyplot")
    mpl.pyplot = plt
    sys.modules.update({"matplotlib": mpl, "matplotlib.path": mpath, "matplotlib.pyplot": plt,
                        "contourpy": types.ModuleType("contourpy")})


def job(args):
    key, path = args
    sys.path.insert(0, str(CP))
    try:
        import matplotlib  # noqa: F401
        import contourpy  # noqa: F401
    except ImportError:
        _stub_plotting()
    from netcond import net_resistance
    kpy = os.environ.get("KAE_KICAD_PYTHON", "/usr/bin/python3")
    with tempfile.TemporaryDirectory(dir=str(XF_WORK / "xf_pour")) as td:
        dj = Path(td) / "dump.json"
        r = subprocess.run([kpy, str(CP / "kicad_dump.py"), "dump", str(path), str(dj), "--refill"],
                           capture_output=True, text=True)
        if r.returncode:
            return key, dict(error=r.stderr[-400:])
        d = json.loads(dj.read_text())
    nets = sorted({z["net"] for z in d["zones"] if z["net"] and any(z["fills"].values())})
    out = {}
    for n in nets:
        full, _, _ = net_resistance(d, n, 0.1)
        if full["pads"] >= 2:
            out[n] = dict(R_eff=full["R_eff"], pads=full["pads"], disc=full["disconnected_pads"],
                          cu=round(full["copper_mm2"], 1))
    return key, out


def collect(runs, suite):
    ids = [l.strip() for l in open(suite) if l.strip()]
    todo = []
    for bid in ids:
        t = json.load(open(TASKS / bid / "task.json"))
        if not t["reference"]["stats"].get("zones"):
            continue
        todo.append((f"human|{bid}|0", TASKS / bid / "reference" / "board.kicad_pcb"))
        for run in runs:
            base = RES / run / f"x-{run}" / "joint" / bid
            for att in sorted(base.glob("attempt-*")):
                p = att / "output" / "board.kicad_pcb"
                if p.exists():
                    todo.append((f"{run}|{bid}|{att.name.split('-')[1]}", p))
    return todo


def gmean(v):
    v = [x for x in v if x and x > 0 and math.isfinite(x)]
    return math.exp(sum(map(math.log, v)) / len(v)) if v else None


def per_board_net(res, run):
    acc = {}
    for k, v in res.items():
        r, bid, s = k.split("|")
        if r != run or "error" in v:
            continue
        for n, x in v.items():
            acc.setdefault((bid, n), []).append(x["R_eff"])
    return {k: gmean(v) for k, v in acc.items() if gmean(v)}


def table(res, base, runs):
    hb = per_board_net(res, "human")
    bb = per_board_net(res, base)
    print("| run | (board, net) | R_eff / base (gmean) | better / worse | R_eff / human (gmean) |")
    print("|---|---|---|---|---|")
    for run in [base] + runs:
        rb = per_board_net(res, run)
        common = sorted(set(rb) & set(bb))
        rat = [rb[k] / bb[k] for k in common]
        hr = [rb[k] / hb[k] for k in rb if k in hb]
        bw = f"{sum(r < 0.98 for r in rat)} / {sum(r > 1.02 for r in rat)}"
        print(f"| {run} | {len(common)} | {gmean(rat):.3f} | {bw} | {gmean(hr):.3f} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--suite", default=str(XF_WORK / "ab33.txt"))
    ap.add_argument("-j", type=int, default=8)
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    res = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else {}
    if a.table:
        table(res, a.runs[0], a.runs[1:])
        return
    (XF_WORK / "xf_pour").mkdir(parents=True, exist_ok=True)
    todo = [t for t in collect(a.runs, a.suite) if t[0] not in res]
    print(f"{len(todo)} boards to score", flush=True)
    with ProcessPoolExecutor(a.j) as ex:
        for k, v in ex.map(job, todo):
            res[k] = v
            print(k, {n: round(x["R_eff"], 3) if x.get("R_eff") else None for n, x in v.items()}
                  if "error" not in v else v, flush=True)
            Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
