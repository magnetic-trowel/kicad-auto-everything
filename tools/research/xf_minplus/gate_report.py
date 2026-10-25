# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize validate.py rows: Spearman rho of predictor vs re-routed cost per board and
pooled; 'within' = mean rho over the candidate poses of one part (the ranking a best
response actually uses).   python gate_report.py ROWS.jsonl... [--target cost|pcost]"""
import json
import sys

import numpy as np
from scipy.stats import spearmanr

PRED = ("hpwl", "jc", "mp")


def within(rows, k, target):
    by = {}
    for x in rows:
        by.setdefault((x["tag"], x["beta"], x["part"]), []).append(x)
    out = []
    for v in by.values():
        if len(v) >= 4 and len({y[target] for y in v}) > 1 and len({y[k] for y in v}) > 1:
            out.append(spearmanr([y[k] for y in v], [y[target] for y in v])[0])
    return float(np.nanmean(out)) if out else float("nan"), len(out)


def paired(rows, target, a="mp", b="hpwl", nboot=2000, seed=0):
    """Mean over parts of within-part rho(a) - rho(b), bootstrap 95% CI; and mean argmin
    regret (target cost of the predictor's pick minus the part's best candidate)."""
    by = {}
    for x in rows:
        by.setdefault((x["tag"], x["beta"], x["part"]), []).append(x)
    d, reg = [], {k: [] for k in PRED}
    for v in by.values():
        if len(v) < 4 or len({y[target] for y in v}) < 2:
            continue
        best = min(y[target] for y in v)
        for k in PRED:
            reg[k].append(min(v, key=lambda y: y[k])[target] - best)
        if len({y[a] for y in v}) > 1 and len({y[b] for y in v}) > 1:
            ra = spearmanr([y[a] for y in v], [y[target] for y in v])[0]
            rb = spearmanr([y[b] for y in v], [y[target] for y in v])[0]
            if np.isfinite(ra) and np.isfinite(rb):
                d.append(ra - rb)
    d = np.array(d)
    rng = np.random.default_rng(seed)
    bs = [rng.choice(d, len(d)).mean() for _ in range(nboot)] if len(d) else [np.nan]
    return len(d), d.mean() if len(d) else np.nan, np.percentile(bs, 2.5), np.percentile(bs, 97.5), \
        {k: float(np.mean(v)) for k, v in reg.items()}


def line(name, rows, target):
    cells = [name, str(len(rows))]
    for kind in ("all", "local", "global"):
        sel = [x for x in rows if kind == "all" or x["kind"] == kind]
        for k in PRED:
            p = spearmanr([x[k] for x in sel], [x[target] for x in sel])[0] if len(sel) > 4 else float("nan")
            w, n = within(sel, k, target)
            cells.append(f"{p:.2f} / {w:.2f}")
    return "| " + " | ".join(cells) + " |"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = "pcost" if "--target=pcost" in sys.argv else "cost"
    rows = []
    for f in args:
        rows += [json.loads(s) for s in open(f) if s.strip()]
    hdr = ["board", "moves"] + [f"{kd} {k}" for kd in ("all", "local", "global") for k in PRED]
    print(f"target={target}; cells: pooled rho / mean within-part rho")
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for b in sorted({x["tag"] for x in rows}):
        print(line(b[:40], [x for x in rows if x["tag"] == b], target))
    print(line("ALL", rows, target))
    for beta in sorted({x["beta"] for x in rows}):
        print(line(f"ALL beta={beta}", [x for x in rows if x["beta"] == beta], target))
    n, m, lo, hi, reg = paired(rows, target)
    print(f"\nwithin-part rho, min-plus minus HPWL, over {n} parts: {m:+.3f} (95% CI {lo:+.3f} to {hi:+.3f})")
    n, m, lo, hi, _ = paired(rows, target, b="jc")
    print(f"within-part rho, min-plus minus jc term, over {n} parts: {m:+.3f} (95% CI {lo:+.3f} to {hi:+.3f})")
    print("argmin regret (target units, mean over parts): " + ", ".join(f"{k} {v:.2f}" for k, v in reg.items()))


if __name__ == "__main__":
    main()
