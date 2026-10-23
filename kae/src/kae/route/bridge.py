# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The KiCad -> Freerouting -> KiCad pipeline.

    route(input, output, seed=0, time_s=600)

1. KiCad exports the DSN and everything the DSN leaves out (pcbnew_io.export_dsn).
2. constraints.plan computes what KiCad's DRC will require; translate.apply writes it into
   the DSN (classes, clearance matrix, pin and obstacle classes, vias).
3. Freerouting routes with settings that stop it narrowing tracks, inside its own deadline.
4. The session is fixed up (translate.fix_session) and imported by KiCad into OUTPUT.
5. repair.loop runs KiCad's DRC on the result and repairs what it finds (see repair).

The output is written as soon as a routed board exists and replaced only by better ones,
so a run that is killed still leaves its best board. Returns a JSON-able report.
"""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from kae.board import pcbnew_io

from . import constraints, drc, freerouting, specctra, translate

DEFAULT_OPTS = dict(
    fanout=False,            # Freerouting's fanout pre-pass narrows tracks (see freerouting.py)
    thermal_repair=True,     # starved thermals get spoke corridors in the repair loop
    passes=0,                # 0: autorouter runs until it stops improving
    repair=True,             # post-route DRC repair loop
    rounds=3,                # repair rounds at most
    router_share=0.6,        # share of the budget for the first routing
)


def _log(msg):
    print(f"[kae.route {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def severities(board_path):
    """DRC rule severities from the board's project file (as the scorer reads them)."""
    pro = Path(board_path).with_suffix(".kicad_pro")
    try:
        d = json.loads(pro.read_text(encoding="utf-8", errors="replace"))
        return ((d.get("board") or {}).get("design_settings") or {}).get("rule_severities") or {}
    except (OSError, ValueError):
        return {}


def route(input_path, output_path, seed=0, time_s=600.0, workdir=None, opts=None, log=_log):
    t0 = time.monotonic()
    opts = {**DEFAULT_OPTS, **(opts or {})}
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    own_wd = workdir is None
    wd = Path(workdir).resolve() if workdir else Path(tempfile.mkdtemp(prefix="kae-route-", dir=output_path.parent))
    wd.mkdir(parents=True, exist_ok=True)
    report = dict(input=str(input_path), seed=seed, budget_s=time_s, opts=opts)

    def left():
        return time_s - (time.monotonic() - t0)

    try:
        # 1-2: export and plan
        kdsn = wd / "kicad.dsn"
        info = pcbnew_io.export_dsn(input_path, kdsn)
        sev = severities(input_path)
        opts["severities"] = sev
        p = constraints.plan(info, input_path, opts)
        tree = specctra.read(kdsn)
        report["translate"] = translate.apply(tree, p, info)
        report["plan"] = plan_summary(p)
        dsn = wd / "board.dsn"
        specctra.write(tree, dsn)
        log(f"plan: {len(p.classes)} classes, {len(p.obstacle_classes)} obstacle classes, "
            f"{report['translate'].get('obstacles')} obstacles ({time.monotonic() - t0:.1f}s)")

        # 3: route
        settings = router_settings(p, opts)
        budget = max(20.0, left() * (opts["router_share"] if opts.get("repair") else 0.9))
        run = freerouting.route(dsn, wd / "board.ses", wd, passes=opts.get("passes") or 0,
                                settings=settings, budget_s=budget, log_path=wd / "freerouting.log")
        report["router"] = dict(seconds=run.seconds, rc=run.rc, timed_out=run.timed_out, report=run.report,
                                settings=settings)
        log(f"freerouting: rc={run.rc} {run.seconds:.1f}s state={run.report.get('final_state')} "
            f"score={run.report.get('router_score')}")
        if run.ses is None:
            report["status"] = "no_session"
            return report

        # 4: import
        ses = specctra.read(run.ses)
        report["session"] = translate.fix_session(ses, p)
        ses_k = wd / "board_kicad.ses"
        specctra.write(ses, ses_k)
        pcbnew_io.import_ses(input_path, ses_k, output_path)
        report["status"] = "routed"

        # 5: DRC and repair
        if opts.get("repair") and left() > 30:
            from . import repair
            report["repair"] = repair.loop(input_path, output_path, wd, p, info, opts, deadline=t0 + time_s - 10,
                                           log=log)
        elif opts.get("drc", True) and left() > 20:
            staged = drc.stage_board(output_path, input_path, wd / "drc")
            rep = drc.run(staged, wd / "drc" / "drc.json", timeout=max(10, left() - 5))
            report["drc"] = drc.summary(rep)
        return report
    finally:
        report["seconds"] = round(time.monotonic() - t0, 2)
        if own_wd and not opts.get("keep"):
            shutil.rmtree(wd, ignore_errors=True)
        else:
            report["workdir"] = str(wd)


def router_settings(p, opts):
    s = {"automatic_neckdown": "false"}
    if not opts.get("fanout"):
        s["fanout.enabled"] = "false"
    s["copper_to_edge_clearance_um"] = specctra.fmt(p.edge_clearance * 1000)
    if p.neck_width:
        s["neck_width_um"] = specctra.fmt(p.neck_width * 1000)
    return s


def plan_summary(p):
    return dict(
        classes={n: dict(nets=len(rc.nets), netclass=rc.netclass, widths=rc.widths, via=rc.via)
                 for n, rc in p.classes.items()},
        obstacle_classes=len(p.obstacle_classes), obstacles=len(p.obstacles),
        pins=len(p.pin_class), edge_clearance=p.edge_clearance, neck_width=p.neck_width,
        notes={k: v for k, v in p.notes.items() if k != "same_net_via_pitch"})
