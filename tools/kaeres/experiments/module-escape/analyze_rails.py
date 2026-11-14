#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""module-rails (PLAN.md, Addendum 6): M-clock-rails vs M-clock. Primary worst_rail_mohm on both-routed boards;
guard opens; Σu physics; CPU."""
import glob, json, math, statistics as st
from pathlib import Path
import analyze_clock as A

A.ARM.update({"Mclockrails": "M-clock-rails"})
D = A.load("module-rails")
E = json.loads((A.BASE / "experiments/module-rails/experiment.json").read_text())
ids = {m["id"][:8]: A.ARM[m["name"].split()[2]] for m in E["methods"]}
W = {}
for b in D:
    for rd in glob.glob(str(A.BASE / "boards" / b / "runs" / "*.a0")):
        mid = Path(rd).name.split(".")[-2]
        if mid in ids:
            for f in glob.glob(rd + "/evals/*.json"):
                p = json.loads(Path(f).read_text()).get("physics") or {}
                if p.get("worst_rail_mohm") is not None:
                    W[(b, ids[mid])] = p["worst_rail_mohm"]
a, c = "M-clock-rails", "M-clock"
B = sorted(b for b in D if a in D[b] and c in D[b])
for name, full in (("both routed (primary)", True), ("any routing", False)):
    xs = []
    for b in B:
        if (b, a) in W and (b, c) in W and W[(b, a)] > 0 and W[(b, c)] > 0 and \
                (not full or not (D[b][a]["s"]["unconnected"] or D[b][c]["s"]["unconnected"])):
            x = math.log(W[(b, a)] / W[(b, c)])
            if abs(x) > 1e-12:
                xs.append(x)
    if xs:
        print(f"worst_rail_mohm {name}: n {len(xs)} median {math.exp(st.median(xs)):.3f} better/worse "
              f"{sum(x < 0 for x in xs)}/{sum(x > 0 for x in xs)} p {A.sign_flip(xs):.4f}")
oa = [D[b][a]["s"]["unconnected"] for b in B]; oc = [D[b][c]["s"]["unconnected"] for b in B]
d = [(x - y) / (x + y + 1) for x, y in zip(oa, oc)]
print(f"opens {sum(oa)} vs {sum(oc)} ({100 * (sum(oa) / max(1, sum(oc)) - 1):+.1f} %), fewer/more "
      f"{sum(x < y for x, y in zip(oa, oc))}/{sum(x > y for x, y in zip(oa, oc))}, mean d {st.mean(d):+.3f}, p {A.sign_flip(d):.4f}")
xs = [x for x in (A.phys(D[b][a], D[b][c]) for b in B) if x is not None and abs(x) > 1e-12]
if xs:
    print(f"Σu {a}/{c}: n {len(xs)} median {math.exp(st.median(xs)):.3f} p {A.sign_flip(xs):.4f} floor {A.floor(len(xs)):.2f}")
print(f"CPU {sum(D[b][a]['cpu'] for b in B) / 3600:.1f} vs {sum(D[b][c]['cpu'] for b in B) / 3600:.1f} h; boards {len(B)}; "
      f"clean {sum(bool(D[b][a]['s'].get('clean')) for b in B)} vs {sum(bool(D[b][c]['s'].get('clean')) for b in B)}")
