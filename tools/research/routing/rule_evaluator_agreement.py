# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Agreement between kae.route's DRC rule evaluator and KiCad's own DRC engine.

For every board given (default: every route task with a .kicad_dru under TASKS), KiCad
exports the board with probe items (a track and a via of every net, see
kae/src/kae/board/kicad_scripts/pcbnew_bridge.py) whose constraints KiCad's engine resolves:
track width min/opt/max, via diameter and drill, annular width and the own clearance of
every pad, track and via on every copper layer. kae.route.constraints.validate evaluates
the same queries with kae.route.rules (the port of KiCad's rule engine) and counts the
answers that differ by more than 1 nm.

Usage: python -I rule_evaluator_agreement.py [--tasks DIR] [--work DIR] [BOARD ...]
Needs KiCad (pcbnew) as kae.board.pcbnew_io finds it; run with kae's venv python.
Prints one markdown row per board and the totals.
"""
import argparse
import glob
import json
import sys
import tempfile
import time
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("boards", nargs="*")
    ap.add_argument("--tasks", default="kae-work-v2/tasks")
    ap.add_argument("--work", help="keep the exported DSN and info JSON here")
    a = ap.parse_args(argv)
    from kae.board import pcbnew_io
    from kae.route import constraints

    boards = a.boards or [str(Path(p).with_suffix(".kicad_pcb"))
                          for p in sorted(glob.glob(f"{a.tasks}/*/route/input/*.kicad_dru"))]
    work = Path(a.work or tempfile.mkdtemp(prefix="rule-agreement-"))
    work.mkdir(parents=True, exist_ok=True)
    tot = dict(boards=0, checked=0, mismatched=0)
    print("| board | checks | mismatches | unsupported functions | rule errors | s |")
    print("|---|---|---|---|---|---|")
    for b in boards:
        name = Path(b).parts[-4] if len(Path(b).parts) >= 4 else Path(b).stem
        t = time.time()
        try:
            info = pcbnew_io.export_dsn(b, work / f"{name}.dsn")
        except Exception as e:  # report and go on
            print(f"| {name} | export failed: {e} | | | | |")
            continue
        (work / f"{name}.info.json").write_text(json.dumps(info))
        v = constraints.validate(info, b)
        tot["boards"] += 1
        tot["checked"] += v["checked"]
        tot["mismatched"] += v["mismatched"]
        print(f"| {name} | {v['checked']} | {v['mismatched']} | {', '.join(v['unsupported']) or '-'} "
              f"| {len(v['rule_errors'])} | {time.time() - t:.0f} |")
        for e in v["examples"][:3]:
            print(f"<!-- {e} -->")
    print(f"\nboards {tot['boards']}, checks {tot['checked']}, mismatches {tot['mismatched']}")
    return 0 if tot["mismatched"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
