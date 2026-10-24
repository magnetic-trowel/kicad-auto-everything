# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the KiCad -> Freerouting -> KiCad bridge.

    python -m kae.route.cli route INPUT OUTPUT [--seed N] [--time S] [--workdir DIR] [--keep]
                                               [--no-repair] [--fanout | --fanout-first] [--no-thermal]
                                               [--passes N] [--rounds N] [--planes cost|keep|strict|allow]
                                               [--report FILE]

INPUT is a .kicad_pcb with its project files (.kicad_pro, .kicad_dru) beside it; OUTPUT is
written as soon as a routed board exists (kaebench scores only the board). The JSON report
goes to the last line of stdout and to --report FILE. As a kaebench method or probe:

    kaebench run --adapter kae-fr --kinds route \\
      --command "<venv>/bin/python -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout}"

Exit status: 0 when a routed board was written, 2 otherwise.
"""
import argparse
import json
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.route.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route", help="route a board through Freerouting with KiCad's rules")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--seed", type=int, default=0, help="0: KiCad's item order; others: a permuted order")
    r.add_argument("--time", type=float, default=600.0, help="total budget in seconds")
    r.add_argument("--workdir", help="keep intermediate files here (DSN, SES, DRC reports)")
    r.add_argument("--keep", action="store_true", help="keep the temporary work directory")
    r.add_argument("--no-repair", action="store_true")
    r.add_argument("--fanout", action="store_true", help="enable Freerouting's fanout pre-pass (narrows tracks)")
    r.add_argument("--fanout-first", action="store_true",
                   help="fanout for the first route only; repair rounds re-route without it")
    r.add_argument("--no-thermal", action="store_true", help="no thermal-spoke corridors in the repair loop")
    r.add_argument("--thermal-all", action="store_true", help="spoke corridors for every thermal pad up front")
    r.add_argument("--passes", type=int, default=0)
    r.add_argument("--rounds", type=int, default=5, help="repair rounds at most")
    r.add_argument("--planes", default="cost", choices=("cost", "keep", "strict", "allow"),
                   help="inner plane layers: traces there cost plane_cost x (cost), none (strict), none unless a repair"
                        " round has open connections (keep), or KiCad's layer types (allow)")
    r.add_argument("--report")
    a = ap.parse_args(argv)
    from kae.route import bridge
    opts = dict(repair=not a.no_repair, fanout=True if a.fanout else ("first" if a.fanout_first else False),
                thermal_repair=not a.no_thermal,
                passes=a.passes, rounds=a.rounds, keep=a.keep, planes=a.planes)
    if a.thermal_all:
        opts["thermal_pads"] = "all"
    try:
        rep = bridge.route(a.input, a.output, seed=a.seed, time_s=a.time, workdir=a.workdir, opts=opts)
    except Exception as e:  # report and fail cleanly; kaebench records the log
        import traceback
        traceback.print_exc()
        rep = dict(status="error", error=f"{type(e).__name__}: {e}")
    text = json.dumps(rep, default=str)
    if a.report:
        with open(a.report, "w") as f:
            f.write(text + "\n")
    print(text, flush=True)
    return 0 if rep.get("status") in ("routed", "repaired") else 2


if __name__ == "__main__":
    sys.exit(main())
