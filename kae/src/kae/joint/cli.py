# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the joint placement and routing loop.

    python -m kae.joint.cli run INPUT OUTPUT [--time S] [--seed N] [--max-iters N]
                                [--no-modules] [--no-physics] [--start PLACED]
                                [--workdir DIR] [--keep] [--report FILE] [--set KEY=VALUE ...]

INPUT is a place task's board (.kicad_pcb with its project files beside it); OUTPUT is the
input with every unlocked footprint placed and the board routed. The JSON report (per
iteration: unrouted, DRC errors, physics, window, accepted) is the last line of stdout and
goes to --report FILE; progress goes to stderr. As a kaebench method:

    kaebench run --kinds joint --adapter kae-joint \\
      --command "<venv>/bin/python -m kae.joint.cli run {input} {output} --seed {attempt} --time {timeout}"

`--max-iters 0 --no-modules` is the staged baseline (kae place, then the bridge);
`--start PLACED` starts from a placed board instead of running the placer.
Exit status: 0 when an output was written, 2 otherwise.
"""
from __future__ import annotations

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
    sopts = dict(opts, keep=a.keep, no_physics=a.no_physics, no_modules=a.no_modules)
    # the finishing stage belongs to the loop: the staged baseline (--max-iters 0) has none
    lopts = dict(opts, max_iters=a.max_iters, modules=not a.no_modules)
    lopts.setdefault("finish", a.max_iters > 0 and not a.no_finish)
    rep = dict(status="error")
    try:
        stages = KaeStages(a.input, wd, opts=sopts, log=_log)
        loop = JointLoop(stages, opts={k: v for k, v in lopts.items() if k in _loop_keys()}, log=_log)
        rep = loop.run(out, time_s=a.time, seed=a.seed, start=a.start)
        rep["status"] = "ok" if out.exists() else "no_output"
    except Exception as e:
        import traceback
        traceback.print_exc()
        rep = dict(status="error", error=f"{type(e).__name__}: {e}")
    finally:
        if own and not a.keep:
            shutil.rmtree(wd, ignore_errors=True)
        else:
            rep["workdir"] = str(wd)
    text = json.dumps(rep, default=str)
    if a.report:
        Path(a.report).write_text(text + "\n")
    print(text, flush=True)
    return 0 if rep.get("status") == "ok" else 2


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
    r.add_argument("--max-iters", type=int, default=30, help="repair iterations at most (0: staged pipeline only)")
    r.add_argument("--no-modules", action="store_true", help="no module stage (kae place, then the bridge)")
    r.add_argument("--no-physics", action="store_true", help="placer without physics terms (ablation)")
    r.add_argument("--no-finish", action="store_true",
                   help="no finishing stage (the full bridge over the whole board in a reserved share of the time)")
    r.add_argument("--start", help="a placed board to start from instead of running the placer")
    r.add_argument("--workdir")
    r.add_argument("--keep", action="store_true", help="keep the work directory")
    r.add_argument("--report")
    r.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="loop or stage option (loop.DEFAULTS, stages.KaeStages), JSON values")
    a = ap.parse_args(argv)
    from kae.cli import _numba_cache
    _numba_cache()
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
