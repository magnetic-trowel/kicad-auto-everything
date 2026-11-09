# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize finish_smoke.sh results: the three gated passes chained (chain) against kae.route.finish.

    python3 tools/research/routing/finish_summary.py DIR... [--json OUT]

Per board: DRC errors/unconnected (input -> chain -> finish) and the error types that differ,
pad entries (perpendicular/oblique/acute), copper length, arcs, KiCad DRC runs and seconds per
stage; then physics totals (before, chain, finish) and the median finish/chain ratio per
observable over the boards.
"""
import json
import statistics
import sys
from pathlib import Path


def _j(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def _terms(st):
    return {t["id"]: t for t in (st or {}).get("terms", []) if t.get("contribution") is not None}


def _drc(d):
    return f"{d.get('errors')}/{d.get('unconnected')}" if d else "-"


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    dirs = [Path(a) for a in argv if not a.startswith("--") and a != out_json]
    rows = []
    print("| board | DRC err/unconn in → chain → finish | types differing (chain / finish) | entries perp/obl/acute "
          "in → chain → finish | length mm | arcs | DRC runs chain / finish | s chain (tails+taut+pc) | "
          "s finish (tails+taut+pc+gate) | finish kept/entries, noise |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for d in dirs:
        st = {t: _j(d / f"stats.{t}.json") or {} for t in ("before", "chain", "finish")}
        ct, cpc, fin = _j(d / "chain_tails.json") or {}, _j(d / "chain_pc.json") or {}, _j(d / "finish.json") or {}
        times = _j(d / "chain.times.json") or {}
        din = ct.get("drc_in") or fin.get("drc_in")
        dch, dfi = cpc.get("drc_out"), fin.get("drc_out")

        def types(x):
            if not (x and din):
                return "-"
            ks = sorted(set(x["by_type"]) | set(din["by_type"]))
            ch = [f"{k} {din['by_type'].get(k, 0)}→{x['by_type'].get(k, 0)}" for k in ks
                  if x["by_type"].get(k, 0) != din["by_type"].get(k, 0)]
            return ", ".join(ch) or "="

        def ent(t):
            x = st[t]
            return f"{x.get('perpendicular')}/{x.get('oblique')}/{x.get('acute_entries')}" if x else "-"

        def length(t):
            x = (st[t] or {}).get("length") or {}
            return f"{sum(v for v in x.values() if isinstance(v, (int, float))):.0f}" if x else "-"
        s, fs = times.get("seconds") or {}, fin.get("seconds") or {}
        row = dict(board=d.name, drc_in=din, drc_chain=dch, drc_finish=dfi, stats=st, chain_times=times,
                   finish_seconds=fs, finish_drc_runs=fin.get("drc_runs"), noise=fin.get("noise"),
                   kept=fin.get("kept"), entries=fin.get("entries"), parts=fin.get("parts"),
                   stages=fin.get("stages"))
        rows.append(row)
        print(f"| {d.name[:30]} | {_drc(din)} → {_drc(dch)} → {_drc(dfi)} | {types(dch)} / {types(dfi)} | "
              f"{ent('before')} → {ent('chain')} → {ent('finish')} | {length('before')} → {length('chain')} → "
              f"{length('finish')} | {st['chain'].get('arcs', '-')} / {st['finish'].get('arcs', '-')} | "
              f"{(times.get('drc_runs') or {}).get('total', '-')} / {fin.get('drc_runs', '-')} | "
              + (f"{s.get('total', 0):.0f} ({s.get('tails', 0):.0f}+{s.get('taut', 0):.0f}+{s.get('power', 0):.0f})"
                 if s else "-") + " | "
              + (f"{fs.get('total', 0):.0f} ({fs.get('tails', 0):.0f}+{fs.get('taut', 0):.0f}+{fs.get('power', 0):.0f}"
                 f"+{fs.get('gate', 0):.0f})" if fs else "-")
              + f" | {fin.get('kept', '-')}/{fin.get('entries', '-')}{', ' + ','.join(fin['noise']) if fin.get('noise') else ''} |")
    print()
    print("| board | physics total before | chain | finish |")
    print("|---|---|---|---|")
    ratios = {}
    for d, r in zip(dirs, rows):
        ph = {t: _j(d / "phys" / f"{t}.status.json") for t in ("before", "chain", "finish")}
        tot = {t: sum(x["contribution"] for x in _terms(ph[t]).values()) if ph[t] else None for t in ph}
        r["phys"] = tot
        print(f"| {d.name[:30]} | " + " | ".join("-" if tot[t] is None else f"{tot[t]:.1f}" for t in ph) + " |")
        tc, tf = _terms(ph["chain"]), _terms(ph["finish"])
        for k, x in tc.items():
            y = tf.get(k)
            if y is not None and x["contribution"]:
                ratios.setdefault(x["obs"], []).append(y["contribution"] / x["contribution"])
    print()
    print("| observable (terms) | finish / chain, median | min | max |")
    print("|---|---|---|---|")
    for o in sorted(ratios):
        v = ratios[o]
        print(f"| {o} ({len(v)}) | {statistics.median(v):.3f} | {min(v):.3f} | {max(v):.3f} |")
    if out_json:
        Path(out_json).write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
