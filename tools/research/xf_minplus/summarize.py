# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-seed legal / clean / completion and length / vias (summed over boards that every
listed run fully routed in that seed), from attempt.json (kicad-cli scores).

    python summarize.py [--suite FILE] RUN [RUN ...]     (run names under kae-work/results)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]


def load(run):
    out = {}
    for f in (ROOT / "kae-work" / "results" / run).glob("*/place/*/attempt-*/attempt.json"):
        a = json.loads(f.read_text())
        p = (a.get("probe") or {}).get("score") or {}
        s = a.get("score") or {}
        out[(a["id"], a["attempt"])] = dict(
            legal=bool(s.get("legal")) and a["status"] == "ok", clean=bool(p.get("clean")),
            comp=float(p.get("completion") or 0.0), len=p.get("track_length_mm"), vias=p.get("vias"),
            full=a["status"] == "ok" and p.get("unconnected") == 0)
    return out


def main():
    args = sys.argv[1:]
    suite = None
    if args[0] == "--suite":
        suite = set(Path(args[1]).read_text().split())
        args = args[2:]
    data = {r: load(r) for r in args}
    boards = sorted({b for d in data.values() for b, _ in d})
    if suite:
        boards = [b for b in boards if b in suite]
    seeds = sorted({k for d in data.values() for _, k in d})
    print("| run | legal | clean | completion | length mm (common full) | vias | boards | clean best-of-3 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in args:
        d = data[r]
        L, C, P, LN, V, NB = [], [], [], [], [], []
        for k in seeds:
            rows = [d.get((b, k)) for b in boards]
            if any(x is None for x in rows):
                continue
            L.append(np.mean([x["legal"] for x in rows]))
            C.append(np.mean([x["clean"] for x in rows]))
            P.append(np.mean([x["comp"] for x in rows]))
            com = [b for b in boards if all((data[q].get((b, k)) or {}).get("full") for q in args)]
            LN.append(sum(d[(b, k)]["len"] for b in com))
            V.append(sum(d[(b, k)]["vias"] for b in com))
            NB.append(len(com))
        best = np.mean([any((d.get((b, k)) or {}).get("clean") for k in seeds) for b in boards])
        f = lambda a, p=3: f"{np.mean(a):.{p}f} ± {np.std(a):.{p}f}"
        print(f"| {r} | {f(L)} | {f(C)} | {f(P)} | {f(LN, 0)} | {f(V, 1)} | {np.mean(NB):.0f} | {best:.3f} |")


if __name__ == "__main__":
    main()
