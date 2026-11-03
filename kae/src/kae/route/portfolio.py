# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restart portfolio: route a board as several short, differently seeded attempts in parallel
and keep the best, instead of one long attempt.

Routing time per board is heavy-tailed: on splits A+B the median bridge attempt ends in ~10 s
and a few run for 1,500 s, often stuck on the last connections a different item order would
not meet. So the budget is spent as restarts: `parallel` attempts run at once, each with a
budget that starts at `first_s` and grows by `growth` for every later wave (a doubling
schedule, so a board that genuinely needs a long attempt still gets one), each with its own
seed. Attempts are ranked in the harness's order, as tools/kaeres/restart.py judges: fewer
unconnected items first, then fewer DRC errors beyond the input's own (repair.input_errors, per
type: routing cannot remove the errors the placed board already has, and 112 of 159 inputs have
some). The first attempt that comes back routed fully (0 unconnected, no error beyond the
input's) ends the run and stops the others; otherwise the best is kept when time runs out.

The kept board then gets one last mile of its own (`final`: kae.route.cli lastmile, i.e.
bridge.last_mile_only), whatever its attempt's timing, with time reserved for it from the start
(final_reserve): an attempt that ended late, or was stopped at its deadline, is not punished for
it. Its board replaces the kept one only when it ranks better. A board routed fully skips it.

Each attempt is a separate `python -m <router> route` process (kae.route.cli or
kae.route.critical_cli), so it can be stopped, and its own report decides its rank:
report["repair"]["final"] = {errors, unconnected, by_type}. CPU use is up to `parallel` cores.

Several routers can share one portfolio (`router` a list; attempts cycle through them): the two
routers fail on different boards (on split C the bridge closes bldcm and aftonsparv, critical
copper + soft last mile closes libresolar), so a mixed portfolio gets the union. Among equally
ranked results the router listed first wins, so list the physics-first router first.

    python -m kae.route.portfolio route IN OUT [--seed S] [--time T] [--parallel P]
        [--first-s F] [--growth G] [--router kae.route.cli|kae.route.critical_cli] [--no-final]
        [-- ARGS...]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

GRACE_S = 30.0       # an attempt is killed this long after its own budget (it writes on its deadline)
MARGIN_S = 15.0      # left at the end of the run to copy the winner
FINAL_MIN_S = 60.0   # the final last mile at least, beyond one DRC of the board (as restart.py)
FINAL_DRC_S = 60.0   # one DRC of the board until the input's own DRC has been timed
FINAL_SHARE = 0.25   # the final's reserve is at most this share of a short run's budget
INF = float("inf")


def _final(rep):
    """The board summary {errors, unconnected, by_type?} of an attempt's report: kae.route.cli has
    it at repair.final (or drc, when the run was too short for repair rounds; `final` for
    lastmile), kae.route.critical_cli at the same places under bridge. None without one."""
    rep = rep or {}
    for r in (rep, rep.get("bridge") or {}):
        fin = (r.get("repair") or {}).get("final") or r.get("drc") or r.get("final") or {}
        if "errors" in fin and "unconnected" in fin:
            return fin
    return None


def _excess(fin, base):
    """DRC errors of summary `fin` beyond the input's own (`base`, {type: count}); every error
    when the summary has no per-type counts."""
    if not isinstance(fin.get("by_type"), dict):
        return int(fin["errors"])
    return sum(max(0, n - (base or {}).get(t, 0)) for t, n in fin["by_type"].items())


def _rank(rep, base=None):
    """(unconnected, errors beyond the input's own) of an attempt's report, lower is better: the
    harness's order and tools/kaeres/restart.py's judge (routed fully, then fewer unconnected, then
    fewer new errors; (0, 0) is routed fully). (inf, inf) without a summary."""
    fin = _final(rep)
    if fin is None:
        return (INF, INF)
    return (int(fin["unconnected"]), _excess(fin, base))


def _input_errors(inp, wd, deadline):
    """{type: count} of the input's own DRC errors (repair.input_errors, cached); {} when unknown."""
    try:
        from . import repair
        return repair.input_errors(inp, wd, deadline)
    except Exception:  # no KiCad, unreadable input: every error counts, as before
        return {}


def final_reserve(time_s, drc_s):
    """Seconds kept free from the start for the final last mile: FINAL_MIN_S plus one DRC of the
    board (`drc_s`) for the pass, and one more DRC for its own judgement, at most FINAL_SHARE of
    the run."""
    return min(FINAL_MIN_S + 2 * drc_s, FINAL_SHARE * time_s)


def run(inp, out, seed=0, time_s=1800.0, parallel=4, first_s=120.0, growth=2.0,
        router="kae.route.cli", extra=(), workdir=None, log=print, final="kae.route.cli"):
    """`router`: a module name, or a list of module names or (module, [args]) pairs; attempts
    cycle through them and `extra` goes to every one. When a routed-fully result comes from a router
    other than the first, the first router's attempts still running are allowed to finish before
    the run ends, and their board is preferred. `final`: the module whose `lastmile` command gives
    the kept board its final last mile (None: no final pass)."""
    routers = [(r, []) if isinstance(r, str) else (r[0], list(r[1]))
               for r in ([router] if isinstance(router, str) else router)]
    inp, out = Path(inp).resolve(), Path(out).resolve()
    t0 = time.monotonic()
    end = t0 + time_s - MARGIN_S
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-portfolio-"))
    wd.mkdir(parents=True, exist_ok=True)
    running = {}            # Popen -> dict(k, seed, budget, out, report, t)
    done, k, wave_budget, best = [], 0, float(first_s), None
    launched_in_wave = 0
    base, drc_s = None, FINAL_DRC_S   # the input's own errors (read when an attempt has errors)

    def deadline():
        """The attempts' end: the run's, less the final last mile's reserve."""
        return end - (final_reserve(time_s, drc_s) if final else 0.0)

    def rank(rep):
        nonlocal base, drc_s
        fin = _final(rep)
        if base is None and fin is not None and int(fin["errors"]) > 0:
            t = time.monotonic()
            base = _input_errors(inp, wd, end)
            drc_s = max(drc_s, time.monotonic() - t)
            log(f"[portfolio] input's own errors {base} ({time.monotonic() - t:.0f}s)")
        return _rank(rep, base)

    def launch():
        nonlocal k, wave_budget, launched_in_wave
        left = deadline() - time.monotonic()
        b = min(wave_budget, left)
        if b < 20:
            return False
        s = seed * 1000 + k
        ri = k % len(routers)
        mod, rargs = routers[ri]
        d = wd / f"a{k}"
        d.mkdir(exist_ok=True)
        o, r = d / "board.kicad_pcb", d / "report.json"
        argv = [sys.executable, "-m", mod, "route", str(inp), str(o), "--seed", str(s),
                "--time", f"{b:.0f}", "--report", str(r), *rargs, *extra]
        p = subprocess.Popen(argv, stdout=open(d / "log", "w"), stderr=subprocess.STDOUT,
                             start_new_session=True)
        running[p] = dict(k=k, seed=s, budget=round(b), out=o, report=r, t=time.monotonic(), router=ri)
        log(f"[portfolio] start #{k} {mod} seed {s} budget {b:.0f}s")
        k += 1
        launched_in_wave += 1
        if launched_in_wave >= parallel:          # next wave: longer attempts
            launched_in_wave = 0
            wave_budget *= growth
        return True

    def stop(p):
        try:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    while len(running) < parallel and launch():
        pass
    clean = failed = waiting = False
    while running:
        time.sleep(1.0)
        for p in list(running):
            a = running[p]
            if p.poll() is None:
                if time.monotonic() - a["t"] > a["budget"] + GRACE_S:
                    stop(p)
                else:
                    continue
            del running[p]
            try:
                rep = json.loads(a["report"].read_text())
            except (OSError, ValueError):
                rep = None
            fin = _final(rep) or {}
            a.update(rank=rank(rep) + (a["router"],), errors=fin.get("errors"), rc=p.returncode, seconds=round(time.monotonic() - a["t"], 1),
                     has_board=a["out"].exists())
            done.append(a)
            log(f"[portfolio] end #{a['k']} rank {a['rank']} in {a['seconds']}s")
            if a["has_board"] and (best is None or a["rank"] < best["rank"]):
                best = a
            if a["has_board"] and a["rank"][:2] == (0, 0):
                clean = True        # routed fully: no open connection, no error beyond the input's
        # attempts that die at once without a board (bad input, broken install): retrying won't help
        tail = done[-2 * parallel:]
        if len(tail) >= 2 * parallel and all(not a["has_board"] and a["seconds"] < 10 for a in tail):
            failed = True
            log(f"[portfolio] {len(tail)} attempts in a row failed at once; see {wd}/a*/log")
        if clean and not failed and best["router"] > 0:
            # a later-listed router finished clean first: let the first-listed router's attempts still
            # running finish (they may be clean too, with better physics), stop the others, launch none
            for p in [q for q in running if running[q]["router"] > 0]:
                stop(p)
                a = running.pop(p)
                a.update(rank=(INF, INF, a["router"]), rc=p.returncode, stopped=True,
                         seconds=round(time.monotonic() - a["t"], 1), has_board=False)
                done.append(a)
            if running:
                waiting = True
                continue
        if clean or failed:
            for p in list(running):
                stop(p)
                a = running.pop(p)
                a.update(rank=(INF, INF, a["router"]), rc=p.returncode, stopped=True,
                         seconds=round(time.monotonic() - a["t"], 1), has_board=False)
                done.append(a)        # stopped after the winner: listed, never a candidate
            break
        while not waiting and len(running) < parallel and launch():
            pass
    fin_rec = None
    if best is not None:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best["out"], out)
        if final and best["rank"][:2] != (0, 0) and not failed:
            fin_rec = final_pass(final, inp, best, out, wd, seed * 1000 + k, end, rank, stop, log)
            if fin_rec.get("kept"):
                best = dict(best, out=fin_rec["out"], report=fin_rec["report"], rank=fin_rec["rank"] + best["rank"][2:],
                            final=True)
    report = dict(input=str(inp), budget_s=time_s, parallel=parallel, first_s=first_s, growth=growth,
                  routers=[[m, a_] for m, a_ in routers], extra=list(extra), seconds=round(time.monotonic() - t0, 1),
                  stop="clean" if clean else ("failed" if failed else "time"), input_errors=base, attempts=[
                      dict({x: a[x] for x in ("k", "seed", "router", "budget", "rank", "rc", "seconds", "has_board")},
                           errors=a.get("errors"), stopped=a.get("stopped", False))
                      for a in done],
                  final=None if fin_rec is None else {x: fin_rec.get(x) for x in
                                                      ("seed", "budget", "rank", "errors", "rc", "seconds", "kept")},
                  best=None if best is None else dict(k=best["k"], seed=best["seed"], rank=best["rank"][:2],
                                                     router=routers[best["router"]][0],
                                                     final=best.get("final", False)))
    try:
        best_rep = json.loads(best["report"].read_text()) if best else None
    except (OSError, ValueError):
        best_rep = None
    report["best_report"] = best_rep
    return report


def final_pass(module, inp, best, out, wd, seed, end, rank, stop, log=print):
    """The final last mile on the kept board (`module` lastmile: bridge.last_mile_only), with all
    the time left up to `end` however late the kept attempt ended (at least FINAL_MIN_S when the
    run overran). Its board replaces `out` only when `rank` puts it before the kept one. Returns its
    record (kept: whether it did)."""
    d = wd / "final"
    d.mkdir(parents=True, exist_ok=True)
    o, r = d / "board.kicad_pcb", d / "report.json"
    b = max(FINAL_MIN_S, end - time.monotonic())
    argv = [sys.executable, "-m", module, "lastmile", str(inp), str(best["out"]), str(o), "--seed", str(seed),
            "--time", f"{b:.0f}", "--report", str(r)]
    log(f"[portfolio] final last mile on #{best['k']}'s board: seed {seed} budget {b:.0f}s")
    t = time.monotonic()
    p = subprocess.Popen(argv, stdout=open(d / "log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    try:
        p.wait(timeout=b + GRACE_S)
    except subprocess.TimeoutExpired:
        stop(p)
    try:
        rep = json.loads(r.read_text())
    except (OSError, ValueError):
        rep = None
    fin = _final(rep) or {}
    rk = rank(rep)
    kept = o.exists() and rk < tuple(best["rank"][:2])
    if kept:
        shutil.copyfile(o, out)
    log(f"[portfolio] final last mile rank {rk}: {'kept' if kept else 'not better'}")
    return dict(seed=seed, budget=round(b), rank=rk, errors=fin.get("errors"), rc=p.returncode,
                seconds=round(time.monotonic() - t, 1), kept=kept, out=o, report=r)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="kae.route.portfolio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route", help="route with parallel, growing, differently seeded restarts")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--time", type=float, default=1800.0)
    r.add_argument("--parallel", type=int, default=4)
    r.add_argument("--first-s", type=float, default=120.0)
    r.add_argument("--growth", type=float, default=2.0)
    r.add_argument("--router", action="append", metavar="MODULE[:ARGS]",
                   help="kae.route.cli (default) or kae.route.critical_cli, optionally with its own "
                        "arguments after a colon; repeat to mix routers (the first wins ties)")
    r.add_argument("--no-final", action="store_true",
                   help="no final last mile on the kept board (by default it gets one, with time reserved)")
    r.add_argument("--workdir")
    r.add_argument("--report")
    a = ap.parse_args(argv)
    routers = []
    for spec in a.router or ["kae.route.cli"]:
        mod, _, rest = spec.partition(":")
        if mod not in ("kae.route.cli", "kae.route.critical_cli"):
            ap.error(f"unknown router {mod}")
        routers.append((mod, rest.split()))
    rep = run(a.input, a.output, seed=a.seed, time_s=a.time, parallel=a.parallel, first_s=a.first_s,
              growth=a.growth, router=routers, extra=extra, workdir=a.workdir,
              log=lambda m: print(m, file=sys.stderr, flush=True), final=None if a.no_final else "kae.route.cli")
    text = json.dumps(rep, default=str)
    if a.report:
        Path(a.report).write_text(text)
    print(text, flush=True)
    return 0 if rep["best"] else 1


if __name__ == "__main__":
    sys.exit(main())
