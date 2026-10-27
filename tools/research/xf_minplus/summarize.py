# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-seed legal / clean / completion and length / vias (summed over boards that every
listed run fully routed in that seed), from attempt.json (kicad-cli scores).

    python summarize.py [--suite FILE] [--exclude ID,ID] RUN [RUN ...]     (run names under $XF_WORK/results)
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(os.environ.get("XF_WORK", ROOT / "kae-work2"))


def load(run):
    out = {}
    for f in (WORK / "results" / run).glob("*/joint/*/attempt-*/attempt.json"):
        a = json.loads(f.read_text())
        s = a.get("score") or {}  # joint task: placement and routing in one score
        ok = a["status"] == "ok" and bool(s.get("valid"))
        out[(a["id"], a["attempt"])] = dict(
            legal=bool(s.get("legal")) and ok, clean=bool(s.get("legal")) and bool(s.get("clean")) and ok,
            comp=float(s.get("completion") or 0.0) if ok else 0.0, len=s.get("track_length_mm"),
            vias=s.get("vias"), full=ok and s.get("unconnected") == 0)
    return out


def main():
    args = sys.argv[1:]
    suite = None
    if args[0] == "--suite":
        suite = set(Path(args[1]).read_text().split())
        args = args[2:]
    excl = set()
    if args[0] == "--exclude":
        excl = set(args[1].split(","))
        args = args[2:]
    data = {r: load(r) for r in args}
    boards = sorted({b for d in data.values() for b, _ in d})
    if suite:
        boards = [b for b in boards if b in suite]
    boards = [b for b in boards if b not in excl]
    seeds = sorted({k for d in data.values() for _, k in d})
    per = {}
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
        f = lambda a, p=3: f"{np.mean(a):.{p}f} ± {np.std(a, ddof=1):.{p}f}"
        print(f"| {r} | {f(L)} | {f(C)} | {f(P)} | {f(LN, 0)} | {f(V, 1)} | {np.mean(NB):.0f} | {best:.3f} |")
        per[r] = (LN, V)
    # paired by seed against the first run (the baseline): % change in length and vias
    b = args[0]
    for r in args[1:]:
        dl = [100 * (x / y - 1) for x, y in zip(per[r][0], per[b][0])]
        dv = [100 * (x / y - 1) if y else float("nan") for x, y in zip(per[r][1], per[b][1])]
        print(f"\n{r} vs {b}, per seed: length " + ", ".join(f"{x:+.1f}%" for x in dl)
              + f" (mean {np.mean(dl):+.1f}%); vias " + ", ".join(f"{x:+.0f}%" for x in dv)
              + f" (mean {np.mean(dv):+.0f}%)")


if __name__ == "__main__":
    main()
