# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Thermal vias: hot parts get vias from their thermal pad into the same net's copper on the
other face, to a heat-sink plate there or to a pour that sheds heat by convection.

FR-4 conducts ~0.3 W/m/K, a plated barrel (25 um copper, 0.3 mm drill) ~1,000 times more per area,
so a part's heat reaches the other face of the board through vias or hardly at all. Every part the
board's operating facts (kae.place.heat: parts.<ref>.P_sustained_W) give at least `heat_min_W` gets
them, in one of two modes:

- "sink": a region sink (requirements.thermal.heatsinks: {"side": "top"|"bottom", "region": [x0, y0,
  x1, y1] board mm | "board", ...}, a plate or a fan's air) on the other face covers the part. The
  vias land in the thermal net's copper on the sink face; the thermal pad itself carries the heat on
  the part's face.
- "both faces": no such sink. As human boards do it, the net's pours on both outer faces are stitched
  under and around the part, so heat leaves the board from both faces by natural convection; a net
  poured on one face only gets nothing ("no copper on the other face"). This pass makes no zones.

Which copper:
- the thermal pad first: the part's largest pad when it is at least twice the next (an exposed pad,
  a SOT-223 / DPAK tab). Vias go inside it, on a grid at `thermal_via_pitch`, as the existing
  handling of exposed pads does (critical_modules: "thermal pads always allow them"), unless
  `thermal_via_in_pad` is 0; else, and when the pad holds fewer than `thermal_via_max`, on the
  part-side pour of its net right around it;
- then the part's other pads whose net is poured on both faces (ground, power), around each pad.

A via is placed only where the net's fill (KiCad's refill of the routed board) covers the whole via
disk on the other face, and, outside the pad, on the part's face in a fill piece that touches the
pad, so it carries heat from the pad through the board; and only where Space.via_violations finds
nothing (the board's own rules, exactly as KiCad checks them).

`run` is the bridge's final stage after the repair and last-mile rounds: the vias are written onto
the routed board, KiCad's DRC judges it like every repair round (no more unconnected items, no more
errors, or none beyond the input's own: repair.errors_no_worse); vias a new violation names are
dropped once and the board judged again; otherwise the board stays as it was.
"""
from __future__ import annotations

import math
import re
import shutil
import time
from pathlib import Path

from shapely.geometry import Point
from shapely.ops import unary_union

from . import constraints as CN

# Calibration: kae's research report on PCB cooling (2026-11; [n] are that report's source numbers).
# Vias belong under the exposed pad and in a ring just outside it: with inner GND planes, vias
# outside the pad region changed theta_JA by 0.5 % or less (TI AN-1520 [2], FEA), and on 2-layer
# boards a ring around the part helps up to about 2-4 rings (Shen et al., IEEE TPEL 2019 [8]);
# across the rest of the pour the faces equalise through the FR-4 within ~1 cm anyway. Returns fall
# fast: 5-9 vias suffice for a small die (TI PowerPAD SLMA002H [4]), a 6 x 6 array gives 90 % of an
# 11 x 11's benefit (Electronics Cooling 2004 [12]): hence thermal_via_max 16 and 1.0 mm pitch (TI
# QFN 1.0 mm [5], ROHM 1.2 mm [15]). The drill comes from the board's own via rules; unfilled
# 0.25-0.33 mm is the sweet spot (0.2 mm costs 15-25 % on pads of <= 4 vias [2]), so the report
# flags a drill outside it.
EP_RATIO = 2.0      # an exposed pad is at least this many times the part's next-largest pad (area)
RING_MM = 2.5       # vias outside a pad: within this distance of the pad's copper (~2 rings at 1 mm)
DRILL_MM = (0.25, 0.33)   # unfilled thermal-via drill sweet spot [2][8]
PROCESSES = ("reflow", "hot_plate", "vapor_phase", "hand", "wave", "unknown")
# Thermal reliefs exist to make a pad solderable by hand or wave: they keep the pour from sinking the
# iron's heat. A whole-board heat process (reflow, hot plate, vapour phase) has no use for them, and
# on a heat-carrying pad they cost the part: four 0.25 mm spokes in 1 oz copper are ~18 K/W per pad,
# more than a 2-layer board's whole spreading floor (~15 K/W), and the sources ask for solid
# connections on exposed pads (TI PowerPAD SLMA002H [4]; the cooling report's relief calc).
WHOLE_BOARD_HEAT = ("reflow", "hot_plate", "vapor_phase")


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
    """([{ref, W, side, sink_side, mode}], report rows): the parts that get thermal vias: every part
    the operating facts give at least `heat_min_W` (P_sustained_W). mode "sink": a region sink on
    the other face covers it (vias into the sink face's copper); "both faces": none does (vias
    stitch its net's pours on both outer faces, so heat leaves the board from both by convection).
    Empty when thermal_vias is 0, or without operating facts or a hot part."""
    from kae.place import heat
    if not op or float(CN.setting("thermal_vias", board_path, opts)) <= 0:
        return [], []
    sinks = heat.sinks(op)
    regions = [h for h in sinks if h.get("side") in ("top", "bottom") and h.get("region") is not None]
    clip = {h.get("part") for h in sinks if h.get("part")}
    w_min = float(CN.setting("heat_min_W", board_path, opts))
    hot = {r: w for r, w in heat.watts(op).items() if w >= w_min}
    by_ref = {f.ref: f for f in board.footprints}
    out, rows = [], []
    for ref, w in sorted(hot.items(), key=lambda kv: -kv[1]):
        f = by_ref.get(ref)
        if f is None:
            rows.append(dict(part=ref, skipped="no such part"))
            continue
        side = "top" if f.side == "F" else "bottom"
        other = [h for h in regions if h["side"] != side and _region_covers(h["region"], f.x, f.y)]
        t = dict(ref=ref, W=w, side=side, sink_side="bottom" if side == "top" else "top",
                 mode="sink" if other else "both faces")
        if ref in clip:
            t["note"] = "part sink on top as well"
        # other ways out for its heat than the board's copper: a part sink on it, a region sink over it
        t["sinks"] = (["part sink"] if ref in clip else []) + [
            f"region sink ({h['side']})" for h in regions if _region_covers(h["region"], f.x, f.y)]
        out.append(t)
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
        row = dict(part=t["ref"], W=t["W"], mode=t.get("mode", "sink"), to_face=sink, vias=0, nets={},
                   notes=[t["note"]] if t.get("note") else [])
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
            thermal = tp is not None and net == tp.net
            on_sink, on_own = bool(sp.zones_of(net, sink)), bool(sp.zones_of(net, own))
            # a pad other than the thermal pad reaches a via only through its pour; without a plate the
            # vias stitch the net's pours on both faces, so the net needs pour on both
            need_own = t["mode"] == "both faces" or not thermal
            if not on_sink or (need_own and not on_own):
                if thermal or on_sink or on_own:
                    where = (f"pour on {own if on_own else sink} only" if on_own or on_sink
                             else f"no pour on {own} or {sink}")
                    row["notes"].append(f"{net}{' (thermal pad)' if thermal else ''}: {where}: no copper on the "
                                        f"other face, no vias")
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
        if n_part:
            row["notes"] += _path_notes(sp, board_path, tp, own, row, added)
        if not n_part and not row["nets"]:
            row["notes"].append(f"no pad net of the part is poured on both {own} and {sink}")
        log(f"{t['ref']} ({t['W']} W, {row['mode']}, to {sink}): {n_part} vias {row['nets']}"
            + (f" [{'; '.join(row['notes'])}]" if row["notes"] else ""))
    return added, rows


def _path_notes(sp, board_path, tp, own, row, added):
    """What in the board's own settings chokes the heat path the vias open, reported, never changed:
    - the thermal pad joined to its pour through thermal reliefs (the pad's or zone's setting). For
      exposed pads and thermal vias the sources ask for a solid connection (TI PowerPAD [4]); a
      relief is ~18 K/W per pad (the report's calc), more than a 2-layer board's spreading floor;
    - a custom rule giving vias a zone connection other than solid (KiCad connects vias solid by
      default);
    - vias in the pad left untented on the component side: TI asks to cap them there (mask = drill +
      0.1 mm); tenting only from the far side raised voiding [4][5];
    - a drill outside the 0.25-0.33 mm sweet spot."""
    out = []
    mine = [v for v in added if v.owner == ("thermal_via", row["part"])]
    if tp is not None:
        k = getattr(tp, "idx", None)
        pd = (sp.info.get("pads") or [])[k] if k is not None else {}
        for z in sp.info.get("zones") or []:
            if z.get("net") != tp.net or own not in (z.get("layers") or []) or z.get("rule_area"):
                continue
            conn = pd.get("zone_connection") or "inherited"
            if conn == "inherited":
                conn = z.get("pad_connection") or "thermal"
            if conn == "thermal" or (conn == "thru_hole_only" and pd.get("attr") == "pth"):
                out.append(f"thermal pad {tp.owner[1]} joins its {own} pour through thermal reliefs (the "
                           f"board's pad/zone setting, kept): the heat path on {own} is choked")
                break
    if board_path:
        dru = Path(board_path).with_suffix(".kicad_dru")
        try:
            txt = dru.read_text(encoding="utf-8", errors="replace")
        except OSError:
            txt = ""
        if "zone_connection" in txt and "via" in txt.lower():
            out.append("the board's custom rules set a zone connection that may name vias: if it gives them "
                       "reliefs, the vias are choked (kept as the board says)")
    in_pad = sum(1 for v in mine if tp is not None and tp.geom.contains(v.geom))
    tent = (sp.settings or {}).get("tent_vias_front" if own == sp.cu[0] else "tent_vias_back", True)
    if in_pad and tent is False:
        out.append(f"{in_pad} vias in the pad untented on {own}, the component side (board setting): cap or plug "
                   f"them against solder wicking")
    drills = sorted({round(v.drill, 3) for v in mine})
    row["via_mm"] = sorted({(round(v.width, 3), round(v.drill, 3)) for v in mine})
    if any(d < DRILL_MM[0] - 1e-9 or d > DRILL_MM[1] + 1e-9 for d in drills):
        out.append(f"via drill {drills} mm (the board's via rule) is outside the {DRILL_MM[0]}-{DRILL_MM[1]} mm "
                   f"sweet spot for unfilled thermal vias")
    return out


def _too_close(added, x, y, pitch):
    return any(math.dist((x, y), (v.geom.x, v.geom.y)) < pitch - 1e-6 for v in added)


def write(src, dst, vias):
    """dst = src plus `vias` (Space via Items), unlocked: ordinary routing a later round may move."""
    from . import critical_write as W
    for v in vias:
        if not v.uuid:
            v.uuid = W.new_uuid()
    W.append_items(src, dst, vias=[(v.net, v.geom.x, v.geom.y, v.width, v.drill, v.uuid, False) for v in vias])


def process(op):
    """The board's assembly process (requirements.assembly.process), "unknown" when not stated."""
    p = (((op or {}).get("requirements") or {}).get("assembly") or {}).get("process")
    return p if p in PROCESSES else "unknown"


# footprints no iron can solder: leadless and ball-grid packages (their joints are under the body),
# as the intent compiler classes them for requirements.assembly.reflow_only_parts
_REFLOW_ONLY = re.compile(r"(?<![A-Z])(V?QFN|[UWVTX]?DFN|BGA|LGA|[WU]?CSP|W?SON|USON|VSON)(?![A-Z])|-1EP|EP_|_EP",
                          re.IGNORECASE)


def reflow_only(board, op):
    """[(ref, why)] of the board's parts that only reflow can solder: requirements.assembly.
    reflow_only_parts when the operating facts give it, else the leadless and ball-grid footprints
    (lib ids naming QFN, DFN, BGA, LGA, CSP, SON or an exposed pad)."""
    asm = ((op or {}).get("requirements") or {}).get("assembly") or {}
    by_ref = {f.ref: f for f in board.footprints}
    if isinstance(asm.get("reflow_only_parts"), list):
        out = []
        for r in asm["reflow_only_parts"]:
            f = by_ref.get(r)
            m = _REFLOW_ONLY.search((f.lib_id or "").split(":")[-1]) if f is not None else None
            out.append((r, m.group(0).strip("-_").upper() if m else "reflow only"))
        return out
    out = []
    for f in board.footprints:
        m = _REFLOW_ONLY.search((f.lib_id or "").split(":")[-1])
        if m:
            out.append((f.ref, m.group(0).strip("-_").upper()))
    return sorted(out)


def effective_process(board, op):
    """(process the policy uses, why): reflow whenever the board needs it anyway (a reflow-only
    part, n_reflow_only_parts > 0, or hand_solder_ok false), else the stated process."""
    asm = ((op or {}).get("requirements") or {}).get("assembly") or {}
    stated = process(op)
    ro = reflow_only(board, op)
    n = asm.get("n_reflow_only_parts")
    if ro or (isinstance(n, (int, float)) and n > 0):
        names = ", ".join(f"{r} {w}" for r, w in ro[:4]) + (", ..." if len(ro) > 4 else "")
        return "reflow", f"board needs reflow ({names or f'{int(n)} reflow-only parts'}): reliefs bring nothing"
    if asm.get("hand_solder_ok") is False:
        return "reflow", "hand soldering is not allowed (hand_solder_ok false): reliefs bring nothing"
    return stated, ""


def planned(board_path, opts=None):
    """(targets, rows) for the board at `board_path` (its operating facts from opts or the project)."""
    from kae.board.kicad_file import load
    from kae.place import heat
    op = heat.operating(board_path, opts)
    if not op:
        return [], []
    return targets(load(board_path), op, board_path, opts)


def _heat_pad(sp, pads, own):
    """The pad carrying most of a part's heat: its exposed pad, else its largest pad whose net is
    poured on its own face (an LDO's GND pin, a FET's drain); None without either."""
    tp = _thermal_pad(pads)
    if tp is not None:
        return tp
    poured = [p for p in pads if any(g.intersects(p.geom) for _l, g in sp.zones_of(p.net, own))]
    return max(poured, key=lambda p: p.geom.area) if poured else None


def _pad_connection(sp, pad, layer):
    """How `pad` joins its net's zone on `layer`: "thermal", "full", "none", or None (no such zone)."""
    k = getattr(pad, "idx", None)
    pd = (sp.info.get("pads") or [])[k] if k is not None else {}
    for n, l, g, rec in sp.zones:
        if n != pad.net or l != layer or not g.intersects(pad.geom):
            continue
        conn = pd.get("zone_connection") or "inherited"
        if conn == "inherited":
            conn = (rec or {}).get("pad_connection") or "thermal"
        if conn == "thru_hole_only":
            conn = "thermal" if pd.get("attr") == "pth" else "full"
        return conn
    return None


_RELIEF_RULE = re.compile(r"\(constraint\s+zone_connection\s+thermal_reliefs\b")


def pushback(sp, board, tgts, rows, op, board_path=None):
    """(entries, pads to connect solid): for each hot part, what its heat path costs and what the
    pass does about it; the bridge reports the entries ("thermal", beside "blocked").

    A heat pad joined to its pour through thermal reliefs is connected solid (a per-pad zone
    connection override; the zone and the board's rules stay) when the board is heated whole
    (reflow, hot plate, vapour phase; also whenever a part only reflow can solder is on the board, or
    hand_solder_ok is false: effective_process), or when the board's copper is the part's only way out for its
    heat whatever the process: a hot chip costs more than a harder solder joint. With a sink also
    cooling it, hand and wave soldering keep the reliefs, and an unstated process keeps them until
    it is stated. A board custom rule that sets thermal reliefs wins (its conditions are not
    evaluated here: any such rule counts). A heat net with no copper on the other face is reported."""
    proc, why = effective_process(board, op)
    stated = process(op)
    dru = ""
    if board_path:
        try:
            dru = Path(board_path).with_suffix(".kicad_dru").read_text(encoding="utf-8", errors="replace")
        except OSError:
            dru = ""
    rule_reliefs = bool(_RELIEF_RULE.search(dru))
    by_ref = {f.ref: f for f in board.footprints}
    row_of = {r.get("part"): r for r in rows}
    out, solid = [], []
    for t in tgts:
        ref, f = t["ref"], by_ref[t["ref"]]
        own = sp.cu[0] if t["side"] == "top" else sp.cu[-1]
        other = sp.cu[-1] if own == sp.cu[0] else sp.cu[0]
        pads = [p for p in sp.pads_by_fp.get(f.uuid, []) if p.kind == "pad" and p.net and own in p.layers]
        hp = _heat_pad(sp, pads, own)
        if hp is None:
            continue
        e = dict(part=ref, W=t["W"], pad=str(hp.owner[1]), net=hp.net, process=proc)
        if why:
            e.update(stated_process=stated, process_why=why)
        if not sp.zones_of(hp.net, other):
            got = sorted(n for n, v in (row_of.get(ref, {}).get("nets") or {}).items() if sum(v.values()))
            out.append(dict(e, issue="no copper on the other face", decision="report only",
                            consequence=f"{ref}'s {'tab' if hp is _thermal_pad(pads) else 'heat'} net {hp.net} has "
                                        f"no copper on {other}: thermal vias went to "
                                        f"{', '.join(got) if got else 'no net'} only",
                            would_change=f"a {hp.net} patch on {other} under {ref} or an inner {hp.net} plane would "
                                         f"carry its heat"))
        if _pad_connection(sp, hp, own) != "thermal":
            continue
        e["issue"] = "heat pad joins its pour through thermal reliefs"
        cooled = t.get("sinks") or []
        if rule_reliefs:
            out.append(dict(e, decision="reliefs kept", consequence="the board's rules require reliefs: heat path "
                            "weakened", would_change="a custom rule exempting this pad from thermal_reliefs"))
            continue
        if proc in WHOLE_BOARD_HEAT:
            out.append(dict(e, decision="solid", consequence=f"{ref} pad {e['pad']} connected solid: "
                            + (why if why else f"{proc} heats the whole board, reliefs only weaken the heat path"),
                            would_change="hand or wave assembly with a sink on the part"
                            + ("" if not why else ", and no reflow-only part on the board")))
            solid.append(hp)
        elif not cooled:
            out.append(dict(e, decision="solid", consequence=f"{ref} pad {e['pad']} connected solid: board copper "
                            f"is its only cooling path; hand soldering needs preheat or a hot plate",
                            would_change="a part sink or region sink on it, with hand or wave assembly"))
            solid.append(hp)
        elif proc in ("hand", "wave"):
            out.append(dict(e, decision="reliefs kept", consequence=f"reliefs kept for {proc} soldering; heat path "
                            f"weakened ({', '.join(cooled)} also cools it)",
                            would_change="reflow, hot plate or vapour-phase assembly"))
        else:
            out.append(dict(e, decision="reliefs kept", consequence="assembly process unknown: state it to decide "
                            f"({', '.join(cooled)} also cools it)",
                            would_change="requirements.assembly.process in the operating facts"))
    return out, solid


def set_solid(src, dst, uuids):
    """dst = src with the pads `uuids` connected solid to their zones: KiCad's per-pad zone connection
    override (zone_connect 2), set or replaced in those pad blocks only. Returns the uuids set."""
    from kae.board import sexpr
    text = Path(src).read_text(encoding="utf-8")
    done = []
    for u in uuids:
        m = re.search(r'\((?:uuid|tstamp) "?' + re.escape(u) + r'"?\)', text)
        if not m:
            continue
        a = text.rfind("(pad ", 0, m.start())
        if a < 0:
            continue
        b = sexpr.block_end(text, a)
        blk = text[a:b]
        if re.search(r"\(zone_connect \d\)", blk):
            nb = re.sub(r"\(zone_connect \d\)", "(zone_connect 2)", blk)
        else:
            i = blk.find("(uuid")
            i = blk.find("(tstamp") if i < 0 else i
            ls = blk.rfind("\n", 0, i) + 1
            nb = blk[:ls] + blk[ls:i] + "(zone_connect 2)\n" + blk[ls:]  # same indent as (uuid
        text = text[:a] + nb + text[b:]
        done.append(u)
    Path(dst).write_text(text, encoding="utf-8")
    return done


def run(input_path, output_path, wd, plan, info, opts, deadline, best=None, log=_log):
    """The bridge's final thermal stage on the routed board `output_path` (routed from the task's
    `input_path`, whose project files and own DRC errors are the reference): thermal vias, then the
    solid connections of heat pads (pushback). Each step is kept only when KiCad's DRC finds no more
    unconnected items and no more errors than the board before it (`best`, its DRC summary; run here
    when None). Returns a report; "thermal" holds the push-back entries for the bridge's report."""
    from kae.board import pcbnew_io
    from kae.board.kicad_file import load

    from . import drc, repair
    from .critical_space import Space
    from kae.place import heat
    t0 = time.monotonic()
    tg, rows = planned(input_path, opts)
    rep = dict(parts=rows, thermal=[])
    if not tg:
        rep["status"] = "no part needs thermal vias"
        return rep
    wd = Path(wd) / "thermal_vias"
    if wd.exists():
        shutil.rmtree(wd)
    base = None

    def left():
        return deadline - time.monotonic()

    def ok(s, ref):
        nonlocal base
        if s["unconnected"] > ref["unconnected"]:
            return False
        if s["errors"] <= ref["errors"]:
            return True
        if base is None:
            base = repair.input_errors(input_path, wd, deadline)
        return repair.errors_no_worse(s, ref, base)

    def judge(board, name):
        d = drc.stage_board(board, input_path, wd / name)
        dr = drc.run(d, wd / name / "drc.json", timeout=max(10, left() - 5))
        return dr, drc.summary(dr)
    try:
        staged = drc.stage_board(output_path, input_path, wd / "base")
        if best is None:
            best = drc.summary(drc.run(staged, wd / "base" / "drc.json", timeout=max(10, left() - 5)))
        rep["before"] = best
        fills = _fill_dict(pcbnew_io.zone_fills(staged)["zones"])
        b = load(staged)
        sp = Space(b, info, plan=plan, sev=opts.get("severities") or {})
        vias, prow = place(sp, b, tg, fills, input_path, opts, log=log)
        entries, solid = pushback(sp, b, tg, prow, heat.operating(input_path, opts), input_path)
        rep["parts"] = rows + prow
        rep["thermal"] = entries
        rep["added"] = 0
        cur, cur_sum, cur_rep = staged, best, None
        # 1. the vias
        if vias and left() > 15:
            cand = wd / "cand" / "board.kicad_pcb"
            cand.parent.mkdir(parents=True, exist_ok=True)
            write(cur, cand, vias)
            dr, s_ = judge(cand, "drc")
            if not ok(s_, cur_sum) and left() > 15:
                # vias a new violation names go, the rest is judged again (as the last mile drops its
                # joins KiCad faults)
                ours = {v.uuid for v in vias}
                bad = {it.get("uuid") for v in drc.errors(dr) for it in v.get("items") or []} & ours
                rep["dropped"] = len(bad)
                if bad and len(bad) < len(vias):
                    vias = [v for v in vias if v.uuid not in bad]
                    write(cur, cand, vias)
                    dr, s_ = judge(cand, "drc2")
            rep["vias_kept"] = ok(s_, cur_sum)
            log(f"thermal vias: {len(vias)} placed: {s_['errors']} errors {s_['by_type']}, {s_['unconnected']} "
                f"unconnected (before {cur_sum['errors']} / {cur_sum['unconnected']}): "
                f"{'kept' if rep['vias_kept'] else 'discarded'}")
            if rep["vias_kept"]:
                cur, cur_sum, cur_rep = cand, s_, dr
                rep["added"] = len(vias)
                per = {}
                for v in vias:
                    per[v.owner[1]] = per.get(v.owner[1], 0) + 1
                rep["vias_per_part"] = per
        # 2. heat pads connected solid (a per-pad override; the zones and rules stay)
        if solid and left() > 15:
            cand = wd / "solid" / "board.kicad_pcb"
            cand.parent.mkdir(parents=True, exist_ok=True)
            done = set(set_solid(cur, cand, [p.uuid for p in solid if p.uuid]))
            dr, s_ = judge(cand, "drc_solid") if done else (None, None)
            kept = bool(done) and ok(s_, cur_sum)
            for e in entries:
                hp = next((p for p in solid if (p.owner[0], str(p.owner[1])) == (e["part"], e["pad"])), None)
                if e.get("decision") != "solid" or hp is None:
                    continue
                if hp.uuid not in done:
                    e.update(decision="reliefs kept",
                             consequence="the pad has no uuid to override: heat path weakened")
                elif not kept:
                    e.update(decision="reliefs kept", consequence="a solid connection made KiCad's DRC worse: heat "
                             "path weakened")
            rep["solid_pads"] = sorted(f"{p.owner[0]}.{p.owner[1]}" for p in solid if p.uuid in done) if kept else []
            if s_ is not None:
                rep["solid_drc"] = s_
                log(f"thermal pads solid {rep['solid_pads'] or sorted(done)}: {s_['errors']} errors {s_['by_type']}, "
                    f"{s_['unconnected']} unconnected: {'kept' if kept else 'discarded'}")
            if kept:
                cur, cur_sum, cur_rep = cand, s_, dr
        rep["after"] = cur_sum
        rep["kept"] = cur is not staged
        if rep["kept"]:
            shutil.copy2(cur, output_path)
            rep["_report"] = cur_rep
        rep["status"] = "kept" if rep["kept"] else ("nothing to change" if not vias and not solid else "discarded")
        for e in entries:
            log(f"thermal: {e['part']} pad {e['pad']} ({e['net']}, {e['W']} W, {e['process']}): {e['decision']}: "
                f"{e['consequence']}")
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
