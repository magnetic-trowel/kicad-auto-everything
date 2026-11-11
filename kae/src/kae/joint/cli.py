# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the joint placement and routing loop.

    python -m kae.joint.cli run INPUT OUTPUT [--time S] [--seed N] [--max-iters N]
                                [--no-modules] [--no-physics] [--start PLACED]
                                [--workdir DIR] [--keep] [--report FILE] [--set KEY=VALUE ...]
                                [--physics-fidelity fast|exact|multi] [--physics-k K]
                                [--route-parallel P]

INPUT is a place task's board (.kicad_pcb with its project files beside it); OUTPUT is the
input with every unlocked footprint placed and the board routed. The JSON report (per
iteration: unrouted, DRC errors, physics, window, accepted) is the last line of stdout and
goes to --report FILE; progress goes to stderr. As a kaebench method:

    kaebench run --kinds joint --adapter kae-joint \\
      --command "<venv>/bin/python -m kae.joint.cli run {input} {output} --seed {attempt} --time {timeout}"

`--max-iters 0 --no-modules` is the staged baseline (kae place, then the bridge);
`--start PLACED` starts from a placed board instead of running the placer.
`--physics-fidelity exact` makes the routed physics (recheck, board_physics, and so the
accept rule's module values) PEEC (kae.physics.exact); `multi` uses closed forms to search
and PEEC on each decision's top K and on finished boards; the default `fast` changes nothing.
The report ends with "hazards" and "hazard_summary" (kae.hazards), including a recheck of
OUTPUT with the safety checks forced on (--recheck, kae.board_hazards). Exit status: 0 when
an output was written, 2 otherwise. The report's status: "ok"; "partial"
when a stage raised after OUTPUT was written (the iterations so far, `output_exists`, `error`);
"error" (nothing written, or an unknown --set key: every key must be one the loop, the stages
or the placer reads); "no_output".
"""
from __future__ import annotations

from kae.budget import start_run as _start_run
from kae.budget import now as clock_now
import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path


def _log(msg):
    print(f"[kae.joint {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def _value(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def run(a):
    from .loop import JointLoop
    from .stages import KaeStages
    out = Path(a.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    own = a.workdir is None
    wd = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(prefix="kae-joint-", dir=out.parent))
    opts = {}
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        opts[k.strip()] = _value(v)
    bad = sorted(k for k in opts if not _known_key(k))
    if bad:
        # a typo would otherwise be ignored silently and the run would not be what was asked
        rep = dict(status="error", error=f"--set: unknown option(s) {', '.join(bad)} (known: loop.DEFAULTS, "
                                         f"stages.STAGE_KEYS, kae.route.constraints.DEFAULTS, bridge.KEY)")
        text = json.dumps(rep)
        if a.report:
            Path(a.report).write_text(text + "\n")
        print(text, flush=True)
        return 2
    sopts = dict(opts, keep=a.keep, no_physics=a.no_physics, no_modules=a.no_modules, budget_s=a.time)
    sopts.setdefault("route_parallel", a.route_parallel)
    # the finishing stage belongs to the loop: the staged baseline (--max-iters 0) has none
    lopts = dict(opts, max_iters=a.max_iters, modules=not a.no_modules)
    lopts.setdefault("finish", (a.max_iters is None or a.max_iters > 0) and not a.no_finish)
    # The first route keeps the bridge's last mile (on since c9c49d6), loop or not. It used to be off
    # when a finishing stage followed, to leave time for windows; loop-window-bench (J14, 69 boards,
    # natural budget) found it on gives 7 % fewer open connections (36 boards fewer, 23 more,
    # p 0.020) at the same CPU: windows start from a board with fewer opens. --set first_last_mile=0
    # restores the old behaviour.
    if lopts["finish"]:
        # the bridge's "blocked" diagnosis is for the final board (loop: rep["final"]["blocked"])
        sopts.setdefault("first_blocked", False)
    rep = dict(status="error")
    t0 = clock_now()
    pre = _mtime(out)
    loop = stages = None
    try:
        stages = KaeStages(a.input, wd, opts=sopts, log=_log)
        loop = JointLoop(stages, opts={k: v for k, v in lopts.items() if k in _loop_keys()}, log=_log)
        rep = loop.run(out, time_s=a.time, seed=a.seed, start=a.start)
        rep["status"] = "ok" if out.exists() else "no_output"
        from kae.route.constraints import setting
        if out.exists() and int(setting("connector_edge", a.input, opts)) >= 1:
            _edge_hazards(rep, a.input, out)
    except Exception as e:
        import traceback
        traceback.print_exc()
        # a board already written (the loop saves its incumbent as it goes) is a result: report
        # "partial" with the iterations so far, not a bare error
        written = out.exists() and _mtime(out) != pre
        rep = dict(getattr(loop, "rep", None) or {})
        rep.update(status="partial" if written else "error", error=f"{type(e).__name__}: {e}",
                   output_exists=written)
    finally:
        rep["physics_fidelity"] = dict(mode=a.physics_fidelity, k=a.physics_k)
        if hasattr(stages, "writer_hazards"):
            # KiCad's writer checks of every pose write (kae.board.pcbnew_io.write_hazards)
            rep.setdefault("hazards", []).extend(stages.writer_hazards())
        if own and not a.keep:
            shutil.rmtree(wd, ignore_errors=True)
        else:
            rep["workdir"] = str(wd)
    from kae.board_hazards import finish
    finish(rep, str(out), a.input, kind="joint", mode=a.recheck, deadline=t0 + float(a.time), log=_log)
    text = json.dumps(rep, default=str)
    if a.report:
        Path(a.report).write_text(text + "\n")
    print(text, flush=True)
    return 0 if rep.get("status") in ("ok", "partial") else 2


def _mtime(p):
    try:
        return Path(p).stat().st_mtime_ns
    except OSError:
        return None


def _edge_hazards(rep, input_path, out):
    """connector_off_edge for each user-facing connector the run moved off the board edge
    (kae.place.edge_check; parts locked in the input are the user's and not judged)."""
    try:
        from kae.board.kicad_file import load
        from kae.place import edge_check
        moved = {fp.uuid for fp in load(input_path).footprints if not fp.locked}
        hz = edge_check.hazards(load(out), moved=moved)
    except Exception as e:      # noqa: BLE001 - a check must not cost the result
        hz = [dict(code="edge_check_failed", severity="info", category="data",
                   message=f"the connector edge check failed ({type(e).__name__}: {e})", objects=[])]
    if hz:
        rep.setdefault("hazards", []).extend(hz)


def _known_key(k):
    """A --set key something reads: the loop, the stages, the placer's limits, bridge.KEY."""
    from kae.route.constraints import DEFAULTS as LIMITS

    from .stages import STAGE_KEYS
    return k in _loop_keys() or k in STAGE_KEYS or k in LIMITS or (k.startswith("bridge.") and len(k) > 7)


def _loop_keys():
    from .loop import DEFAULTS
    return set(DEFAULTS) | {"modules"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae.joint.cli", description="joint placement and routing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="place, route, and repair locally until nothing improves")
    r.add_argument("input")
    r.add_argument("output")
    r.add_argument("--time", type=float, default=900.0, help="wall seconds for everything")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--max-iters", type=int, default=None,
                   help="repair iterations at most (default: as many as the time allows; 0: staged pipeline only)")
    r.add_argument("--no-modules", action="store_true", help="no module stage (kae place, then the bridge)")
    r.add_argument("--no-physics", action="store_true", help="placer without physics terms (ablation)")
    r.add_argument("--route-parallel", type=int, default=1, metavar="P",
                   help="P > 1: the finishing stage is kae.route.portfolio with P parallel restarts "
                        "(critical_cli --last-mile-soft, then the bridge), and a window left open gets "
                        "2 more differently seeded route_open runs at once (default 1: neither)")
    r.add_argument("--no-finish", action="store_true",
                   help="no finishing stage (the full bridge over the whole board in a reserved share of the time)")
    r.add_argument("--start", help="a placed board to start from instead of running the placer")
    r.add_argument("--workdir")
    r.add_argument("--keep", action="store_true", help="keep the work directory")
    r.add_argument("--report")
    from kae.board_hazards import add_arguments as recheck_args
    recheck_args(r)
    r.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="loop or stage option, JSON values (loop.DEFAULTS, stages.STAGE_KEYS, "
                        "kae.route.constraints.DEFAULTS, bridge.KEY; unknown keys are an error). "
                        "margin is the loop's window margin; replace_margin the re-placement's")
    from kae.physics import exact as EX
    EX.add_cli_args(r)                      # --physics-fidelity fast | exact | multi, --physics-k
    a = ap.parse_args(argv)
    if getattr(a, "time", None):
        _start_run(float(a.time))
    EX.configure(a.physics_fidelity, a.physics_k)
    from kae.cli import _numba_cache
    _numba_cache()
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
