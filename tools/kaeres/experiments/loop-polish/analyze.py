#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""loop-polish (PLAN.md): each P arm against R, paired per board, over the experiments given (pooled).
    python3 analyze.py loop-polish loop-polish-ext1"""
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
    for a in ("P-half", "P-late"):
        B = sorted(b for b in D if a in D[b] and "R" in D[b])
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
    main(sys.argv[1:] or ["loop-polish"])
