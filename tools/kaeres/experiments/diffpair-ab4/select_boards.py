#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for diffpair-ab4 (PLAN.md): boards with real high-speed differential pairs, one per repo_family, seeded.

Pool: the full tag suites diffpair_rules, if_usb3, if_hdmi.tmds_pairs, if_mipi, if_pcie, if_ethernet, if_lvds
(board-tags/suites), restricted to boards the pair truth scan covers (one JSON line per board, pairs with tier,
interface, human coupling and pad distance, read from the human layout). A board qualifies as in diffpair-ab: at least
one pair of tier rule or interface, KiCad's suffix rule, both legs at least 4 mm, human coupled share >= 0.5, the
pair's pads within 2 mm on one footprint; usable_route_test; 30 to 500 footprints. One board per repo_family in
sha256(seed, id) order. Selection reads the human layout only, never a method's result.

    select_boards.py SUITES_DIR SCAN USABILITY MANIFEST OUT_ORDERED
OUT_ORDERED lists every qualifying family's board in order; boards.txt is its first 120, the extension the next ones.
"""
import hashlib
import json
import sys

SEED = "diffpair-ab4-2026-11-14"
SUITES = ("diffpair_rules", "if_usb3", "if_hdmi.tmds_pairs", "if_mipi", "if_pcie", "if_ethernet", "if_lvds")


def real(r):
    return [p for p in r.get("pairs") or [] if p["tier"] in ("rule", "interface") and p["kicad"]
            and min(p["len_p"], p["len_n"]) >= 4 and p["coupled"] is not None and p["coupled"] >= 0.5
            and (p["min_pad_d"] if p["min_pad_d"] is not None else 99) <= 2]


def main(suites, scan, usability, manifest, out):
    pool = set()
    for s in SUITES:
        pool |= set(open(f"{suites}/{s}.txt").read().split())
    us = {r["id"]: r for r in map(json.loads, open(usability))}
    fp = {r["id"]: r.get("footprints", 0) for r in map(json.loads, open(manifest))}
    sc = {r["id"]: r for r in map(json.loads, open(scan))}
    good = sorted((i for i in pool if i in sc and us.get(i, {}).get("usable_route_test") and 30 <= fp.get(i, 0) <= 500
                   and real(sc[i])), key=lambda i: hashlib.sha256(f"{SEED}|{i}".encode()).hexdigest())
    seen, ids = set(), []
    for i in good:
        if us[i]["repo_family"] not in seen:
            seen.add(us[i]["repo_family"])
            ids.append(i)
    print(f"pool {len(pool)}, scanned {len(pool & set(sc))}, qualify {len(good)}, families {len(ids)}", file=sys.stderr)
    open(out, "w").write("\n".join(ids) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:6])
