# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Weight-sweep summary on a suite: per run, over seeds and the suite's boards, mean
completion, legal/clean counts, total length and vias on boards every run completed
(per seed, then averaged), and pour R vs the base run from pour_score.py's JSON.

    python sweep_table.py SUITE POUR.json BASE_RUN RUN [...]
"""
import json
import math
import sys
from pathlib import Path

import os

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pour_score import per_board_net, gmean  # noqa: E402

W = Path(os.environ.get("XF_WORK", HERE.parents[2] / "kae-work2"))


def load(run, ids):
    out = {}
    for bid in ids:
        for f in (W / "results" / run / f"x-{run}" / "joint" / bid).glob("attempt-*/attempt.json"):
            r = json.loads(f.read_text())
            s = r.get("score") or {}
            out[(bid, r["attempt"])] = s
    return out


def main():
    suite, pj, base, *runs = sys.argv[1:]
    ids = [l.strip() for l in open(suite) if l.strip()]
    res = json.loads(Path(pj).read_text())
    runs = [base] + runs
    data = {r: load(r, ids) for r in runs}
    seeds = sorted({a for d in data.values() for (_, a) in d})
    done = [(b, a) for b in ids for a in seeds
            if all((data[r].get((b, a)) or {}).get("completion") == 1.0 for r in runs)]
    bb = per_board_net(res, base)
    print(f"{len(ids)} boards, seeds {seeds}; length/vias over {len(done)} (board, seed) all complete")
    print("| run | legal | clean | completion | length mm | vias | pour R / base | (board,net) |")
    print("|---|---|---|---|---|---|---|---|")
    for r in runs:
        d = data[r]
        n = len(d)
        comp = sum((s.get("completion") or 0) if s.get("valid") else 0 for s in d.values()) / max(n, 1)
        leg = sum(bool(s.get("legal")) for s in d.values())
        cl = sum(bool(s.get("legal")) and bool(s.get("clean")) for s in d.values())
        ln = sum(d[k]["track_length_mm"] for k in done) / max(len(seeds), 1)
        vi = sum(d[k]["vias"] for k in done) / max(len(seeds), 1)
        rb = per_board_net({k: v for k, v in res.items() if k.split("|")[1] in ids and
                            (k.split("|")[0] != r or int(k.split("|")[2]) in seeds)}, r)
        common = sorted(set(rb) & set(bb))
        rat = gmean([rb[k] / bb[k] for k in common])
        print(f"| {r} | {leg}/{n} | {cl}/{n} | {comp:.3f} | {ln:.0f} | {vi:.0f} | "
              f"{'-' if rat is None else f'{rat:.3f}'} | {len(common)} |")


if __name__ == "__main__":
    main()
