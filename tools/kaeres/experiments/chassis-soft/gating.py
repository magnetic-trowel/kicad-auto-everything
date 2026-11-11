#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""chassis-soft follow-up analyses on stored runs (no new runs): M vs R by stratum, and the per-board portfolio.
Exploratory: strata were chosen after the experiment's verdict.   python3 gating.py BOARD_TAGS_DIR"""
import collections
import json
import math
import statistics as st
import sys
from pathlib import Path

import analyze as A

TAGS = Path(sys.argv[1] if len(sys.argv) > 1 else "board-tags")


def features():
    ids = (TAGS / "structural" / "all_ids.txt").read_text().split()
    F = {}
    for b, line in zip(ids, open(TAGS / "structural" / "features.jsonl")):
        d = json.loads(line)
        F[b] = dict(pads=d.get("n_pads_cu") or d.get("n_pads"), dens=d.get("pads_per_cm2"), layers=d.get("cu_layers"))
    S = lambda n: set((TAGS / "suites" / f"{n}.txt").read_text().split())  # noqa: E731
    for t in ("easy", "moderate"):
        for b in S(f"route_demand.{t}"):
            F.setdefault(b, {})["demand"] = t
    return F


def ok(m):
    return m and m.get("u") is not None and not (m.get("open_hops") or 0)


def phys_ratio(X, Y):
    """ln(Σu X / Σu Y) over modules valued in both, if both are fully routed; else None."""
    if X["s"]["unconnected"] or Y["s"]["unconnected"] or "mods" not in X or "mods" not in Y:
        return None
    c = [k for k in X["mods"] if ok(X["mods"][k]) and ok(Y["mods"].get(k))]
    a, b = sum(min(5.0, X["mods"][k]["u"]) for k in c), sum(min(5.0, Y["mods"][k]["u"]) for k in c)
    return math.log(a / b) if c and a > 0 and b > 0 else None


def compare(D, boards, a="M", c="R"):
    oa = [D[b][a]["s"]["unconnected"] for b in boards]
    oc = [D[b][c]["s"]["unconnected"] for b in boards]
    d = [(x - y) / (x + y + 1) for x, y in zip(oa, oc)]
    xs = [x for x in (phys_ratio(D[b][a], D[b][c]) for b in boards) if x is not None and abs(x) > 1e-12]
    return (f"n {len(boards):3d} | opens {sum(oa):5d} vs {sum(oc):5d}, fewer/more {sum(x < y for x, y in zip(oa, oc)):2d}/"
            f"{sum(x > y for x, y in zip(oa, oc)):2d}, p {A.sign_flip(d) if d else 1:.3f} | physics n {len(xs):3d}, median "
            f"{(math.exp(st.median(xs)) if xs else float('nan')):.3f}, p {A.sign_flip(xs) if xs else 1:.3f}")


def main():
    D = A.load("chassis-soft")
    F = features()
    B = [b for b in D if "R" in D[b] and "M" in D[b]]
    print(f"{len(B)} boards with R and M\n\nBy R's outcome (outcome strata: not usable as a gate, they need R's result)")
    groups = collections.defaultdict(list)
    for b in B:
        o = D[b]["R"]["s"]["unconnected"]
        groups["R 0 opens" if o == 0 else "R 1-5 opens" if o <= 5 else "R > 5 opens"].append(b)
    for k in ("R 0 opens", "R 1-5 opens", "R > 5 opens"):
        print(f"  {k:12s} {compare(D, groups[k])}")
    print("\nBy features of the bare board (exploratory: strata chosen after the verdict)")
    have = [b for b in B if F.get(b, {}).get("pads")]
    for key, label in (("pads", "copper pads"), ("dens", "pads per cm2")):
        v = sorted(F[b][key] for b in have if F[b].get(key) is not None)
        t1, t2 = v[len(v) // 3], v[2 * len(v) // 3]
        for name, sel in ((f"{label} <= {t1:.0f}", lambda x: x <= t1), (f"{label} {t1:.0f}-{t2:.0f}", lambda x: t1 < x <= t2),
                          (f"{label} > {t2:.0f}", lambda x: x > t2)):
            bs = [b for b in have if F[b].get(key) is not None and sel(F[b][key])]
            print(f"  {name:22s} {compare(D, bs)}")
    for name, sel in (("2 copper layers", lambda f: f.get("layers") == 2), ("4+ copper layers", lambda f: (f.get("layers") or 0) >= 4),
                      ("route_demand easy", lambda f: f.get("demand") == "easy"),
                      ("route_demand moderate", lambda f: f.get("demand") == "moderate")):
        print(f"  {name:22s} {compare(D, [b for b in have if sel(F[b])])}")
    # portfolio
    port, cpu_m, cpu_r = {}, 0.0, 0.0
    for b in B:
        M, R = D[b]["M"], D[b]["R"]
        cpu_m += M["cpu"]
        cpu_r += R["cpu"]
        port[b] = M if (M["s"].get("legal") and M["s"]["unconnected"] <= R["s"]["unconnected"]) else R
    po = sum(port[b]["s"]["unconnected"] for b in B)
    ro = sum(D[b]["R"]["s"]["unconnected"] for b in B)
    xs = [x for x in (phys_ratio(port[b], D[b]["R"]) for b in B) if x is not None and abs(x) > 1e-12]
    nm = sum(1 for b in B if port[b] is D[b]["M"])
    print(f"\nPortfolio (M if legal and its opens <= R's, else R): M chosen on {nm} of {len(B)} boards")
    print(f"  opens {po} vs R {ro}; clean {sum(bool(port[b]['s'].get('clean')) for b in B)} vs R {sum(bool(D[b]['R']['s'].get('clean')) for b in B)}; "
          f"physics vs R: n {len(xs)}, median {(math.exp(st.median(xs)) if xs else float('nan')):.3f}, p {A.sign_flip(xs):.4f}; "
          f"CPU M + R {(cpu_m + cpu_r) / 3600:.1f} h vs R {cpu_r / 3600:.1f} h")
    # the harness's ranking: legal first, then fewer open connections, then fewer DRC errors; M kept when it ranks no worse
    rank = lambda r: (0 if r["s"].get("legal") else 1, r["s"]["unconnected"], r["s"].get("errors") or 0)  # noqa: E731
    port2 = {b: D[b]["M"] if rank(D[b]["M"]) <= rank(D[b]["R"]) else D[b]["R"] for b in B}
    po2 = sum(port2[b]["s"]["unconnected"] for b in B)
    xs2 = [x for x in (phys_ratio(port2[b], D[b]["R"]) for b in B) if x is not None and abs(x) > 1e-12]
    print(f"\nPortfolio, harness-ranked (legal, opens, DRC errors): M chosen on {sum(1 for b in B if port2[b] is D[b]['M'])} of {len(B)}")
    print(f"  opens {po2} vs R {ro}; clean {sum(bool(port2[b]['s'].get('clean')) for b in B)} vs R "
          f"{sum(bool(D[b]['R']['s'].get('clean')) for b in B)}; errors {sum(port2[b]['s'].get('errors') or 0 for b in B)} vs R "
          f"{sum(D[b]['R']['s'].get('errors') or 0 for b in B)}; physics vs R: n {len(xs2)}, median "
          f"{(math.exp(st.median(xs2)) if xs2 else float('nan')):.3f}, p {A.sign_flip(xs2):.4f}; CPU as above")
    return B, D


if __name__ == "__main__":
    main()


def completion_first(D, P, B):
    """Run R; if R routes fully, also run M and keep it when it ranks no worse (legal, opens, DRC errors), else R;
    if R leaves opens, spend the second allowance on another restart run R' and keep the better.
    P: loop-physics-matched's runs (its R is another wrapper setting: --parallel 1, 3.15 B wall)."""
    rank = lambda r: (0 if r["s"].get("legal") else 1, r["s"]["unconnected"], r["s"].get("errors") or 0)  # noqa: E731
    pick, cpu = {}, 0.0
    for b in B:
        R = D[b]["R"]
        if R["s"]["unconnected"] == 0:
            M = D[b]["M"]
            pick[b] = M if rank(M) <= rank(R) else R
            cpu += R["cpu"] + M["cpu"]
        else:
            R2 = P[b]["R"]
            pick[b] = R2 if rank(R2) < rank(R) else R
            cpu += R["cpu"] + R2.get("cpu", 0)
    return pick, cpu
