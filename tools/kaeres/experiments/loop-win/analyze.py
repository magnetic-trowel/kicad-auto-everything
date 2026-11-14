#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""loop-win (PLAN.md): Wall against R (primary), each W arm against W0 (per change), pooled over the experiments given.

    python3 analyze.py loop-win [loop-win-k2 loop-win-ext1 ...] [--looks N]

Scores come from the runs' DRC evaluations (KiCad on the re-opened board); loop facts from the joint loop's JSON
report (adapter.log.gz). A board's d is the mean over the seeds both arms ran.
"""
import collections
import glob
import gzip
import json
import random
import sys
from pathlib import Path

BASE = Path.home() / "kae-baselines"
ARMS = {"restarts": "R", "ctl": "W0", "evidence": "We", "tabu": "Wt", "exact": "Wx", "all": "Wall"}


def arm_of(name):
    """'kae lw joint tabu 48ffd89' -> 'Wt'; 'kae lw restarts 48ffd89' -> 'R'."""
    w = name.split()
    return ARMS.get(w[3] if w[2] == "joint" else w[2])


def load_report(rd):
    p = rd / "adapter.log.gz"
    if not p.exists():
        return {}
    t = gzip.open(p).read().decode("utf8", "replace")
    i = t.find('{"seed"')
    try:
        return json.JSONDecoder().raw_decode(t[i:])[0] if i >= 0 else {}
    except ValueError:
        return {}


def load(exps):
    """{(board, seed): {arm: dict(s=score, cpu, report)}}"""
    D = collections.defaultdict(dict)
    for exp in exps:
        e = json.loads((BASE / "experiments" / exp / "experiment.json").read_text())
        ids = {m["id"][:8]: arm_of(m["name"]) for m in e["methods"]}
        for b in (BASE / "experiments" / exp / "boards.txt").read_text().split():
            for rd in glob.glob(str(BASE / "boards" / b / "runs" / "*.a[0-9]")):
                rd = Path(rd)
                mid, att = rd.name.split(".")[-2], int(rd.name.split(".a")[-1])
                if mid not in ids:
                    continue
                run = json.loads((rd / "run.json").read_text())
                r = dict(cpu=(run.get("method_usage") or {}).get("cpu_s") or 0.0, run=run)
                for f in rd.glob("evals/*.json"):
                    d = json.loads(f.read_text())
                    if (d.get("score") or {}).get("valid") is not None:
                        r["s"] = d["score"]
                if "s" in r:
                    r["report"] = load_report(rd) if ids[mid] != "R" else {}
                    D[(b, att)][ids[mid]] = r
    return D


def sign_flip(xs, n=50000, seed=0):
    xs = [x for x in xs if x]
    if not xs:
        return 1.0
    rng = random.Random(seed)
    t = abs(sum(xs))
    return (1 + sum(abs(sum(x if rng.random() < 0.5 else -x for x in xs)) >= t - 1e-12 for _ in range(n))) / (n + 1)


def opens(r):
    return r["s"]["unconnected"]


def errors(r):
    return r["s"].get("errors") or 0


def placement_errors(r):
    return r["s"].get("placement_errors", 0) or 0


def window_facts(rep):
    """Window counts of one joint report, and the window phase's yield (iteration-0 opens minus the opens of the
    last kept window, before the finishing stage)."""
    its = rep.get("iterations") or []
    w = [r for r in its[1:] if "window" in r]
    seen, rep_n = set(), 0
    for r in w:
        k = tuple(sorted((r["window"].get("parts") or []))) or ("reroute",) + tuple(r["window"].get("rect") or ())
        rep_n += k in seen
        seen.add(k)
    out = collections.Counter(windows=len(w), kept=sum(1 for r in w if r.get("accepted")), repeats=rep_n)
    for r in w:
        rr = r.get("repair") or {}
        oc = rr.get("outcome") or r.get("why") or ""
        out["illegal"] += oc.startswith("illegal")
        rp = rr.get("replace") or {}
        out["home_grid_illegal"] += bool(rp.get("home_grid_illegal"))
        out["legal_by_exact"] += rp.get("legal_by") == "exact"
        out["window_s"] += r.get("seconds") or 0.0
        out["blamed_windows"] += "blame " in " ".join(r["window"].get("reasons") or [])
    out["tabu_skips"] = rep.get("tabu_skips") or 0
    for e in rep.get("evidence") or []:
        out["diagnoses"] += 1
        for k in ("congestion", "rule", "kae default", "geometry", "fixed copper", "dropped", "blamed", "undiagnosed"):
            out["ev_" + k] += e.get(k) or 0
    u0 = its[0].get("unconnected") if its else None
    last = u0
    for r in w:
        if r.get("accepted") and r.get("unconnected") is not None:
            last = r["unconnected"]
    out["yield"] = (u0 - last) if (u0 is not None and last is not None) else 0
    return out


def pair(D, a, b, metric=opens):
    """Per board: mean over seeds of d = (x_a - x_b) / (x_a + x_b + 1); totals; boards fewer / more."""
    per = collections.defaultdict(list)
    ta = tb = 0
    ca = cb = 0.0
    for (bd, _), arms in D.items():
        if a in arms and b in arms:
            x, y = metric(arms[a]), metric(arms[b])
            per[bd].append((x - y) / (x + y + 1))
            ta, tb = ta + x, tb + y
            ca, cb = ca + arms[a]["cpu"], cb + arms[b]["cpu"]
    ds = [sum(v) / len(v) for v in per.values()]
    n = len(ds)
    return dict(n=n, mean_d=sum(ds) / n if n else 0.0, p=sign_flip(ds), total_a=ta, total_b=tb,
                rel=(ta - tb) / tb if tb else 0.0, fewer=sum(d < 0 for d in ds), more=sum(d > 0 for d in ds),
                cpu_a_h=ca / 3600, cpu_b_h=cb / 3600)


def main(argv):
    looks = 4
    if "--looks" in argv:
        i = argv.index("--looks")
        looks = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    D = load(argv)
    arms = sorted({a for v in D.values() for a in v})
    print(f"experiments {', '.join(argv)}: {len({b for b, _ in D})} boards, {len(D)} board-seeds, arms {arms}")
    print("\n| arm | runs | opens | DRC errors | placement errors | cp1 | CPU h | windows | kept | repeats | illegal "
          "| home grid-illegal | exact-legal | tabu skips | diagnoses | dropped | blamed windows | yield |")
    print("|" + "---|" * 18)
    for a in ("R", "W0", "We", "Wt", "Wx", "Wall"):
        rs = [v[a] for v in D.values() if a in v]
        if not rs:
            continue
        F = collections.Counter()
        for r in rs:
            F += window_facts(r.get("report") or {})
        cp1 = sum(1 for r in rs if r["s"].get("clean"))
        print(f"| {a} | {len(rs)} | {sum(map(opens, rs))} | {sum(map(errors, rs))} | {sum(map(placement_errors, rs))} | "
              f"{cp1} | {sum(r['cpu'] for r in rs) / 3600:.1f} | {F['windows']} | {F['kept']} | {F['repeats']} | "
              f"{F['illegal']} | {F['home_grid_illegal']} | {F['legal_by_exact']} | {F['tabu_skips']} | {F['diagnoses']} | "
              f"{F['ev_dropped']} | {F['blamed_windows']} | {F['yield']} |")
    alpha = 0.05 / looks
    p = pair(D, "Wall", "R")
    if p["n"]:
        e = pair(D, "Wall", "R", errors)
        pe = pair(D, "Wall", "R", placement_errors)
        win = p["mean_d"] < 0 and p["p"] < alpha and p["rel"] <= -0.03
        lose = p["mean_d"] > 0 and p["p"] < alpha and p["rel"] >= 0.03
        guards = e["rel"] <= 0.05 and pe["rel"] <= 0.05 and p["cpu_a_h"] <= 1.10 * p["cpu_b_h"]
        print(f"\nPrimary Wall vs R: n {p['n']}, opens {p['total_a']} vs {p['total_b']} ({100 * p['rel']:+.1f} %), "
              f"{p['fewer']} fewer / {p['more']} more, mean d {p['mean_d']:+.3f}, p {p['p']:.4f} (alpha {alpha:.4f}); "
              f"DRC errors {100 * e['rel']:+.1f} %, placement errors {100 * pe['rel']:+.1f} %, "
              f"CPU {p['cpu_a_h']:.1f} vs {p['cpu_b_h']:.1f} h -> "
              + ("Wall WINS" + ("" if guards else " but a guard fails") if win else "R WINS" if lose else "UNDECIDED"))
    print("\nPer change against W0 (window yield decides; final opens reported):")
    for a in ("We", "Wt", "Wx", "Wall"):
        y = pair(D, a, "W0", lambda r: window_facts(r.get("report") or {})["yield"])
        o = pair(D, a, "W0")
        e = pair(D, a, "W0", errors)
        if not o["n"]:
            continue
        print(f"- {a}: yield {y['total_a']} vs {y['total_b']}, {y['fewer']} lower / {y['more']} higher, mean d "
              f"{y['mean_d']:+.3f}, p {y['p']:.4f}; final opens {o['total_a']} vs {o['total_b']} ({100 * o['rel']:+.1f} %, "
              f"p {o['p']:.4f}); DRC errors {100 * e['rel']:+.1f} %; CPU {o['cpu_a_h']:.1f} vs {o['cpu_b_h']:.1f} h")
    print("\nW0 against R (the comparison windows lost):")
    p = pair(D, "W0", "R")
    if p["n"]:
        print(f"- opens {p['total_a']} vs {p['total_b']} ({100 * p['rel']:+.1f} %), mean d {p['mean_d']:+.3f}, p {p['p']:.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])
