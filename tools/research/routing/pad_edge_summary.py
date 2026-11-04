# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize pad_edge_smoke.sh results: one row per board directory (before -> after).

    python3 tools/research/routing/pad_edge_summary.py DIR... [--terms]

Columns: DRC errors and unconnected (kicad-cli on the re-opened boards, trim.json), new
violations of any severity, track length, pad entries at the centre / near the edge, and
oblique (10-45 deg off the edge normal) and acute (> 45 deg) entries; with --terms, the
physics terms (kae.intent status) whose contribution changed by more than 0.05 %.
"""
import json
import sys
from pathlib import Path


def _j(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def _all_types(rep):
    out = {}
    for v in (rep or {}).get("violations", []):
        k = f"{v.get('severity')}:{v.get('type')}"
        out[k] = out.get(k, 0) + 1
    return out


def _terms(st):
    return {t["id"]: (t.get("contribution"), t.get("value")) for t in (st or {}).get("terms", []) if "contribution" in t}


def main(argv):
    terms = "--terms" in argv
    dirs = [Path(a) for a in argv if not a.startswith("--")]
    print("| board | errors | unconnected | new violations | track mm | centre/edge entries | oblique | acute | cut mm | physics total mW_eq |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    notes = []
    for d in dirs:
        tr = _j(d / "trim.json") or {}
        sb, sa = _j(d / "stats.before.json") or {}, _j(d / "stats.after.json") or {}
        di, do = tr.get("drc_in") or {}, tr.get("drc_out") or {}
        wd = d / "trim-work"
        rin = _j(wd / "in.drc.json")
        outs = sorted(wd.glob("out.r*.json"))
        rout = _j(outs[-1]) if outs and tr.get("kept") else rin
        ti, to = _all_types(rin), _all_types(rout)
        new = {k: to[k] - ti.get(k, 0) for k in to if to[k] > ti.get(k, 0)}
        pb, pa = _j(d / "phys" / "before.status.json"), _j(d / "phys" / "after.status.json")

        def tot(s):
            return sum(c for c, _ in _terms(s).values() if c is not None) if s else None
        tb, ta = tot(pb), tot(pa)
        ph = f"{tb:.1f} -> {ta:.1f}" if tb is not None and ta is not None else "-"
        print(f"| {d.name[:40]} | {di.get('errors')} -> {do.get('errors')} | {di.get('unconnected')} -> {do.get('unconnected')} "
              f"| {', '.join(f'{k} +{v}' for k, v in new.items()) or 'none'} "
              f"| {sb.get('track_mm')} -> {sa.get('track_mm')} | {sb.get('at_centre')}/{sb.get('near_edge')} -> "
              f"{sa.get('at_centre')}/{sa.get('near_edge')} | {sb.get('oblique')} -> {sa.get('oblique')} "
              f"| {sb.get('acute')} -> {sa.get('acute')} | {tr.get('cut_mm')} | {ph} |")
        if terms and pb and pa:
            a, b = _terms(pb), _terms(pa)
            for k in sorted(set(a) | set(b)):
                x, y = (a.get(k) or (None, None))[0], (b.get(k) or (None, None))[0]
                if x is None or y is None or abs(y - x) > 5e-4 * max(abs(x), 1e-9):
                    notes.append(f"{d.name[:40]} {k}: {a.get(k, (None, '-'))[1]} -> {b.get(k, (None, '-'))[1]} "
                                 f"({x} -> {y} mW_eq)")
    for n in notes:
        print("-", n)


if __name__ == "__main__":
    main(sys.argv[1:])
