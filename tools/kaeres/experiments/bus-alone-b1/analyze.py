#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""bus-alone-b1 analysis: classify buses as fails alone / loses in contention / fine (PLAN.md).

Usage: analyze.py BUSNETS_DIR VIEW_DIR RUNS_CSV SUITES_DIR OUT_DIR
RUNS_CSV lines: board,arm,run_dir (arms: control, alone, human). Writes OUT_DIR/buses.csv and OUT_DIR/SUMMARY.md."""
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

STRATA = ["bus_width.8-15", "bus_width.16-31", "bus_width.32-63", "bus_width.64plus", "bus_ddr", "bus_kind.parallel_mem",
          "bus_kind.connector_ribbon", "bus_kind.gpio_bank"]


def fine_end(t, pitch):
    t = t or ""
    return "bga" in t or "grid" in t or (pitch is not None and 0 < pitch < 0.5)


def load(busnets, views, runs_csv):
    meta = {}
    for b, arm, rd in csv.reader(open(runs_csv)):
        r = json.loads((Path(rd) / "run.json").read_text()) if (Path(rd) / "run.json").exists() else {}
        am = r.get("adapter_meta") or {}
        rep = am.get("router_report") or {}
        meta[(b, arm)] = dict(status=r.get("status"), partial=bool(am.get("partial") or am.get("timed_out")), final=rep.get("final_state"),
                              runtime=r.get("runtime_s"), cpu=(r.get("method_usage") or {}).get("cpu_s"))
    rows = []
    for f in sorted(Path(busnets).glob("*.buses.json")):
        d = json.loads(f.read_text())
        bid = d["id"]
        if "error" in d:
            continue
        v = {}
        for arm in ("control", "alone", "human"):
            p = Path(views) / f"{bid}.{arm}.json"
            v[arm] = json.loads(p.read_text()) if p.exists() else None
        if not v["control"] or not v["alone"] or "error" in v["control"] or "error" in v["alone"]:
            continue
        hum = (v["human"] or {}).get("opens") or {}
        for i, bus in enumerate(d["buses"]):
            lanes = [ln for ln in bus["nets"] if not any(hum.get(n) for n in ln)]
            if not lanes:
                continue
            oa = [any(v["alone"]["opens"].get(n) for n in ln) for ln in lanes]
            of = [any(v["control"]["opens"].get(n) for n in ln) for ln in lanes]
            esc = fine_end(bus.get("a_type"), bus.get("a_pitch")) or fine_end(bus.get("b_type"), bus.get("b_pitch"))
            cls = "fails_alone" if any(oa) else ("contention" if any(of) else "fine")
            if cls == "contention" and meta.get((bid, "control"), {}).get("partial"):
                cls = "contention_or_budget"
            rows.append(dict(board=bid, bus=i, kind=bus["kind"], width=bus["width"], lanes=len(lanes), excluded=bus["width"] - len(lanes),
                             open_alone=sum(oa), open_full=sum(of), open_both=sum(1 for a, b in zip(oa, of) if a and b),
                             cls=cls, fine_end=int(esc), a_type=bus.get("a_type"), b_type=bus.get("b_type"), lds=bus.get("lds"),
                             ctl_partial=int(meta.get((bid, "control"), {}).get("partial", False)),
                             alone_partial=int(meta.get((bid, "alone"), {}).get("partial", False))))
    return rows, meta


def boot(rows, stat, n=1000, seed=1234):
    by = defaultdict(list)
    for r in rows:
        by[r["board"]].append(r)
    keys = sorted(by)
    if not keys:
        return None, None, None
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        s = [r for k in (rng.choice(keys) for _ in keys) for r in by[k]]
        x = stat(s)
        if x is not None:
            vals.append(x)
    vals.sort()
    return stat(rows), vals[int(0.025 * len(vals))] if vals else None, vals[int(0.975 * len(vals)) - 1] if vals else None


def alone_share(rs):
    """Of lanes open in the control, the share also open alone."""
    f = sum(r["open_full"] for r in rs)
    return sum(r["open_both"] for r in rs) / f if f else None


def board_fails_alone(rs):
    by = defaultdict(list)
    for r in rs:
        by[r["board"]].append(r)
    open_boards = [b for b, v in by.items() if any(r["open_full"] or r["open_alone"] for r in v)]
    return sum(1 for b in open_boards if any(r["cls"] == "fails_alone" for r in by[b])) / len(open_boards) if open_boards else None


def pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def main():
    busnets, views, runs_csv, suites, out = sys.argv[1:6]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows, meta = load(busnets, views, runs_csv)
    with open(out / "buses.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    md = ["# bus-alone-b1: summary", "", f"{len({r['board'] for r in rows})} boards, {len(rows)} buses (width >= 4) with both arms viewed. "
          "Lanes open in the human view are excluded. CIs: board-clustered bootstrap, 1,000 resamples, seed 1234.", ""]
    md += ["## By stratum", "", "| stratum | boards | buses | lanes | lanes open control | lanes open alone | of control's open lanes, also open alone (95% CI) | "
           "boards with opens that fail alone | buses fails alone / contention / budget / fine |", "|---|---|---|---|---|---|---|---|---|"]
    for st in ["all"] + STRATA:
        ids = None if st == "all" else set(Path(suites, f"{st}.txt").read_text().split())   # full suite: only the boards run count
        rs = [r for r in rows if ids is None or r["board"] in ids]
        if not rs:
            continue
        s, lo, hi = boot(rs, alone_share)
        c = Counter(r["cls"] for r in rs)
        md.append(f"| {st} | {len({r['board'] for r in rs})} | {len(rs)} | {sum(r['lanes'] for r in rs)} | {sum(r['open_full'] for r in rs)} | "
                  f"{sum(r['open_alone'] for r in rs)} | {pct(s)} ({pct(lo)}-{pct(hi)}) | {pct(board_fails_alone(rs))} | "
                  f"{c['fails_alone']} / {c['contention']} / {c['contention_or_budget']} / {c['fine']} |")
    md += ["", "## By bus kind (all boards)", "", "| kind | buses | lanes open control | open alone | also open alone | fails alone: fine-pitch/BGA end | other end |",
           "|---|---|---|---|---|---|---|"]
    for k, n in Counter(r["kind"] for r in rows).most_common():
        rs = [r for r in rows if r["kind"] == k]
        fa = [r for r in rs if r["cls"] == "fails_alone"]
        md.append(f"| {k} | {n} | {sum(r['open_full'] for r in rs)} | {sum(r['open_alone'] for r in rs)} | {pct(alone_share(rs))} | "
                  f"{sum(r['fine_end'] for r in fa)} | {sum(1 - r['fine_end'] for r in fa)} |")
    md += ["", "## Sensitivity: did the bus-alone run itself finish? (reported, not pre-registered)", "",
           "| subset | boards | buses | lanes open control | open alone | also open alone (95% CI) | fails alone / contention / budget / fine |",
           "|---|---|---|---|---|---|---|"]
    for lab, f in (("bus-alone COMPLETED", lambda r: not r["alone_partial"]),
                   ("bus-alone and control COMPLETED", lambda r: not r["alone_partial"] and not r["ctl_partial"]),
                   ("bus-alone TIMED_OUT", lambda r: r["alone_partial"])):
        rs = [r for r in rows if f(r)]
        if not rs:
            continue
        s, lo, hi = boot(rs, alone_share)
        c = Counter(r["cls"] for r in rs)
        md.append(f"| {lab} | {len({r['board'] for r in rs})} | {len(rs)} | {sum(r['open_full'] for r in rs)} | {sum(r['open_alone'] for r in rs)} | "
                  f"{pct(s)} ({pct(lo)}-{pct(hi)}) | {c['fails_alone']} / {c['contention']} / {c['contention_or_budget']} / {c['fine']} |")
    fa = [r for r in rows if r["cls"] == "fails_alone"]
    md += ["", "## Buses that fail alone", "", f"{len(fa)} buses; whole bus open alone: {sum(1 for r in fa if r['open_alone'] == r['lanes'])}; "
           f"1-2 lanes: {sum(1 for r in fa if r['open_alone'] <= 2)}; with a BGA/grid or < 0.5 mm end: {sum(r['fine_end'] for r in fa)}; "
           f"control open on the same bus: {sum(1 for r in fa if r['open_full'])}. Lanes open alone but routed in control: "
           f"{sum(r['open_alone'] - r['open_both'] for r in rows)}.", ""]
    arms = Counter((a, m["final"], m["partial"]) for (b, a), m in meta.items())
    md += ["## Router outcomes", "", "| arm | final state | partial | runs |", "|---|---|---|---|"] + \
          [f"| {a} | {f} | {p} | {n} |" for (a, f, p), n in sorted(arms.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), kv[0][2]))]
    (out / "SUMMARY.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
