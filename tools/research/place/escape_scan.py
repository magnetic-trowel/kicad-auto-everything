# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape bands (kae.place.escape_band.bands) on each board of a list, with the placer's own net kinds.

    python escape_scan.py BOARDS.txt CORPUS_DIR OUT.json      (CORPUS_DIR/<id>/board.kicad_pcb)
"""
import json, sys
from kae.board.kicad_file import load
from kae.place.problem import Problem
from kae.place import escape_band as EB
out = {}
for bid in open(sys.argv[1]).read().split():
    try:
        P = Problem.build(load(f"{sys.argv[2]}/{bid}/board.kicad_pcb"))
        _, rows = EB.bands(P)
    except Exception as e:
        out[bid] = dict(error=repr(e)[:120]); continue
    if rows:
        out[bid] = dict(n_fp=len(P.parts), rows=rows)
json.dump(out, open(sys.argv[3], "w"), indent=1)
