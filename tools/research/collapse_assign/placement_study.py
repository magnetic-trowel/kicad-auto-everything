# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Does the lifted-conflict structure of a placement predict its routing outcome?

    python placement_study.py extract CACHE           # KiCad python: extract the boards
    python placement_study.py measure CACHE OUT.jsonl  # lift stats + engine re-route
    python placement_study.py report OUT.jsonl

Placements per A/B board: the human one (route task input), pnr-seq-v5 and
pnr-combo-v5 attempts 0-2 (place-task outputs). Targets: the engine's own PathFinder
re-route of every placement (methods.route_only, same engine and settings, so the
comparison isolates placement) and, where present, the KiCad-scored self-routed probe of
the place run / pnr-route-v5.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/kicad-auto-everything")
RES = ROOT / "kae-work" / "results"
sys.path.insert(0, str(ROOT / "tools/research/pnr"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
RUNS = ("pnr-seq-v5", "pnr-combo-v5")


def placements():
    ids = (ROOT / "kae-work/ab33.txt").read_text().split()
    kic = {}
    for l in open(RES / "pnr-route-v5/results.jsonl"):
        r = json.loads(l)
        kic[("human", r["id"], 0)] = r.get("score")
    for run in RUNS:
        for l in open(RES / run / "results.jsonl"):
            r = json.loads(l)
            kic[(run, r["id"], r["attempt"])] = (r.get("probe") or {}).get("score")
    out = []
    for i in ids:
        out.append(("human", i, 0, ROOT / f"kae-work/tasks/{i}/route/input/board.kicad_pcb", kic.get(("human", i, 0))))
        for run in RUNS:
            for a in range(3):
                b = RES / run / f"x-{run}" / "place" / i / f"attempt-{a}" / "output" / "board.kicad_pcb"
                if b.exists():
                    out.append((run, i, a, b, kic.get((run, i, a))))
    return out


def extract(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    py = os.environ.get("KAE_KICAD_PYTHON", "/usr/bin/python3")
    for run, i, a, b, _ in placements():
        f = cache / f"{run}__{i}__{a}.json"
        if not f.exists():
            subprocess.run([py, str(ROOT / "tools/research/pnr/kicad_io.py"), "extract", str(b), str(f)],
                           capture_output=True)


def measure(cache, out):
    import lifted
    from router import Router
    from world import World
    done = set()
    if Path(out).exists():
        done = {(r["run"], r["id"], r["attempt"]) for r in map(json.loads, open(out))}
    fo = open(out, "a")
    for run, i, a, b, ks in placements():
        if (run, i, a) in done:
            continue
        f = Path(cache) / f"{run}__{i}__{a}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        rec = dict(run=run, id=i, attempt=a, kicad=ks)
        w = World(data, g=0.1)
        for pi in range(len(w.parts)):
            w.place_original(pi)
        rec["hpwl"] = round(w.hpwl(), 2)
        for tag, kw in (("lift", {}), ("spread", dict(spread=2))):
            t = time.time()
            rec[tag] = lifted.lifted_conflicts(w, **kw)
            rec[tag]["t"] = round(time.time() - t, 2)
        t = time.time()
        r = Router(w)
        r.pathfinder(iters=40)
        rec["engine"] = r.stats()
        rec["engine"]["t"] = round(time.time() - t, 2)
        fo.write(json.dumps(rec, default=str) + "\n")
        fo.flush()
        print(run, i, a, rec["lift"].get("forced_vias"), rec["engine"], flush=True)


def report(out):
    import numpy as np
    from scipy.stats import spearmanr
    rows = [json.loads(l) for l in open(out)]
    preds = {
        "hpwl": lambda r: r["hpwl"],
        "lift_len": lambda r: r["lift"]["lift_len_mm"],
        "lift_conflicts": lambda r: r["lift"]["conflicts"],
        "lift_netpairs": lambda r: r["lift"]["net_pairs"],
        "lift_forced_vias": lambda r: r["lift"].get("forced_vias", 0),
        "lift_unresolved": lambda r: r["lift"].get("unresolved", 0),
        "lift_cost": lambda r: r["lift"].get("cost", 0),
        "spread_forced_vias": lambda r: r["spread"].get("forced_vias", 0),
        "spread_unresolved": lambda r: r["spread"].get("unresolved", 0),
        "spread_cost": lambda r: r["spread"].get("cost", 0),
    }
    targets = {
        "eng_vias": lambda r: r["engine"]["vias"],
        "eng_unrouted": lambda r: r["engine"]["unrouted"],
        "eng_len": lambda r: r["engine"]["length_mm"],
        "eng_cost": lambda r: r["engine"]["length_mm"] + 2 * r["engine"]["vias"] + 20 * r["engine"]["unrouted"],
    }
    by = {}
    for r in rows:
        by.setdefault(r["id"], []).append(r)
    print(f"{len(rows)} placements on {len(by)} boards")
    print("pooled Spearman rho (all placements) | mean within-board Spearman rho (boards with >= 4 placements)")
    hdr = "predictor".ljust(20) + "".join(t.rjust(22) for t in targets)
    print(hdr)
    for pn, pf in preds.items():
        line = pn.ljust(20)
        for tn, tf in targets.items():
            x = np.array([pf(r) for r in rows], float)
            y = np.array([tf(r) for r in rows], float)
            rho = spearmanr(x, y).statistic
            ws = []
            for i, rs in by.items():
                if len(rs) < 4:
                    continue
                xx = np.array([pf(r) for r in rs], float)
                yy = np.array([tf(r) for r in rs], float)
                if np.ptp(xx) == 0 or np.ptp(yy) == 0:
                    continue
                ws.append(spearmanr(xx, yy).statistic)
            line += f"{rho:10.2f} | {np.mean(ws):5.2f} ({len(ws):2d})".rjust(22)
        print(line)
    # human vs ours, per placement source
    print("\nmeans per source: forced_vias(lift) unresolved(lift) forced_vias(spread) eng_vias eng_unrouted")
    for src in ("human",) + RUNS:
        rs = [r for r in rows if r["run"] == src]
        if not rs:
            continue
        m = lambda f: round(float(np.mean([f(r) for r in rs])), 2)  # noqa: E731
        print(src.ljust(14), len(rs), m(preds["lift_forced_vias"]), m(preds["lift_unresolved"]),
              m(preds["spread_forced_vias"]), m(targets["eng_vias"]), m(targets["eng_unrouted"]))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "extract":
        extract(sys.argv[2])
    elif cmd == "measure":
        measure(sys.argv[2], sys.argv[3])
    else:
        report(sys.argv[2])
