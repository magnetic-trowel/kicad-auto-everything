# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Thermal vias: hot parts over a heat-sink plate on the other face get vias to it.

The board's operating facts (kae.place.heat: requirements.thermal.heatsinks, parts.<ref>.
P_sustained_W) may name a region sink, a plate or a fan's air under part of the board on one face:
{"side": "top"|"bottom", "region": [x0, y0, x1, y1] board mm | "board", ...}. A part that dissipates
at least `heat_min_W` and sits on the OTHER face over that region reaches the plate only through the
board: FR-4 conducts ~0.3 W/m/K, a plated barrel (25 um copper, 0.3 mm drill) ~1,000 times more per
area. So the part's own copper gets through vias into the same net's copper on the sink face:

- the thermal pad first: the part's largest pad when it is at least twice the next (an exposed pad,
  a SOT-223 / DPAK tab). Vias go inside it, on a grid at `thermal_via_pitch`, as the existing
  handling of exposed pads does (critical_modules: "thermal pads always allow them"), unless
  `thermal_via_in_pad` is 0; else, and when the pad holds fewer than `thermal_via_max`, on the
  part-side pour of its net right around it;
- then the part's other pads whose net is poured on both faces (ground, power), around each pad.

A via is placed only where the net's fill (KiCad's refill of the routed board) covers the whole via
disk on the sink face, and, outside the pad, on the part's face in a fill piece that touches the pad,
so it carries heat from the pad to the plate; and only where Space.via_violations finds nothing (the
board's own rules, exactly as KiCad checks them). A net without a zone on the sink face gets nothing,
and the report says so (a plate under a net that has no copper there is reached only by the other
pads). Part sinks (a clip-on sink on the part) and region sinks on the part's own face need no vias.

`run` is the bridge's pass after the repair and last-mile rounds: the vias are written onto the
routed board, KiCad's DRC judges it like every repair round (no more unconnected items, no more
errors, or none beyond the input's own: repair.errors_no_worse); vias a new violation names are
dropped once and the board judged again; otherwise the board stays as it was.
"""
from __future__ import annotations

import math
import shutil
import time
from pathlib import Path

from shapely.geometry import Point
from shapely.ops import unary_union

from . import constraints as CN

EP_RATIO = 2.0      # an exposed pad is at least this many times the part's next-largest pad (area)
RING_MM = 2.5       # vias outside a pad: within this distance of the pad's copper


def _log(msg):
    print(f"[kae.route.thermal_vias {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _region_covers(rg, x, y):
    if rg == "board":
        return True
    if isinstance(rg, (list, tuple)) and len(rg) == 4:
        x0, y0, x1, y1 = (float(v) for v in rg)
        return min(x0, x1) <= x <= max(x0, x1) and min(y0, y1) <= y <= max(y0, y1)
    return False


def targets(board, op, board_path=None, opts=None):
    """([{ref, W, side, sink_side}], report rows): the parts that need thermal vias. Empty when
    thermal_vias is 0 or the operating facts name no region sink or no hot part."""
    from kae.place import heat
    if not op or float(CN.setting("thermal_vias", board_path, opts)) <= 0:
        return [], []
    sinks = heat.sinks(op)
    regions = [h for h in sinks if h.get("side") in ("top", "bottom") and h.get("region") is not None]
    clip = {h.get("part") for h in sinks if h.get("part")}
    w_min = float(CN.setting("heat_min_W", board_path, opts))
    hot = {r: w for r, w in heat.watts(op).items() if w >= w_min}
    if not regions or not hot:
        return [], []
    by_ref = {f.ref: f for f in board.footprints}
    out, rows = [], []
    for ref, w in sorted(hot.items(), key=lambda kv: -kv[1]):
        f = by_ref.get(ref)
        if f is None:
            rows.append(dict(part=ref, skipped="no such part"))
            continue
        if ref in clip:
            rows.append(dict(part=ref, skipped="part sink: cooled from the top, no vias needed"))
            continue
        side = "top" if f.side == "F" else "bottom"
        over = [h for h in regions if _region_covers(h["region"], f.x, f.y)]
        other = [h for h in over if h["side"] != side]
        if not other:
            rows.append(dict(part=ref, skipped="region sink on the part's own face: no vias needed" if over
                             else "no region sink under the part"))
            continue
        out.append(dict(ref=ref, W=w, side=side, sink_side=other[0]["side"]))
    return out, rows


def _pieces(fills, net, layer):
    """[Polygon] of `net`'s fill on `layer` ({net: {layer: [Polygon]}})."""
    return list(((fills or {}).get(net) or {}).get(layer) or [])


def _thermal_pad(pads):
    """The exposed pad among a part's pads (Space pad Items with a net): the largest when at least
    EP_RATIO x the next-largest pad of another number, else None."""
    pads = sorted((p for p in pads if p.net), key=lambda p: -p.geom.area)
    if not pads:
        return None
    big = pads[0]
    rest = [p for p in pads if p.owner != big.owner]
    if not rest or big.geom.area >= EP_RATIO * rest[0].geom.area:
        return big
    return None


def _grid(region, pitch, centre):
    """Points on a `pitch` grid over `region` (a polygon), nearest `centre` first: of the grids
    aligned on the centre or half a pitch off it (each axis), the one holding the most points (a
    SOT-223 tab of 3.6 x 2.0 mm holds 3 vias at 1 mm on the centred grid, 6 half a pitch off in y)."""
    if region.is_empty:
        return []
    x0, y0, x1, y1 = region.bounds
    best = []
    for ox in (0.0, pitch / 2):
        for oy in (0.0, pitch / 2):
            cx, cy = centre[0] + ox, centre[1] + oy
            i0, i1 = math.floor((x0 - cx) / pitch), math.ceil((x1 - cx) / pitch)
            j0, j1 = math.floor((y0 - cy) / pitch), math.ceil((y1 - cy) / pitch)
            pts = [(cx + i * pitch, cy + j * pitch) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
            pts = [q for q in pts if region.contains(Point(q))]
            if len(pts) > len(best):
                best = pts
    best.sort(key=lambda q: (math.dist(q, centre), q))
    return best


def place(sp, board, tgts, fills, board_path=None, opts=None, log=_log):
    """Commit thermal vias into Space `sp` (the routed board) for each target part; `fills`
    {net: {layer: [Polygon]}} is KiCad's refill of that board. Returns ([via Item], report rows)."""
    pitch = float(CN.setting("thermal_via_pitch", board_path, opts))
    vmax = int(CN.setting("thermal_via_max", board_path, opts))
    in_pad_ok = float(CN.setting("thermal_via_in_pad", board_path, opts)) > 0
    by_ref = {f.ref: f for f in board.footprints}
    added, rows = [], []
    for t in tgts:
        f = by_ref[t["ref"]]
        own = sp.cu[0] if t["side"] == "top" else sp.cu[-1]
        sink = sp.cu[0] if t["sink_side"] == "top" else sp.cu[-1]
        pads = [p for p in sp.pads_by_fp.get(f.uuid, []) if p.kind == "pad" and p.net and own in p.layers]
        row = dict(part=t["ref"], W=t["W"], sink_face=sink, vias=0, nets={}, notes=[])
        rows.append(row)
        if not pads:
            row["notes"].append(f"no pads with a net on {own}")
            continue
        tp = _thermal_pad(pads)
        # nets in order: the thermal pad's, then the others by pad area (ground and power pads are
        # the large ones in the packages that carry heat)
        order = []
        for p in ([tp] if tp is not None else []) + sorted(pads, key=lambda p: -p.geom.area):
            if p.net not in order:
                order.append(p.net)
        n_part = 0
        for net in order:
            if n_part >= vmax:
                break
            if not sp.zones_of(net, sink):
                if tp is not None and net == tp.net:
                    row["notes"].append(f"{net} (thermal pad): no copper (zone) on {sink}, the sink face: no vias "
                                        f"for it")
                continue
            under = unary_union(_pieces(fills, net, sink)) if _pieces(fills, net, sink) else None
            if under is None:
                row["notes"].append(f"{net}: zone on {sink} but no fill there")
                continue
            D, _d = sp.via_size(net)
            rv = D / 2.0
            ok_sink = under.buffer(-rv)
            got = dict(in_pad=0, around=0)
            net_pads = [p for p in pads if p.net == net]
            if net != (tp.net if tp is not None else None) and not sp.zones_of(net, own):
                # a pad that is no thermal pad helps only through a pour on its own face
                row["notes"].append(f"{net}: no zone on {own}: not a pour net, no vias")
                continue
            # 1. inside the exposed pad (an SMD pad; a plated hole is a barrel already)
            if tp is not None and net == tp.net and in_pad_ok and tp.smd and tp.hole is None:
                inner = tp.geom.buffer(-rv - 0.05)
                c = tp.geom.centroid
                saved = sp.via_in_pad
                sp.via_in_pad = True
                try:
                    for x, y in _grid(inner, pitch, (c.x, c.y)):
                        if n_part >= vmax:
                            break
                        if not ok_sink.contains(Point(x, y)) or _too_close(added, x, y, pitch):
                            continue
                        if sp.via_violations(net, x, y, first=True):
                            continue
                        added.append(sp.add_via(net, x, y, owner=("thermal_via", t["ref"])))
                        got["in_pad"] += 1
                        n_part += 1
                finally:
                    sp.via_in_pad = saved
            # 2. around the net's pads, on the part-side pour piece that touches the pad
            own_fill = _pieces(fills, net, own)
            for p in sorted(net_pads, key=lambda p: (p is not tp, -p.geom.area)):
                if n_part >= vmax:
                    break
                touch = [g for g in own_fill if g.intersects(p.geom.buffer(0.05))]
                if not touch:
                    continue
                ok_own = unary_union(touch).buffer(-rv)
                ring = p.geom.buffer(RING_MM).difference(p.geom.buffer(rv))
                c = p.geom.centroid
                for x, y in _grid(ring.intersection(ok_own).intersection(ok_sink), pitch, (c.x, c.y)):
                    if n_part >= vmax:
                        break
                    if _too_close(added, x, y, pitch):
                        continue
                    if sp.via_violations(net, x, y, first=True):
                        continue
                    added.append(sp.add_via(net, x, y, owner=("thermal_via", t["ref"])))
                    got["around"] += 1
                    n_part += 1
            if not own_fill and not got["in_pad"]:
                row["notes"].append(f"{net}: no fill on {own} and no via in its pad")
            row["nets"][net] = got
        row["vias"] = n_part
        if not n_part and not row["nets"]:
            row["notes"].append(f"no pad net of the part is poured on {sink} (and on {own}, outside a thermal pad)")
        log(f"{t['ref']} ({t['W']} W, sink on {sink}): {n_part} vias {row['nets']}"
            + (f" [{'; '.join(row['notes'])}]" if row["notes"] else ""))
    return added, rows


def _too_close(added, x, y, pitch):
    return any(math.dist((x, y), (v.geom.x, v.geom.y)) < pitch - 1e-6 for v in added)


def write(src, dst, vias):
    """dst = src plus `vias` (Space via Items), unlocked: ordinary routing a later round may move."""
    from . import critical_write as W
    for v in vias:
        if not v.uuid:
            v.uuid = W.new_uuid()
    W.append_items(src, dst, vias=[(v.net, v.geom.x, v.geom.y, v.width, v.drill, v.uuid, False) for v in vias])


def planned(board_path, opts=None):
    """(targets, rows) for the board at `board_path` (its operating facts from opts or the project)."""
    from kae.board.kicad_file import load
    from kae.place import heat
    op = heat.operating(board_path, opts)
    if not op:
        return [], []
    return targets(load(board_path), op, board_path, opts)


def run(input_path, output_path, wd, plan, info, opts, deadline, best=None, log=_log):
    """The bridge's pass: thermal vias on the routed board `output_path` (routed from the task's
    `input_path`, whose project files and own DRC errors are the reference), kept only when KiCad's
    DRC finds no more unconnected items and no more errors than `best` (its DRC summary; run here
    when None). Returns a report."""
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load

    from . import drc, repair
    from .critical_space import Space
    t0 = time.monotonic()
    tg, rows = planned(input_path, opts)
    rep = dict(parts=rows)
    if not tg:
        rep["status"] = "no part needs thermal vias"
        return rep
    wd = Path(wd) / "thermal_vias"
    if wd.exists():
        shutil.rmtree(wd)

    def left():
        return deadline - time.monotonic()
    try:
        staged = drc.stage_board(output_path, input_path, wd / "base")
        if best is None:
            best = drc.summary(drc.run(staged, wd / "base" / "drc.json", timeout=max(10, left() - 5)))
        fills = _fill_dict(pcbnew_io.zone_fills(staged)["zones"])
        b = load(staged)
        sp = Space(b, info, plan=plan, sev=opts.get("severities") or {})
        vias, prow = place(sp, b, tg, fills, input_path, opts, log=log)
        rep["parts"] = rows + prow
        rep["added"] = len(vias)
        if not vias:
            rep["status"] = "no legal via site"
            return rep
        if left() < 15:
            rep["status"] = "no time for the DRC"
            return rep
        cand = wd / "cand" / "board.kicad_pcb"
        cand.parent.mkdir(parents=True, exist_ok=True)
        write(staged, cand, vias)
        d = drc.stage_board(cand, input_path, wd / "drc")
        dr = drc.run(d, wd / "drc" / "drc.json", timeout=max(10, left() - 5))
        s_ = drc.summary(dr)
        base = None

        def ok(s):
            nonlocal base
            if s["unconnected"] > best["unconnected"]:
                return False
            if s["errors"] <= best["errors"]:
                return True
            if base is None:
                base = repair.input_errors(input_path, wd, deadline)
            return repair.errors_no_worse(s, best, base)
        if not ok(s_) and left() > 15:
            # vias a new violation names go, the rest is judged again (as the last mile drops its
            # joins KiCad faults)
            ours = {v.uuid for v in vias}
            bad = {it.get("uuid") for v in drc.errors(dr) for it in v.get("items") or []} & ours
            rep["dropped"] = len(bad)
            if bad and len(bad) < len(vias):
                vias = [v for v in vias if v.uuid not in bad]
                write(staged, cand, vias)
                d = drc.stage_board(cand, input_path, wd / "drc2")
                dr = drc.run(d, wd / "drc2" / "drc.json", timeout=max(10, left() - 5))
                s_ = drc.summary(dr)
        rep.update(before=best, after=s_, kept=ok(s_))
        if rep["kept"]:
            shutil.copy2(cand, output_path)
            rep["_report"] = dr
            rep["added"] = len(vias)
            per = {}
            for v in vias:
                per[v.owner[1]] = per.get(v.owner[1], 0) + 1
            rep["vias_per_part"] = per
        else:
            rep["added"] = 0
        rep["status"] = "kept" if rep["kept"] else "discarded"
        log(f"thermal vias: {len(vias)} placed: {s_['errors']} errors {s_['by_type']}, {s_['unconnected']} "
            f"unconnected (before {best['errors']} / {best['unconnected']}): {rep['status']}")
        return rep
    except Exception as e:  # noqa: BLE001 - the routed board stays
        rep["status"] = "error"
        rep["error"] = f"{type(e).__name__}: {e}"
        log(f"thermal vias: {rep['error']}")
        return rep
    finally:
        rep["seconds"] = round(time.monotonic() - t0, 1)


def _fill_dict(zones):
    from .lastmile import _fill_polys
    return _fill_polys(zones)
