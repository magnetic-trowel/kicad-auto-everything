#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for barrier-fit-ab (PLAN.md): true region splits not used by barrier-split-ab2.

    select_boards.py SCAN.jsonl FEATURES USABILITY USED_BOARDS [--stage1 120]

Pool: usable_route_test boards of at most 1,000 pads whose outline less all-copper track keepouts falls
into two or more regions (the barrier scan, kae.place.barriers.regions) and whose courtyards cover at most
90 % of the outline on a side, as in barrier-ab. Boards of barrier-split-ab2 and every board of their
repo families are left out (the boards that suggested the hypothesis, and their near copies). One board
per repo_family, in sha256(SEED, id) order. Writes boards.txt (all, in that order) and stage1.boards.txt
(the first --stage1). Deterministic.
"""
import argparse
import hashlib
import json

SEED = "barrier-fit-ab-2026-11-14"


def key(b):
    return hashlib.sha256((SEED + "\0" + b).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan"), ap.add_argument("features"), ap.add_argument("usability"), ap.add_argument("used")
    ap.add_argument("--stage1", type=int, default=120)
    a = ap.parse_args()
    use = {r["id"]: r for r in map(json.loads, open(a.usability))}
    feats = {r["id"]: r for r in map(json.loads, open(a.features))}
    used = {x.strip() for x in open(a.used) if x.strip()}
    fam = lambda b: use.get(b, {}).get("repo_family") or b
    used_fams = {fam(b) for b in used}
    fits = lambda b: max(feats[b].get("courtyard_frac_front") or 0, feats[b].get("courtyard_frac_back") or 0) <= 0.9
    pool = [r for r in map(json.loads, open(a.scan))
            if "err" not in r and use.get(r["board"], {}).get("usable_route_test")
            and 0 < (feats.get(r["board"], {}).get("n_pads") or 0) <= 1000 and r["n_regions"] >= 2 and fits(r["board"])
            and r["board"] not in used and fam(r["board"]) not in used_fams]
    fams, out = set(), []
    for r in sorted(pool, key=lambda r: key(r["board"])):
        if fam(r["board"]) in fams:
            continue
        fams.add(fam(r["board"]))
        out.append(r)
    with open("boards.txt", "w") as h:
        h.write("\n".join(r["board"] for r in out) + "\n")
    with open("stage1.boards.txt", "w") as h:
        h.write("\n".join(r["board"] for r in out[:a.stage1]) + "\n")
    print("pool", len(pool), "chosen", len(out), "stage1", min(a.stage1, len(out)),
          "with keepout walls", sum(1 for r in out if r["barriers"] > 0), "with signal nets across regions (scan)", sum(1 for r in out if r["cross_nets"] > 0))


if __name__ == "__main__":
    main()
