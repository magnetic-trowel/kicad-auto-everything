# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pre-polish search quality: best objective found by a qd archive vs the best of jc's
restarts (both routed cost + phys_w * fast physics, before the anneal_phys polish).

    python search_cost.py kae-work/qd/<run> kae-work/jc-png/ab33-jc
"""
import json
import sys
from pathlib import Path

import numpy as np

qd_dir, jc_dir = Path(sys.argv[1]), Path(sys.argv[2])
rat, wins, ncand, njc = [], 0, [], []
for f in sorted(qd_dir.glob("*.json")):
    p = jc_dir / f"{f.stem}.runs.json"
    if not p.exists():
        continue
    A = json.loads(f.read_text())
    R = json.loads(p.read_text())["runs"]
    q = min(c["cost"] for c in A["cells"])
    j = min(r["cost"] for r in R)
    rat.append(q / j)
    wins += q < j - 1e-6
    ncand.append(len(A["hist"]))
    njc.append(len(R))
    print(f"{f.stem[:44]:44s} qd {q:9.1f} ({len(A['hist'])} cand)  jc {j:9.1f} ({len(R)} runs)  x{q / j:.3f}")
r = np.array(rat)
print(f"boards {len(r)}: qd better on {wins}, worse on {int((r > 1 + 1e-6).sum())}; gmean x{np.exp(np.log(r).mean()):.3f}; "
      f"median candidates {np.median(ncand):.0f} vs jc runs {np.median(njc):.0f}")
