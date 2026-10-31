# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The KiCad -> Freerouting -> KiCad pipeline.

    route(input, output, seed=0, time_s=600)

1. KiCad exports the DSN and everything the DSN leaves out (pcbnew_io.export_dsn). Locked
   tracks and vias in the input (pre-routes) go in as fixed wiring: Freerouting routes around
   them and does not return them, KiCad's import keeps them as they are, the repair loop
   never touches them. Zones are never edited: Freerouting sees them as planes, which other
   nets may cross, except zones named "kae-crit:..." (kae.route.critical's pours), which are
   also hard obstacles for the other nets.
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
    fanout=False,            # Freerouting's fanout pre-pass narrows tracks (see freerouting.py):
                             # True everywhere, "first" for the first route only (repair rounds
                             # re-route what was narrowed without it)
    thermal_repair=True,     # starved thermals get spoke corridors in the repair loop
    passes=0,                # 0: autorouter runs until it stops improving
    repair=True,             # post-route DRC repair loop
    rounds=5,                # repair rounds at most (each also bounded by the time left); "auto": until
                             # repair.FAILS rounds in a row are not better, or the time is spent (a round
                             # replaces the board only when it is better, so more rounds never make it worse)
    router_share=0.6,        # share of the budget for the first routing; "auto": max(0.6, 1 - repair_reserve_s
                             # / time left), the same 0.6 up to a 1,500 s budget and more beyond, since the
                             # router stops by itself (COMPLETED / STAGNATION) and leaves the rest to repair
    repair_reserve_s=600.0,  # with router_share "auto": the time kept for the repair rounds at long budgets
    last_mile=True,          # after the repair rounds, join what is still open with the grid router and
                             # rip-up (kae.route.lastmile; repair._last_mile). On by default since the
                             # A+B k=3 suite at 57487e6: cp1 0.727 -> 0.909, cpk 0.818 -> 0.970, 0 errors
    last_mile_reserve_s=90.0,  # with last_mile: the repair rounds stop this much before the deadline
    last_mile_free_first=True,  # one last-mile round before those that joins without ripping anything
    planes="cost",           # inner plane layers (translate.plane_layers): "cost" (traces there cost
                             # plane_cost x, so they go there only when nothing shorter exists), "keep"
                             # (Freerouting power layers, no traces; a repair round with open connections
                             # may use them), "strict" (power layers, never), "allow" (KiCad's types)
    plane_cost=4.0,          # plane-layer trace cost for planes="cost"
    outer_surcharge=None,    # outer-layer trace cost per signal layer beyond two (None: Freerouting's 0.2)
    neckdown=False,          # Freerouting's neck-down at pins, floored at the board's legal minimum width
    plane_escapes=True,      # before routing, join each pad of a zone net that the input's fill does not
                             # reach to that fill with a short stub and via (lastmile.plane_escapes),
                             # unlocked: the plane connections the human boards make first
    ball_escapes=True,       # with them, dog-bones for the inner rings of ball grids (escape.dog_bones)
    region=True,             # before the last mile, the dense windows holding open connections (ball grids,
                             # fine-pitch packages) are re-routed whole by negotiated congestion (kae.route.region,
                             # repair._region), kept only when KiCad's DRC ranks the board better
    region_share=0.5,        # with region: the share of the time left after the repair rounds it may take
    blocked=True,            # at the end, diagnose the connections still open (kae.route.blocked): the report's
                             # "blocked" names the board rule (or kae default) that makes each impossible
    blocked_s=30.0,          # with blocked: seconds kept for it at most (taken from the repair rounds)
    pad_shapes="kicad",      # pin shapes in the DSN: "kicad" (KiCad's export: rounded corners and arcs as
                             # chords inside the outline, up to 4 um at r 0.25 mm, 10 um on custom pads) or
                             # "outside" (polygons that contain the pad's copper, translate.circumscribe_pins)
)


# zones that kae.route.critical emitted: hard obstacles for the other nets
CRIT_PREFIX = "kae-crit:"


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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    own_wd = workdir is None
    wd = Path(workdir).resolve() if workdir else Path(tempfile.mkdtemp(prefix="kae-route-", dir=output_path.parent))
    wd.mkdir(parents=True, exist_ok=True)
    report = dict(input=str(input_path), seed=seed, budget_s=time_s, opts=opts)
    original_input = input_path

    def left():
        return time_s - (time.monotonic() - t0)

    try:
        # 1-2: export and plan
        kdsn = wd / "kicad.dsn"
        info = pcbnew_io.export_dsn(input_path, kdsn)
        sev = severities(input_path)
        opts["severities"] = sev
        opts["seed"] = seed
        if any((z.get("name") or "").startswith(CRIT_PREFIX) for z in info.get("zones") or []):
            opts["crit_zones"] = [z for z in pcbnew_io.zone_fills(input_path)["zones"]
                                  if (z.get("name") or "").startswith(CRIT_PREFIX)]
        p = constraints.plan(info, input_path, opts)
        planes = opts.get("plane_escapes") and any(z.get("net") for z in info.get("zones") or [])
        if planes or opts.get("ball_escapes"):
            from . import lastmile
            te = time.monotonic()
            staged = drc.stage_board(input_path, input_path, wd / "escapes")
            fills = pcbnew_io.zone_fills(staged)["zones"] if planes else []
            esc = wd / "escapes" / "escaped.kicad_pcb"
            got = lastmile.plane_escapes(staged, info, p, fills, esc, sev=sev, log=log, balls=opts.get("ball_escapes"),
                                         deadline=time.monotonic() + max(10.0, 0.1 * left()))
            report["plane_escapes"] = {k: v for k, v in got.items() if k != "added"}
            if got["added"]:
                esc_in = drc.stage_board(esc, input_path, wd / "escaped")
                input_path = esc_in
                info = pcbnew_io.export_dsn(input_path, kdsn)
                p = constraints.plan(info, input_path, opts)
            report["plane_escapes"]["seconds"] = round(time.monotonic() - te, 1)
        p.plane_policy = plane_policy(opts)
        p.plane_cost = opts.get("plane_cost")
        p.outer_surcharge = opts.get("outer_surcharge")
        p.pad_shapes = opts.get("pad_shapes") or "kicad"
        tree = specctra.read(kdsn)
        report["translate"] = translate.apply(tree, p, info)
        report["permuted"] = translate.permute(tree, seed)
        report["plan"] = plan_summary(p)
        dsn = wd / "board.dsn"
        specctra.write(tree, dsn)
        translate.write_rules(p, dsn)
        log(f"plan: {len(p.classes)} classes, {len(p.obstacle_classes)} obstacle classes, "
            f"{report['translate'].get('obstacles')} obstacles ({time.monotonic() - t0:.1f}s)")

        # 3: route. Freerouting stops itself at its job timeout and writes what it has; it is
        # killed only past its grace period, inside our deadline. If it still writes nothing,
        # one quick pass gives a partial board, and the output is never missing.
        settings = router_settings(p, opts)
        reserve = 20.0 if opts.get("repair") else 10.0
        grace = opts.get("router_grace", freerouting.GRACE_S)
        budget = router_budget(left(), opts)
        run = freerouting.route(dsn, wd / "board.ses", wd, passes=opts.get("passes") or 0, settings=settings,
                                budget_s=budget, hard_s=max(budget, min(budget + grace, left() - reserve)),
                                log_path=wd / "freerouting.log")
        report["router"] = dict(seconds=run.seconds, rc=run.rc, timed_out=run.timed_out, report=run.report,
                                settings=settings)
        log(f"freerouting: rc={run.rc} {run.seconds:.1f}s state={run.report.get('final_state')} "
            f"score={run.report.get('router_score')}")
        if run.ses is None and left() > 25:
            quick = max(10.0, min(60.0, (left() - 15) * 0.5))
            log(f"freerouting wrote no session ({'killed' if run.timed_out else 'rc=' + str(run.rc)}): "
                f"one quick pass ({quick:.0f}s)")
            run = freerouting.route(dsn, wd / "board_quick.ses", wd, passes=1, settings=settings, budget_s=quick,
                                    hard_s=max(quick, min(quick + grace, left() - 10)),
                                    log_path=wd / "freerouting_quick.log")
            report["router_quick"] = dict(seconds=run.seconds, rc=run.rc, timed_out=run.timed_out,
                                          report=run.report)
        if run.ses is None:
            # nothing from the router (a board too big for one pass in the time: polarfire SoM,
            # every attempt): the input goes on unrouted, and the repair rounds and the last
            # mile route what they can, instead of ending the attempt with no board
            shutil.copy2(input_path, output_path)
            from .critical_write import routing
            routed = routing(output_path)
            report["status"] = "no_session"
        else:
            # 4: import
            ses = specctra.read(run.ses)
            report["session"] = translate.fix_session(ses, p)
            ses_k = wd / "board_kicad.ses"
            specctra.write(ses, ses_k)
            routed = pcbnew_io.import_ses(input_path, ses_k, output_path).get("routing") or []
            report["status"] = "routed"
        # the input's locked tracks and vias (pre-routes): exported as fixed wiring, never
        # returned by Freerouting, kept as they are by KiCad's import; the repair loop never
        # rips, widens or unlocks them
        opts["fixed_uuids"] = sorted(r["uuid"] for r in routed if r.get("locked"))
        report["fixed_items"] = len(opts["fixed_uuids"])

        # 5: DRC and repair
        diag_s = min(float(opts.get("blocked_s") or 0.0), 0.05 * time_s) if opts.get("blocked") else 0.0
        if opts.get("repair") and left() > 30:
            from . import repair
            report["repair"] = repair.loop(input_path, output_path, wd, p, info, opts,
                                           deadline=t0 + time_s - 10 - diag_s, log=log)
            final_rep = report["repair"].pop("_report", None)
            if diag_s and final_rep and (report["repair"].get("final") or {}).get("unconnected"):
                regions = [r["region"] for r in report["repair"].get("rounds") or [] if r.get("region")]
                report["blocked"] = diagnose(output_path, input_path, original_input, info, p, final_rep, sev, wd,
                                             deadline=time.monotonic() + max(5.0, left() - 8), log=log,
                                             regions=regions)
        elif opts.get("drc", True) and left() > 20:
            staged = drc.stage_board(output_path, input_path, wd / "drc")
            rep = drc.run(staged, wd / "drc" / "drc.json", timeout=max(10, left() - 5))
            report["drc"] = drc.summary(rep)
        return report
    finally:
        report["opts"] = {k: v for k, v in opts.items()
                          if k not in ("crit_zones", "fixed_uuids", "severities", "soft_fixed", "physics_guard")}
        report["seconds"] = round(time.monotonic() - t0, 2)
        if own_wd and not opts.get("keep"):
            shutil.rmtree(wd, ignore_errors=True)
        else:
            report["workdir"] = str(wd)


def diagnose(output_path, input_path, original_input, info, plan, drc_report, sev, wd, deadline, log=_log, regions=()):
    """kae.route.blocked on the final board: what makes each open connection impossible."""
    from kae.board.kicad_file import load
    from . import blocked
    try:
        staged = drc.stage_board(output_path, input_path, wd / "blocked")
        fills = pcbnew_io.zone_fills(staged)["zones"]
        inb = load(original_input)
        ids = {t.uuid for t in inb.tracks} | {v.uuid for v in inb.vias}
        out = blocked.diagnose(staged, info, plan, fills, drc_report, sev=sev, input_ids=ids, deadline=deadline,
                               log=log, regions=regions)
        log(f"blocked: {len(out['blocked'])} connections the rules block, {len(out['congestion'])} congestion, "
            f"{out['undiagnosed']} not diagnosed ({out['seconds']} s)")
        return out
    except Exception as e:  # noqa: BLE001 - a diagnosis never costs the routed board
        log(f"blocked: diagnosis failed: {type(e).__name__}: {e}")
        return dict(error=f"{type(e).__name__}: {e}")


def router_budget(left_s, opts):
    """Seconds for the first routing out of `left_s`: router_share of it (router_share_alone
    without the repair loop); router_share "auto" keeps repair_reserve_s for the repair
    rounds and never gives the router less than 0.6."""
    if not opts.get("repair"):
        share = opts.get("router_share_alone", 0.9)
    else:
        share = opts.get("router_share", 0.6)
        if share == "auto":
            reserve = float(opts.get("repair_reserve_s", 600.0))
            share = max(0.6, 1.0 - reserve / max(left_s, 1.0))
    return max(20.0, left_s * float(share))


def plane_policy(opts, free_round_with_open=False):
    """translate's plane_policy for a routing: 'cost' (inner planes priced high), 'power'
    (inner planes carry no traces) or 'signal'. With opts planes 'keep', a repair round with
    open connections falls back to 'signal'."""
    pol = opts.get("planes", "cost")
    if pol == "cost":
        return "cost"
    if pol == "allow" or (pol == "keep" and free_round_with_open):
        return "signal"
    return "power"


def router_settings(p, opts, repair=False):
    # neck-down at pins: a net class's width is KiCad's default, not a limit (DRC checks the
    # board minimum and custom rules); with the fork's floor (min_trace_width_um, the largest
    # legal minimum) Freerouting may narrow a track into a pin narrower than the class
    neck = bool(opts.get("neckdown")) and bool(p.min_width)
    s = {"automatic_neckdown": "true" if neck else "false"}
    fan = opts.get("fanout")
    if not fan or (repair and fan == "first"):
        s["fanout.enabled"] = "false"
    s["copper_to_edge_clearance_um"] = specctra.fmt(p.edge_clearance * 1000)
    if p.neck_width:
        s["neck_width_um"] = specctra.fmt(p.neck_width * 1000)
    if p.min_width:
        # the fork's floor for every neck-down (pads, fanout, retries); older builds ignore it
        s["min_trace_width_um"] = specctra.fmt(p.min_width * 1000)
    return s


def plan_summary(p):
    return dict(
        classes={n: dict(nets=len(rc.nets), netclass=rc.netclass, widths=rc.widths, via=rc.via)
                 for n, rc in p.classes.items()},
        obstacle_classes=len(p.obstacle_classes), obstacles=len(p.obstacles), net_graphics=len(p.net_graphics),
        pins=len(p.pin_class), edge_clearance=p.edge_clearance, neck_width=p.neck_width, min_width=p.min_width,
        notes={k: v for k, v in p.notes.items() if k != "same_net_via_pitch"})
