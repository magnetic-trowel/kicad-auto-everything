# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-board and aggregate comparison of kaebench place runs (with a routing probe).

  summarize.py RESULTS_DIR RUN [RUN ...] [--md]

Per run: legal share, probe clean pass, mean probe completion, mean HPWL ratio, total
probe DRC errors by type, method seconds. Attempt 0 only (cp1); every attempt counts as is.
"""
import json
import sys
from collections import Counter
from pathlib import Path


def rows(run_dir):
    out = {}
    for p in sorted(Path(run_dir).glob("*/place/*/attempt-0/attempt.json")):
        r = json.loads(p.read_text())
        out[r["id"]] = r
    return out


def cell(r):
    s = r.get("score") or {}
    pr = (r.get("probe") or {}).get("score") or {}
    return dict(legal=bool(s.get("legal")), valid=bool(s.get("valid")), hpwl=s.get("hpwl_ratio"),
                clean=bool(pr.get("clean")), comp=pr.get("completion"), err=pr.get("errors") or 0,
                types=(pr.get("error_types") or {}), unc=pr.get("unconnected"), t=r.get("runtime_s"),
                status=r["status"], perr=s.get("placement_errors") or {})


def main(argv):
    md = "--md" in argv
    argv = [a for a in argv if a != "--md"]
    base, runs = Path(argv[0]), argv[1:]
    data = {run: {i: cell(r) for i, r in rows(base / run).items()} for run in runs}
    ids = sorted(set().union(*[set(d) for d in data.values()]))
    print("| run | n | legal | probe clean | probe completion (mean) | hpwl_ratio (mean, legal) | probe errors | method s (mean) |")
    print("|---|---|---|---|---|---|---|---|")
    for run in runs:
        d = data[run]
        n = len(d)
        legal = sum(c["legal"] for c in d.values())
        clean = sum(c["clean"] and c["legal"] for c in d.values())
        comps = [c["comp"] if (c["legal"] and c["comp"] is not None) else 0.0 for c in d.values()]
        hp = [c["hpwl"] for c in d.values() if c["legal"] and c["hpwl"]]
        errs = Counter()
        for c in d.values():
            errs.update(c["types"])
        t = [c["t"] for c in d.values() if c["t"]]
        print(f"| {run} | {n} | {legal}/{n} | {clean}/{n} | {sum(comps)/max(n,1):.3f} | "
              f"{(sum(hp)/len(hp)) if hp else float('nan'):.3f} | {sum(errs.values())} "
              f"({', '.join(f'{k} {v}' for k, v in errs.most_common(3))}) | {sum(t)/max(len(t),1):.0f} |")
    print()
    print("| board | " + " | ".join(runs) + " |")
    print("|---|" + "---|" * len(runs))
    for i in ids:
        cells = []
        for run in runs:
            c = data[run].get(i)
            if c is None:
                cells.append("—")
            elif not c["legal"]:
                cells.append("ILLEGAL " + ",".join(f"{k}:{v}" for k, v in c["perr"].items()) if c["valid"] else c["status"])
            else:
                cells.append(f"{'**C**' if c['clean'] else ''} {c['comp'] if c['comp'] is not None else '?'}"
                             f" u{c['unc']} e{c['err']} h{c['hpwl']:.2f}" if c["hpwl"] else "?")
        print(f"| {i[:40]} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
