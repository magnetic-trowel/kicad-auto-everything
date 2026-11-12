#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""module-clock2 (PLAN.md, Addenda 3-4): M-clock vs M, and each ablation vs M-clock, on the share set (37,
primary), the mechanism set (41) and the physics set (98); pooled; per-arm knob checks from the origin attempt's
stage report.    python3 analyze_clock.py [EXPERIMENT]"""
import collections
import glob
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

BASE = Path.home() / "kae-baselines"
HERE = Path(__file__).resolve().parent
ARM = {"M": "M", "Mclock": "M-clock", "Mclocklocal": "M-clock-local", "Mclocknoguard": "M-clock-noguard",
       "Mclocknorails": "M-clock-norails"}
SETS = {n: set((HERE / f).read_text().split()) for n, f in
        (("share37", "boards-share37.txt"), ("mech41", "boards-mechanism.txt"), ("phys98", "boards-physics.txt"))}


def sign_flip(xs, n=50000, seed=0):
    xs = [x for x in xs if x]
    if not xs:
        return 1.0
    rng = random.Random(seed)
    t = abs(sum(xs))
    return (1 + sum(abs(sum(x if rng.random() < 0.5 else -x for x in xs)) >= t - 1e-12 for _ in range(n))) / (n + 1)


def load(exp):
    e = json.loads((BASE / "experiments" / exp / "experiment.json").read_text())
    ids = {m["id"][:8]: ARM[m["name"].split()[2]] for m in e["methods"]}
    D = collections.defaultdict(dict)
    for b in (BASE / "experiments" / exp / "boards.txt").read_text().split():
        for rd in glob.glob(str(BASE / "boards" / b / "runs" / "*.a0")):
            rd = Path(rd)
            mid = rd.name.split(".")[-2]
            if mid not in ids:
                continue
            r = dict(cpu=(json.loads((rd / "run.json").read_text()).get("method_usage") or {}).get("cpu_s") or 0)
            for f in rd.glob("evals/*.json"):
                d = json.loads(f.read_text())
                if (d.get("score") or {}).get("valid") is not None:
                    r["s"] = d["score"]
                if d.get("physics"):
                    r["mods"] = d["physics"].get("modules") or {}
            for fn in ("restart-report-origin.json", "restart-report.json"):
                if (rd / fn).exists():
                    its = json.loads((rd / fn).read_text()).get("iterations") or [{}]
                    stg = its[0].get("stages") or {}
                    r["mod"], r["route"] = stg.get("modules") or {}, stg.get("route") or {}
                    break
            if "s" in r:
                D[b][ids[mid]] = r
    return D


def phys(X, Y):
    ok = lambda m: m and m.get("u") is not None and not (m.get("open_hops") or 0)  # noqa: E731
    if X["s"]["unconnected"] or Y["s"]["unconnected"]:
        return None
    c = [k for k in X.get("mods", {}) if ok(X["mods"][k]) and ok(Y.get("mods", {}).get(k))]
    a, b = sum(min(5.0, X["mods"][k]["u"]) for k in c), sum(min(5.0, Y["mods"][k]["u"]) for k in c)
    return math.log(a / b) if c and a > 0 and b > 0 else None


def floor(n):
    return 1.04 if n >= 80 else 1.05 if n >= 50 else 1.06 if n >= 38 else 1.08 if n >= 30 else 1.12


def compare(D, a, c, alpha):
    print(f"\n{a} vs {c}")
    for name, sel in (("share37 (primary)", SETS["share37"]), ("mech41", SETS["mech41"]), ("pooled", None)):
        B = sorted(b for b in D if a in D[b] and c in D[b] and (sel is None or b in sel))
        if not B:
            continue
        oa = [D[b][a]["s"]["unconnected"] for b in B]
        oc = [D[b][c]["s"]["unconnected"] for b in B]
        d = [(x - y) / (x + y + 1) for x, y in zip(oa, oc)]
        p = sign_flip(d)
        g = lambda arm, k: sum((D[b][arm]["s"].get(k) or 0) for b in B)  # noqa: E731
        verdict = ""
        if name.startswith("share37"):
            moves = st.mean(d) < 0 and p < alpha and sum(oa) <= 0.97 * sum(oc)
            worse = st.mean(d) > 0 and p < alpha and sum(oa) >= 1.03 * sum(oc)
            verdict = f" -> {'fewer opens' if moves else 'more opens' if worse else 'no decision'} (p < {alpha})"
        print(f"  {name:18s} n {len(B):3d} opens {sum(oa):5d} vs {sum(oc):5d} ({100 * (sum(oa) / max(1, sum(oc)) - 1):+.1f} %) "
              f"fewer/more {sum(x < y for x, y in zip(oa, oc))}/{sum(x > y for x, y in zip(oa, oc))} mean d {st.mean(d):+.3f} "
              f"p {p:.4f}{verdict}")
        print(f"  {'':18s} clean {g(a, 'clean')} vs {g(c, 'clean')}, legal {g(a, 'legal')} vs {g(c, 'legal')}, errors "
              f"{g(a, 'errors')} vs {g(c, 'errors')}, CPU {sum(D[b][a]['cpu'] for b in B) / 3600:.1f} vs "
              f"{sum(D[b][c]['cpu'] for b in B) / 3600:.1f} h")
    B = [b for b in D if a in D[b] and c in D[b] and b in SETS["phys98"]]
    xs = [x for x in (phys(D[b][a], D[b][c]) for b in B) if x is not None and abs(x) > 1e-12]
    if xs:
        m = math.exp(st.median(xs))
        print(f"  physics (phys98, both routed) n {len(xs)}, median {a}/{c} {m:.3f}, p {sign_flip(xs):.4f}, "
              f"floor {floor(len(xs)):.2f} -> guard {'holds' if m <= floor(len(xs)) else 'fails'}")


def knobs(D):
    print("\nKnob checks (origin attempt): module stage s / budget, clock skips, guard zones, rail pieces, owners")
    for arm in ARM.values():
        rows = [D[b][arm] for b in D if arm in D[b]]
        if not rows:
            continue
        own = collections.Counter()
        for r in rows:
            own.update({k.split("/")[0]: v for k, v in (r.get("mod", {}).get("copper_by_owner") or {}).items()})
        secs = [r["mod"].get("seconds") / r["mod"]["budget_s"] for r in rows if r.get("mod", {}).get("seconds") and r["mod"].get("budget_s")]
        print(f"  {arm:16s} n {len(rows):3d} stage/budget median {st.median(secs) if secs else float('nan'):.2f} max "
              f"{max(secs) if secs else float('nan'):.2f}; guard zones {sum(r.get('mod', {}).get('guard_zones') or 0 for r in rows)}; "
              f"rails skipped {sum('rails' in ((r.get('mod', {}).get('clock') or {}).get('skipped') or []) for r in rows)}; "
              f"router s median {st.median([r['route'].get('router_s') or 0 for r in rows if r.get('route')] or [0]):.0f}; owners {dict(own)}")


def main(exp):
    D = load(exp)
    print(f"{exp}: {len(D)} boards with runs")
    knobs(D)
    compare(D, "M-clock", "M", 0.05)
    for a in ("M-clock-local", "M-clock-noguard", "M-clock-norails"):
        compare(D, a, "M-clock", 0.017)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "module-clock2")
