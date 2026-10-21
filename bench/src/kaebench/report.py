# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate attempt results into leaderboard tables (@1 and best-of-k)."""
import json
import statistics
from collections import defaultdict
from pathlib import Path

from .score import place_potential, potential


def load_rows(run_dir):
    """Read every attempt.json under a run (works for interrupted runs too)."""
    return [json.loads(p.read_text()) for p in sorted(Path(run_dir).glob("*/*/*/attempt-*/attempt.json"))]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 3) if xs else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def _route_best(attempts):
    return max(attempts, key=lambda r: potential(r.get("score")))


def _place_best(attempts):
    return max(attempts, key=lambda r: place_potential(r.get("score"), (r.get("probe") or {}).get("score")))


def summarize(rows):
    """Return {(adapter, kind, split): metrics} including an 'all' split."""
    by_board = defaultdict(list)
    for r in rows:
        by_board[(r["adapter"], r["kind"], r["id"], r["split"])].append(r)
    groups = defaultdict(list)
    for (adapter, kind, bid, split), atts in by_board.items():
        atts.sort(key=lambda r: r["attempt"])
        for sp in (split, "all"):
            groups[(adapter, kind, sp)].append(atts)
    out = {}
    for key, boards in sorted(groups.items()):
        adapter, kind, split = key
        first = [b[0] for b in boards]
        k = max(len(b) for b in boards)
        m = dict(boards=len(boards), k=k,
                 failures=sum(1 for b in boards for r in b if r["status"] != "ok"),
                 time_s=_mean([r.get("runtime_s") for b in boards for r in b]))
        if kind == "route":
            best = [_route_best(b) for b in boards]
            sc1 = [r.get("score") or {} for r in first]
            sck = [r.get("score") or {} for r in best]
            m.update(cp1=_mean([1.0 if s.get("clean") else 0.0 for s in sc1]),
                     cpk=_mean([1.0 if s.get("clean") else 0.0 for s in sck]),
                     completion=_mean([s.get("completion", 0.0) for s in sck]),
                     errors=_mean([s.get("errors") for s in sck]),
                     invalid=sum(1 for s in sck if s and not s.get("valid")),
                     wl_ratio=_median([s.get("wl_ratio") for s in sck]),
                     via_delta=_mean([s.get("via_delta") for s in sck]))
        else:
            best = [_place_best(b) for b in boards]
            sck = [r.get("score") or {} for r in best]
            prb = [((r.get("probe") or {}).get("score")) or {} for r in best]
            m.update(legal=_mean([1.0 if s.get("legal") else 0.0 for s in sck]),
                     hpwl_ratio=_median([s.get("hpwl_ratio") for s in sck]),
                     outside=_mean([s.get("outside") for s in sck]),
                     probe_cp=_mean([1.0 if p.get("clean") else 0.0 for p in prb]) if any(prb) else None,
                     probe_completion=_mean([p.get("completion", 0.0) for p in prb]) if any(prb) else None)
        out[key] = m
    return out


ROUTE_COLS = ("adapter", "split", "boards", "k", "cp1", "cpk", "completion", "errors", "invalid",
              "wl_ratio", "via_delta", "time_s", "failures")
PLACE_COLS = ("adapter", "split", "boards", "k", "legal", "hpwl_ratio", "outside", "probe_cp",
              "probe_completion", "time_s", "failures")


def to_markdown(summary):
    lines = []
    for kind, cols in (("route", ROUTE_COLS), ("place", PLACE_COLS)):
        rows = [(key, m) for key, m in summary.items() if key[1] == kind]
        if not rows:
            continue
        lines.append(f"### {kind}\n")
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for (adapter, _, split), m in rows:
            vals = dict(m, adapter=adapter, split=split)
            lines.append("| " + " | ".join("" if vals.get(c) is None else str(vals.get(c)) for c in cols) + " |")
        lines.append("")
    lines.append("cp1/cpk: clean pass on attempt 0 / best of k (fully connected, no error-level DRC, "
                 "placement and nets untouched). completion: share of start-of-task unconnected items "
                 "routed. wl_ratio: track length / human. Scored by kicad-cli on re-opened boards.")
    return "\n".join(lines)


def report(run_dirs):
    rows = []
    for d in run_dirs:
        rows.extend(load_rows(d))
    return summarize(rows), rows
