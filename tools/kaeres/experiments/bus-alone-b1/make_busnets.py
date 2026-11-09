#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bus-net lists for the bus-alone experiment, from kae.bus's bare-board detector (it reads no copper).

Usage: make_busnets.py IDS_FILE OUT_DIR. Writes OUT_DIR/<id>.txt (one net per line: every lane net of every bus of width
>= 4 except keyboard matrices) and OUT_DIR/<id>.buses.json (those buses: kind, width, ends, end types, nets per lane)."""
import json
import os
import resource
import sys

from kae.board.kicad_file import load
from kae.bus import detect_board

KEEP_EV_NOT = ("matrix_lines",)     # no shared second end: not a thing to route as a bus


def main():
    ids, out = open(sys.argv[1]).read().split(), sys.argv[2]
    resource.setrlimit(resource.RLIMIT_AS, (16 * 2 ** 30, 16 * 2 ** 30))
    os.makedirs(out, exist_ok=True)
    for bid in ids:
        if os.path.exists(f"{out}/{bid}.buses.json"):
            continue
        try:
            board = load(os.path.expanduser(f"~/kae-boards/boards/{bid}/board.kicad_pcb"), rules=False)
            board.tracks, board.vias = [], []      # bare-board detection, whatever the file holds
            bs = detect_board(board)
            rows = []
            for r in bs.buses:
                if r["width"] < 4 or r["kind"] in KEEP_EV_NOT:
                    continue
                rows.append(dict(kind=r["kind"], width=r["width"], a=r.get("a"), b=r.get("b"), a_type=r.get("a_type"), b_type=r.get("b_type"),
                                 a_pitch=r.get("a_pitch"), b_pitch=r.get("b_pitch"), multi_lanes=r.get("multi_lanes"), dist=r.get("dist"),
                                 ev=r["ev"], names=r["names"], nets=r["nets"], lds=(r.get("perm") or {}).get("lds")))
            nets = sorted({n for r in rows for ns in r["nets"] for n in ns})
            with open(f"{out}/{bid}.txt", "w") as f:
                f.write("\n".join(nets) + ("\n" if nets else ""))
            with open(f"{out}/{bid}.buses.json", "w") as f:
                json.dump(dict(id=bid, n_nets=len(board.nets), buses=rows), f, separators=(",", ":"))
        except Exception as e:      # one board's failure must not stop the list
            with open(f"{out}/{bid}.buses.json", "w") as f:
                json.dump(dict(id=bid, error=repr(e)[:300]), f)
            print(bid, repr(e)[:200], flush=True)


if __name__ == "__main__":
    main()
