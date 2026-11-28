# SPDX-FileCopyrightText: 2026 HaslamPCB contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarise width_human_corpus.py output: per method and definition, the corpus mean with a board bootstrap
interval, paired against the human floor; seed-to-seed stability; sensitivity to the option sets; per suite.

    width_human_report.py DIR/rows.jsonl [--subset power] [--suites bench/suites/mech/buck.txt ...] > REPORT.md
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

DEFS = ("share", "share_x", "deficit", "share_i", "share_neck")
NAMES = {"288a499c": "bridge", "85993b60": "staged", "human": "human"}


def load(path):
    v = defaultdict(dict)      # (method, attempt, opts, subset, def) -> {board: value}
    errors = defaultdict(int)
    nets = defaultdict(int)
    for line in Path(path).read_text().splitlines():
        r = json.loads(line)
        if "error" in r:
            errors[(NAMES.get(r.get("method"), r.get("method")), r["error"].split(":")[0])] += 1
            continue
        m = NAMES.get(r["method"], r["method"])
        if r["opts"] == "d" and m == "human":
            nets["boards_with_power_nets"] += bool(r["n_ref"])
        for s, p in r["pooled"].items():
            for k in DEFS:
                if p.get(k) is not None:
                    v[(m, r["attempt"], r["opts"], s, k)][r["board"]] = p[k]
    return v, errors, nets


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def boot(xs, n=4000, seed=0):
    if len(xs) < 2:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed)
    ms = sorted(mean([rnd.choice(xs) for _ in xs]) for _ in range(n))
    return ms[int(0.025 * n)], ms[int(0.975 * n) - 1]


def spearman(a, b):
    def rank(x):
        o = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and x[o[j + 1]] == x[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2
            i = j + 1
        return r
    if len(a) < 3:
        return float("nan")
    ra, rb = rank(a), rank(b)
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def seed_mean(v, m, opts, s, k, boards=None):
    """{board: mean over attempts 0, 1} (boards with both seeds)."""
    a, b = v.get((m, 0, opts, s, k), {}), v.get((m, 1, opts, s, k), {})
    return {x: (a[x] + b[x]) / 2 for x in a if x in b and (boards is None or x in boards)}


def f(x, d=3):
    return "-" if x != x else f"{x:.{d}f}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--subset", default="power")
    ap.add_argument("--suites", nargs="*", default=[])
    a = ap.parse_args(argv)
    v, errors, nets = load(a.rows)
    s = a.subset
    out = [f"# width_human on stored runs (subset `{s}`)", ""]
    out.append(f"Boards with >= 1 power net with human track: {nets['boards_with_power_nets']}. "
               f"Errors: {dict(errors) or 'none'}.")
    out += ["", "## 1. Corpus mean, paired against the human floor (option set d, mean of seeds 0 and 1 per board)", "",
            "| method | definition | boards | mean | median | human floor | method - floor [95 % CI] |",
            "|---|---|---|---|---|---|---|"]
    for m in ("bridge", "staged"):
        for k in DEFS:
            x = seed_mean(v, m, "d", s, k)
            h = v.get(("human", 0, "d", s, k), {})
            common = [b for b in x if b in h]
            if not common:
                continue
            d = [x[b] - h[b] for b in common]
            lo, hi = boot(d)
            xs = sorted(x[b] for b in common)
            out.append(f"| {m} | {k} | {len(common)} | {f(mean(xs))} | {f(xs[len(xs) // 2])} | "
                       f"{f(mean([h[b] for b in common]))} | {f(mean(d))} [{f(lo)}, {f(hi)}] |")
    out += ["", "## 2. Stability: seed 0 vs seed 1 (Spearman across boards) and option-set sensitivity", "",
            "| method | definition | boards (both seeds) | Spearman s0-s1 | mean abs s0-s1 | "
            "mean d | tol15 - d | reach05 - d | nopour - d |", "|---|---|---|---|---|---|---|---|---|"]
    for m in ("bridge", "staged"):
        for k in DEFS:
            a0, a1 = v.get((m, 0, "d", s, k), {}), v.get((m, 1, "d", s, k), {})
            both = [b for b in a0 if b in a1]
            if not both:
                continue
            rho = spearman([a0[b] for b in both], [a1[b] for b in both])
            mad = mean([abs(a0[b] - a1[b]) for b in both])
            base = seed_mean(v, m, "d", s, k)
            sens = []
            for o in ("tol15", "reach05", "nopour"):
                y = seed_mean(v, m, o, s, k)
                c = [b for b in base if b in y]
                sens.append(f(mean([y[b] - base[b] for b in c])) if c else "-")
            out.append(f"| {m} | {k} | {len(both)} | {f(rho, 2)} | {f(mad)} | {f(mean(list(base.values())))} | "
                       + " | ".join(sens) + " |")
    out += ["", "## 3. Subsets (bridge, option set d, share_x, mean of seeds)", "",
            "| subset | boards | bridge | human floor | staged |", "|---|---|---|---|---|"]
    for sub in ("power", "power_no_gnd", "by_role", "by_width", "all"):
        x = seed_mean(v, "bridge", "d", sub, "share_x")
        h = v.get(("human", 0, "d", sub, "share_x"), {})
        st = seed_mean(v, "staged", "d", sub, "share_x")
        out.append(f"| {sub} | {len(x)} | {f(mean(list(x.values())))} | {f(mean([h[b] for b in x if b in h]))} | "
                   f"{f(mean(list(st.values())))} |")
    if a.suites:
        out += ["", "## 4. By suite (option set d, mean of seeds; bridge - floor with 95 % CI)", "",
                "| suite | definition | boards | bridge | floor | bridge - floor [CI] | staged |",
                "|---|---|---|---|---|---|---|"]
        for sf in a.suites:
            bs = {b for b in Path(sf).read_text().split() if not b.startswith("#")}
            for k in ("share_x", "share_neck", "deficit", "share_i"):
                x = seed_mean(v, "bridge", "d", s, k, bs)
                h = v.get(("human", 0, "d", s, k), {})
                c = [b for b in x if b in h]
                if not c:
                    continue
                d = [x[b] - h[b] for b in c]
                lo, hi = boot(d)
                st = seed_mean(v, "staged", "d", s, k, bs)
                out.append(f"| {Path(sf).stem} | {k} | {len(c)} | {f(mean([x[b] for b in c]))} | "
                           f"{f(mean([h[b] for b in c]))} | {f(mean(d))} [{f(lo)}, {f(hi)}] | {f(mean(list(st.values())))} |")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
