#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""module-clock2 rail check: M-clock vs M on worst_rail_mohm (physics eval), on boards where M-clock's clock
skipped the rails, and pooled. Boards where both route fully; paired ratio, sign-flip."""
import glob, json, math, statistics as st
from pathlib import Path
import analyze_clock as A

D = A.load("module-clock2")
E = json.loads((A.BASE / "experiments/module-clock2/experiment.json").read_text())
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
skipped = {b for b in D if "M-clock" in D[b] and "rails" in ((D[b]["M-clock"].get("mod") or {}).get("clock") or {}).get("skipped", [])}
for name, sel, full in (("rails skipped", skipped, True), ("rails skipped, any routing", skipped, False),
                        ("pooled", set(D), True), ("pooled, any routing", set(D), False)):
    xs = []
    for b in sel:
        if not all(a in D[b] for a in ("M", "M-clock")) or (b, "M") not in W or (b, "M-clock") not in W:
            continue
        if full and (D[b]["M"]["s"]["unconnected"] or D[b]["M-clock"]["s"]["unconnected"]):
            continue
        x, y = W[(b, "M-clock")], W[(b, "M")]
        if x > 0 and y > 0 and abs(math.log(x / y)) > 1e-12:
            xs.append(math.log(x / y))
    if xs:
        print(f"{name:28s} n {len(xs):3d} median M-clock/M {math.exp(st.median(xs)):.3f} worse/better "
              f"{sum(x > 0 for x in xs)}/{sum(x < 0 for x in xs)} p {A.sign_flip(xs):.4f} floor {A.floor(len(xs)):.2f}")
print("boards with rails skipped:", len(skipped))
