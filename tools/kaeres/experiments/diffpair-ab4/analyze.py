#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""diffpair-ab4 analysis: the pre-registered numbers of PLAN.md. Report only.

Needs `kaeres exp report NAME` (results.csv: every attempt) and the bus scorecard of every run
(`kaeres bus submit NAME ...`), and a venv with the kae package (pair tiers from the human board):

    python analyze.py NAME [--level 0.95] [--eid BUS_EVALUATOR] [--out FILE]

Arms are found by name: dp4-control 900 (C), dp4-control 1080 (Ct), dp4-first (F), dp4-firstsoft (FS), dp4-post (P).
Primaries (each pair arm against C): coupled_3w median paired change, skew median paired ratio, on the scorecard's
pair rows of tier rule or interface (tier from the human board with its rules), measured in both arms, len_mean >= 4 mm
in C; each (board, pair) value is the mean over the attempts both arms have. Guards (F and FS against Ct, P against C):
per board the mean over attempts of log(opens + 1) and log(errors + 1), arm minus comparator; the geometric-mean ratio
and its bootstrap interval over boards; and the change in total opens and errors. Pair-rule errors (track_width,
diff_pair_gap_out_of_range, items_not_allowed) per arm. Intervals resample boards (B = 4000, fixed seed).
"""
import argparse
import csv
import gzip
import json
import math
import os
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

STORE = Path(os.environ.get("KAE_RESULTS") or Path.home() / "kae-baselines")
CORPUS = Path(os.environ.get("KAE_BOARDS") or Path.home() / "kae-boards")
B, SEED = 4000, 20261114
ARMS = (("C", "dp4-control 900"), ("Ct", "dp4-control 1080"), ("F", "dp4-first 900"), ("FS", "dp4-firstsoft 900"),
        ("P", "dp4-post 900"))
GUARD_VS = {"F": "Ct", "FS": "Ct", "P": "C"}
MARGIN = math.log(1.05)          # guards: +5 % (PLAN.md)
PAIR_RULE_TYPES = ("track_width", "diff_pair_gap_out_of_range", "items_not_allowed")


def fl(x):
    return None if x in ("", None, "None") else float(x)


def boot(units, stat, level):
    r = random.Random(SEED)
    vals = []
    for _ in range(B):
        v = stat([units[r.randrange(len(units))] for _ in units])
        if v is not None:
            vals.append(v)
    vals.sort()
    lo = (1.0 - level) / 2.0
    return (round(vals[int(lo * len(vals))], 4), round(vals[min(len(vals) - 1, int((1.0 - lo) * len(vals)))], 4)) if vals else None


def scorecard(board, run, eid=None):
    d = STORE / "boards" / board / "runs" / run / "bus"
    fs = [d / f"{eid}.json.gz"] if eid else (sorted(d.glob("*.json.gz"), key=lambda f: f.stat().st_mtime) if d.is_dir() else [])
    fs = [f for f in fs if f.exists()]
    if not fs:
        return None
    with gzip.open(fs[-1], "rt") as f:
        return json.load(f)


def human_tiers(board):
    from kae.board.kicad_file import load
    from kae.route import pairs as P
    b = load(CORPUS / "boards" / board / "board.kicad_pcb")
    try:
        from kae.circuit.brief import build
        brief = build(b)
    except Exception:  # noqa: BLE001 - names and classes still tier the pairs
        brief = None
    return {pr.key(): (pr.tier, pr.interface) for pr in P.detect(b, brief=brief)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--level", type=float, default=0.95, help="interval level (0.975 at each of two looks, PLAN.md)")
    ap.add_argument("--eid")
    ap.add_argument("--min-len", type=float, default=4.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    d = STORE / "experiments" / a.name
    exp = json.load(open(d / "experiment.json"))
    arm_of = {}
    for m in exp["methods"]:
        for key, sub in ARMS:
            if sub in m["name"]:
                arm_of[m["name"]] = key
    runs = defaultdict(dict)        # (board, arm) -> attempt -> row
    for r in csv.DictReader(open(d / "results.csv")):
        k = arm_of.get(r["method"])
        if k and r["status"] == "ok" and r["unconnected"] not in ("", None):
            runs[(r["board"], k)][int(r["attempt"])] = r
    out = dict(experiment=a.name, level=a.level, arms={k: [n for n, v in arm_of.items() if v == k] for k, _ in ARMS})
    boards = sorted({b for b, _ in runs})

    # ---- guards
    def per_board(arm, comp, field):
        rows = []
        for b in boards:
            ra, rc = runs.get((b, arm), {}), runs.get((b, comp), {})
            if not ra or not rc:
                continue
            la = st.fmean(math.log(fl(x[field]) + 1.0) for x in ra.values())
            lc = st.fmean(math.log(fl(x[field]) + 1.0) for x in rc.values())
            ta = st.fmean(fl(x[field]) for x in ra.values())
            tc = st.fmean(fl(x[field]) for x in rc.values())
            rows.append(dict(board=b, d=la - lc, a=ta, c=tc, k=(len(ra), len(rc))))
        return rows

    def gm(rows):
        return st.fmean(r["d"] for r in rows) if rows else None

    def tot(rows):
        c = sum(r["c"] for r in rows)
        return (sum(r["a"] for r in rows) - c) / c if c else None

    guards = {}
    for arm, comp in GUARD_VS.items():
        g = {}
        for field, label in (("unconnected", "opens"), ("errors", "errors")):
            rows = per_board(arm, comp, field)
            if not rows:
                continue
            ci = boot(rows, gm, a.level)
            g[label] = dict(boards=len(rows), attempts=sorted({r["k"] for r in rows}), gm_ratio=round(math.exp(gm(rows)), 4),
                            gm_ratio_ci=[round(math.exp(x), 4) for x in ci] if ci else None,
                            total=[round(sum(r["c"] for r in rows), 1), round(sum(r["a"] for r in rows), 1)],
                            total_change=round(tot(rows), 4), total_change_ci=boot(rows, tot, a.level),
                            better_worse=[sum(r["a"] < r["c"] for r in rows), sum(r["a"] > r["c"] for r in rows)],
                            holds=(ci is not None and ci[1] <= MARGIN and tot(rows) <= 0.05),
                            fails=(ci is not None and ci[0] > MARGIN))
        guards[f"{arm} vs {comp}"] = g
    out["guards"] = guards

    # ---- per-type errors, cp1, completion, CPU, timeouts (attempt means summed over boards with every arm)
    full = [b for b in boards if all(runs.get((b, k)) for k, _ in ARMS if any(v == k for v in arm_of.values()))]
    summ = {}
    for k, _ in ARMS:
        rs = [x for b in full for x in runs.get((b, k), {}).values()]
        if not rs:
            continue
        types = defaultdict(float)
        for x in rs:
            for t, v in json.loads(x["errors_by_type"] or "{}").items():
                types[t] += v
        n_att = len(rs) / max(1, len(full))
        summ[k] = dict(runs=len(rs), cp1=round(sum(x["clean"] == "True" for x in rs) / len(rs), 4),
                       completion=round(st.fmean(fl(x["completion"]) or 0.0 for x in rs), 4),
                       opens_per_attempt=round(sum(fl(x["unconnected"]) for x in rs) / n_att, 1),
                       errors_per_attempt=round(sum(fl(x["errors"]) for x in rs) / n_att, 1),
                       timeouts=sum(x["timed_out"] == "True" for x in rs), cpu_h=round(sum(fl(x["cpu_s"]) or 0 for x in rs) / 3600, 1),
                       pair_rule_errors={t: round(types.get(t, 0.0) / n_att, 1) for t in PAIR_RULE_TYPES},
                       errors_by_type={t: round(v / n_att, 1) for t, v in sorted(types.items(), key=lambda kv: -kv[1])})
    out["summary_boards_with_every_arm"] = len(full)
    out["summary"] = summ

    # ---- primaries: pair quality, each pair arm against C
    tiers, prim = {}, {}
    for arm in ("F", "FS", "P"):
        per = defaultdict(list)
        missing = 0
        for b in boards:
            ra, rc = runs.get((b, arm), {}), runs.get((b, "C"), {})
            att = sorted(set(ra) & set(rc))
            if not att:
                continue
            acc = defaultdict(lambda: defaultdict(list))
            ok = True
            for t in att:
                sc = {s: scorecard(b, r[t]["run"], a.eid) for s, r in (("a", ra), ("c", rc))}
                if any(v is None or v.get("error") for v in sc.values()):
                    ok = False
                    break
                by = {s: {(x.get("p"), x.get("n")): x for x in v.get("pairs") or [] if x.get("p")} for s, v in sc.items()}
                for key, c in by["c"].items():
                    x = by["a"].get(key)
                    if x is None or c.get("coupled_3w") is None or x.get("coupled_3w") is None:
                        continue
                    for s, v in (("c", c), ("a", x)):
                        acc[key][s + "cpl"].append(v["coupled_3w"])
                        acc[key][s + "sk"].append(v.get("skew_mm"))
                        acc[key][s + "len"].append(v.get("len_mean") or 0.0)
                        acc[key][s + "via"].append(2.0 * (v.get("vias_lane") or 0.0))
            if not ok:
                missing += 1
                continue
            if b not in tiers:
                tiers[b] = human_tiers(b)
            for key, v in acc.items():
                tier, iface = tiers[b].get(tuple(sorted(key)), (None, None))
                if tier not in ("rule", "interface") or st.fmean(v["clen"]) < a.min_len:
                    continue
                sk_c = [x for x in v["csk"] if x is not None]
                sk_a = [x for x in v["ask"] if x is not None]
                per[b].append(dict(p=key[0], iface=iface, cpl_c=st.fmean(v["ccpl"]), cpl_a=st.fmean(v["acpl"]),
                                   sk_c=st.fmean(sk_c) if sk_c else None, sk_a=st.fmean(sk_a) if sk_a else None,
                                   v_c=st.fmean(v["cvia"]), v_a=st.fmean(v["avia"])))
        units = [v for v in per.values() if v]
        rows = [r for u in units for r in u]
        if not rows:
            prim[arm] = dict(pairs=0, boards_without_scorecards=missing)
            continue

        def dcpl(s):
            v = [r["cpl_a"] - r["cpl_c"] for u in s for r in u]
            return st.median(v) if v else None

        def skr(s):
            v = [r["sk_a"] / r["sk_c"] for u in s for r in u if r["sk_c"] and r["sk_a"] is not None]
            return st.median(v) if v else None
        c_ci, s_ci = boot(units, dcpl, a.level), boot(units, skr, a.level)
        prim[arm] = dict(pairs=len(rows), boards=len(units), boards_without_scorecards=missing,
                         coupled_delta_median=round(dcpl(units), 3), coupled_delta_ci=c_ci,
                         skew_ratio_median=round(skr(units), 3) if skr(units) is not None else None, skew_ratio_ci=s_ci,
                         coupled_median=[round(st.median(r["cpl_c"] for r in rows), 3), round(st.median(r["cpl_a"] for r in rows), 3)],
                         skew_median_mm=[round(st.median(r["sk_c"] for r in rows if r["sk_c"] is not None), 3),
                                         round(st.median(r["sk_a"] for r in rows if r["sk_a"] is not None), 3)],
                         vias_per_pair_mean=[round(st.fmean(r["v_c"] for r in rows), 2), round(st.fmean(r["v_a"] for r in rows), 2)],
                         reached=bool(c_ci and s_ci and c_ci[0] >= 0.30 and s_ci[1] <= 0.5))
    out["primaries"] = prim
    txt = json.dumps(out, indent=1)
    print(txt)
    (Path(a.out) if a.out else d / "DP4.json").write_text(txt)


if __name__ == "__main__":
    main()
