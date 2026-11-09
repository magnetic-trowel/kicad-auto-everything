#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read a loop-window-bench experiment: paired arm tables and the window budget curve (see PLAN.md).

    python3 analyze.py EXPERIMENT [RESULTS_DIR]        # RESULTS_DIR defaults to ~/kae-baselines

Scores come from the runs' DRC evaluations (KiCad on the re-opened board), loop facts from the JSON report the run
printed (adapter.log.gz). Pairs: each arm against its control, on the boards both arms ran.
"""
import collections
import glob
import gzip
import json
import random
import statistics as st
import sys
from pathlib import Path

PAIRS = [("j2", "ctl"), ("j5", "ctl"), ("j14", "ctl"), ("w2 j3", "w2 ctl"), ("w2 j4t", "w2 ctl"), ("w2 j4", "w2 ctl"),
         ("w2 all", "w2 ctl"), ("w2 ctl", "ctl")]
CURVE_B = (0.5, 1, 2, 4)


def arm_of(name):
    """'kae wb w2 j4t abc1234' -> 'w2 j4t'."""
    return " ".join(name.split()[2:-1])


def load_report(rd):
    t = gzip.open(rd / "adapter.log.gz").read().decode("utf8", "replace")
    i = t.find('{"seed"')
    try:
        return json.JSONDecoder().raw_decode(t[i:])[0] if i >= 0 else {}
    except ValueError:
        return {}


def load(exp, base):
    e = json.loads((base / "experiments" / exp / "experiment.json").read_text())
    want = {m["id"][:8]: arm_of(m["name"]) for m in e["methods"]}
    out = collections.defaultdict(dict)
    for b in (base / "experiments" / exp / "boards.txt").read_text().split():
        for rd in glob.glob(str(base / "boards" / b / "runs" / "kae-wb-*")):
            rd = Path(rd)
            mid = rd.name.split(".")[-2]
            if mid not in want or not rd.name.endswith(".a0"):
                continue
            score = None
            for f in rd.glob("evals/*.json"):
                d = json.loads(f.read_text())
                if d.get("score", {}).get("valid") is not None:
                    score = d["score"]
            run = json.loads((rd / "run.json").read_text())
            if score:
                out[b][want[mid]] = dict(score=score, run=run, report=load_report(rd))
    return out


def windows(rep):
    return [r for r in (rep.get("iterations") or [])[1:] if "window" in r]


def facts(r):
    w = windows(r["report"])
    outcome = collections.Counter((x.get("repair") or {}).get("outcome") or "routed" for x in w)
    ill = sum(v for k, v in outcome.items() if k.startswith("illegal"))
    return dict(windows=len(w), kept=sum(1 for x in w if x.get("accepted")), illegal=ill,
                cpu=(r["run"].get("method_usage") or {}).get("cpu_s") or 0.0, stop=(r["report"].get("stop") or "")[:24])


def sign_flip(ds, n=20000, seed=0):
    """Two-sided p of the mean of per-board values under random sign flips."""
    ds = [d for d in ds if d]
    if not ds:
        return 1.0
    obs = abs(sum(ds))
    rng = random.Random(seed)
    return (1 + sum(abs(sum(d if rng.random() < 0.5 else -d for d in ds)) >= obs - 1e-12 for _ in range(n))) / (n + 1)


def pair_table(data):
    print("| arm vs control | n | cp1 | completion | opens | errors | fewer/more opens | mean d, p | windows | kept | illegal | CPU h |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for a, c in PAIRS:
        both = [b for b, d in data.items() if a in d and c in d]
        if not both:
            continue
        s = lambda arm, k: [data[b][arm]["score"].get(k) or 0 for b in both]
        fa = [facts(data[b][a]) for b in both]
        fc = [facts(data[b][c]) for b in both]
        oa, oc = s(a, "unconnected"), s(c, "unconnected")
        d = [(x - y) / (x + y + 1) for x, y in zip(oa, oc)]
        print(f"| {a} vs {c} | {len(both)} | {sum(s(a, 'clean')) / len(both):.3f} / {sum(s(c, 'clean')) / len(both):.3f} "
              f"| {st.mean(s(a, 'completion')):.3f} / {st.mean(s(c, 'completion')):.3f} | {sum(oa)} / {sum(oc)} "
              f"| {sum(s(a, 'errors'))} / {sum(s(c, 'errors'))} | {sum(x < y for x, y in zip(oa, oc))} / {sum(x > y for x, y in zip(oa, oc))} "
              f"| {st.mean(d):+.3f}, {sign_flip(d):.3f} | {sum(x['windows'] for x in fa)} / {sum(x['windows'] for x in fc)} "
              f"| {sum(x['kept'] for x in fa)} / {sum(x['kept'] for x in fc)} | {sum(x['illegal'] for x in fa)} / {sum(x['illegal'] for x in fc)} "
              f"| {sum(x['cpu'] for x in fa) / 3600:.1f} / {sum(x['cpu'] for x in fc) / 3600:.1f} |")


def types_table(data):
    arms = sorted({a for d in data.values() for a in d})
    tot = {a: collections.Counter() for a in arms}
    for d in data.values():
        for a, r in d.items():
            tot[a].update(r["score"].get("errors_by_type") or {})
    keys = sorted({k for c in tot.values() for k in c}, key=lambda k: -sum(c[k] for c in tot.values()))
    print("\n| DRC type | " + " | ".join(arms) + " |\n|---|" + "---|" * len(arms))
    for k in keys:
        print(f"| {k} | " + " | ".join(str(tot[a][k]) for a in arms) + " |")


def curve(data, arm="w4 all"):
    """Opens of the incumbent after B x (0.5, 1, 2, 4) seconds of windows, per board, from the iterations' seconds."""
    rows = collections.defaultdict(list)
    for d in data.values():
        if arm not in d:
            continue
        rep = d[arm]["report"]
        its = rep.get("iterations") or []
        if not its:
            continue
        B, spent, cur = float(rep["time_s"]), 0.0, its[0].get("unconnected") or 0
        start, trace = cur, []
        for r in its[1:]:
            if "window" not in r:
                continue
            spent += r.get("seconds") or 0.0
            if r.get("accepted") and r.get("unconnected") is not None:
                cur = r["unconnected"]
            trace.append((spent, cur))
        for f in CURVE_B:
            rows[f].append(start - next((c for t, c in reversed(trace) if t <= f * B), start))
    print(f"\nWindow budget curve ({arm}): opens removed by windows alone, before the finish")
    print("| window time (x B) | boards | median removed | mean removed | total removed |\n|---|---|---|---|---|")
    for f in CURVE_B:
        v = rows[f]
        if v:
            print(f"| {f} | {len(v)} | {st.median(v):.1f} | {st.mean(v):.2f} | {sum(v)} |")


def main():
    exp = sys.argv[1]
    base = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else Path.home() / "kae-baselines"
    data = load(exp, base)
    print(f"{exp}: {len(data)} boards with results; arms per board {collections.Counter(len(d) for d in data.values())}\n")
    pair_table(data)
    types_table(data)
    curve(data)


if __name__ == "__main__":
    main()
