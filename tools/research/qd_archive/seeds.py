# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-seed summary of joint runs (kaebench, harness score v7): mean and [min, max]
over seeds of legal, clean (cp), completion, and length / vias on the boards every run
completed in that seed; cpk (clean on any seed); optional physics ratios parsed from
physics_score.py markdown, one file per attempt.

    python seeds.py RUN_DIR... [--seeds 3] [--suite kae-v7/ab33.txt]
                    [--phys 'kae-v7/score/{run}-a{seed}.md']
"""
import argparse
import json
from pathlib import Path

import numpy as np


def load(run, seed):
    rows = {}
    for f in Path(run).glob(f"*/*/*/attempt-{seed}/attempt.json"):
        r = json.loads(f.read_text())
        s = r.get("score") or {}
        p = s if r.get("kind") == "joint" else ((r.get("probe") or {}).get("score") or {})
        rows[r["id"]] = dict(legal=bool(s.get("legal")), clean=bool(s.get("legal")) and bool(p.get("clean")),
                             completion=p.get("completion", 0.0) if s.get("valid") else 0.0,
                             length=p.get("track_length_mm"), vias=p.get("vias"),
                             cpu=(r.get("meta") or {}).get("cpu_s") or r.get("cpu_s"))
    return rows


def phys_row(md, run):
    """(fast physics x human, routed physics x human) from a physics_score markdown table."""
    p = Path(md)
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if c and c[0] == run and len(c) > 10:
            try:
                return float(c[4]), float(c[10])
            except ValueError:
                return None
    return None


def fmt(v, d=3):
    v = [x for x in v if x is not None]
    if not v:
        return "—"
    return f"{np.mean(v):.{d}f} [{min(v):.{d}f}, {max(v):.{d}f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--suite")
    ap.add_argument("--phys", help="markdown path pattern with {run} and {seed}")
    a = ap.parse_args()
    names = [Path(r).name for r in a.runs]
    data = {n: [load(r, s) for s in range(a.seeds)] for n, r in zip(names, a.runs)}
    ids = set.intersection(*[set(d) for v in data.values() for d in v if d]) if data else set()
    if a.suite:
        ids &= {l.strip() for l in open(a.suite) if l.strip()}
    ids = sorted(ids)
    print(f"boards in common (all runs, all seeds): {len(ids)}; seeds {a.seeds}; mean [min, max] over seeds\n")
    full = {s: [i for i in ids if all(data[n][s].get(i, {}).get("completion", 0) >= 1.0 and data[n][s][i]["length"]
                                      for n in names)] for s in range(a.seeds)}
    hdr = "| run | legal | clean (cp) | cpk | completion | length (common complete) | vias |"
    if a.phys:
        hdr += " fast phys x human | routed phys x human |"
    print(hdr)
    print("|" + "---|" * (hdr.count("|") - 1))
    for n in names:
        S = [s for s in range(a.seeds) if data[n][s]]
        leg = [np.mean([data[n][s][i]["legal"] for i in ids]) for s in S]
        cln = [np.mean([data[n][s][i]["clean"] for i in ids]) for s in S]
        cpk = np.mean([any(data[n][s][i]["clean"] for s in S) for i in ids])
        com = [np.mean([data[n][s][i]["completion"] for i in ids]) for s in S]
        L = [sum(data[n][s][i]["length"] for i in full[s]) for s in S]
        V = [sum(data[n][s][i]["vias"] for i in full[s]) for s in S]
        row = f"| {n} | {fmt(leg)} | {fmt(cln)} | {cpk:.3f} | {fmt(com)} | {fmt(L, 0)} | {fmt(V, 0)} |"
        if a.phys:
            ph = [phys_row(a.phys.format(run=n, seed=s), n) for s in S]
            row += f" {fmt([p[0] if p else None for p in ph], 2)} | {fmt([p[1] if p else None for p in ph], 2)} |"
        print(row)
    print("\ncommon complete boards per seed: " + ", ".join(f"s{s} {len(v)}" for s, v in full.items()))


if __name__ == "__main__":
    main()
