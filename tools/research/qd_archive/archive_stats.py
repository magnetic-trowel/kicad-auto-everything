# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize qd archives (qd_dir JSON per board) and, optionally, jc restart logs.

    python archive_stats.py kae-work/qd/<run> [--jc kae-work/jc-png/ab33-jc] [--suite FILE]

Per run: candidates and cells per board, share of candidates that opened a new cell /
improved a cell / improved the global best, where the final pick came from (init vs a
mutation), per operator success, and diversity: length-best and physics-best elites
vs the objective pick (and the same over jc's restarts when --jc is given).
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def gmean(x):
    x = [v for v in x if v and v > 0]
    return float(np.exp(np.mean(np.log(x)))) if x else float("nan")


def lv(d):
    return d["len"] + 2.0 * d["vias"] + 1e3 * d["unrouted"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--jc")
    ap.add_argument("--suite")
    a = ap.parse_args()
    files = sorted(Path(a.dir).glob("*.json"))
    if a.suite:
        keep = {l.strip() for l in open(a.suite) if l.strip()}
        files = [f for f in files if f.stem in keep]
    n = cells = nm = 0
    newc = imp = gb = 0
    pick = Counter()
    ops = defaultdict(lambda: [0, 0, 0])
    lv_gain, ph_gain, ph_cost, lv_cost, jlv_gain, jph_gain = [], [], [], [], [], []
    for f in files:
        A = json.loads(f.read_text())
        H = A["hist"]
        n += len(H)
        nm += sum(h["op"] not in ("init", "fresh") for h in H)
        cells += len(A["cells"])
        newc += sum(h["new_cell"] for h in H if h["op"] not in ("init", "fresh"))
        imp += sum(h["improved"] for h in H if h["op"] not in ("init", "fresh"))
        gb += sum(h["gbest"] for h in H if h["op"] not in ("init", "fresh"))
        by = {tuple(c["key"]): c for c in A["cells"]}
        best = by[tuple(A["best"])]
        pick["restart" if best["meta"]["op"] in ("init", "fresh") else "mutation"] += 1
        for h in H:
            if h["op"] in ("init", "fresh"):
                continue
            o = "".join(ch for ch in h["op"].split("@")[0] if ch.isalpha())
            ops[o][0] += 1
            ops[o][1] += h["improved"]
            ops[o][2] += h["gbest"]
        bl = by[tuple(A["by_len"])]
        if lv(best) > 0:
            lv_gain.append(lv(bl) / lv(best))
            lv_cost.append(bl["cost"] / best["cost"])
        if A.get("by_phys"):
            bp = by[tuple(A["by_phys"])]
            if best["phys"] > 0:
                ph_gain.append(max(bp["phys"], 1e-3) / best["phys"])
                ph_cost.append(bp["cost"] / best["cost"])
        if a.jc:
            p = Path(a.jc) / f"{f.stem}.runs.json"
            if p.exists():
                R = json.loads(p.read_text())["runs"]
                jb = min(R, key=lambda r: r["cost"])
                jl = min(R, key=lambda r: r["length_mm"] + 2 * r["vias"] + 1e3 * r["unrouted"])
                f_ = lambda r: r["length_mm"] + 2 * r["vias"] + 1e3 * r["unrouted"]
                if f_(jb) > 0:
                    jlv_gain.append(f_(jl) / f_(jb))
                if jb["phys"] > 0:
                    jp = min(R, key=lambda r: (r["unrouted"], r["phys"]))
                    jph_gain.append(max(jp["phys"], 1e-3) / jb["phys"])
    m = max(1, nm)
    print(f"boards {len(files)}; candidates/board {n / max(1, len(files)):.1f}; cells/board "
          f"{cells / max(1, len(files)):.1f}")
    print(f"mutations: new cell {newc / m:.2f}, improved a cell {imp / m:.2f}, new global best {gb / m:.3f}")
    print(f"final pick from: {dict(pick)}")
    print("operators (tries, cell-improve rate, global-best rate): " +
          ", ".join(f"{o} {v[0]} {v[1] / max(1, v[0]):.2f} {v[2] / max(1, v[0]):.3f}" for o, v in sorted(ops.items())))
    print(f"length-best elite vs pick: length+vias x{gmean(lv_gain):.3f} (n={len(lv_gain)}), "
          f"objective x{gmean(lv_cost):.3f}")
    if ph_gain:
        print(f"physics-best elite vs pick: physics x{gmean(ph_gain):.3f} (n={len(ph_gain)}), "
              f"objective x{gmean(ph_cost):.3f}")
    if a.jc:
        print(f"jc restarts, same: length-best x{gmean(jlv_gain):.3f} (n={len(jlv_gain)}), "
              f"physics-best x{gmean(jph_gain):.3f} (n={len(jph_gain)})")


if __name__ == "__main__":
    main()
