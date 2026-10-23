# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the critical-net router.

    python -m kae.route.critical_cli route INPUT OUTPUT [--seed N] [--time S] [--no-bridge]
                                     [--rails auto|all|none] [--kinds cell,decap,crystal,chain]
                                     [--guards cell,crystal|none] [--no-chain-tail] [--rounds N]
                                     [--workdir DIR] [--keep] [--report FILE]
    python -m kae.route.critical_cli physics BOARD [--brief FILE]

`route` routes the critical copper of INPUT (a placed .kicad_pcb with its project files
beside it), locks it, lets the Freerouting bridge route everything else around it, runs
`--rounds` recheck / re-tweak rounds, and writes OUTPUT = INPUT + routing. The JSON report
is the last line of stdout. As a kaebench method:

    kaebench run --adapter kae-crit --kinds route \\
      --command "<venv>/bin/python -m kae.route.critical_cli route {input} {output} --seed {attempt} --time {timeout}"

`physics` prints the routed physics of a finished board's modules (critical_recheck).
Exit status: 0 when an output was written, 2 otherwise.
"""
import argparse
import json
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.route.critical_cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route", help="critical copper, then the bridge, then recheck")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--time", type=float, default=900.0)
    r.add_argument("--no-bridge", action="store_true", help="critical copper only")
    r.add_argument("--rails", default="auto", choices=("auto", "all", "none"))
    r.add_argument("--kinds", default="cell,decap,crystal,chain")
    r.add_argument("--guards", default="cell,crystal",
                   help="modules whose ground plane the bridge must keep other nets off (or 'none')")
    r.add_argument("--no-chain-tail", action="store_true",
                   help="leave a protection chain's hops after the protector to the bridge")
    r.add_argument("--rounds", type=int, default=0, help="recheck / re-tweak rounds after the bridge")
    r.add_argument("--workdir")
    r.add_argument("--keep", action="store_true")
    r.add_argument("--report")
    p = sub.add_parser("physics", help="routed physics of a finished board's modules")
    p.add_argument("board")
    p.add_argument("--brief")
    a = ap.parse_args(argv)
    from kae.cli import _numba_cache
    _numba_cache()
    if a.cmd == "route":
        from kae.route import critical
        opts = dict(rails=a.rails, kinds=tuple(k for k in a.kinds.split(",") if k), keep=a.keep,
                    guards=tuple(k for k in a.guards.split(",") if k and k != "none"),
                    chain_tail=not a.no_chain_tail)
        rep = critical.run(a.input, a.output, seed=a.seed, time_s=a.time, opts=opts, rounds=a.rounds,
                           workdir=a.workdir, bridge=not a.no_bridge)
        text = json.dumps(rep, default=str)
        if a.report:
            with open(a.report, "w") as f:
                f.write(text + "\n")
        print(text, flush=True)
        return 0 if rep.get("status") == "ok" else 2
    if a.cmd == "physics":
        from kae.route.critical_recheck import board_physics
        brief = json.load(open(a.brief)) if a.brief else None
        print(json.dumps(board_physics(a.board, brief=brief), default=str), flush=True)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
