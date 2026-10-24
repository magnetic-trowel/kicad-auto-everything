# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Paired comparison of joint place-and-route runs (kaebench place runs with --probe self).

    python compare.py kae-work/results/RUN1 kae-work/results/RUN2 ...

Per run: legal rate, clean rate (legal placement AND self-routed copper clean), mean
completion, routed length and vias over boards where every run completed, and DRC error
types. Then a per-board table.
"""
import json
import sys
from collections import Counter
from pathlib import Path


def load(run):
    rows = {}
    for f in Path(run).glob("*/place/*/attempt-0/attempt.json"):
        r = json.loads(f.read_text())
        s = r.get("score") or {}
        p = (r.get("probe") or {}).get("score") or {}
        rows[r["id"]] = dict(
            split=r["split"], status=r["status"], legal=bool(s.get("legal")),
            clean=bool(s.get("legal")) and bool(p.get("clean")),
            completion=p.get("completion", 0.0) if s.get("valid") else 0.0,
            length=p.get("track_length_mm"), vias=p.get("vias"),
            errors=p.get("errors_by_type") or {}, place_err=s.get("placement_errors") or {},
            outside=s.get("outside"), t=r.get("runtime_s"))
    return rows


def main(runs):
    data = {Path(r).name: load(r) for r in runs}
    ids = sorted(set.intersection(*[set(d) for d in data.values()]))
    print(f"boards in common: {len(ids)}\n")
    full = [i for i in ids if all(d[i]["completion"] >= 1.0 and d[i]["length"] for d in data.values())]
    print("| run | legal | clean | completion | len (all-complete boards) | vias | mean t (s) | top DRC errors |")
    print("|---|---|---|---|---|---|---|---|")
    for name, d in data.items():
        rows = [d[i] for i in ids]
        n = len(rows)
        errs = Counter()
        for r in rows:
            errs.update(r["errors"])
        L = sum(d[i]["length"] for i in full)
        V = sum(d[i]["vias"] for i in full)
        print(f"| {name} | {sum(r['legal'] for r in rows) / n:.3f} | {sum(r['clean'] for r in rows) / n:.3f} "
              f"| {sum(r['completion'] for r in rows) / n:.3f} | {L:.0f} ({len(full)} boards) | {V} "
              f"| {sum((r['t'] or 0) for r in rows) / n:.0f} | {dict(errs.most_common(3))} |")
    print("\nper board: clean/completion/length")
    names = list(data)
    print("| board | split | " + " | ".join(names) + " |")
    print("|---|---|" + "---|" * len(names))
    for i in ids:
        cells = []
        for nm in names:
            r = data[nm][i]
            mark = "C" if r["clean"] else ("L" if r["legal"] else "-")
            cells.append(f"{mark} {r['completion']:.2f} {r['length'] or 0:.0f}")
        print(f"| {i[:40]} | {data[names[0]][i]['split']} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
