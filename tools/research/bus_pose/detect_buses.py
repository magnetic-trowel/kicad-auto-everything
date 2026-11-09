#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pose compiler's bus detector on corpus boards (netlist and footprint pad geometry only).

Usage: detect_buses.py IDS.txt OUT.jsonl. One JSON line per board: {id, buses: [{a, b, n, a_pads, b_pads}]}.
"""
import json, os, re, sys, traceback, warnings

warnings.simplefilter('ignore')

CORPUS = os.path.expanduser('~/kae-boards/boards')
CONN = re.compile(r'^(J|P|CN|X|CON|JP|H)\d', re.I)


def main():
    from kae.board.kicad_file import load
    from kae.place.problem import Problem
    from kae.place import buspose as BP
    with open(sys.argv[2], 'a') as out:
        for line in open(sys.argv[1]):
            bid = line.strip()
            if not bid:
                continue
            try:
                b = load(f'{CORPUS}/{bid}/board.kicad_pcb', rules=False)
                P = Problem.build(b)
                pads = {p.i: int(sum(1 for j in p.pad_net if j >= 0)) for p in P.parts}
                rows = [dict(a=P.parts[B.a].ref, b=P.parts[B.b].ref, n=B.n, a_pads=pads[B.a], b_pads=pads[B.b],
                             ic_ic=not (CONN.match(P.parts[B.a].ref) or CONN.match(P.parts[B.b].ref)))
                        for B in BP.detect(P)]
                out.write(json.dumps(dict(id=bid, buses=rows)) + '\n')
            except Exception as e:
                traceback.print_exc()
                out.write(json.dumps(dict(id=bid, error=f'{type(e).__name__}: {e}')) + '\n')
            out.flush()


if __name__ == '__main__':
    main()
