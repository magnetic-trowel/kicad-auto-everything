#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for barrier-ab (see PLAN.md), from a scan of region splits and barriers (kae.place.barriers).

    select_boards.py SCAN.jsonl FEATURES USABILITY MERIT [--split-n 100] [--weight-n 80]

Writes split.boards.txt (several regions) and weight.boards.txt (one region with barriers).
One board per repo_family, in sha256(SEED, id) order, merit boards first. Deterministic.
"""
import argparse
import hashlib
import json

SEED = "barrier-ab-2026-11-09"


def key(b):
    return hashlib.sha256((SEED + "\0" + b).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan"), ap.add_argument("features"), ap.add_argument("usability"), ap.add_argument("merit")
    ap.add_argument("--split-n", type=int, default=100), ap.add_argument("--weight-n", type=int, default=80)
    a = ap.parse_args()
    use = {r["id"]: r for r in map(json.loads, open(a.usability))}
    feats = [json.loads(x) for x in open(a.features)]
    pads = {r["id"]: r.get("n_pads") or 0 for r in feats}
    # courtyards per side at most 90% of the outline: the parts fit the board as parsed
    fits = {r["id"]: max(r.get("courtyard_frac_front") or 0, r.get("courtyard_frac_back") or 0) <= 0.9 for r in feats}
    merit = {x.strip() for x in open(a.merit) if x.strip()}
    rows = [r for r in map(json.loads, open(a.scan)) if "err" not in r and use.get(r["board"], {}).get("usable_route_test")
            and 0 < pads.get(r["board"], 0) <= 1000]
    split = [r for r in rows if r["n_regions"] >= 2 and fits.get(r["board"], False)]  # parts that cannot fit the outline: a broken outline
    weight = [r for r in rows if r["n_regions"] < 2 and (r["barriers"] > 0 or (r["holes"] > 0 and r["hole_area"] >= 0.03 * max(r["board_area"], 1.0)))]

    def pick(pool, n):
        fams, out = set(), []
        for r in sorted(pool, key=lambda r: (r["board"] not in merit, key(r["board"]))):
            f = use[r["board"]].get("repo_family") or r["board"]
            if f in fams and r["board"] not in merit:
                continue
            fams.add(f)
            out.append(r)
            if len(out) >= n:
                break
        return out

    for name, pool, n in (("split", split, a.split_n), ("weight", weight, a.weight_n)):
        chosen = pick(pool, n)
        with open(f"{name}.boards.txt", "w") as h:
            h.write("\n".join(sorted(r["board"] for r in chosen)) + "\n")
        print(name, "pool", len(pool), "chosen", len(chosen), "merit", sum(r["board"] in merit for r in chosen),
              "with keepout walls", sum(1 for r in chosen if r["barriers"] > 0), "signal nets across regions", sum(1 for r in chosen if r["cross_nets"] > 0))


if __name__ == "__main__":
    main()
