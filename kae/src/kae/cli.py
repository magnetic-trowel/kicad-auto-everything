# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""kae command line.

    kae place INPUT OUTPUT [--seed N] [--time S] [--no-physics] [--stages seed,anneal,legalize]
                           [--workers W] [--writer auto|pcbnew|sexpr] [--edge-mate] [--report FILE]
                           [--drc auto|on|off] [--drc-rounds N]
    kae brief INPUT [--out FILE]

`kae place` reads INPUT (.kicad_pcb with its project files beside it), places every unlocked
footprint (locked ones stay; sides are kept) and writes OUTPUT; a JSON report goes to the
last line of stdout, to OUTPUT.kae.json beside the board, and to --report FILE. (kaebench
keeps only the board and the method's log of a --command method, so in a run the report is
the last line of adapter.log.) As a kaebench method:

    kaebench run --adapter kae --kinds place --probe freerouting \\
      --command "<venv>/bin/python -m kae.cli place {input} {output} --seed {attempt} --time {timeout}"

Legality is closed-loop: the placer repairs against its exact check (kae.place.exact), and
then, when kicad-cli is found (KAE_KICAD_CLI / KAE_KICAD_WRAP / PATH; --drc auto|on|off),
KiCad's DRC on the written board feeds every placement error back as a constraint and the
board is repaired and written again (--drc-rounds, default 6) until KiCad has no placement
error or the time is up. Exit status: 0 when the placement passed the exact check and KiCad
(when it ran), 3 when an output was written but violations remain (listed in the report,
with the closed loop's diagnosis per part), 2 on errors.

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
    kw = dict(physics=not a.no_physics, workers=a.workers, log=_log, anneal=anneal, edge_mate=a.edge_mate,
              anneal_args=anneal_args, angle_step=a.angles)
    if a.probe_select and a.probe_select > 1:
        res = _probe_select(a, board, kw, t0, write)
    else:
        res = place(board, seed=a.seed, time_s=a.time, **kw)
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


DRC_RETRIES = 2                      # kicad-cli runs again after dying on a signal
_DRC_SIGNAL = __import__("re").compile(r"rc=-\d+")


def _kicad_loop(a, res, t0, write):
    """KiCad's DRC on the written placement, fed back until it is clean (kae.place.exact:
    kicad_feedback -> repair -> write again), within the caller's time. The best placement
    KiCad has judged (clean, else fewest placement errors) is kept: when the loop ends on a
    worse verdict, or on a repair KiCad has not judged (time, a DRC failure), that one is
    written again (report: kicad_written_round). Returns (clean or None when KiCad could not
    run, the last writer report or None)."""
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
    before = st.poses()
    best = None            # (placement errors, round, X, Y, K, poses) KiCad judged
    judged = None          # errors of the board as written now (None: not judged yet)
    for it in range(a.drc_rounds + 1):
        left = t0 + 0.97 * float(a.time) - time.monotonic()
        if left < 15.0:
            rounds.append(dict(round=it, skipped="time"))
            break
        t = time.monotonic()
        report, err, crashes = None, None, 0
        for attempt in range(1 + DRC_RETRIES):
            # a fresh staged copy each attempt; the first verdict may take nearly all that is
            # left, repairs need a share after
            staged = kdrc.stage_board(a.output, a.input, tempfile.mkdtemp(prefix="kae-drc-", dir=tmp))
            left = t0 + 0.97 * float(a.time) - time.monotonic()
            try:
                report = kdrc.run(staged, Path(staged).parent / "drc.json",
                                  timeout=max(10.0, min(600.0, (left - 5.0) if it == 0 else 0.5 * left)))
                err = None
                break
            except kdrc.DrcError as e:
                err = str(e)
                # kicad-cli killed by a signal (rc < 0, e.g. -11 on buspirate5): run it again
                if not _DRC_SIGNAL.search(err) or left < 30.0:
                    break
                crashes += 1
                _log(f"KiCad DRC round {it} crashed ({err[:60]}); retrying")
        if report is None:
            rounds.append(dict(round=it, error=(err or "")[:200], crashes=crashes))
            break
        fb = X.kicad_feedback(P, st, report)
        rounds.append(dict(round=it, errors=fb["errors"], by_type=fb["by_type"], fixed_only=fb["fixed_only"],
                           seconds=round(time.monotonic() - t, 1), **({"crashes": crashes} if crashes else {})))
        _log(f"KiCad DRC round {it}: {fb['errors']} placement errors {fb['by_type']}")
        clean = fb["errors"] == fb["fixed_only"]
        judged = fb["errors"] - fb["fixed_only"]
        if best is None or judged < best[0]:
            best = (judged, it, st.X.copy(), st.Y.copy(), st.K.copy(), dict(res.poses))
        if clean or it == a.drc_rounds:
            break
        left = t0 + 0.97 * float(a.time) - time.monotonic()
        rounds[-1]["repair"] = X.repair(P, st, time_s=max(3.0, min(120.0, 0.4 * left)), log=_log)
        rounds[-1]["repair"].pop("findings", None)
        poses = dict(res.poses)
        poses.update(st.poses())
        res.poses = poses
        wrep = write(a.input, a.output, res.poses, mode=a.writer, log=_log)
        judged = None
    written = None if judged is None else rounds[-1]["round"] if "errors" in rounds[-1] else None
    if not clean and best is not None and (judged is None or judged > best[0]):
        # the loop ended worse than a placement KiCad already judged: write that one again
        _, written, X0, Y0, K0, poses0 = best
        st.X[:], st.Y[:], st.K[:] = X0, Y0, K0
        res.poses = poses0
        wrep = write(a.input, a.output, res.poses, mode=a.writer, log=_log)
        clean = best[0] == 0
        _log(f"KiCad DRC: wrote round {written}'s placement again ({best[0]} placement errors)")
    res.report["kicad_written_round"] = written
    res.report["kicad_drc"] = rounds
    res.report["kicad_verified"] = clean is not None
    res.report["exact"] = exact_check(P, st)
    if st.poses() != before:
        _refresh_physics(res)
    return clean, wrep


PROBE_PHYS_SLACK = 0.10       # a probed candidate may cost 10% more physics than the best one
PROBE_JITTER = 0.15           # candidates after the first start from a seed stage jittered this much


def _probe_select(a, board, kw, t0, write):
    """--probe-select N: place N times (seeds seed .. seed+N-1, each a share of the time; the
    candidates after the first also start from a jittered seed stage, --probe-jitter, so they
    differ beyond the annealer's seed), route each placement briefly with kae.route.bridge
    (last mile on; --probe-parallel P of them at once), and keep the one with the fewest open
    connections; physics breaks ties, and a candidate with fewer opens is taken only within
    PROBE_PHYS_SLACK of the best physics among the candidates. A fallback for when the
    congestion estimates cannot tell which placement routes (paw3395)."""
    import math
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from kae.board.kicad_file import load
    from kae.place.pipeline import place
    from kae.route import bridge
    from kae.route import drc as kdrc
    n = int(a.probe_select)
    par = max(1, min(n, int(getattr(a, "probe_parallel", 1) or 1)))
    waves = math.ceil(n / par)
    jitter = float(getattr(a, "probe_jitter", PROBE_JITTER))
    usable = float(a.time) * 0.85
    place_s = max(30.0, 0.45 * usable / n)
    probe_s = max(30.0, min(300.0, (usable - n * place_s) / waves))
    tmp = tempfile.mkdtemp(prefix="kae-probe-")
    cands = []
    for k in range(n):
        if k and time.monotonic() - t0 > usable - place_s - waves * probe_s:
            break
        kk = dict(kw)
        if k and jitter > 0:
            kk["anneal_args"] = dict(kk.get("anneal_args") or {}, seed_jitter=jitter)
        r = place(load(a.input) if k else board, seed=a.seed + k, time_s=place_s, **kk)
        legal = not r.report.get("exact") and not r.report.get("outline_incomplete")
        phys = (r.report.get("scorecard") or {}).get("total_linear") or 0.0
        out = Path(tmp) / f"cand{k}" / "board.kicad_pcb"
        out.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        if r.poses and legal:
            write(a.input, str(out), r.poses, mode=a.writer, log=_log)
            staged = kdrc.stage_board(str(out), a.input, str(out.parent / "staged"))
        cands.append(dict(seed=a.seed + k, jitter=jitter if k else 0.0, res=r, legal=legal, physics=phys,
                          unconnected=None, staged=staged, out=out))

    def probe(c):
        if c["staged"] is None:
            return None
        try:
            rep = bridge.route(c["staged"], str(c["out"].parent / "routed.kicad_pcb"), seed=0, time_s=probe_s,
                               opts=dict(last_mile=True), log=lambda m: None)
            return ((rep.get("repair") or {}).get("final") or {}).get("unconnected")
        except Exception as e:      # noqa: BLE001 - a probe that fails leaves the candidate unranked
            _log(f"probe of seed {c['seed']} failed: {type(e).__name__}: {e}")
            return None
    t_probe = time.monotonic()
    with ThreadPoolExecutor(max_workers=par) as ex:
        for c, unc in zip(cands, ex.map(probe, cands)):
            c["unconnected"] = unc
            _log(f"probe seed {c['seed']}: legal={c['legal']} physics={c['physics']:.4g} unconnected={unc}")
    ok = [c for c in cands if c["legal"] and c["unconnected"] is not None]
    if not ok:
        best = cands[0]
    else:
        floor = min(c["physics"] for c in ok)
        within = [c for c in ok if c["physics"] <= floor * (1.0 + PROBE_PHYS_SLACK) + 1e-9]
        best = min(within, key=lambda c: (c["unconnected"], c["physics"]))
    res = best["res"]
    res.report["probe_select"] = dict(n=n, parallel=par, jitter=jitter, place_s=round(place_s, 1),
                                      probe_s=round(probe_s, 1), probe_wall_s=round(time.monotonic() - t_probe, 1),
                                      chosen=best["seed"],
                                      candidates=[{k: c[k] for k in ("seed", "jitter", "legal", "physics", "unconnected")}
                                                  for c in cands])
    return res


def _refresh_physics(res):
    """A KiCad round moved parts: protection order and the physics scorecard again, for the
    board as written; the values place() reported stay as *_pre_drc."""
    from kae.place.pipeline import final_physics
    for k in ("protection_order", "scorecard"):
        if k in res.report:
            res.report[f"{k}_pre_drc"] = res.report[k]
    final_physics(res)


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
    sp.add_argument("--drc-rounds", type=int, default=6, help="repair rounds driven by KiCad's DRC")
    sp.add_argument("--angles", type=float, default=None, metavar="STEP",
                    help="let parts turn to any multiple of STEP degrees, not only right angles "
                         "(heatsink-mount packages keep right angles; CP-SAT stays on right angles)")
    sp.add_argument("--probe-select", type=int, default=0, metavar="N",
                    help="place N times (seeds seed..seed+N-1) and keep the placement a quick kae.route "
                         "probe leaves the fewest open connections on (physics within 10%%; off by default)")
    sp.add_argument("--probe-parallel", type=int, default=1, metavar="P",
                    help="with --probe-select: probe P candidates at once (each probe runs Freerouting)")
    sp.add_argument("--probe-jitter", type=float, default=PROBE_JITTER, metavar="F",
                    help="with --probe-select: candidates after the first start from a seed stage moved by "
                         "F x the board span (0: annealer seeds only)")
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
