# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Markdown table of crit_tighten_smoke.py results: ROOT/<board>/<arm>/<arm>.json.

    python tools/research/routing/crit_tighten_summary.py ROOT
"""
import json
import sys
from pathlib import Path


def load(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def mods(r):
    return {m["id"]: m for m in r.get("modules") or [] if m.get("value") is not None}


def main(root):
    root = Path(root)
    print("| Board | Arm | Crit mm | Corners | Arcs | Kept / refused groups | DRC errors (by type) | Unconnected | s |")
    print("|---|---|---|---|---|---|---|---|---|")
    phys = []
    for b in sorted(p for p in root.iterdir() if p.is_dir()):
        rs = {arm: load(b / arm / f"{arm}.json") for arm in ("grid", "taut")}
        for arm, r in rs.items():
            if r is None:
                print(f"| {b.name[:30]} | {arm} | (missing) |||||||")
                continue
            c = r.get("crit_copper") or {}
            t = r.get("tighten") or {}
            d = r.get("drc") or {}
            by = ", ".join(f"{k} {v}" for k, v in sorted((d.get("by_type") or {}).items()))
            kr = f"{t.get('kept', '-')} / {t.get('refused', '-')}" if t else "-"
            print(f"| {b.name[:30]} | {arm} | {c.get('length_mm')} | {c.get('corners')} | {c.get('arcs')} | {kr} | "
                  f"{d.get('errors')} ({by}) | {d.get('unconnected')} | {r.get('seconds')} |")
        if rs["grid"] and rs["taut"]:
            mg, mt = mods(rs["grid"]), mods(rs["taut"])
            for k in sorted(set(mg) & set(mt)):
                a, z = mg[k]["value"], mt[k]["value"]
                if a and abs(z - a) > 1e-9:
                    phys.append((b.name[:30], k, a, z, mg[k].get("unit")))
    print("\nModules whose value differs (grid -> taut):\n")
    print("| Board | Module | Grid | Taut | Ratio |")
    print("|---|---|---|---|---|")
    for bn, k, a, z, u in phys:
        print(f"| {bn} | {k} | {a:.4g} {u} | {z:.4g} | {z / a:.3f} |")


if __name__ == "__main__":
    main(sys.argv[1])
