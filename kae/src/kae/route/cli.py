# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the KiCad -> Freerouting -> KiCad bridge.

    python -m kae.route.cli route INPUT OUTPUT [--seed N] [--time S] [--workdir DIR] [--keep]
                                               [--no-repair] [--fanout | --fanout-first] [--no-thermal]
                                               [--passes N] [--rounds N|auto] [--router-share F|auto]
                                               [--planes cost|keep|strict|allow] [--pad-shapes kicad|outside]
                                               [--[no-]last-mile] [--[no-]blocked] [--[no-]finish] [--report FILE]
    python -m kae.route.cli lastmile INPUT BOARD OUTPUT [--seed N] [--time S] [--workdir DIR] [--keep]
                                               [--set KEY=VALUE] [--report FILE]
    python -m kae.route.cli finish INPUT BOARD OUTPUT [--time S] [--parts tails,taut,power] [--input-drc FILE]
                                               [--set KEY=VALUE] [--report FILE]

INPUT is a .kicad_pcb with its project files (.kicad_pro, .kicad_dru) beside it; OUTPUT is
written as soon as a routed board exists (kaebench scores only the board). The JSON report
goes to the last line of stdout and to --report FILE. As a kaebench method or probe:

    kaebench run --adapter kae-fr --kinds route \\
      --command "<venv>/bin/python -m kae.route.cli route {input} {output} --seed {attempt} --time {timeout}"

When connections stay open, the report's "blocked" section says why, per connection: congestion
(a path exists without our other copper), the input's own copper, or the board rule that makes
it impossible, with the value required and the value available, where, and the rule's source
(.kicad_pro net class or board setup, .kicad_dru rule, footprint, rule area) or the kae default
and its override (KAE_<NAME> text variable, --set). The router never relaxes a rule itself;
"blocked" is for the caller to decide (change the rule, move a part, or accept). The same
lines go to the log as "blocked: ...". `python -m kae.route.blocked ROUTED INPUT` runs the
diagnosis alone on any routed board.

`lastmile` is the post-route stage alone (bridge.last_mile_only): BOARD, routed from the task
INPUT, gets the last mile with INPUT's rules; OUTPUT is BOARD or a round KiCad's DRC finds better.

`finish` is stage 7 alone (kae.route.finish): BOARD gets rule D tails, taut arcs and power copper
behind one journaled KiCad DRC gate with INPUT's rules; OUTPUT is never worse than BOARD. --set
takes finish options (zone_above_a, drc_budget, ...); --input-drc a DRC report of BOARD to reuse.

The report ends with "hazards" and "hazard_summary" (kae.hazards): among them a recheck of
OUTPUT with the safety checks forced on whatever the project's severities say (--recheck,
kae.board_hazards). Exit status: 0 when a routed board was written, 2 otherwise.
"""
import argparse
import json
import sys
import time


# the router keeps its own budget (--time); the recheck may run this much past it (a kaebench
# --command method gets the attempt's timeout as --time, and the board is written by then)
RECHECK_GRACE_S = 0.0


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
    r.add_argument("--rounds", default="5",
                   help="repair rounds at most, or 'auto' (until two rounds in a row are not better, or the time)")
    r.add_argument("--router-share", default="0.6",
                   help="share of the budget for the first routing, or 'auto' (0.6 up to 1,500 s, then all but"
                        " 600 s: the router stops by itself and the repair rounds get the rest)")
    r.add_argument("--planes", default="cost", choices=("cost", "keep", "strict", "allow"),
                   help="inner plane layers: traces there cost plane_cost x (cost), none (strict), none unless a repair"
                        " round has open connections (keep), or KiCad's layer types (allow)")
    r.add_argument("--pad-shapes", default="kicad", choices=("kicad", "outside"),
                   help="pin polygons in the DSN: KiCad's (arc chords inside the pad) or ones that contain the pad")
    r.add_argument("--last-mile", action=argparse.BooleanOptionalAction, default=True,
                   help="after the repair rounds, join what is still open with the grid router "
                        "(kae.route.lastmile; default on, --no-last-mile turns it off)")
    r.add_argument("--blocked", action=argparse.BooleanOptionalAction, default=True,
                   help="at the end, diagnose the connections still open: the report's \"blocked\" names the "
                        "board rule (or kae default) that makes each impossible (kae.route.blocked)")
    r.add_argument("--finish", action=argparse.BooleanOptionalAction, default=False,
                   help="at the end, when time is left: the finish stage (rule D tails, taut arcs, power copper, "
                        "one journaled DRC gate; kae.route.finish)")
    r.add_argument("--neckdown", action=argparse.BooleanOptionalAction, default=False,
                   help="Freerouting's neck-down at pins, floored at the board's legal minimum width")
    r.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="override one of kae's own defaults (e.g. ignored_clearance_floor=0.08); a "
                        "KAE_<KEY> text variable in the KiCad project overrides this in turn")
    r.add_argument("--report")
    from kae.board_hazards import add_arguments as recheck_args
    recheck_args(r)
    m = sub.add_parser("lastmile", help="the last mile alone on a routed board (with the task input's rules)")
    m.add_argument("input")
    m.add_argument("board")
    m.add_argument("output")
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--time", type=float, default=120.0)
    m.add_argument("--workdir")
    m.add_argument("--keep", action="store_true")
    m.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    m.add_argument("--report")
    recheck_args(m)
    f = sub.add_parser("finish", help="the finish stage alone on a routed board (with the task input's rules)")
    f.add_argument("input")
    f.add_argument("board")
    f.add_argument("output")
    f.add_argument("--time", type=float, default=600.0)
    f.add_argument("--parts", default="tails,taut,power", help="comma list of tails, taut, power, trim")
    f.add_argument("--input-drc", help="KiCad DRC JSON of BOARD with INPUT's rules (the gate reuses it)")
    f.add_argument("--drc-s", type=float, help="seconds one DRC of BOARD takes (for the estimates)")
    f.add_argument("--workdir")
    f.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    f.add_argument("--report")
    recheck_args(f)
    a = ap.parse_args(argv)
    from kae.route import bridge
    if a.cmd == "finish":
        from kae.route import finish

        def run_finish(opts):
            rep = finish.run(a.board, a.output, project=a.input, opts=opts, workdir=a.workdir, time_s=a.time,
                             base_report=a.input_drc or None, drc_s=a.drc_s)
            rep["status"] = "finished"
            return rep
        return _finish(a, run_finish, dict(parts=tuple(p for p in a.parts.split(",") if p)))
    if a.cmd == "lastmile":
        return _finish(a, lambda opts: bridge.last_mile_only(a.input, a.board, a.output, time_s=a.time, seed=a.seed,
                                                             workdir=a.workdir, opts=opts),
                       dict(keep=a.keep))
    opts = dict(repair=not a.no_repair, fanout=True if a.fanout else ("first" if a.fanout_first else False),
                thermal_repair=not a.no_thermal,
                passes=a.passes, rounds=a.rounds if a.rounds == "auto" else int(a.rounds), keep=a.keep,
                planes=a.planes, pad_shapes=a.pad_shapes,
                router_share=a.router_share if a.router_share == "auto" else float(a.router_share),
                last_mile=a.last_mile, neckdown=a.neckdown, blocked=a.blocked, finish=a.finish)
    if a.thermal_all:
        opts["thermal_pads"] = "all"
    return _finish(a, lambda o: bridge.route(a.input, a.output, seed=a.seed, time_s=a.time, workdir=a.workdir,
                                             opts=o), opts)


def _finish(a, run, opts):
    t0 = time.monotonic()
    for kv in a.set:
        k, _, v = kv.partition("=")
        try:
            opts[k] = json.loads(v)
        except ValueError:
            opts[k] = v
    try:
        rep = run(opts)
    except Exception as e:  # report and fail cleanly; kaebench records the log
        import traceback
        traceback.print_exc()
        rep = dict(status="error", error=f"{type(e).__name__}: {e}")
    from kae.board_hazards import finish
    finish(rep, a.output, a.input, kind="route", mode=a.recheck, deadline=t0 + float(a.time) + RECHECK_GRACE_S,
           log=lambda m: print(f"[kae.route] {m}", file=sys.stderr, flush=True))
    text = json.dumps(rep, default=str)
    if a.report:
        with open(a.report, "w") as f:
            f.write(text + "\n")
    print(text, flush=True)
    return 0 if rep.get("status") in ("routed", "repaired", "finished") else 2


if __name__ == "__main__":
    sys.exit(main())
