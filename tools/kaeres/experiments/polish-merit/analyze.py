#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""polish-merit (PLAN.md): P-late against R, paired per board (loop-polish's analysis, plus Freerouting's
optimizer stops per run).    python3 analyze.py [polish-merit]"""
import collections
import glob
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

BASE = Path.home() / "kae-baselines"
ARM = {"restarts": "R", "late": "P-late", "half": "P-half"}


def opt_stops(rd):
    """Freerouting's optimizer stops in the stored reports of a run (the kept attempt's and its origin's): every
    `stops.optimizer` found. In work mode the optimizer was neither charged nor capped by passes until
    fr-budget-calibration; "timed_out" means the 4x wall ceiling cut it (load-dependent)."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            st_ = x.get("stops")
            if isinstance(st_, dict) and st_.get("optimizer") is not None:
                out.append(str(st_["optimizer"]))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for fn in ("restart-report.json", "restart-report-origin.json"):
        if (rd / fn).exists():
            walk(json.loads((rd / fn).read_text()))
    return out


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
            r["opt"] = opt_stops(rd)
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


def main(exps):
    D = {}
    for e in exps:
        for b, v in load(e).items():
            D[b] = v
    pe = lambda r: sum((r["s"].get("placement_errors") or {}).values())  # noqa: E731
    print("Freerouting optimizer stops (kept and origin attempts' reports; timed_out = cut by the wall ceiling)")
    for arm in ("R", "P-late", "P-half"):
        rows = [D[b][arm] for b in D if arm in D[b]]
        if rows:
            c = collections.Counter(x.lower() for r in rows for x in r.get("opt") or [])
            to = sum(any("timed_out" in x.lower() for x in r.get("opt") or []) for r in rows)
            print(f"  {arm:7s} runs {len(rows):3d}, runs with an optimizer timed_out {to}; stops {dict(c)}")
    print()
    for a in ("P-half", "P-late"):
        B = sorted(b for b in D if a in D[b] and "R" in D[b])
        if not B:
            continue
        oa = [D[b][a]["s"]["unconnected"] for b in B]
        orr = [D[b]["R"]["s"]["unconnected"] for b in B]
        d = [(x - y) / (x + y + 1) for x, y in zip(oa, orr)]
        g = lambda arm, k: sum((D[b][arm]["s"].get(k) or 0) for b in B)  # noqa: E731
        xs = [x for x in (phys(D[b][a], D[b]["R"]) for b in B) if x is not None and abs(x) > 1e-12]
        p = sign_flip(d)
        print(f"{a} vs R: {len(B)} boards ({', '.join(exps)})")
        print(f"  opens {sum(oa)} vs {sum(orr)} ({100 * (sum(oa) / max(1, sum(orr)) - 1):+.1f} %), fewer/more "
              f"{sum(x < y for x, y in zip(oa, orr))}/{sum(x > y for x, y in zip(oa, orr))}, mean d {st.mean(d):+.4f}, p {p:.4f}")
        print(f"  DRC errors {g(a, 'errors')} vs {g('R', 'errors')} ({100 * (g(a, 'errors') / max(1, g('R', 'errors')) - 1):+.1f} %); "
              f"placement errors {sum(pe(D[b][a]) for b in B)} vs {sum(pe(D[b]['R']) for b in B)}; "
              f"cp1 (clean) {sum(bool(D[b][a]['s'].get('clean')) for b in B)} vs {sum(bool(D[b]['R']['s'].get('clean')) for b in B)}; "
              f"legal {sum(bool(D[b][a]['s'].get('legal')) for b in B)} vs {sum(bool(D[b]['R']['s'].get('legal')) for b in B)}")
        print(f"  CPU {sum(D[b][a]['cpu'] for b in B) / 3600:.1f} h vs {sum(D[b]['R']['cpu'] for b in B) / 3600:.1f} h; "
              f"physics (all routed) n {len(xs)}, median {math.exp(st.median(xs)) if xs else float('nan'):.3f}")
        win = st.mean(d) < 0 and p < 0.025 and sum(oa) <= 0.97 * sum(orr)
        lose = st.mean(d) > 0 and p < 0.025 and sum(oa) >= 1.03 * sum(orr)
        guards = (g(a, "errors") <= 1.03 * g("R", "errors")
                  and sum(pe(D[b][a]) for b in B) <= 1.03 * sum(pe(D[b]["R"]) for b in B)
                  and sum(bool(D[b][a]["s"].get("clean")) for b in B) >= sum(bool(D[b]["R"]["s"].get("clean")) for b in B))
        print(f"  primary: {'P wins' if win else 'R wins' if lose else 'undecided'}; guards {'hold' if guards else 'fail'}\n")


if __name__ == "__main__":
    main(sys.argv[1:] or ["polish-merit"])
