#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read chassis-soft (PLAN.md): arms R, M, Msoft (names "kae chassis <arm> <sha>"), pairs M-R, Msoft-R, Msoft-M.
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
    ids = {m["id"][:8]: m["name"].split()[2] for m in e["methods"]}
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
            for fn in ("restart-report-origin.json", "restart-report.json"):
                if (rd / fn).exists():
                    its = json.loads((rd / fn).read_text()).get("iterations") or [{}]
                    r["mc"] = ((its[0].get("stages") or {}).get("route") or {}).get("module_copper")
                    break
            if "s" in r:
                D[b][ids[mid]] = r
    return D


def pair(D, A_, C):
    both = [b for b in D if A_ in D[b] and C in D[b]]
    g = lambda a, k: [D[b][a]["s"].get(k) or 0 for b in both]  # noqa: E731
    oA, oC = g(A_, "unconnected"), g(C, "unconnected")
    d = [(x - y) / (x + y + 1) for x, y in zip(oA, oC)]
    print(f"\n{A_} vs {C}: {len(both)} boards")
    print(f"  opens {sum(oA)} vs {sum(oC)} ({100 * (sum(oA) / max(1, sum(oC)) - 1):+.1f} %), fewer/more "
          f"{sum(x < y for x, y in zip(oA, oC))}/{sum(x > y for x, y in zip(oA, oC))}, mean d {st.mean(d):+.3f}, p {sign_flip(d):.4f}")
    print(f"  clean {sum(map(bool, g(A_, 'clean')))} vs {sum(map(bool, g(C, 'clean')))}; legal {sum(map(bool, g(A_, 'legal')))} vs "
          f"{sum(map(bool, g(C, 'legal')))}; errors {sum(g(A_, 'errors'))} vs {sum(g(C, 'errors'))}; CPU h "
          f"{sum(D[b][A_]['cpu'] for b in both) / 3600:.1f} vs {sum(D[b][C]['cpu'] for b in both) / 3600:.1f}")
    xs, kinds = [], collections.defaultdict(list)
    ok = lambda m: m and m.get("u") is not None and not (m.get("open_hops") or 0)  # noqa: E731
    for b in both:
        W, R = D[b][A_], D[b][C]
        if W["s"]["unconnected"] or R["s"]["unconnected"] or "mods" not in W or "mods" not in R:
            continue
        common = [k for k in W["mods"] if ok(W["mods"][k]) and ok(R["mods"].get(k))]
        sw = sum(min(5.0, W["mods"][k]["u"]) for k in common)
        sr = sum(min(5.0, R["mods"][k]["u"]) for k in common)
        if common and sw > 0 and sr > 0:
            xs.append(math.log(sw / sr))
            per = collections.defaultdict(lambda: [0.0, 0.0])
            for k in common:
                kind = W["mods"][k].get("kind") or k.split(":")[0]
                per[kind][0] += min(5.0, W["mods"][k]["u"])
                per[kind][1] += min(5.0, R["mods"][k]["u"])
            for kind, (a, c) in per.items():
                if a > 0 and c > 0:
                    kinds[kind].append(math.log(a / c))
    nz = [x for x in xs if abs(x) > 1e-12]
    med = math.exp(st.median(nz)) if nz else None
    print(f"  physics: both fully routed with valued modules {len(xs)} ({len(nz)} differ), median {A_}/{C} "
          f"{med and round(med, 3)}, floor {floor(len(nz))}, p {sign_flip(nz):.4f}, lower {sum(x < 0 for x in nz)} / higher {sum(x > 0 for x in nz)}")
    for kind, v in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        v = [x for x in v if abs(x) > 1e-12]
        if v:
            print(f"    {kind}: n {len(v)}, median {math.exp(st.median(v)):.3f}, p {sign_flip(v):.3f}")


def main():
    exp = sys.argv[1] if len(sys.argv) > 1 else "chassis-soft"
    D = load(exp)
    for a, c in (("M", "R"), ("Msoft", "R"), ("Msoft", "M")):
        pair(D, a, c)
    for a in ("M", "Msoft"):
        mc = [D[b][a]["mc"] for b in D if a in D[b] and D[b][a].get("mc") and D[b][a]["mc"].get("mm")]
        if mc:
            mm, kept = sum(x["mm"] for x in mc), sum(x["kept_mm"] for x in mc)
            print(f"\n{a}: module copper on the kept board's first route, {len(mc)} boards: {mm:.0f} mm, kept {kept:.0f} mm "
                  f"({100 * kept / mm:.1f} %); boards with all kept {sum(1 for x in mc if x['share'] == 1.0)}")


if __name__ == "__main__":
    main()
