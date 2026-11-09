# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Edge rates per panel-connector kind (kae.place.edge_check's rules) from edge_scan.py rows.

    edge_rates.py ROWS.jsonl [--ids IDS.txt] [--sample KIND]

Columns: share of parts whose courtyard is within 0.5 / 1 / 2 / 3 / 5 mm of the outer edge,
share overhanging it, and the share facing out (cos >= FACE_MIN) among those within 1 mm.
Vertical (top-entry) parts are listed as KIND-vert. --sample lists parts > 3 mm inside.
"""
import argparse
import collections
import json
import random

from kae.place import edge_check as E


def kind_of(row):
    text = f"{row.get('lib') or ''} {row.get('value') or ''}"
    if row.get("cls") != "connector" or E.NOT_PANEL.search(text):
        return None
    for name, rx in E.KINDS:
        if rx.search(text):
            return name + ("-vert" if E.VERTICAL.search(text) else "")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--ids")
    ap.add_argument("--sample")
    a = ap.parse_args()
    ids = set(open(a.ids).read().split()) if a.ids else None
    res = collections.defaultdict(list)
    for line in open(a.rows):
        r = json.loads(line)
        if "d" not in r or (ids and r["id"] not in ids):
            continue
        k = kind_of(r)
        if k:
            res[k].append(r)
    print(f"{'kind':16s} {'n':>5s} {'brds':>5s} {'<=0.5':>6s} {'<=1':>5s} {'<=2':>5s} {'<=3':>5s} {'<=5':>5s} "
          f"{'over':>5s} {'face+':>5s}")
    for k, v in sorted(res.items(), key=lambda kv: -len(kv[1])):
        n = len(v)
        f = lambda t: sum(1 for r in v if r["d"] <= t) / n  # noqa: E731
        fv = [r for r in v if r["d"] <= 1 and r.get("face") is not None]
        fo = sum(1 for r in fv if r["face"] >= E.FACE_MIN) / len(fv) if fv else float("nan")
        print(f"{k:16s} {n:5d} {len(set(r['id'] for r in v)):5d} {f(0.5):6.2f} {f(1):5.2f} {f(2):5.2f} {f(3):5.2f} "
              f"{f(5):5.2f} {sum(r['over'] > 0 for r in v) / n:5.2f} {fo:5.2f}")
    if a.sample:
        v = [r for r in res[a.sample] if r["d"] > 3]
        random.seed(2)
        for r in random.sample(v, min(25, len(v))):
            print(r["id"][:40], r.get("tag", ""), r["ref"], r["lib"][:50], r["value"][:18], r["d"], r["span"])


if __name__ == "__main__":
    main()
