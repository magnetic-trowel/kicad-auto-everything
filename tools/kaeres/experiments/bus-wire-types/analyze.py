#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""bus-wire-types / diffpair-soft analysis (PLAN.md): each arm against the control, overall and split by whether the
control's Freerouting finished at least 2 passes. Needs `kaeres exp report NAME` (results.csv). Report only.

    python analyze.py NAME [--control SUBSTRING]      (control: the method whose name contains 'control')

Per arm: boards both ok, total open connections and DRC errors (change, 95 % bootstrap over boards), cp1, CPU,
pass-1 timeouts, the router's passes; for pair arms the share of pair copper surviving (report["pairs"]["survival"]).
"""
import argparse
import csv
import gzip
import json
import os
import random
from collections import Counter
from pathlib import Path

STORE = Path(os.environ.get("KAE_RESULTS") or Path.home() / "kae-baselines")
B, SEED = 4000, 20261109


def run_report(board, method, mid):
    """The bridge's JSON report: the last JSON line of the run's adapter.log."""
    slug = method.lower().replace(" ", "-").replace(".", "-")
    for d in (STORE / "boards" / board / "runs").glob(f"*.{mid[:8]}.a0"):
        lg = d / "adapter.log.gz"
        if not lg.exists():
            continue
        last = None
        with gzip.open(lg, "rt", errors="replace") as f:
            for line in f:
                if line.startswith("{\"input\""):
                    last = line
        if last:
            try:
                return json.loads(last)
            except ValueError:
                return None
    return None


def fr_of(rep):
    """(autorouter stop, passes in the first loop or None without telemetry) of the first Freerouting run."""
    r = ((rep or {}).get("router") or {}).get("report") or {}
    loops = (r.get("telemetry") or {}).get("loops") or []
    return r.get("autorouter_stop") or r.get("final_state"), (len(loops[0]["unrouted"]) if loops else None)


def boot(rows, f):
    r = random.Random(SEED)
    v = sorted(f([rows[r.randrange(len(rows))] for _ in rows]) for _ in range(B))
    return round(v[int(0.025 * B)], 4), round(v[int(0.975 * B)], 4)


def rel(rows, k):
    c = sum(x[k + "_c"] for x in rows)
    return (sum(x[k + "_a"] for x in rows) - c) / c if c else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--control", default="control")
    a = ap.parse_args()
    d = STORE / "experiments" / a.name
    exp = json.load(open(d / "experiment.json"))
    ids = {m["name"]: m["id"] for m in exp["methods"]}
    res = {(r["board"], r["method"]): r for r in csv.DictReader(open(d / "results.csv")) if r["attempt"] == "0"}
    ctl = next(m for m in ids if a.control in m)
    reps = {}
    for (b, m), r in res.items():
        if m in ids and r["status"] == "ok":
            reps[(b, m)] = run_report(b, m, ids[m])
    out = {}
    for m in ids:
        if m == ctl:
            continue
        rows = []
        for (b, mm), r in res.items():
            c = res.get((b, ctl))
            if mm != m or not c or r["status"] != "ok" or c["status"] != "ok":
                continue
            fs_c, np_c = fr_of(reps.get((b, ctl)))
            fs_a, np_a = fr_of(reps.get((b, m)))
            surv = (((reps.get((b, m)) or {}).get("pairs") or {}).get("survival") or {})
            rows.append(dict(board=b, un_c=float(c["unconnected"]), un_a=float(r["unconnected"]), er_c=float(c["errors"]),
                             er_a=float(r["errors"]), cl_c=c["clean"] == "True", cl_a=r["clean"] == "True",
                             cpu_c=float(c["cpu_s"] or 0), cpu_a=float(r["cpu_s"] or 0), passes_c=np_c, passes_a=np_a,
                             to1_c=fs_c == "TIMED_OUT" and (np_c or 0) <= 1, to1_a=fs_a == "TIMED_OUT" and (np_a or 0) <= 1,
                             surv_fr=(surv.get("after_freerouting") or {}).get("share"), surv_final=(surv.get("final") or {}).get("share"),
                             wires=((reps.get((b, m)) or {}).get("wire_types") or {}).get("wires")))
        res_m = {}
        for label, sub in (("all", rows), ("control >= 2 passes", [x for x in rows if (x["passes_c"] or 0) >= 2]),
                           ("control < 2 passes", [x for x in rows if x["passes_c"] is not None and x["passes_c"] < 2]),
                           ("arm rewrote >= 50 wires", [x for x in rows if (x["wires"] or 0) >= 50])):
            if not sub:
                continue
            sv = [x["surv_fr"] for x in sub if x["surv_fr"] is not None]
            res_m[label] = dict(
                boards=len(sub), opens=[sum(x["un_c"] for x in sub), sum(x["un_a"] for x in sub)],
                opens_change=round(rel(sub, "un"), 4), opens_ci=boot(sub, lambda s: rel(s, "un")),
                errors=[sum(x["er_c"] for x in sub), sum(x["er_a"] for x in sub)],
                errors_change=round(rel(sub, "er"), 4), errors_ci=boot(sub, lambda s: rel(s, "er")),
                cp1=[sum(x["cl_c"] for x in sub), sum(x["cl_a"] for x in sub)],
                better_worse_opens=[sum(x["un_a"] < x["un_c"] for x in sub), sum(x["un_a"] > x["un_c"] for x in sub)],
                cpu_h=[round(sum(x["cpu_c"] for x in sub) / 3600, 1), round(sum(x["cpu_a"] for x in sub) / 3600, 1)],
                pass1_timeouts=[sum(x["to1_c"] for x in sub), sum(x["to1_a"] for x in sub)],
                passes_median=[sorted(x["passes_c"] or 0 for x in sub)[len(sub) // 2], sorted(x["passes_a"] or 0 for x in sub)[len(sub) // 2]],
                pair_survival_after_fr=(round(sum(sv) / len(sv), 3) if sv else None))
        types = Counter()
        for (b, mm), r in res.items():
            if mm in (m, ctl) and r["status"] == "ok" and (b, ctl) in res and (b, m) in res:
                for k, v in json.loads(r["errors_by_type"] or "{}").items():
                    types[(k, "arm" if mm == m else "control")] += v
        res_m["errors_by_type"] = {k: [types[(k, "control")], types[(k, "arm")]] for k in sorted({k for k, _ in types})}
        out[m] = res_m
    print(json.dumps(dict(experiment=a.name, control=ctl, arms=out), indent=1))


if __name__ == "__main__":
    main()
