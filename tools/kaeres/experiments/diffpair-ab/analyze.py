#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""diffpair-ab analysis: the pre-registered numbers (PLAN.md). Needs `kaeres exp report` and `pair_report.py` run.

    python analyze.py NAME CONTROL_METHOD_NAME ARM_METHOD_NAME [--min-len 4]     (once for each arm)

Pairs: tier rule or interface, both legs routed in both arms and at least --min-len mm a leg in the control.
Pair statistics are paired by (board, p); intervals bootstrap over boards (a board's pairs are not independent).
"""
import argparse
import csv
import json
import os
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

STORE = Path(os.environ.get("KAE_RESULTS") or Path.home() / "kae-baselines")
B = 4000
SEED = 20261109


def fl(x):
    return None if x in ("", None, "None") else float(x)


def boot(boards, stat):
    """95 % interval of stat(list of boards) resampling boards."""
    r = random.Random(SEED)
    vals = []
    for _ in range(B):
        v = stat([boards[r.randrange(len(boards))] for _ in boards])
        if v is not None:
            vals.append(v)
    vals.sort()
    return round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals))], 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name"), ap.add_argument("control"), ap.add_argument("pairs")
    ap.add_argument("--min-len", type=float, default=4.0)
    a = ap.parse_args()
    d = STORE / "experiments" / a.name
    res = {}
    for r in csv.DictReader(open(d / "results.csv")):
        if int(r["attempt"]) == 0:
            res[(r["board"], r["method"])] = r
    boards = sorted({b for b, m in res if m == a.control} & {b for b, m in res if m == a.pairs})
    both_ok = [b for b in boards if res[(b, a.control)]["status"] == "ok" and res[(b, a.pairs)]["status"] == "ok"]
    out = dict(boards=len(boards), both_ok=len(both_ok), arms=[a.control, a.pairs])
    # guardrails: board level
    per = []
    for b in both_ok:
        c, p = res[(b, a.control)], res[(b, a.pairs)]
        per.append(dict(board=b, un_c=fl(c["unconnected"]), un_p=fl(p["unconnected"]), er_c=fl(c["errors"]), er_p=fl(p["errors"]),
                        cl_c=c["clean"] == "True", cl_p=p["clean"] == "True", cp_c=fl(c["completion"]), cp_p=fl(p["completion"]),
                        cpu_c=fl(c["cpu_s"]), cpu_p=fl(p["cpu_s"]), ph_c=fl(c["physics_total"]), ph_p=fl(p["physics_total"]),
                        ty_c=json.loads(c["errors_by_type"] or "{}"), ty_p=json.loads(p["errors_by_type"] or "{}")))

    def ratio_total(field_c, field_p):
        def f(sample):
            sc, sp = sum(x[field_c] or 0 for x in sample), sum(x[field_p] or 0 for x in sample)
            return (sp - sc) / sc if sc > 0 else None
        return f
    gr = {}
    for label, c, p in (("opens", "un_c", "un_p"), ("errors", "er_c", "er_p")):
        sc, sp = sum(x[c] or 0 for x in per), sum(x[p] or 0 for x in per)
        ci = boot(per, ratio_total(c, p))
        gr[label] = dict(total_control=sc, total_pairs=sp, change=round((sp - sc) / sc, 4) if sc else None, ci95=ci,
                         worse_boards=sum((x[p] or 0) > (x[c] or 0) for x in per), better_boards=sum((x[p] or 0) < (x[c] or 0) for x in per))
    gr["clean"] = dict(control=sum(x["cl_c"] for x in per), pairs=sum(x["cl_p"] for x in per),
                       only_control=sum(x["cl_c"] and not x["cl_p"] for x in per),
                       only_pairs=sum(x["cl_p"] and not x["cl_c"] for x in per))
    gr["cp1"] = dict(control=round(gr["clean"]["control"] / len(per), 3) if per else None,
                     pairs=round(gr["clean"]["pairs"] / len(per), 3) if per else None)
    gr["completion_mean"] = dict(control=round(st.fmean(x["cp_c"] for x in per), 4) if per else None,
                                 pairs=round(st.fmean(x["cp_p"] for x in per), 4) if per else None)
    cpu = [x for x in per if x["cpu_c"] and x["cpu_p"]]
    gr["cpu_s_mean"] = dict(control=round(st.fmean(x["cpu_c"] for x in cpu)), pairs=round(st.fmean(x["cpu_p"] for x in cpu))) if cpu else {}
    ph = [x for x in per if x["ph_c"] is not None and x["ph_p"] is not None and x["un_c"] == 0 and x["un_p"] == 0]
    gr["physics_both_complete"] = dict(n=len(ph), median_ratio=round(st.median(x["ph_p"] / x["ph_c"] for x in ph), 4)) if ph else {}
    types = sorted({t for x in per for t in list(x["ty_c"]) + list(x["ty_p"])})
    gr["errors_by_type"] = {t: [sum(x["ty_c"].get(t, 0) for x in per), sum(x["ty_p"].get(t, 0) for x in per)] for t in types}
    out["guardrails"] = gr
    # pairs
    pc = defaultdict(dict)
    for r in csv.DictReader(open(d / "pairs.csv")):
        if r["method"] in (a.control, a.pairs, "human") and r["board"] in both_ok and r["routed"] == "True" and r["tier"] in ("rule", "interface"):
            pc[(r["board"], r["p"])][r["method"]] = r
    keep = {k: v for k, v in pc.items() if a.control in v and a.pairs in v and float(v[a.control]["len_p"]) >= a.min_len and float(v[a.control]["len_n"]) >= a.min_len}
    per_board = defaultdict(list)
    rows = []
    for (b, p), v in keep.items():
        c, x = v[a.control], v[a.pairs]
        rows.append(dict(board=b, p=p, iface=c["interface"], tier=c["tier"], cpl_c=fl(c["coupled_share"]), cpl_p=fl(x["coupled_share"]),
                         sk_c=fl(c["skew"]), sk_p=fl(x["skew"]), v_c=fl(c["vias_p"]) + fl(c["vias_n"]), v_p=fl(x["vias_p"]) + fl(x["vias_n"]),
                         ref_c=fl(c["ref_changes"]), ref_p=fl(x["ref_changes"]), nr_c=fl(c["no_ref_mm"]), nr_p=fl(x["no_ref_mm"])))
        per_board[b].append(rows[-1])
    bl = list(per_board.values())

    def pair_stats(sample):
        rs = [r for b in sample for r in b]
        return rs
    out["pairs_n"] = len(rows)
    out["pair_boards"] = len(bl)
    if rows:
        def dcpl(s):
            v = [r["cpl_p"] - r["cpl_c"] for r in pair_stats(s) if r["cpl_p"] is not None and r["cpl_c"] is not None]
            return st.median(v) if v else None

        def skr(s):
            v = [r for r in pair_stats(s) if r["sk_c"] is not None and r["sk_p"] is not None and r["sk_c"] > 0]
            return st.median([r["sk_p"] / r["sk_c"] for r in v]) if v else None

        def dvia(s):
            v = [r["v_p"] - r["v_c"] for r in pair_stats(s)]
            return st.mean(v) if v else None
        out["coupled_median_paired_delta"] = dict(point=round(dcpl(bl), 3), ci95=boot(bl, dcpl))
        out["skew_median_paired_ratio"] = dict(point=round(skr(bl), 3), ci95=boot(bl, skr))
        out["vias_per_pair_delta_mean"] = dict(point=round(dvia(bl), 3), ci95=boot(bl, dvia))
        out["coupled_median"] = dict(control=round(st.median(r["cpl_c"] for r in rows if r["cpl_c"] is not None), 3),
                                     pairs=round(st.median(r["cpl_p"] for r in rows if r["cpl_p"] is not None), 3))
        out["skew_median_mm"] = dict(control=round(st.median(r["sk_c"] for r in rows if r["sk_c"] is not None), 3),
                                     pairs=round(st.median(r["sk_p"] for r in rows if r["sk_p"] is not None), 3))

        def part(name, flt):
            s = [r for r in rows if flt(r)]
            if not s:
                return
            out.setdefault("subsets", {})[name] = dict(
                n=len(s), boards=len({r["board"] for r in s}),
                coupled=[round(st.median(r["cpl_c"] for r in s if r["cpl_c"] is not None), 3),
                         round(st.median(r["cpl_p"] for r in s if r["cpl_p"] is not None), 3)],
                skew=[round(st.median(r["sk_c"] for r in s if r["sk_c"] is not None), 3),
                      round(st.median(r["sk_p"] for r in s if r["sk_p"] is not None), 3)],
                ref_changes_mean=[round(st.fmean(r["ref_c"] or 0 for r in s), 2), round(st.fmean(r["ref_p"] or 0 for r in s), 2)],
                no_ref_mm_mean=[round(st.fmean(r["nr_c"] or 0 for r in s), 1), round(st.fmean(r["nr_p"] or 0 for r in s), 1)],
                vias_mean=[round(st.fmean(r["v_c"] for r in s), 2), round(st.fmean(r["v_p"] for r in s), 2)])
        part("crossing a plane change in control", lambda r: (r["ref_c"] or 0) > 0)
        part("with a layer change in control", lambda r: r["v_c"] > 0)
        part("all layers same, no plane change", lambda r: (r["ref_c"] or 0) == 0 and r["v_c"] == 0)
        for t in ("rule", "interface"):
            part("tier " + t, lambda r: r["tier"] == t)
        for i in sorted({r["iface"] for r in rows}):
            if sum(r["iface"] == i for r in rows) >= 5:
                part("interface " + i, lambda r: r["iface"] == i)
    print(json.dumps(out, indent=1))
    (d / "PAIR_AB.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
