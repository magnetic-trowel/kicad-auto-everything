#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where do bus lanes die? Read-only diagnosis of stored bus-alone runs (bus-alone-b1).

For every lane open in a bus-alone output (and not open in the human view), take each open net's copper islands
(kae.bus.copper.NetGraph: tracks, vias, pads) and measure, at each end part of the bus, how far the island holding
that end's pad got: no copper at all ("bare"), copper that stays inside the end part's pad field, copper that just
leaves it, or copper well out of it. The lane's death is read at its fine end (BGA / grid / < 0.5 mm pitch) when it
has one. The human layout of the same board gives the via technology and the layers the human used on the lane.

Usage: where_lanes_die.py BUSNETS_DIR VIEWS_DIR RUNS_CSV IDS_FILE OUT_JSONL
RUNS_CSV lines: board,arm,run_dir (the bus-alone-b1 runs file; arm `alone` is read). One JSON line per board."""
from __future__ import annotations

import csv
import gzip
import json
import math
import os
import resource
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from kae.board.kicad_file import load
from kae.bus import copper as C
from kae.route.escape import _grid

BOARDS = Path(os.path.expanduser("~/kae-boards/boards"))


def fine(t, pitch):
    t = t or ""
    return "bga" in t or "grid" in t or (pitch is not None and 0 < pitch < 0.5)


def field_of(fp):
    """Pad field rectangle of a part: its pads' copper extent (board axes)."""
    xs0 = [p.x - max(p.size) / 2 for p in fp.pads]
    xs1 = [p.x + max(p.size) / 2 for p in fp.pads]
    ys0 = [p.y - max(p.size) / 2 for p in fp.pads]
    ys1 = [p.y + max(p.size) / 2 for p in fp.pads]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def outside(bb, x, y):
    """Signed distance of (x, y) outside rectangle bb (negative: inside, by the distance to its nearest edge)."""
    dx = max(bb[0] - x, x - bb[2])
    dy = max(bb[1] - y, y - bb[3])
    if dx <= 0 and dy <= 0:
        return max(dx, dy)
    return math.hypot(max(dx, 0), max(dy, 0))


def rings_of(fp):
    """{pad number: ring} for a ball grid (0 = outer ring), else {}; and the grid pitch."""
    smd = [p for p in fp.pads if p.kind == "smd"]
    if len(smd) < 16:
        return {}, None
    med = sorted(p.size[0] * p.size[1] for p in smd)[len(smd) // 2]
    balls = [p for p in smd if p.size[0] * p.size[1] <= 4 * med]
    g = _grid([(p.x, p.y) for p in balls]) if len(balls) >= 16 else None
    if g is None:
        return {}, None
    pitch, _ang, _loc, rings = g
    return {p.number: r for p, r in zip(balls, rings)}, pitch


def components(g):
    """Node -> component id over a NetGraph."""
    comp = {}
    for s in range(len(g.xy)):
        if s in comp:
            continue
        comp[s] = s
        st = [s]
        while st:
            u = st.pop()
            for v, _w, _i in g.adj[u]:
                if v not in comp:
                    comp[v] = s
                    st.append(v)
    return comp


def human_lane(hb, nets, cu):
    """Vias (and their types) and copper layers the human layout uses on a lane's nets."""
    vias = [v for v in hb.vias if v.net in nets]
    lay = sorted({t.layer for t in hb.tracks if t.net in nets})
    return dict(vias=len(vias), via_types=dict(Counter(v.type for v in vias)), layers=lay, n_layers=len(lay))


def board_facts(ob, hb):
    cu = [l for l, t in ob.layers.items() if l.endswith(".Cu")]
    zones_on = Counter(l for z in ob.zones if z.net for l in z.layers if l.endswith(".Cu"))
    inner = [l for l in cu if l not in ("F.Cu", "B.Cu")]
    plane_like = [l for l in inner if ob.layers.get(l) in ("power", "mixed") or zones_on.get(l)]
    r = ob.rules
    hv = Counter(v.type for v in hb.vias)
    via_sizes = Counter(round(v.size, 3) for v in hb.vias)
    return dict(copper=len(cu), inner=len(inner), plane_like=len(plane_like),
                signal_layers=len(cu) - len(plane_like), layer_types={l: ob.layers.get(l) for l in cu},
                clearance=r.clearance if r else None, track_min=r.track_min if r else None, via_min=r.via_min if r else None,
                via_drill_min=r.via_drill_min if r else None, microvia_min=r.microvia_min if r else None,
                human_via_types=dict(hv), human_via_sizes=dict(via_sizes.most_common(4)))


def end_state(g, comp, pad_node, bb, pitch):
    """State of the copper island holding an end pad: bare / inside / leaves / out, reach (mm past the field edge),
    vias in the island."""
    cid = comp.get(pad_node)
    nodes = [i for i, c in comp.items() if c == cid and g.xy[i][2] is not None]   # track nodes (pads, vias: layer None)
    vias = [i for i, c in comp.items() if c == cid and i not in g.pad_nodes and g.xy[i][2] is None]
    pts = [g.xy[i] for i in nodes] + [g.xy[i] for i in vias]
    if not pts:
        return dict(state="bare", reach=None, vias=0, copper=0)
    reach = max(outside(bb, x, y) for x, y, _ in pts)
    p = pitch or 0.5
    st = "inside" if reach <= 0.5 * p else ("leaves" if reach <= 2.0 else "out")
    return dict(state=st, reach=round(reach, 3), vias=len(vias), copper=len(nodes))


def gap(g, comp, a, b):
    """Shortest distance between the copper (or pads) of the islands holding nodes a and b."""
    ca, cb = comp.get(a), comp.get(b)
    if ca is None or cb is None or ca == cb:
        return 0.0
    pa = [g.xy[i] for i, c in comp.items() if c == ca]
    pb = [g.xy[i] for i, c in comp.items() if c == cb]
    if len(pa) * len(pb) > 4_000_000:
        pa, pb = pa[:: max(1, len(pa) // 2000)], pb[:: max(1, len(pb) // 2000)]
    return round(min(math.dist(p[:2], q[:2]) for p in pa for q in pb), 3)


def one_board(bid, busnets, views, run_dir, tmp):
    d = json.loads((Path(busnets) / f"{bid}.buses.json").read_text())
    va = json.loads((Path(views) / f"{bid}.alone.json").read_text())
    vh_p = Path(views) / f"{bid}.human.json"
    vh = json.loads(vh_p.read_text()) if vh_p.exists() else {}
    oa, hum = va.get("opens") or {}, (vh.get("opens") or {})
    out_pcb = Path(tmp) / f"{bid}.kicad_pcb"
    with gzip.open(Path(run_dir) / "output.kicad_pcb.gz", "rb") as f, open(out_pcb, "wb") as g:
        shutil.copyfileobj(f, g)
    ab = load(out_pcb, rules=False)
    ob = load(BOARDS / bid / "board.kicad_pcb", rules=True)     # the human layout: rules, layers, via technology
    out_pcb.unlink()
    fps = {f.ref: f for f in ab.footprints}
    cu = [l for l in ab.layers if l.endswith(".Cu")]
    tr, vs = C.flatten_tracks(ab)
    pads_of = defaultdict(list)
    for f in ab.footprints:
        for p in f.pads:
            if p.net:
                pads_of[p.net].append((f.ref, p))
    fields, rings = {}, {}
    graphs = {}
    lanes = []
    for bi, bus in enumerate(d["buses"]):
        a, b = bus.get("a"), bus.get("b")
        fa, fb = fine(bus.get("a_type"), bus.get("a_pitch")), fine(bus.get("b_type"), bus.get("b_pitch"))
        for ref in (a, b):
            if ref in fps and ref not in fields:
                fields[ref] = field_of(fps[ref])
                rings[ref] = rings_of(fps[ref])
        for li, ln in enumerate(bus["nets"]):
            if any(hum.get(n) for n in ln):
                continue
            opn = [n for n in ln if oa.get(n)]
            if not opn:
                continue
            rec = dict(bus=bi, kind=bus["kind"], width=bus["width"], lane=li, nets=ln, open_nets=opn, a=a, b=b,
                       a_type=bus.get("a_type"), b_type=bus.get("b_type"), a_pitch=bus.get("a_pitch"), b_pitch=bus.get("b_pitch"),
                       fine_a=fa, fine_b=fb, lds=bus.get("lds"), ends={})
            for n in opn:
                if n not in graphs:
                    pl = [p for _r, p in pads_of.get(n, [])]
                    graphs[n] = (C.NetGraph(tr.get(n, []), vs.get(n, []), pl), pads_of.get(n, []))
                g, pl = graphs[n]
                comp = components(g)
                pn = {id(p): g.pad_nodes[i] for i, (_r, p) in enumerate(pl)}
                ends = {}
                pads = []
                for r_, p_ in pl:
                    if r_ not in fps:
                        continue
                    side = "a" if r_ == a else ("b" if r_ == b else "s")
                    if r_ not in fields:
                        fields[r_] = field_of(fps[r_])
                    pitch = bus.get(f"{side}_pitch") if side in "ab" else None
                    if side in "ab" and not pitch and rings.get(r_):
                        pitch = rings[r_][1]
                    st = end_state(g, comp, pn[id(p_)], fields[r_], pitch)
                    st.update(ref=r_, side=side, pad=p_.number, npads=len(fps[r_].pads),
                              ring=(rings.get(r_) or ({}, None))[0].get(p_.number) if side in "ab" else None)
                    st["_node"] = pn[id(p_)]
                    pads.append(st)
                na = next((s["_node"] for s in pads if s["side"] == "a"), None)
                nb = next((s["_node"] for s in pads if s["side"] == "b"), None)
                if na is not None and nb is not None:
                    ends["gap"] = gap(g, comp, na, nb)
                    ends["joined"] = comp.get(na) == comp.get(nb)
                # pads whose island holds no other pad of the net: the ends this open is about
                cnt = Counter(comp[s["_node"]] for s in pads)
                for s in pads:
                    s["alone"] = cnt[comp[s["_node"]]] == 1
                    s.pop("_node")
                ends["pads"] = pads
                ends["islands"] = len({comp[i] for i in g.pad_nodes})
                rec["ends"][n] = ends
            rec["human"] = human_lane(ob, set(ln), cu)
            lanes.append(rec)
    return dict(board=bid, facts=board_facts(ob, ob), lanes=lanes)


def main():
    busnets, views, runs_csv, ids_file, out = sys.argv[1:6]
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    lim = 24 * 2 ** 30 if hard == resource.RLIM_INFINITY else min(hard, 24 * 2 ** 30)
    resource.setrlimit(resource.RLIMIT_AS, (lim, hard))
    runs = {b: rd for b, arm, rd in csv.reader(open(runs_csv)) if arm == "alone"}
    done = set()
    if Path(out).exists():
        done = {json.loads(line)["board"] for line in open(out) if line.strip()}
    tmp = tempfile.mkdtemp(prefix="lanes-die-")
    with open(out, "a") as fo:
        for bid in open(ids_file).read().split():
            if bid in done or bid not in runs:
                continue
            try:
                rec = one_board(bid, busnets, views, runs[bid], tmp)
            except Exception as e:  # noqa: BLE001 - one board must not stop the list
                rec = dict(board=bid, error=f"{type(e).__name__}: {e}"[:300])
            fo.write(json.dumps(rec, separators=(",", ":")) + "\n")
            fo.flush()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
