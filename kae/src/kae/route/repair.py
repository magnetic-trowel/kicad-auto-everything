# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Post-route repair driven by KiCad's DRC.

Each round runs kicad-cli DRC (zones refilled, as the scorer does) on the current board and
reads every error-level violation and missing connection:

- a track narrower than its rule (track_width on a routed track) is widened to the
  required minimum, in place;
- any other violation that involves routed copper (a track or via the router drew) rips up
  every routed item of the nets involved;
- a missing connection marks its net for routing again; when the connection runs through a
  zone (Freerouting counts every pin inside a plane as connected, KiCad's fill does not when
  other nets cut it into islands or starve its spokes), the net's planes on those layers are
  left out of the next DSN, so the router has to connect those pins with copper.

The remaining routing is locked (exported as fixed wiring), Freerouting routes only what is
open, the session is imported on top, the routing unlocked again, and the result checked by
the next round's DRC. A round's board replaces the output only if it is better (fewer
missing connections, then fewer errors), so the output never gets worse. Stops when the
board is clean, nothing more can be done, the round limit is reached, or time runs out.
"""
import json
import re
import shutil
import time
from pathlib import Path

from kae.board import pcbnew_io

from . import constraints, drc, freerouting, specctra, translate
from .specctra import find, findall

_NET = re.compile(r"\[([^\]]*)\]")
_MIN = re.compile(r"min (?:width )?([\d.]+) mm")
_LAYER = re.compile(r" on ([A-Za-z0-9_.]+)")


def _key(s):
    """Better boards sort higher: clean, then fewer missing connections, then fewer errors."""
    return (s["errors"] == 0 and s["unconnected"] == 0, -s["unconnected"], -s["errors"])


def _nets_of(item_desc):
    return [m for m in _NET.findall(item_desc or "") if m and m != "<no net>"]


def _routed_geom(r):
    from shapely.geometry import LineString, Point
    if r["kind"] == "via":
        return Point(r["pos"]).buffer(r["size"] / 2, quad_segs=16)
    return LineString([r["a"], r["b"]]).buffer(r["width"] / 2, quad_segs=8)


def analyse(report, routed, info=None, plan=None, thermal=None):
    """What a DRC report asks for, given `routed` = {uuid: routing item}: {widen: {uuid: mm},
    rip: {net}, open: {net: set(layers) or None}, thermal: {pad uuid}, unattributed: [type]}.

    A starved thermal, or a pad that misses its own zone, gets a spoke corridor (see
    constraints.thermal_corridors) and the routed nets that cross it are ripped up."""
    widen, rip, opened, other = {}, set(), {}, []
    pads = {pd.get("uuid"): pd for pd in (info or {}).get("pads", []) if pd.get("uuid")}
    want_corridor = set()
    for v in drc.errors(report):
        items = v.get("items") or []
        if v.get("type") == "starved_thermal":
            want_corridor.update(it.get("uuid") for it in items if it.get("uuid") in pads)
            continue
        ours = [it for it in items if it.get("uuid") in routed]
        if not ours:
            other.append(v.get("type"))
            continue
        if v.get("type") == "track_width":
            m = _MIN.search(v.get("description", ""))
            for it in ours:
                r = routed[it["uuid"]]
                if m and r["kind"] in ("track", "arc"):
                    widen[it["uuid"]] = float(m.group(1)) + 1e-4
                else:
                    rip.add(r["net"])
            continue
        for it in ours:
            rip.add(routed[it["uuid"]]["net"])
    for u in report.get("unconnected_items") or []:
        items = u.get("items") or []
        nets = {n for it in items for n in _nets_of(it.get("description"))}
        zone_layers, has_zone = set(), False
        pad_ids = [it.get("uuid") for it in items if it.get("uuid") in pads]
        for it in items:
            d = it.get("description") or ""
            if d.startswith("Zone") or d.startswith("Teardrop"):
                has_zone = True
                for lm in re.finditer(r"on ([A-Za-z0-9_.]+(?: and [A-Za-z0-9_.]+)*)", d):
                    zone_layers.update(x.strip() for x in lm.group(1).split(" and "))
        if has_zone and pad_ids:
            want_corridor.update(pad_ids)  # a pad cut off from its zone
            continue
        for n in nets:
            if has_zone:
                cur = opened.get(n, set())
                opened[n] = None if cur is None else (cur | zone_layers)
            else:
                opened[n] = None  # re-route; a plane of the net may have hidden the gap
    new_thermal = set()
    if want_corridor and info is not None and plan is not None:
        from shapely.strtree import STRtree
        from .constraints import thermal_corridors
        geoms = {u: _routed_geom(r) for u, r in routed.items()}
        keys = list(geoms)
        tree = STRtree([geoms[k] for k in keys]) if keys else None
        for geo, layer, pad in thermal_corridors(info, plan, want_corridor):
            new_thermal.add(pad["uuid"])
            if tree is None:
                continue
            for i in tree.query(geo, predicate="intersects"):
                r = routed[keys[int(i)]]
                if r["net"] != pad["net"] and (r["kind"] == "via" or r.get("layer") == layer):
                    rip.add(r["net"])
    return dict(widen=widen, rip=rip, open=opened, thermal=new_thermal, unattributed=other)


def _drop_planes(tree, nets_layers):
    """Remove the planes of nets (on the given layers; all layers when None) from a DSN."""
    struct = find(tree, "structure")
    n = 0
    for pl in findall(struct, "plane"):
        net = str(pl[1]) if len(pl) > 1 else ""
        if net not in nets_layers:
            continue
        layers = nets_layers[net]
        shape = next((c for c in pl[2:] if isinstance(c, list)), None)
        layer = str(shape[1]) if shape is not None and len(shape) > 1 else ""
        if layers is None or not layers or layer in layers:
            struct.remove(pl)
            n += 1
    return n


def loop(input_path, output_path, wd, plan, info, opts, deadline, log=print):
    """Repair `output_path` in place (see the module docstring). Returns a report."""
    wd = Path(wd)
    output_path = Path(output_path)
    rounds = []
    t_start = time.monotonic()

    def left():
        return deadline - time.monotonic()

    def check(board, d):
        staged = drc.stage_board(board, input_path, d)
        return drc.run(staged, d / "drc.json", timeout=max(10, left() - 5))

    thermal = set(opts.get("thermal_pads") or [])
    sev = opts.get("severities") or {}
    try:
        best_rep = check(output_path, wd / "repair0" / "drc")
    except drc.DrcError as e:
        return dict(rounds=[dict(round=0, drc_error=str(e))], final=None)
    best = drc.summary(best_rep)
    rounds.append(dict(round=0, **best))
    log(f"repair round 0: {best['errors']} errors {best['by_type']}, {best['unconnected']} unconnected")
    modes = list(opts.get("repair_modes") or ("fixed", "free"))
    mode_i = 0
    for k in range(1, int(opts.get("rounds", 3)) + 1):
        if best["errors"] == 0 and best["unconnected"] == 0:
            break
        mode = modes[mode_i]
        rec = dict(round=k, mode=mode)
        rounds.append(rec)
        if left() < 45:
            rec["stopped"] = "time"
            break
        rdir = wd / f"repair{k}"
        if rdir.exists():
            shutil.rmtree(rdir)
        rdir.mkdir(parents=True)
        listing = pcbnew_io.edit_routing(output_path, rdir / "listing.kicad_pcb")["routing"]
        routed = {r["uuid"]: r for r in listing if not r.get("locked")}
        a = analyse(best_rep, routed, info, plan)
        rec.update(widen=len(a["widen"]), rip=sorted(a["rip"]), open=sorted(a["open"]),
                   thermal=len(a["thermal"] - thermal), unattributed=sorted(set(a["unattributed"])))
        if a["thermal"] - thermal and opts.get("thermal_repair", True):
            thermal |= a["thermal"]
            plan = constraints.plan(info, input_path, dict(opts, severities=sev, thermal_pads=sorted(thermal)))
        elif not a["widen"] and not a["rip"] and not a["open"]:
            rec["stopped"] = "nothing attributable"
            break
        # 1. widen and rip up; lock the rest
        rip_uuids = [u for u, r in routed.items() if r["net"] in a["rip"]]
        fixed = drc.stage_board(output_path, input_path, rdir / "fixed")
        # fixed: the rest of the routing is locked (exported as fixed wiring); free: it stays
        # routable, so Freerouting may shove or re-route it to make room
        pcbnew_io.edit_routing(fixed, fixed, delete=rip_uuids, widths=a["widen"], lock_all=mode == "fixed")
        cand = rdir / "cand.kicad_pcb"
        if a["rip"] or a["open"]:
            # 2. route what is open, everything else fixed
            dsn_k = rdir / "kicad.dsn"
            pcbnew_io.export_dsn(fixed, dsn_k, probes=False)
            tree = specctra.read(dsn_k)
            translate.apply(tree, plan, info)
            rec["planes_dropped"] = _drop_planes(tree, a["open"])
            dsn = rdir / "board.dsn"
            specctra.write(tree, dsn)
            budget = max(15.0, min(left() * 0.5, left() - 30))
            from .bridge import router_settings
            run = freerouting.route(dsn, rdir / "board.ses", rdir, passes=opts.get("passes") or 0,
                                    settings=router_settings(plan, opts), budget_s=budget,
                                    log_path=rdir / "freerouting.log")
            rec["router"] = dict(seconds=run.seconds, state=run.report.get("final_state"),
                                 score=run.report.get("router_score"))
            if run.ses is None:
                rec["stopped"] = "router produced no session"
                break
            ses = specctra.read(run.ses)
            translate.fix_session(ses, plan)
            ses_k = rdir / "board_kicad.ses"
            specctra.write(ses, ses_k)
            pcbnew_io.import_ses(fixed, ses_k, cand)
            pcbnew_io.edit_routing(cand, cand, unlock_all=True)
        else:
            pcbnew_io.edit_routing(fixed, cand, unlock_all=True)
        if left() < 10:
            rec["stopped"] = "time"
            break
        try:
            rep = check(cand, rdir / "drc")
        except drc.DrcError as e:
            rec["drc_error"] = str(e)
            break
        s = drc.summary(rep)
        rec.update(s)
        if _key(s) > _key(best):
            shutil.copy2(cand, output_path)
            best, best_rep = s, rep
            rec["kept"] = True
        else:
            rec["kept"] = False
        log(f"repair round {k} ({mode}): {s['errors']} errors {s['by_type']}, {s['unconnected']} unconnected "
            f"({'kept' if rec['kept'] else 'discarded'})")
        if not rec["kept"]:
            mode_i += 1
            if mode_i >= len(modes):
                rec["stopped"] = "no improvement"
                break
        else:
            mode_i = 0
    return dict(rounds=rounds, final=best, seconds=round(time.monotonic() - t_start, 1))
