# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tables for RESULTS.md from kae-work/pour/<board>/<tag>/results.json and place.json.

    python summarize.py [--place kae-work/pour/place.json]
"""
import glob
import json
import os
import sys

import numpy as np
from scipy.stats import pearsonr, spearmanr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
WORK = os.path.join(ROOT, "kae-work", "pour")


def short(b):
    return b.replace("pcbcorpus-", "").split("-")[0:2] and "-".join(b.replace("pcbcorpus-", "").split("-")[:2])


def boards_table():
    rows = []
    for f in sorted(glob.glob(os.path.join(WORK, "*", "*", "results.json"))):
        tag = os.path.basename(os.path.dirname(f))
        if tag not in ("iso_area", "fill"):
            continue
        r = json.load(open(f))
        for ln, lr in r["layers"].items():
            for k in [k for k in lr if k.startswith("mbo_")]:
                h, m = lr["human"], lr[k]
                nets = lr["nets"]
                for n in nets:
                    rows.append(dict(board=short(r["board"]), layer=ln, mode=tag, kernel=k[4:],
                                     npour=len(nets), net=n,
                                     A_h=h[n]["area_mm2"], A_m=m[n]["area_mm2"],
                                     R_h=h[n]["R_mean_sq"], R_m=m[n]["R_mean_sq"],
                                     c_h=h[n]["pairs_connected"], c_m=m[n]["pairs_connected"],
                                     pairs=h[n]["pairs"],
                                     isl_h=h[n]["islands"], isl_m=m[n]["islands"],
                                     split_h=h[n]["split_mm"], split_m=m[n]["split_mm"]))
        for k in [k for k in r if k.startswith("net_mbo_")]:
            for n, hm in r["net_human"].items():
                mm = r[k][n]
                rows.append(dict(board=short(r["board"]), layer="ALL", mode=tag, kernel=k[8:],
                                 net=n, A_h=hm["copper_mm2"], A_m=mm["copper_mm2"],
                                 R_h=hm["R_mean"], R_m=mm["R_mean"], c_h=hm["connected"],
                                 c_m=mm["connected"], pairs=hm["pairs"],
                                 drc_h=r.get("drc_human"), drc_m=r.get(f"drc_{k[8:]}")))
    return rows


def fmt(v, p=2):
    return "-" if v is None else f"{v:.{p}f}"


def print_boards(rows):
    print("| board | layer | mode | kernel | net | A human | A MBO | R human | R MBO | R ratio | conn h/m | split h/m |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        ratio = (r["R_m"] / r["R_h"]) if r["R_h"] and r["R_m"] else None
        print(f"| {r['board']} | {r['layer']} | {r['mode']} | {r['kernel']} | {r['net'][:14]} | "
              f"{r['A_h']:.0f} | {r['A_m']:.0f} | {fmt(r['R_h'])} | {fmt(r['R_m'])} | {fmt(ratio)} | "
              f"{r['c_h']}/{r['c_m']} of {r['pairs']} | "
              f"{fmt(r.get('split_h'), 0)}/{fmt(r.get('split_m'), 0)} |")


def place_table(path):
    res = json.load(open(path))
    rows = []
    for key, row in res.items():
        if "error" in row:
            continue
        bid, who = key.split("|")
        for n, v in row.items():
            f = v["full"]
            if not f["R_mean"] or f["connected"] < f["pairs"] or not v.get("world"):
                frac = f["connected"] / max(f["pairs"], 1)
            else:
                frac = 1.0
            rows.append(dict(board=bid, who=who, net=n, R=f["R_mean"], frac=frac, pads=f["pads"],
                             Rw=v["world"]["R_pred"] if v.get("world") else None,
                             Ri=v["world"]["R_ideal"] if v.get("world") else None,
                             fw=v["world"]["free"] if v.get("world") else None,
                             Rr=v["routed"]["R_pred"] if v.get("routed") else None,
                             spread=v["world"]["spread_mm"] if v.get("world") else None))
    ok = [r for r in rows if r["R"] and r["Rw"] and r["frac"] == 1.0]
    print(f"\nplacement study: {len(rows)} (board, placement, net) rows, {len(ok)} fully connected")
    for name, key in (("ideal sheet (pads only)", "Ri"), ("World pour_score (pads block)", "Rw"),
                      ("routed board term", "Rr"), ("pad spread mm", "spread"),
                      ("free fraction", "fw")):
        x = np.array([r[key] for r in ok if r[key] is not None], float)
        y = np.array([r["R"] for r in ok if r[key] is not None], float)
        if len(x) > 3:
            print(f"  {name:32s} n={len(x)} spearman={spearmanr(x, y)[0]:+.2f} "
                  f"pearson(log)={pearsonr(np.log(np.abs(x) + 1e-9), np.log(y))[0]:+.2f}")
    # within-board: does the term rank the three placements like the full metric?
    agree = tot = 0
    by = {}
    for r in ok:
        by.setdefault((r["board"], r["net"]), {})[r["who"]] = r
    for (b, n), d in by.items():
        ws = list(d)
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                a, c = d[ws[i]], d[ws[j]]
                if abs(a["R"] - c["R"]) / max(a["R"], c["R"]) < 0.02:
                    continue
                tot += 1
                agree += (a["R"] < c["R"]) == (a["Rw"] < c["Rw"])
    print(f"  pairwise ranking agreement (World term vs full, |dR|>2%): {agree}/{tot}")
    # who wins on the full metric
    print("\n| board | net | pads | R human | R seq | R combo | pred human | pred seq | pred combo | conn h/s/c |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (b, n), d in sorted(by.items()):
        pass
    allby = {}
    for r in rows:
        allby.setdefault((r["board"], r["net"]), {})[r["who"]] = r
    for (b, n), d in sorted(allby.items()):
        g = lambda w, k: d[w][k] if w in d and d[w][k] is not None else None  # noqa: E731
        print(f"| {short(b)} | {n[:10]} | {d.get('human', {}).get('pads', '-')} | "
              f"{fmt(g('human', 'R'))} | {fmt(g('pnr-seq-v5', 'R'))} | {fmt(g('pnr-combo-v5', 'R'))} | "
              f"{fmt(g('human', 'Rw'))} | {fmt(g('pnr-seq-v5', 'Rw'))} | {fmt(g('pnr-combo-v5', 'Rw'))} | "
              f"{fmt(g('human', 'frac'))}/{fmt(g('pnr-seq-v5', 'frac'))}/{fmt(g('pnr-combo-v5', 'frac'))} |")
    return rows


if __name__ == "__main__":
    print_boards(boards_table())
    p = sys.argv[sys.argv.index("--place") + 1] if "--place" in sys.argv else os.path.join(WORK, "place.json")
    if os.path.exists(p):
        place_table(p)
