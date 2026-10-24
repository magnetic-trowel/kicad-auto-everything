# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Restart portfolio: route a board as several short, differently seeded attempts in parallel
and keep the best, instead of one long attempt.

Routing time per board is heavy-tailed: on splits A+B the median bridge attempt ends in ~10 s
and a few run for 1,500 s, often stuck on the last connections a different item order would
not meet. So the budget is spent as restarts: `parallel` attempts run at once, each with a
budget that starts at `first_s` and grows by `growth` for every later wave (a doubling
schedule, so a board that genuinely needs a long attempt still gets one), each with its own
seed. The first attempt that comes back clean (0 DRC errors, 0 unconnected) ends the run and
stops the others; otherwise the best by (errors, unconnected) is kept when time runs out.

Each attempt is a separate `python -m <router> route` process (kae.route.cli or
kae.route.critical_cli), so it can be stopped, and its own report decides its rank:
report["repair"]["final"] = {errors, unconnected}. CPU use is up to `parallel` cores.

    python -m kae.route.portfolio route IN OUT [--seed S] [--time T] [--parallel P]
        [--first-s F] [--growth G] [--router kae.route.cli|kae.route.critical_cli] [-- ARGS...]
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


def _rank(rep):
    fin = ((rep or {}).get("repair") or {}).get("final") or {}
    if "errors" not in fin or "unconnected" not in fin:
        return (float("inf"), float("inf"))
    return (int(fin["errors"]), int(fin["unconnected"]))


def run(inp, out, seed=0, time_s=1800.0, parallel=4, first_s=120.0, growth=2.0,
        router="kae.route.cli", extra=(), workdir=None, log=print):
    inp, out = Path(inp).resolve(), Path(out).resolve()
    t0 = time.monotonic()
    deadline = t0 + time_s - MARGIN_S
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-portfolio-"))
    wd.mkdir(parents=True, exist_ok=True)
    running = {}            # Popen -> dict(k, seed, budget, out, report, t)
    done, k, wave_budget, best = [], 0, float(first_s), None
    launched_in_wave = 0

    def launch():
        nonlocal k, wave_budget, launched_in_wave
        left = deadline - time.monotonic()
        b = min(wave_budget, left)
        if b < 20:
            return False
        s = seed * 1000 + k
        d = wd / f"a{k}"
        d.mkdir(exist_ok=True)
        o, r = d / "board.kicad_pcb", d / "report.json"
        argv = [sys.executable, "-m", router, "route", str(inp), str(o), "--seed", str(s),
                "--time", f"{b:.0f}", "--report", str(r), *extra]
        p = subprocess.Popen(argv, stdout=open(d / "log", "w"), stderr=subprocess.STDOUT,
                             start_new_session=True)
        running[p] = dict(k=k, seed=s, budget=round(b), out=o, report=r, t=time.monotonic())
        log(f"[portfolio] start #{k} seed {s} budget {b:.0f}s")
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
    clean = failed = False
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
            a.update(rank=_rank(rep), rc=p.returncode, seconds=round(time.monotonic() - a["t"], 1),
                     has_board=a["out"].exists())
            done.append(a)
            log(f"[portfolio] end #{a['k']} rank {a['rank']} in {a['seconds']}s")
            if a["has_board"] and (best is None or a["rank"] < best["rank"]):
                best = a
            if a["rank"] == (0, 0):
                clean = True
        # attempts that die at once without a board (bad input, broken install): retrying won't help
        tail = done[-2 * parallel:]
        if len(tail) >= 2 * parallel and all(not a["has_board"] and a["seconds"] < 10 for a in tail):
            failed = True
            log(f"[portfolio] {len(tail)} attempts in a row failed at once; see {wd}/a*/log")
        if clean or failed:
            for p in list(running):
                stop(p)
                running.pop(p)
            break
        while len(running) < parallel and launch():
            pass
    if best is not None:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best["out"], out)
    report = dict(input=str(inp), budget_s=time_s, parallel=parallel, first_s=first_s, growth=growth,
                  router=router, extra=list(extra), seconds=round(time.monotonic() - t0, 1),
                  stop="clean" if clean else ("failed" if failed else "time"), attempts=[
                      {x: a[x] for x in ("k", "seed", "budget", "rank", "rc", "seconds", "has_board")}
                      for a in done],
                  best=None if best is None else dict(k=best["k"], seed=best["seed"], rank=best["rank"]))
    try:
        best_rep = json.loads(best["report"].read_text()) if best else None
    except (OSError, ValueError):
        best_rep = None
    report["best_report"] = best_rep
    return report


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
    r.add_argument("--router", default="kae.route.cli", choices=("kae.route.cli", "kae.route.critical_cli"))
    r.add_argument("--workdir")
    r.add_argument("--report")
    a = ap.parse_args(argv)
    rep = run(a.input, a.output, seed=a.seed, time_s=a.time, parallel=a.parallel, first_s=a.first_s,
              growth=a.growth, router=a.router, extra=extra, workdir=a.workdir,
              log=lambda m: print(m, file=sys.stderr, flush=True))
    text = json.dumps(rep, default=str)
    if a.report:
        Path(a.report).write_text(text)
    print(text, flush=True)
    return 0 if rep["best"] else 1


if __name__ == "__main__":
    sys.exit(main())
