# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize diag.py output: LDS-optimality of orientations per run, and how well the
predicted forced vias / crossings / overflow track the routed vias.

    python diag_report.py DIAG.json
"""
import json
import sys
from collections import defaultdict

import numpy as np
from scipy.stats import spearmanr


def main(path):
    res = json.load(open(path))
    runs = defaultdict(list)
    for key, v in res.items():
        if "error" in v:
            continue
        run, bid, a = key.split("/")
        runs[run].append((bid, int(a), v))
    print("| run | buses | fv-optimal | sum fv | sum fv_min | vias on bus nets | boards | sum vias |")
    print("|---|---|---|---|---|---|---|---|")
    allb = []
    for run, rows in runs.items():
        bs = [b for _, _, v in rows for b in v["buses"]]
        opt = sum(b["fv"] == b["fv_min"] for b in bs)
        print(f"| {run} | {len(bs)} | {opt}/{len(bs)} | {sum(b['fv'] for b in bs)} | {sum(b['fv_min'] for b in bs)} "
              f"| {sum(b['routed_vias'] for b in bs)} | {len(rows)} | {sum(v['vias'] for _, _, v in rows)} |")
        allb += bs
    if allb:
        fv = np.array([b["fv"] for b in allb])
        rv = np.array([b["routed_vias"] for b in allb])
        print(f"\nper bus (all runs, n={len(allb)}): spearman(fv, routed vias on bus nets) = "
              f"{spearmanr(fv, rv)[0]:.2f}; mean vias fv=0: {rv[fv == 0].mean():.2f}, fv>0: "
              f"{rv[fv > 0].mean() if (fv > 0).any() else float('nan'):.2f}")
    # board level: within-board (demeaned across runs/attempts) correlation
    byb = defaultdict(list)
    for run, rows in runs.items():
        for bid, a, v in rows:
            byb[bid].append(v)
    for term in ("fv", "x", "ovf"):
        xs, ys = [], []
        for bid, vs in byb.items():
            if len(vs) < 3:
                continue
            x = np.array([v[term] for v in vs], float)
            y = np.array([v["vias"] for v in vs], float)
            xs += list(x - x.mean())
            ys += list(y - y.mean())
        xs, ys = np.array(xs), np.array(ys)
        ok = (xs != 0) | (ys != 0)
        r = spearmanr(xs[ok], ys[ok])[0] if ok.sum() > 3 else float("nan")
        pooled = spearmanr([v[term] for vs in byb.values() for v in vs], [v["vias"] for vs in byb.values() for v in vs])[0]
        print(f"board level {term}: pooled spearman vs routed vias {pooled:.2f}; within-board (demeaned) {r:.2f} (n={ok.sum()})")


if __name__ == "__main__":
    main(sys.argv[1])
