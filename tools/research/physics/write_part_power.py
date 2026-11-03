# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Each part's sustained dissipation, from an evaluation of the board, into its operating facts: the placer's
pull towards cooling reads parts.<ref>.P_sustained_W and does not recompute rail voltages.

    python write_part_power.py EV.json OPERATING.json [-o OUT.json] [--min-W 0.001]

EV.json is kae.excite.evaluate's output (part_power_W: W at the typical point: a converter's or regulator's
loss, a load's sustained draw turned into heat, a lumped part's DC loss). Dissipation barely depends on the
layout, so the human layout's evaluation serves every placement of the board.
"""
import argparse
import json
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ev"), ap.add_argument("operating")
    ap.add_argument("-o", "--out", help="output (default: rewrite OPERATING.json)")
    ap.add_argument("--min-W", type=float, default=0.001, help="leave out parts below this (W)")
    a = ap.parse_args(argv)
    ev, op = json.load(open(a.ev)), json.load(open(a.operating))
    power = ev.get("part_power_W")
    if power is None:
        sys.exit(f"{a.ev}: no part_power_W (an evaluation from before it existed, or without a DC band)")
    why = op.setdefault("provenance", {}).setdefault("why", {})
    n = 0
    for ref, w in sorted(power.items()):
        if w >= a.min_W:
            op.setdefault("parts", {}).setdefault(ref, {})["P_sustained_W"] = round(w, 4)
            why[f"parts.{ref}.P_sustained_W"] = f"kae.excite.evaluate at the typical point on {ev.get('board')}"
            n += 1
    json.dump(op, open(a.out or a.operating, "w"), indent=1)
    print(f"{n} parts with P_sustained_W (of {len(power)} dissipating) -> {a.out or a.operating}")


if __name__ == "__main__":
    sys.exit(main())
