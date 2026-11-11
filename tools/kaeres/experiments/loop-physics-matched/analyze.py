#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read a W (joint + windows) vs R (staged + restarts) experiment (loop-physics-matched PLAN.md; also loop-compute-matched).
    python3 analyze.py [EXPERIMENT]
Physics: per board, the modules valued in both arms (u not None, no open hop), on boards both arms route fully;
x = ln(sum u_W / sum u_R); also per structure kind."""
import collections
import glob
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

BASE = Path.home() / "kae-baselines"
J21 = ((80, 1.04), (60, 1.04), (50, 1.05), (38, 1.06), (30, 1.08), (20, 1.12))   # A/A median-ratio floor by n


def floor(n):
    return next((f for m, f in J21 if n >= m), None)


def sign_flip(xs, n=50000, seed=0):
    xs = [x for x in xs if x]
    if not xs:
        return 1.0
    rng, obs = random.Random(seed), abs(sum(xs))
    return (1 + sum(abs(sum(x if rng.random() < 0.5 else -x for x in xs)) >= obs - 1e-12 for _ in range(n))) / (n + 1)


def load(exp):
    e = json.loads((BASE / "experiments" / exp / "experiment.json").read_text())
    ids = {m["id"][:8]: ("W" if "joint" in m["name"] else "R") for m in e["methods"]}
    D = collections.defaultdict(dict)
    for b in (BASE / "experiments" / exp / "boards.txt").read_text().split():
        for rd in glob.glob(str(BASE / "boards" / b / "runs" / "*")):
            rd = Path(rd)
            mid = rd.name.split(".")[-2]
            if mid not in ids or not rd.name.endswith(".a0"):
                continue
            r = dict(cpu=(json.loads((rd / "run.json").read_text()).get("method_usage") or {}).get("cpu_s") or 0)
            for f in rd.glob("evals/*.json"):
                d = json.loads(f.read_text())
                if d.get("score", {}).get("valid") is not None:
                    r["s"] = d["score"]
                if d.get("physics"):
                    r["mods"] = d["physics"].get("modules") or {}
            if "s" in r:
                D[b][ids[mid]] = r
    return D


def main():
    exp = sys.argv[1] if len(sys.argv) > 1 else "loop-physics-matched"
    D = load(exp)
    both = [b for b in D if "W" in D[b] and "R" in D[b]]
    g = lambda a, k: [D[b][a]["s"].get(k) or 0 for b in both]  # noqa: E731
    oW, oR = g("W", "unconnected"), g("R", "unconnected")
    d = [(x - y) / (x + y + 1) for x, y in zip(oW, oR)]
    print(f"{exp}: {len(both)} boards with both arms")
    print(f"opens W {sum(oW)} R {sum(oR)} ({100 * (sum(oW) / max(1, sum(oR)) - 1):+.1f} %), W fewer/more "
          f"{sum(x < y for x, y in zip(oW, oR))}/{sum(x > y for x, y in zip(oW, oR))}, mean d {st.mean(d):+.3f}, p {sign_flip(d):.4f}")
    print(f"clean W {sum(map(bool, g('W', 'clean')))} R {sum(map(bool, g('R', 'clean')))}; fully routed W "
          f"{sum(1 for x in oW if x == 0)} R {sum(1 for x in oR if x == 0)}; errors W {sum(g('W', 'errors'))} R {sum(g('R', 'errors'))}; "
          f"CPU h W {sum(D[b]['W']['cpu'] for b in both) / 3600:.1f} R {sum(D[b]['R']['cpu'] for b in both) / 3600:.1f}")
    xs, kinds = [], collections.defaultdict(list)
    for b in both:
        W, R = D[b]["W"], D[b]["R"]
        if W["s"]["unconnected"] or R["s"]["unconnected"] or "mods" not in W or "mods" not in R:
            continue
        ok = lambda m: m and m.get("u") is not None and not (m.get("open_hops") or 0)  # noqa: E731
        common = [k for k in W["mods"] if ok(W["mods"][k]) and ok(R["mods"].get(k))]
        if not common:
            continue
        sw = sum(min(5.0, W["mods"][k]["u"]) for k in common)
        sr = sum(min(5.0, R["mods"][k]["u"]) for k in common)
        if sw > 0 and sr > 0:
            xs.append(math.log(sw / sr))
        per = collections.defaultdict(lambda: [0.0, 0.0])
        for k in common:
            kind = W["mods"][k].get("kind") or k.split(":")[0]
            per[kind][0] += min(5.0, W["mods"][k]["u"])
            per[kind][1] += min(5.0, R["mods"][k]["u"])
        for kind, (a, c) in per.items():
            if a > 0 and c > 0:
                kinds[kind].append(math.log(a / c))
    n, nz = len(xs), [x for x in xs if abs(x) > 1e-12]
    med = math.exp(st.median(nz)) if nz else None
    print(f"physics (valued in both, both fully routed): n {n} boards ({len(nz)} differ), median W/R "
          f"{med and round(med, 3)}, J21 floor {floor(len(nz))}, sign-flip p {sign_flip(nz):.4f}, W lower on "
          f"{sum(x < 0 for x in nz)} / higher on {sum(x > 0 for x in nz)}")
    for kind, v in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        v = [x for x in v if abs(x) > 1e-12]
        if v:
            print(f"  {kind}: n {len(v)}, median W/R {math.exp(st.median(v)):.3f}, p {sign_flip(v):.3f}")


if __name__ == "__main__":
    main()
