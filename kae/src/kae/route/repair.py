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
violations in all, then fewer missing connections), so the output never gets worse. Stops when the
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
    """Better boards sort higher: clean, then fewer violations in all (errors plus missing
    connections), then fewer missing connections."""
    return (s["errors"] == 0 and s["unconnected"] == 0, -(s["errors"] + s["unconnected"]), -s["unconnected"])


def _nets_of(item_desc):
    return [m for m in _NET.findall(item_desc or "") if m and m != "<no net>"]


def _routed_geom(r, grow=0.0):
    from shapely.geometry import LineString, Point
    if r["kind"] == "via":
        return Point(r["pos"]).buffer(r["size"] / 2 + grow, quad_segs=16)
    return LineString([r["a"], r["b"]]).buffer(r["width"] / 2 + grow, quad_segs=8)


class _Space:
    """Foreign copper around routed items, with the clearance the plan requires, to decide
    whether a track can be widened in place."""

    def __init__(self, routed, info, plan):
        from shapely.strtree import STRtree
        from .constraints import _pad_shapes, _poly
        self.routed, self.plan = routed, plan
        self.items = []   # (geometry, net, kind, layer or None, obstacle class or None)
        for u, r in routed.items():
            self.items.append((_routed_geom(r), r["net"], "routed", r.get("layer"), None, u))
        for pd in info.get("pads") or []:
            _, real = _pad_shapes(pd)
            cls = plan.pin_class.get((pd.get("comp"), pd.get("pin")))
            for l, g in real.items():
                if g is not None and not g.is_empty:
                    self.items.append((g, pd.get("net") or "", "pad", l, cls, None))
        for g in info.get("graphics") or []:
            for l, polys in (g.get("layers") or {}).items():
                for rr in polys:
                    pg = _poly(rr)
                    if pg is not None:
                        self.items.append((pg, g.get("net") or "", "graphic", l, None, None))
        self.tree = STRtree([it[0] for it in self.items]) if self.items else None

    def _need(self, net, layer, it):
        cls = self.plan.net_class.get(net)
        other = it[1]
        if it[2] == "routed":
            ocls = self.plan.net_class.get(other)
            a, b = sorted((cls, ocls)) if cls and ocls else (cls, ocls)
            v = self.plan.matrix.get((a, b, layer), (0.2, 0.2, 0.2))
            r = self.routed.get(it[5])
            return v[1] if r is not None and r["kind"] == "via" else v[0]
        if it[2] == "pad" and it[4] in self.plan.obstacle_classes:
            return self.plan.obstacle_classes[it[4]].values.get((cls, layer), (0.2, 0.2))[0]
        vals = [oc.values.get((cls, layer)) for n, oc in self.plan.obstacle_classes.items() if n.startswith("kae_cu")]
        return max([v[0] for v in vals if v is not None] or [0.2])

    def fits(self, uuid, width):
        """Whether routed track `uuid` widened to `width` keeps every required clearance."""
        r = self.routed[uuid]
        from shapely.geometry import LineString
        seg = LineString([r["a"], r["b"]]).buffer(width / 2, quad_segs=8)
        if self.tree is None:
            return True
        for i in self.tree.query(seg.buffer(1.0)):
            it = self.items[int(i)]
            if it[1] == r["net"] and r["net"]:
                continue
            if it[3] is not None and it[3] != r["layer"] and not (it[2] == "routed" and self.routed[it[5]]["kind"] == "via"):
                continue
            if seg.distance(it[0]) < self._need(r["net"], r["layer"], it) - 1e-6:
                return False
        return True


def analyse(report, routed, info=None, plan=None):
    """What a DRC report asks for, given `routed` = {uuid: routing item}:
    widen {uuid: mm}, items {uuid} and nets {net} to rip up, open {net: set(layers) or None},
    thermal {pad uuid}, unattributed [type].

    A track narrower than its rule is widened in place when the plan's clearances allow it,
    otherwise ripped up. A starved thermal, or a pad that misses its own zone, gets a spoke
    corridor (constraints.thermal_corridors) and the routed items crossing it are ripped up."""
    widen, items, nets, opened, other = {}, set(), set(), {}, []
    pads = {pd.get("uuid"): pd for pd in (info or {}).get("pads", []) if pd.get("uuid")}
    want_corridor = set()
    space = None
    for v in drc.errors(report):
        its = v.get("items") or []
        if v.get("type") == "starved_thermal":
            want_corridor.update(it.get("uuid") for it in its if it.get("uuid") in pads)
            continue
        ours = [it for it in its if it.get("uuid") in routed]
        if not ours:
            other.append(v.get("type"))
            continue
        if v.get("type") == "track_width":
            m = _MIN.search(v.get("description", ""))
            for it in ours:
                r = routed[it["uuid"]]
                w = float(m.group(1)) + 1e-4 if m else None
                if w and r["kind"] in ("track", "arc") and info is not None and plan is not None:
                    space = space or _Space(routed, info, plan)
                    if space.fits(it["uuid"], w):
                        widen[it["uuid"]] = w
                        continue
                items.add(it["uuid"])
                nets.add(r["net"])
            continue
        for it in ours:
            items.add(it["uuid"])
            nets.add(routed[it["uuid"]]["net"])
    for u in report.get("unconnected_items") or []:
        its = u.get("items") or []
        uns = {n for it in its for n in _nets_of(it.get("description"))}
        zone_layers, has_zone = set(), False
        pad_ids = [it.get("uuid") for it in its if it.get("uuid") in pads]
        for it in its:
            d = it.get("description") or ""
            if d.startswith("Zone") or d.startswith("Teardrop"):
                has_zone = True
                for lm in re.finditer(r"on ([A-Za-z0-9_.]+(?: and [A-Za-z0-9_.]+)*)", d):
                    zone_layers.update(x.strip() for x in lm.group(1).split(" and "))
        if has_zone and pad_ids:
            want_corridor.update(pad_ids)  # a pad cut off from its zone
            continue
        for n in uns:
            if has_zone:
                cur = opened.get(n, set())
                opened[n] = None if cur is None else (cur | zone_layers)
            else:
                opened[n] = None  # re-route; a plane of the net may have hidden the gap
    thermal = set()
    if want_corridor and info is not None and plan is not None:
        from shapely.strtree import STRtree
        from .constraints import thermal_corridors
        keys = list(routed)
        tree = STRtree([_routed_geom(routed[k]) for k in keys]) if keys else None
        for geo, layer, pad in thermal_corridors(info, plan, want_corridor):
            thermal.add(pad["uuid"])
            if tree is None:
                continue
            for i in tree.query(geo, predicate="intersects"):
                r = routed[keys[int(i)]]
                if r["net"] != pad["net"] and (r["kind"] == "via" or r.get("layer") == layer):
                    items.add(r["uuid"])
                    nets.add(r["net"])
    return dict(widen=widen, items=items, nets=nets, open=opened, thermal=thermal, unattributed=other)


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


# Escalation: rip only the offending items with the rest fixed; then their whole nets; then
# their whole nets with the rest of the routing left to the router.
LEVELS = ("items", "nets", "free")


def loop(input_path, output_path, wd, plan, info, opts, deadline, log=print):
    """Repair `output_path` in place (see the module docstring). Returns a report."""
    wd = Path(wd)
    output_path = Path(output_path)
    rounds = []
    t_start = time.monotonic()
    thermal = set(opts.get("thermal_pads") or []) if opts.get("thermal_pads") != "all" else set()
    sev = opts.get("severities") or {}

    def left():
        return deadline - time.monotonic()

    def check(board, d):
        staged = drc.stage_board(board, input_path, d)
        return drc.run(staged, d / "drc.json", timeout=max(10, left() - 5))

    try:
        best_rep = check(output_path, wd / "repair0" / "drc")
    except drc.DrcError as e:
        return dict(rounds=[dict(round=0, drc_error=str(e))], final=None)
    best = drc.summary(best_rep)
    rounds.append(dict(round=0, **best))
    log(f"repair round 0: {best['errors']} errors {best['by_type']}, {best['unconnected']} unconnected")
    level = 0
    for k in range(1, int(opts.get("rounds", 3)) + 1):
        if best["errors"] == 0 and best["unconnected"] == 0:
            break
        rec = dict(round=k)
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
        new_thermal = a["thermal"] - thermal
        if new_thermal and opts.get("thermal_repair", True):
            thermal |= new_thermal
            plan = constraints.plan(info, input_path, dict(opts, severities=sev, thermal_pads=sorted(thermal)))
        if not a["widen"] and not a["items"] and not a["open"] and not new_thermal:
            rec["stopped"] = "nothing attributable"
            rec["unattributed"] = sorted(set(a["unattributed"]))
            break
        if not a["items"] and not a["widen"] and level == 0:
            level = 2  # only open connections: the router needs room, not the same board again
        mode = LEVELS[level]
        rec.update(level=mode, widen=len(a["widen"]), rip_items=len(a["items"]), rip_nets=sorted(a["nets"]),
                   open=sorted(a["open"]), thermal=len(new_thermal), unattributed=sorted(set(a["unattributed"])))
        if mode == "items":
            rip = set(a["items"])
        else:
            rip = {u for u, r in routed.items() if r["net"] in a["nets"]}
        fixed = drc.stage_board(output_path, input_path, rdir / "fixed")
        pcbnew_io.edit_routing(fixed, fixed, delete=sorted(rip), widths=a["widen"], lock_all=mode != "free")
        cand = rdir / "cand.kicad_pcb"
        if rip or a["open"]:
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
        s_ = drc.summary(rep)
        rec.update(s_)
        rec["kept"] = _key(s_) > _key(best)
        log(f"repair round {k} ({mode}): {s_['errors']} errors {s_['by_type']}, {s_['unconnected']} unconnected "
            f"({'kept' if rec['kept'] else 'discarded'})")
        if rec["kept"]:
            shutil.copy2(cand, output_path)
            best, best_rep = s_, rep
            level = 0
        else:
            level += 1
            if level >= len(LEVELS):
                rec["stopped"] = "no improvement"
                break
    return dict(rounds=rounds, final=best, thermal_pads=len(thermal), seconds=round(time.monotonic() - t_start, 1))
