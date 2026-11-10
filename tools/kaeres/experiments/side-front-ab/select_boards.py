#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boards for side-front-ab: where a part's side is a real decision.

    select_boards.py --tags DIR --merit FILE --corpus DIR [--n 150] [--out boards.txt]

A board qualifies when it is in the `double_sided_assembly` or `back_heavy` tag suite, has more than 10 back-side SMD parts (counted by parsing the board, not
just the features' proxy), its assembled parts' courtyards (both sides) cover at most 85% of the
outline so front-only assembly is thinkable, it passes `usable_route_test`, and it has at most
1,000 pads (bigger boards are memory-bound: a different experiment). All qualifying merit boards
are taken; the rest of the list comes from one board per repo_family, in sha256(SEED, id) order.

Prints one line per board chosen: id, front SMD, back SMD, fill, merit or corpus. Deterministic.
"""
import argparse
import hashlib
import json
import os
import re
import sys

SEED = "side-front-ab-2026-11-09"
NOT_ASSEMBLED = re.compile(r"^(TP|FID|H\d|MH|LOGO|REF|G\d)", re.I)


def key(bid):
    return hashlib.sha256((SEED + "\0" + bid).encode()).hexdigest()


def count_sides(path):
    from kae.board.kicad_file import load
    b = load(path)
    def smd(f):
        return f.pads and all(not p.drill and p.kind in ("smd", "connect") for p in f.pads) and not NOT_ASSEMBLED.match(f.ref)
    return sum(1 for f in b.footprints if f.side == "F" and smd(f)), sum(1 for f in b.footprints if f.side == "B" and smd(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", required=True), ap.add_argument("--merit", required=True), ap.add_argument("--corpus", required=True)
    ap.add_argument("--n", type=int, default=300), ap.add_argument("--out", default="boards.txt")
    ap.add_argument("--suites", default="/var/tmp/eriks/board-tags/suites", help="double_sided_assembly.txt and back_heavy.txt live here")
    a = ap.parse_args()
    feats = {r["id"]: r for r in map(json.loads, open(os.path.join(a.tags, "features.jsonl")))}
    use = {r["id"]: r for r in map(json.loads, open(os.path.join(a.tags, "usability.jsonl")))}
    merit = [x.strip() for x in open(a.merit) if x.strip()]
    suite = set()
    for t in ("double_sided_assembly", "back_heavy"):
        suite |= {x.strip() for x in open(os.path.join(a.suites, t + ".txt")) if x.strip()}

    def eligible(b):
        f, u = feats.get(b), use.get(b)
        if not f or not u or not u.get("usable_route_test") or b not in suite:
            return False
        fill = (f.get("courtyard_frac_front") or 0) + (f.get("courtyard_frac_back") or 0)
        return f.get("smd_pads_back", 0) >= 24 and fill <= 0.85 and 0 < (f.get("n_pads") or 0) <= 1000

    chosen, rows, seen = [], [], set()
    pool = sorted((b for b in use if eligible(b)), key=key)
    fams = {b: use[b].get("repo_family") or b for b in use}
    for b in [m for m in merit if m in use and eligible(m)] + [b for b in pool if b not in merit]:
        fam = fams[b]
        if fam in seen and b not in merit:
            continue
        p = os.path.join(a.corpus, "boards", b, "board.kicad_pcb")
        if not os.path.isfile(p):
            continue
        try:
            nf, nb = count_sides(p)
        except Exception as e:
            print("skip", b, e, file=sys.stderr)
            continue
        if nb <= 10:
            continue
        seen.add(fam)
        chosen.append(b)
        f = feats[b]
        rows.append(dict(id=b, front_smd=nf, back_smd=nb, fill=round((f.get("courtyard_frac_front") or 0) + (f.get("courtyard_frac_back") or 0), 3),
                         pads=f.get("n_pads"), merit=b in merit, family=fam))
        if len(rows) >= a.n:
            break
    with open(a.out, "w") as h:
        h.write("\n".join(sorted(chosen)) + "\n")
    with open(a.out.rsplit(".", 1)[0] + ".jsonl", "w") as h:
        for r in rows:
            h.write(json.dumps(r) + "\n")
    print(f"chose {len(chosen)}: {sum(r['merit'] for r in rows)} merit, {sum(not r['merit'] for r in rows)} corpus; "
          f"back SMD median {sorted(r['back_smd'] for r in rows)[len(rows)//2]}; pads median {sorted(r['pads'] for r in rows)[len(rows)//2]}")


if __name__ == "__main__":
    main()
