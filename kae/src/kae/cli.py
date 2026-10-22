# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae command line.

    kae place INPUT OUTPUT [--seed N] [--time S] [--no-physics] [--workers W] [--writer auto|pcbnew|sexpr]
                           [--edge-mate] [--report FILE]
    kae brief INPUT [--out FILE]

`kae place` reads INPUT (.kicad_pcb with its project files beside it), places every unlocked
footprint (locked ones stay; sides are kept) and writes OUTPUT; a JSON report goes to
stdout (and to --report FILE). As a kaebench method:

    kaebench run --adapter kae --kinds place --probe freerouting \\
      --command "<venv>/bin/python -m kae.cli place {input} {output} --seed {attempt} --time {timeout}"

Exit status: 0 when the placement passed the exact legality check, 3 when an output was
written but violations remain (listed in the report), 2 on errors.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _log(msg):
    print(f"[kae {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def cmd_place(a):
    from kae.board.kicad_file import load
    from kae.place.pipeline import place
    from kae.place.writer import write
    t0 = time.monotonic()
    board = load(a.input)
    _log(f"loaded {a.input}: {len(board.footprints)} footprints ({time.monotonic() - t0:.2f}s)")
    res = place(board, seed=a.seed, time_s=a.time, physics=not a.no_physics, workers=a.workers, log=_log,
                anneal=not a.no_anneal, edge_mate=a.edge_mate)
    t1 = time.monotonic()
    wrep = write(a.input, a.output, res.poses, mode=a.writer, log=_log) if res.poses else None
    if wrep is None:
        import shutil
        shutil.copy2(a.input, a.output)
        wrep = dict(writer="copy", moved=0)
    res.report["writer"] = wrep
    res.report["write_s"] = round(time.monotonic() - t1, 2)
    res.report["total_s"] = round(time.monotonic() - t0, 2)
    legal = res.report.get("legal_grid") and not res.report.get("exact") and not res.report.get("outline_incomplete")
    res.report["legal"] = bool(legal)
    text = json.dumps(res.report, default=str)
    print(text, flush=True)
    if a.report:
        Path(a.report).write_text(json.dumps(res.report, indent=1, default=str))
    _log(f"wrote {a.output} with {wrep.get('writer')} in {res.report['total_s']}s; legal={legal}")
    return 0 if legal else 3


def cmd_brief(a):
    from kae.board.kicad_file import load
    board = load(a.input)
    try:
        from kae.circuit.brief import build
    except ImportError:
        from kae.place.stubs import stub_brief as build
    b = build(board)
    text = json.dumps(b, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae", description="Physics-first placement and routing for KiCad boards")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("place", help="place the unlocked footprints of a board")
    sp.add_argument("input")
    sp.add_argument("output")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--time", type=float, default=300.0, help="wall-clock seconds the caller allows")
    sp.add_argument("--no-physics", action="store_true", help="routability and legality only (ablation)")
    sp.add_argument("--no-anneal", action="store_true", help="seed and legalize only")
    sp.add_argument("--workers", type=int, default=None, help="CP-SAT threads (default: KAE_WORKERS or cores/2)")
    sp.add_argument("--writer", default="auto", choices=("auto", "pcbnew", "sexpr"))
    sp.add_argument("--edge-mate", action="store_true",
                    help="place staged footprints that carry Edge.Cuts where their open pieces close the "
                         "outline exactly (default: hold them and flag outline_incomplete)")
    sp.add_argument("--report", help="also write the JSON report here")
    sp.set_defaults(fn=cmd_place)
    sb = sub.add_parser("brief", help="print the physics brief of a board")
    sb.add_argument("input")
    sb.add_argument("--out")
    sb.set_defaults(fn=cmd_brief)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except Exception as e:  # report and fail
        import traceback
        traceback.print_exc()
        _log(f"error: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
