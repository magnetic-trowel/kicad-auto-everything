#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read loop-legal-ab2 (PLAN.md; also loop-legal-ab): per arm over board x attempt, legality, clean, opens, per-type DRC, CPU; Fisher exact
on legal for each anchored arm against its control.   python3 analyze.py [EXPERIMENT]"""
import collections
import glob
import json
import math
import sys
from pathlib import Path

BASE = Path.home() / "kae-baselines"
FOCUS = ("courtyards_overlap", "shorting_items", "items_not_allowed", "hole_to_hole", "copper_edge_clearance", "clearance",
         "pth_inside_courtyard", "npth_inside_courtyard", "hole_clearance", "solder_mask_bridge")


def arm(name):
    w = name.split()
    return " ".join(w[2:w.index(next(x for x in w if len(x) == 7 and all(c in "0123456789abcdef" for c in x)))])


def fisher(a, b, c, d):
    """Two-sided Fisher exact p for [[a, b], [c, d]]."""
    n, r1, c1 = a + b + c + d, a + b, a + c
    lp = lambda k: (math.lgamma(r1 + 1) + math.lgamma(n - r1 + 1) + math.lgamma(c1 + 1) + math.lgamma(n - c1 + 1)
                    - math.lgamma(k + 1) - math.lgamma(r1 - k + 1) - math.lgamma(c1 - k + 1) - math.lgamma(n - r1 - c1 + k + 1)
                    - math.lgamma(n + 1))
    p0 = lp(a)
    return min(1.0, sum(math.exp(lp(k)) for k in range(max(0, r1 + c1 - n), min(r1, c1) + 1) if lp(k) <= p0 + 1e-9))


def sign_flip(ds, n=50000, seed=0):
    import random
    ds = [d for d in ds if d]
    if not ds:
        return 1.0
    rng, obs = random.Random(seed), abs(sum(ds))
    return (1 + sum(abs(sum(d if rng.random() < 0.5 else -d for d in ds)) >= obs - 1e-12 for _ in range(n))) / (n + 1)


def primary(R, boards):
    """PLAN.md primary: per board, KiCad placement errors summed over the seeds, d = (t - c) / (t + c + 1); and the
    guard: a board legal in at least 2 of 3 seeds under control and at most 1 under the change."""
    print("\nPrimary (placement errors per board, summed over seeds):")
    for t, c in (("staged", "staged ctl"), ("joint", "joint ctl")):
        ds, worse, better, reg = [], 0, 0, []
        for b in boards:
            cells = [R[(b, f"a{k}")] for k in range(3) if (b, f"a{k}") in R and t in R[(b, f"a{k}")] and c in R[(b, f"a{k}")]]
            if not cells:
                continue
            pe = lambda a: sum(sum((x[a]["s"].get("placement_errors") or {}).values()) for x in cells)
            lg = lambda a: sum(bool(x[a]["s"].get("legal")) for x in cells)
            pt, pc = pe(t), pe(c)
            ds.append((pt - pc) / (pt + pc + 1))
            better += pt < pc
            worse += pt > pc
            if lg(c) >= 2 and lg(t) <= 1:
                reg.append(b)
        print(f"  {t} vs {c}: boards {len(ds)}, fewer / more placement errors {better} / {worse}, mean d {sum(ds) / max(1, len(ds)):+.3f}, "
              f"sign-flip p {sign_flip(ds):.3g}; legality regressions {reg or 'none'}")


def main():
    exp = sys.argv[1] if len(sys.argv) > 1 else "loop-legal-ab3"
    e = json.loads((BASE / "experiments" / exp / "experiment.json").read_text())
    ids = {m["id"][:8]: arm(m["name"]) for m in e["methods"]}
    boards = (BASE / "experiments" / exp / "boards.txt").read_text().split()
    R = collections.defaultdict(dict)        # (board, attempt) -> arm -> score + cpu
    for b in boards:
        for rd in glob.glob(str(BASE / "boards" / b / "runs" / "*")):
            rd = Path(rd)
            mid, att = rd.name.split(".")[-2], rd.name.split(".")[-1]
            if mid not in ids:
                continue
            s = None
            for f in rd.glob("evals/*.json"):
                d = json.loads(f.read_text())
                if d.get("score", {}).get("valid") is not None:
                    s = d["score"]
            run = json.loads((rd / "run.json").read_text())
            if s:
                R[(b, att)][ids[mid]] = dict(s=s, cpu=(run.get("method_usage") or {}).get("cpu_s") or 0)
    arms = sorted({a for v in R.values() for a in v})
    print(f"{exp}: {len(boards)} boards, {len(R)} board x attempt cells; arms {arms}\n")
    print("| arm | runs | legal | legal_strict | clean | completion | opens | errors | placement errors | CPU h |\n|---|---|---|---|---|---|---|---|---|---|")
    for a in arms:
        L = [v[a] for v in R.values() if a in v]
        s = lambda k: [x["s"].get(k) for x in L]
        pe = sum(sum((x["s"].get("placement_errors") or {}).values()) for x in L)
        print(f"| {a} | {len(L)} | {sum(map(bool, s('legal')))} | {sum(map(bool, s('legal_strict')))} | {sum(map(bool, s('clean')))} "
              f"| {sum(s('completion')) / len(L):.3f} | {sum(s('unconnected'))} | {sum(s('errors'))} | {pe} | {sum(x['cpu'] for x in L) / 3600:.1f} |")
    for t, c in (("staged", "staged ctl"), ("joint", "joint ctl")):
        cells = [v for v in R.values() if t in v and c in v]
        lt, lc = sum(bool(v[t]["s"].get("legal")) for v in cells), sum(bool(v[c]["s"].get("legal")) for v in cells)
        print(f"\n{t} vs {c}: paired cells {len(cells)}, legal {lt} vs {lc}, Fisher p {fisher(lt, len(cells) - lt, lc, len(cells) - lc):.2g}; "
              f"opens {sum(v[t]['s']['unconnected'] for v in cells)} vs {sum(v[c]['s']['unconnected'] for v in cells)}; "
              f"errors {sum(v[t]['s']['errors'] for v in cells)} vs {sum(v[c]['s']['errors'] for v in cells)}; "
              f"clean {sum(bool(v[t]['s'].get('clean')) for v in cells)} vs {sum(bool(v[c]['s'].get('clean')) for v in cells)}")
    primary(R, boards)
    print("\nPlacement errors by type (all runs):\n| type | " + " | ".join(arms) + " |\n|---|" + "---|" * len(arms))
    tot = {a: collections.Counter() for a in arms}
    for v in R.values():
        for a, x in v.items():
            tot[a].update(x["s"].get("placement_errors") or {})
    for k in sorted({k for c in tot.values() for k in c}, key=lambda k: -sum(c[k] for c in tot.values())):
        print(f"| {k} | " + " | ".join(str(tot[a][k]) for a in arms) + " |")
    print("\nPer board (legal of attempts, opens, errors):")
    print("| board | " + " | ".join(arms) + " |\n|---|" + "---|" * len(arms))
    for b in boards:
        cells = [R[(b, f"a{k}")] for k in range(3) if (b, f"a{k}") in R]
        row = []
        for a in arms:
            L = [c[a]["s"] for c in cells if a in c]
            row.append(f"{sum(bool(x.get('legal')) for x in L)}/{len(L)}, {sum(x['unconnected'] for x in L)}, {sum(x['errors'] for x in L)}")
        print(f"| {b[:44]} | " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
