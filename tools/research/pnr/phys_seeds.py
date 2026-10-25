# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics table over seeds, from physics_score.py outputs (one --out dir per attempt).

    python phys_seeds.py kae-v7/phys/a0 kae-v7/phys/a1 kae-v7/phys/a2 [--runs RUN1,RUN2]

Per run: legal / clean of the physics boards, fast physics (place terms total and capped
u, method / human geometric mean) and routed physics (all scored boards, and boards with
no open hop on either side), each as mean ± half-range over the seeds, then per seed.
"""
import argparse
import json
import sys
from pathlib import Path


def ms(xs, nd=2):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "-"
    m = sum(xs) / len(xs)
    return f"{m:.{nd}f} ± {(max(xs) - min(xs)) / 2:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--runs", default=None)
    ap.add_argument("--suite", default=None, help="restrict to these board ids (summaries recomputed)")
    ap.add_argument("--override", action="append", default=[], metavar="RUN=OTHER",
                    help="take the --override-ids boards of RUN from run OTHER (same seed dir)")
    ap.add_argument("--override-ids", default=None)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pnr_phys"))
    from physics_score import summarize
    keep = set(Path(a.suite).read_text().split()) if a.suite else None
    oids = set(Path(a.override_ids).read_text().split()) if a.override_ids else set()
    over = dict(o.split("=", 1) for o in a.override)
    seeds = []
    for d in a.dirs:
        raw = {p.stem: json.loads(p.read_text()) for p in Path(d).glob("*.json")}
        out = {}
        for name, j in raw.items():
            boards = dict(j["boards"])
            if name in over and over[name] in raw:
                boards = {b: r for b, r in boards.items() if b not in oids}
                boards.update({b: r for b, r in raw[over[name]]["boards"].items() if b in oids})
            if keep is not None:
                boards = {b: r for b, r in boards.items() if b in keep}
            out[name] = summarize(name, boards, j["human"])
        seeds.append(out)
    runs = a.runs.split(",") if a.runs else sorted(set.intersection(*[set(s) for s in seeds]))
    print("| run | legal (of n) | clean (of n) | completion | place terms x human | capped u x human "
          "| routed x human | routed, no open hop: x human (n) | open hops / board |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        S = [s[r] for s in seeds if r in s]
        hp = [x["harness"]["phys"] for x in S]
        n = hp[0]["n"]
        print(f"| {r} | {ms([h['legal'] for h in hp], 1)} ({n}) | {ms([h['clean'] for h in hp], 1)} | "
              f"{ms([h['completion'] for h in hp])} | {ms([x['place_gmean_ratio'] for x in S])} | "
              f"{ms([x['capped_gmean_ratio'] for x in S])} | {ms([x['routed_gmean_ratio'] for x in S])} | "
              f"{ms([x['closed_routed_gmean_ratio'] for x in S])} ({'/'.join(str(x['closed_scored']) for x in S)}) | "
              f"{ms([x['open_hops_mean'] for x in S], 1)} |")
    print("\nPer seed (capped u / routed x human):\n")
    for r in runs:
        cells = []
        for k, s in enumerate(seeds):
            x = s.get(r)
            if x:
                f = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
                cells.append(f"seed {k}: {f(x['capped_gmean_ratio'])} / {f(x['routed_gmean_ratio'])}")
        print(f"- {r}: " + "; ".join(cells))
    h = seeds[0][runs[0]]
    print(f"\nHuman open hops / board: {h['open_hops_mean_human']}")


if __name__ == "__main__":
    main()
