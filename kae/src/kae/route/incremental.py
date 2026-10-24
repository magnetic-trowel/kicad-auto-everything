# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Incremental routing for small changes: route only what is open, fast.

    rep = route_open(input, output, seed=0, time_s=30)

For the joint loop's windows (kae.joint): a board whose routing is all locked except what a
window ripped up. The constraint translation is the bridge's (constraints.plan,
translate.apply, the bridge's router settings); what differs is how hard Freerouting works:

- every routing item of the input is locked: Freerouting sees it as fixed wiring and routes
  only the open connections (the bridge's own export does this; nothing to change);
- `passes` autorouter passes (default 1; `-mp`), the post-route optimizer off
  (`--router.optimizer.enabled=false`), so Freerouting stops when its pass ends, or
  earlier when nothing is left to route;
- the fork's `item_order_seed` gives the item order of `seed` (the bridge's DSN permutation
  is applied too, for builds without it);
- no repair rounds, no DRC: the caller runs the single KiCad DRC on its final board (the
  joint loop does, after it drops its guard pours, which a DRC here would count as copper).

A run that writes no session leaves OUTPUT = INPUT (status no_session).
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from kae.board import pcbnew_io

from . import constraints, freerouting, specctra, translate

DEFAULTS = dict(passes=1, optimizer=False, router_share=0.9, grace=10.0)


def _log(msg):
    print(f"[kae.route.incremental {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def route_open(input_path, output_path, seed=0, time_s=30.0, workdir=None, opts=None, log=_log):
    """Route the open connections of INPUT (all its routing fixed) into OUTPUT. Returns a
    JSON-able report (status routed | no_session | error, router seconds and state,
    seconds by step)."""
    from . import bridge as BR
    t0 = time.monotonic()
    o = {**BR.DEFAULT_OPTS, **DEFAULTS, **(opts or {})}
    o["repair"] = False
    input_path, output_path = Path(input_path).resolve(), Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    own_wd = workdir is None
    wd = Path(workdir).resolve() if workdir else Path(tempfile.mkdtemp(prefix="kae-inc-", dir=output_path.parent))
    wd.mkdir(parents=True, exist_ok=True)
    rep = dict(input=str(input_path), seed=seed, budget_s=time_s, steps={})

    def step(name, t):
        rep["steps"][name] = round(time.monotonic() - t, 2)

    def left():
        return time_s - (time.monotonic() - t0)

    try:
        t = time.monotonic()
        kdsn = wd / "kicad.dsn"
        info = pcbnew_io.export_dsn(input_path, kdsn)
        o["severities"] = BR.severities(input_path)
        o["seed"] = seed
        crit = getattr(BR, "CRIT_PREFIX", "kae-crit:")
        if any((z.get("name") or "").startswith(crit) for z in info.get("zones") or []):
            o["crit_zones"] = [z for z in pcbnew_io.zone_fills(input_path)["zones"]
                               if (z.get("name") or "").startswith(crit)]
        step("export", t)
        t = time.monotonic()
        p = constraints.plan(info, input_path, o)
        if hasattr(BR, "plane_policy"):
            p.plane_policy = BR.plane_policy(o)
            p.plane_cost = o.get("plane_cost")
        tree = specctra.read(kdsn)
        rep["translate"] = translate.apply(tree, p, info)
        translate.permute(tree, seed)
        dsn = wd / "board.dsn"
        specctra.write(tree, dsn)
        if hasattr(translate, "write_rules"):
            translate.write_rules(p, dsn)
        step("plan", t)

        t = time.monotonic()
        settings = dict(BR.router_settings(p, o))
        if not o.get("optimizer"):
            settings["optimizer.enabled"] = "false"
        settings["item_order_seed"] = str(int(seed) % 2_147_483_647)
        budget = max(8.0, left() * float(o["router_share"]))
        run = freerouting.route(dsn, wd / "board.ses", wd, passes=int(o.get("passes") or 1), settings=settings,
                                budget_s=budget, hard_s=max(budget, min(budget + float(o["grace"]), left())),
                                log_path=wd / "freerouting.log")
        step("router", t)
        rep["router"] = dict(seconds=round(run.seconds, 2), rc=run.rc, timed_out=run.timed_out,
                             state=(run.report or {}).get("final_state"), settings=settings)
        log(f"freerouting: rc={run.rc} {run.seconds:.1f}s state={(run.report or {}).get('final_state')}")
        if run.ses is None:
            shutil.copy2(input_path, output_path)
            rep["status"] = "no_session"
            return rep
        t = time.monotonic()
        ses = specctra.read(run.ses)
        rep["session"] = translate.fix_session(ses, p)
        ses_k = wd / "board_kicad.ses"
        specctra.write(ses, ses_k)
        pcbnew_io.import_ses(input_path, ses_k, output_path)
        step("import", t)
        rep["status"] = "routed"
        return rep
    except Exception as e:  # noqa: BLE001 - the caller judges the board; leave the input
        import traceback
        rep["status"] = "error"
        rep["error"] = f"{type(e).__name__}: {e}"
        rep["trace"] = traceback.format_exc(limit=4)
        if not output_path.exists():
            shutil.copy2(input_path, output_path)
        return rep
    finally:
        rep["seconds"] = round(time.monotonic() - t0, 2)
        if own_wd and not o.get("keep"):
            shutil.rmtree(wd, ignore_errors=True)
        else:
            rep["workdir"] = str(wd)
