# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the critical-net router.

    python -m kae.route.critical_cli route INPUT OUTPUT [--seed N] [--time S] [--no-bridge]
                                     [--rails auto|all|none] [--kinds cell,decap,crystal,chain]
                                     [--guards cell,crystal|none] [--chain-tail] [--rail-light]
                                     [--complete-mm MM] [--island-mm MM] [--no-stitch] [--trim-tol F]
                                     [--soft complete,pad|none] [--skip ID,ID] [--planes cost|keep|strict|allow]
                                     [--rounds N]
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
    r.add_argument("--kinds", default="cell,path,decap,rgroup,crystal,chain")
    r.add_argument("--guards", default="cell,path,crystal",
                   help="modules whose ground plane the bridge must keep other nets off (or 'none')")
    r.add_argument("--chain-tail", action="store_true",
                   help="also route a protection chain's hops after the protector (default: the bridge does)")
    r.add_argument("--rail-light", action="store_true",
                   help="also route rail branches that need only the class width (default: the bridge does)")
    r.add_argument("--complete-mm", type=float, default=None,
                   help="join a rail's own pads within this reach of its critical copper (0: off)")
    r.add_argument("--island-mm", type=float, default=None,
                   help="join a rail's critical-copper islands within this reach (0: off)")
    r.add_argument("--no-stitch", action="store_true", help="no stitching vias for isolated ground-pour pieces")
    r.add_argument("--trim-tol", type=float, default=None,
                   help="narrow loop hops while the loop stays within this fraction of the wide loop (0: off)")
    r.add_argument("--soft", default=None,
                   help="joins written unlocked for Freerouting to keep or rip: complete,pad (or 'none')")
    r.add_argument("--dense-ic-pins", type=int, default=None,
                   help="ICs with at least this many pads get no ground-pin vias from the critical stage")
    r.add_argument("--skip", default="", help="comma-separated module id prefixes to leave out (diagnosis)")
    r.add_argument("--rounds", type=int, default=0, help="recheck / re-tweak rounds after the bridge")
    r.add_argument("--planes", default="cost", choices=("cost", "keep", "strict", "allow"),
                   help="the bridge's inner plane layers (kae.route.bridge DEFAULT_OPTS planes)")
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
                    chain_tail=a.chain_tail, rail_light=a.rail_light, stitch=not a.no_stitch)
        if a.complete_mm is not None:
            opts["complete_mm"] = a.complete_mm
        if a.island_mm is not None:
            opts["island_mm"] = a.island_mm
        if a.soft is not None:
            opts["soft"] = tuple(x for x in a.soft.split(",") if x and x != "none")
        if a.dense_ic_pins is not None:
            opts["dense_ic_pins"] = a.dense_ic_pins
        if a.skip:
            opts["skip"] = tuple(x for x in a.skip.split(",") if x)
        if a.trim_tol is not None:
            opts["trim_tol"] = a.trim_tol
        rep = critical.run(a.input, a.output, seed=a.seed, time_s=a.time, opts=opts, rounds=a.rounds,
                           workdir=a.workdir, bridge=not a.no_bridge, bridge_opts=dict(planes=a.planes))
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
