# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae command line.

    kae place INPUT OUTPUT [--seed N] [--time S] [--no-physics] [--stages seed,anneal,legalize]
                           [--workers W] [--writer auto|pcbnew|sexpr] [--edge-mate] [--report FILE]
    kae brief INPUT [--out FILE]

`kae place` reads INPUT (.kicad_pcb with its project files beside it), places every unlocked
footprint (locked ones stay; sides are kept) and writes OUTPUT; a JSON report goes to the
last line of stdout, to OUTPUT.kae.json beside the board, and to --report FILE. (kaebench
keeps only the board and the method's log of a --command method, so in a run the report is
the last line of adapter.log.) As a kaebench method:

    kaebench run --adapter kae --kinds place --probe freerouting \\
      --command "<venv>/bin/python -m kae.cli place {input} {output} --seed {attempt} --time {timeout}"

Exit status: 0 when the placement passed the exact legality check, 3 when an output was
written but violations remain (listed in the report), 2 on errors.

The place terms run numba kernels when numba is installed. A read-only NUMBA_CACHE_DIR
(e.g. a cache pre-warmed beside a frozen snapshot, used inside the benchmark sandbox) is
copied to a temporary directory first, because numba ignores cache directories it cannot
write to and would recompile every time.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _log(msg):
    print(f"[kae {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def _numba_cache():
    """Make a read-only NUMBA_CACHE_DIR usable. numba (0.68) only uses a cache directory it can
    write to and otherwise falls back to ~/.cache, so inside the benchmark sandbox (a frozen,
    read-only snapshot; tmpfs home) every attempt would recompile the place-term kernels.
    A read-only cache directory (pre-warmed beside the snapshot) is therefore copied to a
    private temporary directory, and numba is pointed there, before numba is imported.
    Returns (source, used) or None."""
    import os
    src = os.environ.get("NUMBA_CACHE_DIR")
    if not src or not os.path.isdir(src) or os.access(src, os.W_OK) or "numba" in sys.modules:
        return None
    import shutil
    import tempfile
    try:
        dst = tempfile.mkdtemp(prefix="kae-numba-")
        shutil.copytree(src, dst, dirs_exist_ok=True)
    except OSError as e:
        _log(f"numba cache {src} is read-only and could not be copied ({e}); kernels will compile")
        return None
    os.environ["NUMBA_CACHE_DIR"] = dst
    return src, dst


def cmd_place(a):
    from kae.board.kicad_file import load
    from kae.place.pipeline import place
    from kae.place.writer import write
    t0 = time.monotonic()
    board = load(a.input)
    _log(f"loaded {a.input}: {len(board.footprints)} footprints ({time.monotonic() - t0:.2f}s)")
    stages = {x.strip() for x in a.stages.split(",") if x.strip()}
    unknown = stages - {"seed", "anneal", "legalize"}
    if unknown:
        raise SystemExit(f"unknown stages {sorted(unknown)} (seed, anneal, legalize)")
    anneal = "anneal" in stages and not a.no_anneal
    anneal_args = json.loads(a.anneal_args) if a.anneal_args else None
    res = place(board, seed=a.seed, time_s=a.time, physics=not a.no_physics, workers=a.workers, log=_log,
                anneal=anneal, edge_mate=a.edge_mate, anneal_args=anneal_args, angle_step=a.angles)
    res.report["stages_run"] = sorted({"seed", "legalize"} | ({"anneal"} if anneal else set()))
    t1 = time.monotonic()
    wrep = write(a.input, a.output, res.poses, mode=a.writer, log=_log) if res.poses else None
    if wrep is None:
        import shutil
        shutil.copy2(a.input, a.output)
        wrep = dict(writer="copy", moved=0)
    res.report["writer"] = wrep
    res.report["write_s"] = round(time.monotonic() - t1, 2)
    kicad_clean = None
    if a.drc != "off" and res.poses and res.state is not None:
        kicad_clean, wrep2 = _kicad_loop(a, res, t0, write)
        if wrep2 is not None:
            res.report["writer"] = wrep2
    res.report["total_s"] = round(time.monotonic() - t0, 2)
    legal = not res.report.get("exact") and not res.report.get("outline_incomplete") and kicad_clean is not False
    res.report["legal"] = bool(legal)
    text = json.dumps(res.report, default=str)
    print(text, flush=True)          # last line of stdout: what kaebench keeps (adapter.log)
    side = Path(str(a.output) + ".kae.json")
    try:
        side.write_text(json.dumps(res.report, indent=1, default=str))
    except OSError as e:
        _log(f"could not write {side}: {e}")
    if a.report:
        Path(a.report).write_text(json.dumps(res.report, indent=1, default=str))
    _log(f"wrote {a.output} with {wrep.get('writer')} in {res.report['total_s']}s; legal={legal}")
    return 0 if legal else 3


def _kicad_loop(a, res, t0, write):
    """KiCad's DRC on the written placement, fed back until it is clean (kae.place.exact:
    kicad_feedback -> repair -> write again), within the caller's time. Returns (clean or
    None when KiCad could not run, the last writer report or None)."""
    import tempfile
    try:
        from kae.route import drc as kdrc
        kdrc.kicad_cli()
    except Exception as e:      # noqa: BLE001 - no KiCad here: the exact check stands alone
        if a.drc == "on":
            _log(f"KiCad DRC unavailable: {e}")
        res.report["kicad_drc"] = dict(skipped=str(e)[:200])
        return None, None
    from kae.place import exact as X
    from kae.place.legalize import exact_check
    P, st = res.problem, res.state
    tmp = tempfile.mkdtemp(prefix="kae-drc-")
    rounds, clean, wrep = [], None, None
    for it in range(a.drc_rounds + 1):
        left = t0 + 0.97 * float(a.time) - time.monotonic()
        if left < 15.0:
            rounds.append(dict(round=it, skipped="time"))
            break
        staged = kdrc.stage_board(a.output, a.input, tmp)
        t = time.monotonic()
        try:
            report = kdrc.run(staged, Path(tmp) / "drc.json", timeout=max(10.0, min(600.0, 0.5 * left)))
        except kdrc.DrcError as e:
            rounds.append(dict(round=it, error=str(e)[:200]))
            break
        fb = X.kicad_feedback(P, st, report)
        rounds.append(dict(round=it, errors=fb["errors"], by_type=fb["by_type"], fixed_only=fb["fixed_only"],
                           seconds=round(time.monotonic() - t, 1)))
        _log(f"KiCad DRC round {it}: {fb['errors']} placement errors {fb['by_type']}")
        clean = fb["errors"] == fb["fixed_only"]
        if clean or it == a.drc_rounds:
            break
        left = t0 + 0.97 * float(a.time) - time.monotonic()
        rounds[-1]["repair"] = X.repair(P, st, time_s=max(3.0, min(120.0, 0.4 * left)), log=_log)
        rounds[-1]["repair"].pop("findings", None)
        poses = dict(res.poses)
        poses.update(st.poses())
        res.poses = poses
        wrep = write(a.input, a.output, res.poses, mode=a.writer, log=_log)
    res.report["kicad_drc"] = rounds
    res.report["exact"] = exact_check(P, st)
    return clean, wrep


def cmd_brief(a):
    from kae.board.kicad_file import load
    board = load(a.input)
    try:
        from kae.circuit.brief import build
    except ImportError:
        from kae.place.stubs import stub_brief as build
    b = build(board)
    text = json.dumps(b, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kae", description="Physics-first placement and routing for KiCad boards")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("place", help="place the unlocked footprints of a board")
    sp.add_argument("input")
    sp.add_argument("output")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--time", type=float, default=300.0, help="wall-clock seconds the caller allows")
    sp.add_argument("--no-physics", action="store_true", help="routability and legality only (ablation)")
    sp.add_argument("--no-anneal", action="store_true", help="seed and legalize only (= --stages seed,legalize)")
    sp.add_argument("--stages", default="seed,anneal,legalize",
                    help="stages to run; seed and legalize always run, so 'seed,legalize' skips the annealer")
    sp.add_argument("--workers", type=int, default=None, help="CP-SAT threads (default: KAE_WORKERS or cores/2)")
    sp.add_argument("--writer", default="auto", choices=("auto", "pcbnew", "sexpr"))
    sp.add_argument("--edge-mate", action="store_true",
                    help="place staged footprints that carry Edge.Cuts where their open pieces close the "
                         "outline exactly (default: hold them and flag outline_incomplete)")
    sp.add_argument("--report", help="also write the JSON report here")
    sp.add_argument("--drc", default="auto", choices=("auto", "on", "off"),
                    help="KiCad DRC on the result, fed back until clean (auto: when kicad-cli is found)")
    sp.add_argument("--drc-rounds", type=int, default=3, help="repair rounds driven by KiCad's DRC")
    sp.add_argument("--angles", type=float, default=None, metavar="STEP",
                    help="let parts turn to any multiple of STEP degrees, not only right angles "
                         "(heatsink-mount packages keep right angles; CP-SAT stays on right angles)")
    sp.add_argument("--anneal-args", help="JSON of annealer weights for experiments, e.g. '{\"w_phys\": 2.0}' "
                                          "(w_phys, w_wl, w_cong, w_order, w_disp, cong_args, ...)")
    sp.set_defaults(fn=cmd_place)
    sb = sub.add_parser("brief", help="print the physics brief of a board")
    sb.add_argument("input")
    sb.add_argument("--out")
    sb.set_defaults(fn=cmd_brief)
    a = ap.parse_args(argv)
    nc = _numba_cache()
    if nc:
        _log(f"numba cache: read-only {nc[0]} copied to {nc[1]}")
    try:
        return a.fn(a)
    except Exception as e:  # report and fail
        import traceback
        traceback.print_exc()
        _log(f"error: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
