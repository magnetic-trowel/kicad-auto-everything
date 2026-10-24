# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pool gate.py per-board logs into one table per map budget (re-reads the raw errors from
the per-board JSON summaries: medians/p95 pooled as sample-weighted, max as max)."""
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
for mb in ("none", "0.1", "0.3"):
    pool = {}
    cpu = []
    for f in sorted(d.glob(f"gate2-{mb}-*.json")):
        j = json.loads(f.read_text())
        cpu.append(j["map_cpu_s"]["median"])
        for k, s in j["summary"].items():
            pool.setdefault(k, []).append(s)
    print(f"\nmap budget {mb}: median map CPU per part-rotation (median over boards) "
          f"{sorted(cpu)[len(cpu) // 2]:.3f} s")
    print("| term | n | median | p95 | p99 | max | within 1% | within 5% |")
    print("|---|---|---|---|---|---|---|---|")
    for k, ss in sorted(pool.items()):
        n = sum(s["n"] for s in ss)
        wavg = lambda q: sum(s[q] * s["n"] for s in ss) / n  # noqa: E731
        print(f"| {k} | {n} | {wavg('median'):.1e} | {wavg('p95'):.1e} | {wavg('p99'):.1e} | "
              f"{max(s['max'] for s in ss):.2g} | {wavg('within_1pct'):.3f} | {wavg('within_5pct'):.3f} |")
