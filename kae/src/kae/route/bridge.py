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
import math
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
    last_mile_rounds=4,      # last-mile rip-up rounds at most (each joins what the previous one left or ripped)
    last_mile_free_first=True,  # one last-mile round before those that joins without ripping anything
    planes="cost",           # inner plane layers (translate.plane_layers): "cost" (traces there cost
                             # plane_cost x, so they go there only when nothing shorter exists), "keep"
                             # (Freerouting power layers, no traces; a repair round with open connections
                             # may use them), "strict" (power layers, never), "allow" (KiCad's types)
    plane_cost=4.0,          # plane-layer trace cost for planes="cost"
    neckdown=False,          # Freerouting's neck-down at pins, floored at the board's legal minimum width
    escapes=False,           # escape pre-pass (kae.route.escape): dog-bones of grid packages' balls laid
                             # before Freerouting; "lock" keeps them as fixed copper, "soft" (or True) unlocks
                             # them after the first routing so the repair rounds and last mile may rip them
    pad_shapes="kicad",      # pin shapes in the DSN: "kicad" (KiCad's export: rounded corners and arcs as
                             # chords inside the outline, up to 4 um at r 0.25 mm, 10 um on custom pads) or
                             # "outside" (polygons that contain the pad's copper, translate.circumscribe_pins)
)


# zones that kae.route.critical emitted: hard obstacles for the other nets
CRIT_PREFIX = "kae-crit:"
# mm around a pad whose thermal relief new escapes starve: escapes there are taken out
ESCAPE_SPOKE_MM = 1.2


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

    def left():
        return time_s - (time.monotonic() - t0)

    try:
        # 1-2: export and plan
        kdsn = wd / "kicad.dsn"
        info = pcbnew_io.export_dsn(input_path, kdsn)
        sev = severities(input_path)
        opts["severities"] = sev
        opts["seed"] = seed
        route_input = input_path          # the board Freerouting's session is imported into
        escape_uuids = []
        if opts.get("escapes"):
            route_input, escape_uuids, report["escapes"] = _escape_prepass(input_path, info, opts, wd, log,
                                                                            deadline=t0 + time_s * 0.25)
            if escape_uuids:
                info = pcbnew_io.export_dsn(route_input, kdsn)
        if any((z.get("name") or "").startswith(CRIT_PREFIX) for z in info.get("zones") or []):
            opts["crit_zones"] = [z for z in pcbnew_io.zone_fills(input_path)["zones"]
                                  if (z.get("name") or "").startswith(CRIT_PREFIX)]
        p = constraints.plan(info, route_input, opts)
        p.plane_policy = plane_policy(opts)
        p.plane_cost = opts.get("plane_cost")
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
            shutil.copy2(input_path, output_path)   # the input, unrouted: a board in every case
            report["status"] = "no_session"
            return report

        # 4: import
        ses = specctra.read(run.ses)
        report["session"] = translate.fix_session(ses, p)
        ses_k = wd / "board_kicad.ses"
        specctra.write(ses, ses_k)
        imported = pcbnew_io.import_ses(route_input, ses_k, output_path)
        # the input's locked tracks and vias (pre-routes): exported as fixed wiring, never
        # returned by Freerouting, kept as they are by KiCad's import; the repair loop never
        # rips, widens or unlocks them
        soft = set(escape_uuids) if opts.get("escapes") != "lock" else set()
        if soft:
            from . import critical_write as W
            W.edit(output_path, output_path, unlock=sorted(soft))
        opts["fixed_uuids"] = sorted(r["uuid"] for r in imported.get("routing") or []
                                     if r.get("locked") and r["uuid"] not in soft)
        report["fixed_items"] = len(opts["fixed_uuids"])
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
        report["opts"] = {k: v for k, v in opts.items()
                          if k not in ("crit_zones", "fixed_uuids", "severities", "soft_fixed", "physics_guard")}
        report["seconds"] = round(time.monotonic() - t0, 2)
        if own_wd and not opts.get("keep"):
            shutil.rmtree(wd, ignore_errors=True)
        else:
            report["workdir"] = str(wd)


def _escape_prepass(input_path, info, opts, wd, log, deadline=None):
    """(board with the escapes as locked copper, their uuids, report); the input itself when
    there is nothing to lay. With escape_drc (default), the escapes are laid as planned and
    checked by KiCad's DRC: a dog-bone or stub in an error the input did not have, or within
    ESCAPE_SPOKE_MM of a pad whose thermal relief it starves, is taken out, and the board
    checked again (twice at most; then the guarded plan, which keeps the vias off the
    plan's spoke strips, without a check)."""
    from kae.board.kicad_file import load

    from . import critical_write as W
    from . import escape
    from .critical_space import Space
    t = time.monotonic()
    check = bool(opts.get("escape_drc", True))
    p0 = constraints.plan(info, input_path, opts)

    def plan(guard):
        sp = Space(load(input_path), info, plan=p0, sev=opts.get("severities") or {})
        got = escape.plan_escapes(input_path, info, p0, space=sp, opts=dict(opts, escape_spoke_guard=guard), log=log)
        groups = []          # one dog-bone (stub + via) or one row stub each
        nv = len(got["vias"])
        for k, (net, layer, w, a, b) in enumerate(got["tracks"]):
            g = [("t", (net, layer, w, a, b, W.new_uuid(), True))]
            if k < nv:
                net_, x, y, D, d = got["vias"][k]
                g.append(("v", (net_, x, y, D, d, W.new_uuid(), True)))
            groups.append(g)
        return got["report"], groups

    def write(groups):
        board = W.stage(input_path, wd / "escaped", "board")
        W.append_items(board, board, tracks=[it for g in groups for k, it in g if k == "t"],
                       vias=[it for g in groups for k, it in g if k == "v"])
        return board

    rep, groups = plan(not check)
    if not groups:
        return input_path, [], dict(rep, seconds=round(time.monotonic() - t, 1))
    board = write(groups)
    if check:
        from . import repair
        dl = deadline or (time.monotonic() + 900)
        base = repair.input_errors(input_path, wd, dl)
        try:
            ref = json.loads((wd / "input_drc" / "drc.json").read_text())
        except (OSError, ValueError):
            ref = None
        sig = lambda v: (v["type"], tuple(sorted(i.get("uuid", "") for i in v.get("items", []))))
        old = {sig(v) for v in drc.errors(ref)} if ref else set()
        dropped = 0
        for attempt in range(3):
            if ref is None:
                break
            rp = drc.run(drc.stage_board(board, input_path, wd / "escaped_drc"), wd / "escaped_drc" / "drc.json",
                         timeout=max(30, min(900, dl - time.monotonic() - 60)))
            new = [v for v in drc.errors(rp) if sig(v) not in old]
            if not new and drc.excess(drc.summary(rp), base) <= 0:
                break
            if attempt == 2:
                rep, groups = plan(True)
                board = write(groups) if groups else input_path
                rep["escape_drc"] = "guarded"
                break
            uu = {i.get("uuid") for v in new for i in v.get("items", [])}
            pts = [(i["pos"]["x"], i["pos"]["y"]) for v in new for i in v.get("items", [])
                   if not (i.get("description") or "").startswith("Zone")]
            reach = float(opts.get("escape_spoke_mm", ESCAPE_SPOKE_MM))

            def hit(g):
                for k, it in g:
                    if it[5] in uu:
                        return True
                    xy = [it[3], it[4]] if k == "t" else [(it[1], it[2])]
                    if any(math.dist(q, p) < reach for q in xy for p in pts):
                        return True
                return False
            keep = [g for g in groups if not hit(g)]
            dropped += len(groups) - len(keep)
            if len(keep) == len(groups):
                rep, groups = plan(True)
                board = write(groups) if groups else input_path
                rep["escape_drc"] = "guarded"
                break
            groups = keep
            board = write(groups)
        rep["dropped"] = dropped
    rep["seconds"] = round(time.monotonic() - t, 1)
    if not groups:
        return input_path, [], rep
    uuids = [it[5] for g in groups for _k, it in g]
    log(f"escapes: {sum(1 for g in groups if len(g) == 2)} dog-bones, "
        f"{sum(1 for g in groups if len(g) == 1)} row stubs laid ({rep['seconds']}s)")
    return board, uuids, rep


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
