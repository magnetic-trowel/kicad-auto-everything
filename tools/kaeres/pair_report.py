#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Differential-pair report of a kaeres experiment: skew, coupled share and vias per pair (E36).

Report only: nothing here touches a score or an evaluator. Pairs that matter (kae.route.pairs tiers
rule and interface, ignoring name-only ones) are measured on each method's attempt-0 output and on the
human board; results go to experiments/<name>/pairs.csv and PAIRS.md, which `kaeres exp report`
appends to REPORT.md when present.

    python tools/kaeres/pair_report.py NAME [-j 8]     (run in a venv with the kae package)
"""
import argparse
import csv
import gzip
import json
import multiprocessing as mp
import os
import shutil
import statistics as st
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

STORE = Path(os.environ.get("KAE_RESULTS") or Path.home() / "kae-baselines")
CORPUS = Path(os.environ.get("KAE_BOARDS") or Path.home() / "kae-boards")


FIELDS = ("board", "method", "p", "n", "tier", "interface", "routed", "len_p", "len_n", "skew", "coupled_share", "vias_p", "vias_n",
          "no_ref_mm", "ref_changes")


def out_board(run_dir, tmp):
    """The run's output board, unpacked to tmp; None if there is no output."""
    gz = run_dir / "output.kicad_pcb.gz"
    if not gz.exists():
        return None
    dst = Path(tmp) / f"{run_dir.name}.kicad_pcb"
    with gzip.open(gz, "rb") as f, open(dst, "wb") as g:
        shutil.copyfileobj(f, g)
    return dst


def measure(path, brief):
    from kae.board.kicad_file import load
    from kae.route import pairs as P
    b = load(path)
    return [m for m in P.report(b, brief=brief) if m["tier"] in ("rule", "interface")]


def one_board(arg):
    bid, methods = arg
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    human = CORPUS / "boards" / bid / "board.kicad_pcb"
    out = []
    try:
        b = load(human)
    except Exception as e:  # noqa: BLE001
        return dict(board=bid, error=f"human load: {type(e).__name__}: {e}"[:200], rows=[])
    try:
        brief = build(b)
    except Exception:  # noqa: BLE001
        brief = None
    with tempfile.TemporaryDirectory(prefix="pairs-") as tmp:
        sets = [("human", human)]
        for name, mid, slug in methods:
            d = STORE / "boards" / bid / "runs" / f"{slug}.{mid[:8]}.a0"
            p = out_board(d, tmp) if d.exists() else None
            if p is not None:
                sets.append((name, p))
        for name, p in sets:
            try:
                ms = measure(p, brief)
            except Exception as e:  # noqa: BLE001
                out.append(dict(method=name, error=f"{type(e).__name__}: {e}"[:200]))
                continue
            out += [dict(board=bid, method=name, **{k: m.get(k) for k in FIELDS[2:]})
                    for m in ms]
    return dict(board=bid, rows=out)


def med(v):
    v = [x for x in v if x is not None]
    return round(st.median(v), 3) if v else None


def mean(v):
    v = [x for x in v if x is not None]
    return round(st.fmean(v), 2) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("-j", type=int, default=4)
    a = ap.parse_args()
    d = STORE / "experiments" / a.name
    exp = json.loads((d / "experiment.json").read_text())
    boards = (d / "boards.txt").read_text().split()
    methods = []
    for m in exp["methods"]:
        rec = json.loads((STORE / "methods" / f"{m['id']}.json").read_text())
        methods.append((rec["name"], rec["id"], rec["slug"]))
    with mp.Pool(a.j) as pool:
        res = pool.map(one_board, [(b, methods) for b in boards], chunksize=2)
    rows = [r for x in res for r in x["rows"] if "error" not in r]
    fields = list(FIELDS)
    with open(d / "pairs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    errs = [x for x in res if x.get("error")]
    table = pair_table(rows, ["human"] + [m[0] for m in methods])
    text = ["## Differential pairs (report-only, no effect on any score)", "",
            f"Pairs tiered rule or interface (kae.route.pairs), both legs routed. {len(boards)} boards, {len(errs)} without a human board.", ""] + table
    (d / "PAIRS.md").write_text("\n".join(text) + "\n")
    print(f"wrote {d / 'PAIRS.md'}, pairs.csv ({len(rows)} rows)")


def pair_table(rows, names):
    """Per method over all its measured pairs; a second table per method over pairs routed in every method."""
    by = defaultdict(list)
    for r in rows:
        by[r["method"]].append(r)
    out = ["| method | boards | pairs | skew med (mm) | skew p90 | coupled med | vias/pair | routed |",
           "|---|---|---|---|---|---|---|---|"]

    def line(n, sub):
        rs = [r for r in sub if r["routed"]]
        skew = sorted(r["skew"] for r in rs if r["skew"] is not None)
        p90 = skew[int(0.9 * (len(skew) - 1))] if skew else None
        return (f"| {n} | {len({r['board'] for r in sub})} | {len(sub)} | {med(skew)} | {p90} | "
                f"{med([r['coupled_share'] for r in rs])} | {mean([r['vias_p'] + r['vias_n'] for r in rs])} | {len(rs)} |")
    for n in names:
        out.append(line(n, by.get(n, [])))
    keys = set.intersection(*[{(r["board"], r["p"]) for r in by[n] if r["routed"]} for n in names if by.get(n)]) if names else set()
    out += ["", f"Over the {len(keys)} pairs routed by every method:", "", out[0], out[1]]
    for n in names:
        out.append(line(n, [r for r in by.get(n, []) if (r["board"], r["p"]) in keys]))
    return out


if __name__ == "__main__":
    sys.exit(main())
