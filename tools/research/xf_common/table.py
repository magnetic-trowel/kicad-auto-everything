# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One summary row per run: DRC/joint score over seeds plus physics over seeds.

    python table.py PHYS_DIR RUN_DIR [RUN_DIR ...]

RUN_DIRs are $XF_WORK/results/RUN; PHYS_DIR is score.sh's NAME-phys/ (seed-N/<run>.json),
or '-' for none. Columns: legal and clean (mean +- sd over seeds), clean best-of-k,
completion (mean over seeds), length and vias summed over the boards that every run and
every seed completed (mean over seeds), then fast and routed physics (method/human gmean,
mean +- sd over seeds). Reads the same fields as compare.py and seeds.py.
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path


def load(run):
    rows = defaultdict(dict)  # seed -> id -> metrics
    for f in [*Path(run).glob("*/joint/*/attempt-*/attempt.json"), *Path(run).glob("*/place/*/attempt-*/attempt.json")]:
        r = json.loads(f.read_text())
        s = r.get("score") or {}
        p = s if r.get("kind") == "joint" else ((r.get("probe") or {}).get("score") or {})
        rows[r["attempt"]][r["id"]] = dict(
            legal=bool(s.get("legal")), clean=bool(s.get("legal")) and bool(p.get("clean")),
            completion=p.get("completion", 0.0) if s.get("valid") else 0.0,
            length=p.get("track_length_mm"), vias=p.get("vias"))
    return rows


def ms(xs, nd=3):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "-"
    return f"{st.mean(xs):.{nd}f} ± {st.stdev(xs):.{nd}f}" if len(xs) > 1 else f"{xs[0]:.{nd}f}"


def main(phys, runs):
    data = {Path(r).name: load(r) for r in runs}
    ids = sorted(set.union(*[set(d[s]) for d in data.values() for s in d]))
    full = [i for i in ids if all(d[s].get(i, {}).get("completion", 0) >= 1.0 and d[s][i].get("length")
                                  for d in data.values() for s in d)]
    ph = defaultdict(dict)
    if phys != "-":
        for f in Path(phys).glob("seed-*/*.json"):
            ph[f.stem][int(f.parent.name.split("-")[1])] = json.loads(f.read_text())["summary"]
    print(f"{len(ids)} boards; length and vias over the {len(full)} boards every run and seed completed.\n")
    print("| run | seeds | legal | clean | clean best-of-k | completion | length (mm) | vias | fast phys | routed phys |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name, d in data.items():
        seeds = sorted(d)
        m = lambda k: [sum(d[s].get(i, {}).get(k, 0.0) for i in ids) / len(ids) for s in seeds]  # noqa: E731
        best = sum(any(d[s].get(i, {}).get("clean") for s in seeds) for i in ids) / len(ids)
        L = [sum(d[s][i]["length"] for i in full) for s in seeds]
        V = [sum(d[s][i]["vias"] for i in full) for s in seeds]
        p = ph.get(name, {})
        fast = [p[s]["place_gmean_ratio"] for s in sorted(p)]
        rout = [p[s]["routed_gmean_ratio"] for s in sorted(p)]
        print(f"| {name} | {len(seeds)} | {ms(m('legal'))} | {ms(m('clean'))} | {best:.3f} | {ms(m('completion'))} "
              f"| {st.mean(L):.0f} | {st.mean(V):.0f} | {ms(fast, 2)} | {ms(rout, 2)} |")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
