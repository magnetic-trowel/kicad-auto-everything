# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Why each stage of kae.joint runs stopped, arm by arm: was the extra time used?

Reads the joint loop's JSON report (the first JSON line of each attempt's adapter.log in a
kaebench `joint` run) and tabulates, per arm:
- time used: the run's seconds over its budget (mean, max);
- the loop's stop reason (clean / no improvement (cycle k) / time / no window / iteration cap);
- iteration 0: the placer's annealer (planned moves done / clock), its closed-loop legality
  (legal / round cap / clock), the module stage (done / clock), the first route's autorouter
  (COMPLETED / STAGNATION / NO_IMPROVEMENT / TIMED_OUT), optimizer and repair rounds;
- windows: how many, kept, and their route_open autorouter stops;
- the finishing stage: tries, kept, autorouter and repair stops.

Usage:
  python tools/research/joint/joint_stops.py NAME=RESULTS/<run>/<adapter> [...] [--out FILE.md]
"""
import argparse
import collections
import json
from pathlib import Path


def reports(arm_dir):
    for f in sorted(Path(arm_dir).glob("joint/*/attempt-*/adapter.log")):
        for line in f.read_text(errors="replace").splitlines():
            if line.startswith('{"seed"'):
                try:
                    yield f.parts[-3], json.loads(line)
                except ValueError:
                    pass
                break


def fmt(c):
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))) or "—"


def arm_summary(arm_dir):
    C = collections.defaultdict(collections.Counter)
    used, n, wins, kept, fins, fkept = [], 0, 0, 0, 0, 0
    for _, r in reports(arm_dir):
        n += 1
        used.append(float(r.get("seconds") or 0) / max(1.0, float(r.get("time_s") or 1)))
        C["loop"][(r.get("stop") or "?").split(" (")[0]] += 1     # "time (45s left ...)" -> "time"
        st = (r.get("iterations") or [{}])[0].get("stages") or {}
        ps = (st.get("place") or {}).get("stops") or {}
        C["anneal"][ps.get("anneal") or "?"] += 1
        if ps.get("closed_loop"):
            C["closed loop"][ps["closed_loop"]] += 1
        C["modules"][(st.get("modules") or {}).get("stop") or "—"] += 1
        rs = (st.get("route") or {}).get("stops") or {}
        C["route0 autorouter"][rs.get("autorouter") or "?"] += 1
        C["route0 optimizer"][rs.get("optimizer") or "?"] += 1
        C["route0 repair"][rs.get("repair") or "—"] += 1
        for row in (r.get("iterations") or [])[1:]:
            if row.get("finish"):
                fins += 1
                fkept += bool(row.get("accepted"))
                fs = (row.get("route") or {}).get("stops") or {}
                C["finish autorouter"][fs.get("autorouter") or "?"] += 1
                C["finish repair"][fs.get("repair") or "—"] += 1
                continue
            rt = (row.get("repair") or {}).get("route") or {}
            if rt:
                wins += 1
                kept += bool(row.get("accepted"))
                C["window autorouter"][((rt.get("stops") or {}).get("autorouter")) or "?"] += 1
    return dict(n=n, used=used, C=C, wins=wins, kept=kept, fins=fins, fkept=fkept)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="+", help="NAME=RESULTS/<run>/<adapter>")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    keys = ["loop", "anneal", "closed loop", "modules", "route0 autorouter", "route0 optimizer", "route0 repair",
            "window autorouter", "finish autorouter", "finish repair"]
    lines = []
    for spec in a.arms:
        name, d = spec.split("=", 1)
        s = arm_summary(d)
        if not s["n"]:
            continue
        u = s["used"]
        lines.append(f"### {name} ({s['n']} attempts)\n")
        lines.append(f"- time used / budget: mean {sum(u) / len(u):.2f}, max {max(u):.2f}")
        lines.append(f"- windows: {s['wins']} routed, {s['kept']} kept; finishing tries: {s['fins']}, {s['fkept']} kept")
        lines += [f"- {k}: {fmt(s['C'][k])}" for k in keys if s["C"].get(k)]
        lines.append("")
    md = "\n".join(lines)
    if a.out:
        Path(a.out).write_text(md)
    print(md)


if __name__ == "__main__":
    main()
