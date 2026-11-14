# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convergence of the per-cell hot-loop window solve (kae.excite.hotloop) in pitch and window margin.

    hl_cell_convergence.py BOARD.kicad_pcb OPERATING.json OUT.json [--pitches 0.25 0.125 0.0625 0.03125]
                           [--margins 3 6]

For every pitch (at the default margin) and every extra margin (at the second pitch given), one evaluation of the
board (DC band off) with its cells' window solves; OUT.json holds each cell's L_loop, R_loop at f_sw, 3 f_sw and
5 f_sw, the board solve's values, the window and the seconds. Run it through kaeq (KAEQ_CPUS sets the threads).
"""
import argparse
import json
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("intent")
    ap.add_argument("out")
    ap.add_argument("--pitches", type=float, nargs="+", default=[0.25, 0.125, 0.0625, 0.03125])
    ap.add_argument("--margins", type=float, nargs="*", default=[])
    ap.add_argument("--no-skin", action="store_true")
    a = ap.parse_args(argv)
    from kae.excite import hotloop as HL
    from kae.excite.beliefs import load_intent
    from kae.excite.evaluate import evaluate
    it = load_intent(a.intent)
    runs = [(p, None) for p in a.pitches] + [(a.pitches[min(1, len(a.pitches) - 1)], m) for m in a.margins]
    out = dict(board=a.board, runs=[])
    m0, h0 = HL.MARGIN_MM, HL.MARGIN_H
    for p, m in runs:
        if m is not None:
            HL.MARGIN_MM, HL.MARGIN_H = m, 0.0
        t = time.time()
        r = evaluate(a.board, 0.25, intent=it, dc=False, cell_pitch=p, cell_skin=not a.no_skin,
                     log=lambda s: print(s, file=sys.stderr))
        HL.MARGIN_MM, HL.MARGIN_H = m0, h0
        out["runs"].append(dict(pitch=p, margin=m, seconds=round(time.time() - t, 1), cells=r["cells"]))
        json.dump(out, open(a.out, "w"), indent=1, default=float)
        for c in r["cells"]:
            print(p, m, c["source"], c["state"], c.get("L_loop_nH"), c.get("R_loop_mohm"),
                  (c.get("global") or {}).get("L_loop_nH"), (c.get("window") or {}).get("seconds"), flush=True)


if __name__ == "__main__":
    main()
