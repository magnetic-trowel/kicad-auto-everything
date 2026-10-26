# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Routed physics of one task's boards (human reference and each router's scored board).

Same measure as tools/research/joint/joint_physics.py (the "module physics" numbers in the
joint results): the brief and place terms are built once from the route task's input (the
human placement), so module ids pair across boards; each board is measured with
kae.route.critical_recheck.board_physics (fills="kicad", fast fidelity) and summarized by
kae.joint.scorecard.physics_total (sum of min(u, 5), modules without a value at 3). Also
records each module's open hops (unrouted copper measured as a straight strip, see
critical_recheck.hop) and errors, so unrouted boards can be told apart.

Runs in a venv with the kae package (campaign.py init builds one):
  python physics_board.py --input TASK/route/input/board.kicad_pcb --board human=PATH --board arm=PATH --out OUT.json
"""
import argparse
import json
import os
import sys
import time
import traceback

os.environ.setdefault("OMP_NUM_THREADS", "1")


def measure(path, brief, terms):
    from kae.board.kicad_file import load
    from kae.joint.scorecard import physics_total
    from kae.route.critical_recheck import board_physics
    b = load(path)
    ph = board_physics(b, brief=brief, fills="kicad", terms=terms)
    mods = {k: v for k, v in ph.items() if not k.startswith("_") and isinstance(v, dict)}
    us = {k: v.get("u") for k, v in mods.items()}
    rails = [x for loads in (ph.get("_rails") or {}).values() if isinstance(loads, dict)
             for x in loads.values() if isinstance(x, (int, float))]
    pt = None
    if terms is not None:
        try:
            pt = float(terms.total({fp.uuid: (fp.x, fp.y, fp.rot, fp.side) for fp in b.footprints}))
        except Exception:  # noqa: BLE001
            pt = None
    return dict(
        physics_total=round(physics_total(us), 4),
        modules={k: dict(kind=v.get("kind"), value=v.get("value"), u=v.get("u"), open_hops=v.get("open_hops"),
                         **({"error": str(v["error"])[:300]} if v.get("error") else {})) for k, v in mods.items()},
        n_modules=len(mods), n_missing=sum(1 for u in us.values() if u is None),
        n_open=sum(1 for v in mods.values() if v.get("open_hops")),
        worst_rail_mohm=round(max(rails), 3) if rails else None, place_terms=pt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="route task input board (the human placement, no copper)")
    ap.add_argument("--board", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from kae.board.kicad_file import load
    from kae.circuit.brief import build
    from kae.place.stubs import make_terms
    t0 = time.time()
    rec = dict(boards={})
    try:
        inp = load(a.input)
        brief = build(inp)
        try:
            terms, _ = make_terms(inp, brief)
        except Exception as e:  # noqa: BLE001
            terms = None
            rec["terms_error"] = f"{type(e).__name__}: {e}"[:500]
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"[:500]
        rec["traceback"] = traceback.format_exc()[-3000:]
        brief = None
    for spec in a.board:
        name, _, path = spec.partition("=")
        if brief is None:
            break
        t1 = time.time()
        try:
            rec["boards"][name] = measure(path, brief, terms)
        except Exception as e:  # noqa: BLE001
            rec["boards"][name] = dict(error=f"{type(e).__name__}: {e}"[:500], traceback=traceback.format_exc()[-3000:])
        rec["boards"][name]["wall_s"] = round(time.time() - t1, 2)
    rec["wall_s"] = round(time.time() - t0, 2)
    with open(a.out, "w") as f:
        json.dump(rec, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
