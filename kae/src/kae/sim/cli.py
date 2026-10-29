# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae.sim command line.

    python -m kae.sim.cli testbench BOARD.kicad_pcb [--pintypes pintypes.json] [--schematic ROOT.kicad_sch] -o board.tb.cir
    python -m kae.sim.cli evaluate  BOARD.kicad_pcb --testbench board.tb.cir [--pintypes FILE] [--schematic ROOT]
                                    [--input TASK_INPUT.kicad_pcb] [--ideal-only] [-j 8] [--only ID ...]
                                    [--workdir DIR] -o eval.json
    python -m kae.sim.cli questions eval.json       # what to research: marginal, unknown, priors-only verdicts

`testbench` writes the default testbench (autotb.py) for a board. `evaluate` simulates it on BOARD's
copper (zones refilled by kicad-cli) and writes the verdicts. The brief (structures, roles) is built
from --input when given, else from BOARD, so two layouts of one task share it. pintypes.json
(tools/kaeres/pintypes.py) fills pin names and types that a board never received from its schematic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def load_board(path, pintypes=None, schematic=None):
    from kae.board.kicad_file import load
    b = load(path)
    if schematic:
        from .schematic import fields, fill_values
        fill_values(b, fields(schematic))
    if pintypes:
        refs = json.loads(Path(pintypes).read_text()).get("refs") or {}
        for fp in b.footprints:
            m = refs.get(fp.ref)
            for pad in fp.pads if m else ():
                pin = m.get(str(pad.number))
                if pin and not pad.pintype and not pad.pinfunction:
                    pad.pintype, pad.pinfunction = pin.get("type") or "", pin.get("name") or ""
    return b


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.sim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("testbench")
    a.add_argument("board")
    a.add_argument("--pintypes")
    a.add_argument("--schematic", help="root .kicad_sch: values for footprints that carry none")
    a.add_argument("-o", "--out", required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("board")
    e.add_argument("--testbench", required=True)
    e.add_argument("--pintypes")
    e.add_argument("--schematic")
    e.add_argument("--input")
    e.add_argument("--ideal-only", action="store_true")
    e.add_argument("-j", "--jobs", type=int, default=8)
    e.add_argument("--only", nargs="*")
    e.add_argument("--workdir", default="kae-sim")
    e.add_argument("-o", "--out", required=True)
    g = sub.add_parser("budgets", help="per-structure budgets from the testbench (cell: hot-loop nH)")
    g.add_argument("board")
    g.add_argument("--testbench", required=True)
    g.add_argument("--pintypes")
    g.add_argument("--schematic")
    g.add_argument("--input")
    g.add_argument("-j", "--jobs", type=int, default=8)
    g.add_argument("--workdir", default="kae-sim-budget")
    g.add_argument("-o", "--out", required=True, help="board.budgets.json")
    q = sub.add_parser("questions")
    q.add_argument("evaluation")
    a = ap.parse_args(argv)
    if a.cmd == "questions":
        from .evaluate import questions
        print(json.dumps(questions(json.loads(Path(a.evaluation).read_text())), indent=1))
        return 0

    from kae.circuit.brief import build as brief_of

    from . import design as D
    from . import testbench as TB
    if a.cmd == "testbench":
        from .autotb import generate
        b = load_board(a.board, a.pintypes, a.schematic)
        br = brief_of(b)
        tests = generate(b, br, D.build(b, br))
        sha = hashlib.sha256(Path(a.board).read_bytes()).hexdigest()
        Path(a.out).write_text(TB.render(tests, sha))
        TB.parse(Path(a.out).read_text())            # what we write must read back
        print(json.dumps(dict(tests=len(tests), unknown=sum(1 for t in tests if t.unknown), out=a.out)))
        return 0
    if a.cmd == "budgets":
        from . import budget as BG
        from .evaluate import Context
        b = load_board(a.board, a.pintypes, a.schematic)
        br = brief_of(load_board(a.input, a.pintypes, a.schematic) if a.input else b)
        tests = TB.parse(Path(a.testbench).read_text())
        ctx = Context(b, br, D.build(b, br), rb=None, workdir=a.workdir)
        bud = BG.cell_budgets(tests, ctx, jobs=a.jobs)
        for sid, x in bud.items():
            pr = BG.prior_of(br, sid)
            x["prior_nH"] = None if pr is None else round(pr, 4)
        sha = lambda f: hashlib.sha256(Path(f).read_bytes()).hexdigest()
        BG.write(bud, a.out, sha(a.board), sha(a.testbench))
        print(json.dumps({k: dict(value=v.get("value"), lenient=(v.get("detail") or {}).get("lenient_nH"),
                                  floor=(v.get("detail") or {}).get("floor_nH"), prior_nH=v["prior_nH"],
                                  status=v["status"]) for k, v in bud.items()}, indent=1))
        return 0
    from .evaluate import Context, evaluate, write
    b = load_board(a.board, a.pintypes, a.schematic)
    br = brief_of(load_board(a.input, a.pintypes, a.schematic) if a.input else b)
    tests = TB.parse(Path(a.testbench).read_text())
    rb = None
    if not a.ideal_only:
        from kae.route.critical_recheck import RoutedBoard, fills_of
        rb = RoutedBoard(b, fills=fills_of(a.board), brief=br)
    ctx = Context(b, br, D.build(b, br), rb=rb, workdir=a.workdir)
    rep = evaluate(tests, ctx, jobs=a.jobs, only=set(a.only) if a.only else None)
    rep["board"] = dict(file=a.board, sha256=hashlib.sha256(Path(a.board).read_bytes()).hexdigest())
    rep["testbench"] = dict(file=a.testbench, sha256=hashlib.sha256(Path(a.testbench).read_bytes()).hexdigest())
    rep["design_skipped"] = ctx.design.skipped
    write(rep, a.out)
    print(json.dumps(rep["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
