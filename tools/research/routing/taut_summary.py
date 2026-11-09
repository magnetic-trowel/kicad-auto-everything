# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Summarize taut_smoke.sh results: one row per board, input -> taut -> taut + power copper.

    python3 tools/research/routing/taut_summary.py DIR... [--terms] [--json OUT]

Tables: DRC (errors, unconnected), track length per class (signal, power, ground), corners and
acute corners, arcs, pad entries (perpendicular / oblique / acute), runtime; physics total and
the median ratio per observable over the boards (--terms: every term that moved > 0.05 %).
"""
import json
import statistics
import sys
from pathlib import Path

TAGS = ("before", "taut", "tautpc", "pc")


def _j(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def _terms(st):
    return {t["id"]: t for t in (st or {}).get("terms", []) if t.get("contribution") is not None}


def main(argv):
    terms = "--terms" in argv
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    dirs = [Path(a) for a in argv if not a.startswith("--") and a != out_json]
    rows = []
    for d in dirs:
        st = {t: _j(d / f"stats.{t}.json") for t in TAGS}
        tr, pc, pin = _j(d / "taut.json") or {}, _j(d / "pc.json") or {}, _j(d / "pcin.json") or {}
        ph = {t: _j(d / "phys" / f"{t}.status.json") for t in TAGS}
        times = {}
        try:
            parts = (d / "times.txt").read_text().split()
            times = {parts[i]: float(parts[i + 1]) for i in range(0, len(parts) - 1, 2)}
        except (OSError, ValueError, IndexError):
            pass
        rows.append(dict(board=d.name, stats=st, taut=tr, pc=pc, pcin=pin, phys=ph, times=times))
    print("| board | DRC err/unconn: in -> taut -> taut+pc | signal mm | power mm | ground mm | corners | acute | arcs | entries perp/obl/acute | taut s | pc s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        s = r["stats"]
        if not s["before"]:
            continue

        def f(k, sub=None):
            v = [((s[t] or {}).get(k) or {}).get(sub) if sub else (s[t] or {}).get(k) for t in ("before", "taut", "tautpc")]
            return " → ".join("-" if x is None else (f"{x:.0f}" if isinstance(x, float) else str(x)) for x in v)

        def drc(d):
            return f"{d.get('errors')}/{d.get('unconnected')}" if d else "-"

        def ent(t):
            x = s[t] or {}
            return f"{x.get('perpendicular')}/{x.get('oblique')}/{x.get('acute_entries')}"
        print(f"| {r['board'][:34]} | {drc(r['taut'].get('drc_in'))} → {drc(r['taut'].get('drc_out'))} → "
              f"{drc(r['pc'].get('drc_out'))} | {f('length', 'signal')} | {f('length', 'power')} | {f('length', 'ground')} "
              f"| {f('corners')} | {f('acute')} | {f('arcs')} | {ent('before')} → {ent('taut')} | "
              f"{r['times'].get('taut_s', '-')} | {r['times'].get('pc_s', '-')} |")
    # physics
    print()
    print("| board | physics total before | taut | taut+pc | pc only |")
    print("|---|---|---|---|---|")
    ratios = {"taut": {}, "tautpc": {}, "pc": {}}
    notes = []
    for r in rows:
        tb = _terms(r["phys"]["before"])
        if not tb:
            continue
        tot = {t: sum(x["contribution"] for x in _terms(r["phys"][t]).values()) if r["phys"][t] else None for t in TAGS}
        print(f"| {r['board'][:34]} | " + " | ".join("-" if tot[t] is None else f"{tot[t]:.1f}" for t in TAGS) + " |")
        for t in ("taut", "tautpc", "pc"):
            ta = _terms(r["phys"][t])
            for k, x in tb.items():
                y = ta.get(k)
                if y is None or not x["contribution"]:
                    continue
                ratios[t].setdefault(x["obs"], []).append(y["contribution"] / x["contribution"])
                if terms and abs(y["contribution"] - x["contribution"]) > 5e-4 * abs(x["contribution"]):
                    notes.append(f"{r['board'][:30]} {t} {k} {x['obs']}: {x.get('value')} -> {y.get('value')}")
    print()
    print("| observable (terms) | taut | taut+pc | pc only |")
    print("|---|---|---|---|")
    obs = sorted(set().union(*[set(v) for v in ratios.values()]))
    for o in obs:
        cells = []
        for t in ("taut", "tautpc", "pc"):
            v = ratios[t].get(o)
            cells.append(f"{statistics.median(v):.3f} ({len(v)})" if v else "-")
        print(f"| {o} | " + " | ".join(cells) + " |")
    for n in notes:
        print("-", n)
    if out_json:
        Path(out_json).write_text(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
