# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Totals and per-board rows of the native rule D entry A/B (fr_entry_ab.sh score.json files).

    python tools/research/routing/fr_entry_summary.py BOARDS_DIR ARM [ARM ...]

Per arm and stage (routed: kae.route.cli's output; rr: after pad_reroute): oblique / acute
entries, entries on the long centre line, overhanging entries, unconnected, DRC errors (and by
type), track m, vias, route seconds, and the fork's tail counts."""
import json
import sys
from collections import Counter
from pathlib import Path


def main(argv):
    root, arms = Path(argv[0]), argv[1:]
    boards = sorted(p.name for p in root.iterdir() if p.is_dir())
    rows = {}
    for arm in arms:
        tot = {s: Counter() for s in ("routed", "rr")}
        types = {s: Counter() for s in ("routed", "rr")}
        fork, n, t_route = Counter(), 0, 0.0
        for b in boards:
            f = root / b / arm / "score.json"
            if not f.exists():
                continue
            d = json.loads(f.read_text())
            n += 1
            t_route += d.get("route_s") or 0
            for k, v in (d.get("fork") or {}).items():
                if isinstance(v, int):
                    fork[k] += v
            for s in ("routed", "rr"):
                e, r = d[s]["entries"], d[s]["drc"]
                for k in ("entries", "oblique", "acute", "on_centreline", "overhanging", "vias"):
                    tot[s][k] += e.get(k, 0)
                tot[s]["track_mm"] += e.get("track_mm", 0)
                tot[s]["unconnected"] += r.get("unconnected") or 0
                tot[s]["errors"] += r.get("errors") or 0
                types[s].update(r.get("by_type") or {})
                rows.setdefault(b, {})[(arm, s)] = (e.get("oblique"), e.get("acute"), r.get("unconnected"),
                                                     r.get("errors"), round(e.get("track_mm", 0)))
        print(f"## {arm}: {n} boards, route {t_route:.0f} s; fork {dict(fork)}")
        for s in ("routed", "rr"):
            t = tot[s]
            print(f"  {s}: oblique/acute {t['oblique']}/{t['acute']}, centre line {t['on_centreline']}/{t['entries']}, "
                  f"overhanging {t['overhanging']}, unconnected {t['unconnected']}, errors {t['errors']}, "
                  f"track {t['track_mm'] / 1000:.2f} m, vias {t['vias']}; {dict(types[s])}")
    print("\n| Board | " + " | ".join(f"{a} {s}" for a in arms for s in ("routed", "rr")) + " |")
    for b in boards:
        cells = [rows.get(b, {}).get((a, s)) for a in arms for s in ("routed", "rr")]
        print(f"| {b[:30]} | " + " | ".join("-" if c is None else "{}/{} u{} e{} {}mm".format(*c) for c in cells) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
