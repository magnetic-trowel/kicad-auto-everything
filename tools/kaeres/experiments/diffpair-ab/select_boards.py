#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for diffpair-ab: boards that have real differential pairs, one per repo_family, seeded.

Pool: the union of the pair-relevant n100 suites (kept for a reproducible study of 659 boards) with a truth scan
(one JSON line per board: pairs with tier, interface, human coupling, pad distance; from the human layout).
A board qualifies when it has at least one pair that is real and matters: tier rule or interface, KiCad's own suffix rule,
both legs at least 4 mm, human coupled share >= 0.5, the pads of the pair at least once within 2 mm on one
footprint. usable_route_test true, 30 to 500 footprints (fixed before results: bigger boards leave Freerouting
timing out at the 900 s budget and move with host load), one per repo_family. Boards are ordered by sha256(seed, id).
"""
import hashlib
import json
import sys

SEED = "diffpair-ab-2026-11-09"


def main(scan, usability, manifest, n, out):
    us = {r["id"]: r for r in map(json.loads, open(usability))}
    fp = {r["id"]: r.get("footprints", 0) for r in map(json.loads, open(manifest))}
    good = []
    for line in open(scan):
        r = json.loads(line)
        if "pairs" not in r or not us.get(r["id"], {}).get("usable_route_test") or not 30 <= fp.get(r["id"], 0) <= 500:
            continue
        real = [p for p in r["pairs"] if p["tier"] in ("rule", "interface") and p["kicad"] and min(p["len_p"], p["len_n"]) >= 4
                and p["coupled"] is not None and p["coupled"] >= 0.5 and (p["min_pad_d"] if p["min_pad_d"] is not None else 99) <= 2]
        if real:
            good.append(r["id"])
    good.sort(key=lambda i: hashlib.sha256(f"{SEED}|{i}".encode()).hexdigest())
    seen, out_ids = set(), []
    for i in good:
        fam = us[i]["repo_family"]
        if fam in seen:
            continue
        seen.add(fam)
        out_ids.append(i)
    print(f"{len(good)} boards qualify, {len(out_ids)} families", file=sys.stderr)
    open(out, "w").write("\n".join(out_ids[:n]) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:4], int(sys.argv[4]), sys.argv[5])
