# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Power copper: a post-pass that gives power and ground nets the free space a routed board leaves.

    from kae.route import power_copper
    rep = power_copper.run("routed.kicad_pcb", "out.kicad_pcb")        # widen, ground vias, stitch, DRC-gated

    python -m kae.route.power_copper IN.kicad_pcb OUT.kicad_pcb [--no-widen] [--no-vias] [--no-stitch]

The bridge routes every net at its net-class width and only ever narrows; it never adds ground
vias. This pass changes only routing, and only on power and ground nets:

1. Widen. Each straight track of a rail or ground net (never a switch node) is cut into runs and
   each run is widened to the widest ladder step its surroundings allow (`width_ladder`). Copper
   only grows in place: no track moves and no other net is touched, so signals are never pushed.
   Beyond the board's own clearance, the grown copper keeps `signal_gap` from ordinary signal
   copper (a 3W-like rule: twice the board clearance and twice the signal's width) and
   `victim_gap` from sensitive nets (clocks, high-speed, analog, RF, crystals, feedback and sense
   nodes, antennas), on its own layer and on the adjacent ones. Rule sources: the crosstalk
   budget K = 1/(1+(D/h)^2) of docs/topics/rules/si-fundamentals.md (D = h*sqrt(1/K-1)), the
   power-copper waveform classes of docs/topics/physics/power-copper.md (pour freely on quiet
   nodes, keep SW copper small).
2. Ground vias. Every SMD ground pad of a capacitor or of a decoupled IC ground pin without a
   ground barrel within `via_reach` mm gets one through via, as close as it is legal, where the
   same ground has fill on another layer, with a short pad-to-via track (PDN-01 and LearnEMC's
   "via adjacent to the pad" in docs/topics/rules/decoupling-pdn.md).
3. Stitching. Ground fill pieces other than a layer's largest that hold ground pads and fewer
   than `stitch_want` barrels get vias `stitch_pitch` apart into another layer's ground fill
   (the stitch_ground rule of kae.route.critical).

No pours are added (si-fundamentals: "guard traces and ground fill are never defaults").

The result is DRC-gated (`run`): KiCad's DRC on the written board must show no error type and no
unconnected count above the input's; violations naming an added item revert that item, and if
the board is still worse the pass falls back stage by stage to the input.
"""
from __future__ import annotations

from kae.budget import now as clock_now
import argparse
import json
import math
import re
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from kae import materials as MAT

from . import arcs as A
from . import critical_write as W

DEFAULTS = dict(
    widen=True,
    vias=True,
    stitch=True,
    max_width=3.0,            # mm: widest power/ground track (sweep 1/2/3/20 mm on 10 boards: 3 mm ties 20 mm
                              # on every term and beats it on loop loss; was 1.0, the feed width of 0603-1206 passives;
                              # power-copper.md: area efficiency peaks at feed width)
    ladder=(20.0, 15.0, 12.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.5, 2.0, 1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3),
    mode="widen",             # "widen": constant-width runs centred on each track; "vector": the free region
                              # around the net's copper on each layer, filled with overlapping track strips
    vector_out="strips",      # vector copper as "strips" (tracks: all a route task may add today) or "zones"
                              # (one KiCad zone per piece, priority above the layer's zones, solid pad
                              # connection; thermal reliefs when hand soldered; KiCad's refill sets the
                              # exact clearance)
    zone_above_a=None,        # A: a power/ground net whose operating current is above this gets vector copper
                              # written as zones (pours) instead of widened tracks; kae.route.finish passes 5
                              # (pours, not tracks, above ~5 A: critical_rails' rail_max_mm); None: never
    vector_strip=0.5,         # mm: strip width of the vector fill (pitch 0.8 x that)
    vector_min_gain=0.5,      # mm^2: a vector piece adding less copper than this is dropped
    into_pours=False,         # vector: may grow into other nets' zone fills (False: those fills are obstacles,
                              # so a rail never cuts a ground pour)
    neck=True,                # necks at the pads of small two-terminal parts (tombstoning; see neck_rule):
                              # within neck_len of such a pad, grown copper is at most the neck width
    neck_len=0.5,             # mm from the pad edge
    tht_loss_frac=0.002,      # the necks at THT pads of a net together add at most this share of the net's routed
                              # copper loss under the DC plan (the evaluator's noise floor is ~0.6 %); a pad whose
                              # neck would need to be wider than a relief's webs keeps its copper (tht_pad_kept_wide)
    tht_neck_dK=10.0,         # K: the most a THT neck may rise at current_margin x its current, as a short conductor
                              # between the pad and the wider copper (short_neck_width; IPC-2221's 10 K, which the
                              # long-trace widths use, applied to the neck's own heating)
    tht_heat_dK=20.0,         # K: THT pads where a hot part holds the board this far above ambient (fin model) are on
                              # its heat path and keep their copper (tht_pad_kept_wide)
    tht_heat_fill=0.5,        # copper fill per layer of that fin model
    tht_gap=0.25,             # mm: grown copper of a track that passes a necked THT pad of its net (does not end in
                              # it) keeps this gap from the pad, a relief's gap (IPC-2222 9.1.2 air gap); the run
                              # is not necked
    neck_via="own",           # ground via at a necked land: "own" (its own pad-to-via track, no wider than the
                              # neck, via edge >= neck_via_gap from the land: IPC-7351's "narrow conductor between
                              # the land area and the via") or "track" (on the land's routed track, neck_len away,
                              # no second entry; see docs/research/routing/kae-power-copper.md)
    neck_via_gap=0.25,        # mm, via edge to a necked land (Eurocircuits)
    land_cap=True,            # every other SMD land: grown copper within neck_len at most the land's width
    share=True,               # competing power/ground nets share room at w ~ I (False: first come, first served,
                              # highest current first)
    current_margin=3.0,       # a net's operating current x this sizes its IPC width (when above max_width)
    current_cap=3.0,          # mm: the widest any current asks for
    operating=None,           # operating facts JSON (kae.intent operating: parts.<ref>.I_A / I_sustained_A);
                              # default: the KAE_OPERATING text variable of the board's .kicad_pro
    sample=0.1,               # mm between sample points along a track
    min_run=1.0,              # mm: a wider run shorter than this is merged into its narrower neighbour
    signal_clr_mult=2.0,      # grown copper keeps >= this x the board clearance from signal copper
    signal_w_mult=2.0,        # and >= this x the signal track's width (3W centre to centre)
    victim_k=0.05,            # crosstalk budget to sensitive nets: D = h*sqrt(1/K - 1)
    victim_gap_min=0.5,       # mm, bounds of that gap
    victim_gap_max=2.0,
    antenna_gap=3.0,          # mm from an antenna part's pads
    via_reach=1.0,            # mm: a ground pad with a ground barrel this close needs no via
    via_track_max=0.5,        # mm: width of the pad-to-via track at most
    stitch_want=3,
    stitch_pitch=2.0,
    stitch_min_area=0.3,
    drc_budget=80,            # KiCad DRC runs the gate may spend (attribution and bisection)
)

VICTIM_ROLES = ("clock", "high_speed", "analog", "rf")
TOL = 0.002
VTOL = 0.03          # mm: vector mode's margin over each requirement (polygonal shapes, simplification)


# ----------------------------------------------------------------------------- pure rules
def ipc_width(current_a, dt_k=10.0, t_mm=MAT.CU_1OZ_MM, external=True):
    """IPC-2221 track width (mm) for `current_a` at a `dt_k` rise: I = k*dT^0.44*A^0.725, A in mil^2."""
    if current_a <= 0:
        return 0.0
    k = 0.048 if external else 0.024
    area_mil2 = (current_a / (k * dt_k ** 0.44)) ** (1.0 / 0.725)
    return area_mil2 / (t_mm / 0.0254) * 0.0254


def net_currents(operating, pads_by_ref, power, ground):
    """{net: A} from operating facts: each part's current (the upper end of I_A, else I_sustained_A)
    on every power net it has a pad on, and the sum of all of them on each ground net.
    pads_by_ref: {ref: set of nets of its pads}."""
    out = {}
    tot = 0.0
    for ref, f in ((operating or {}).get("parts") or {}).items():
        ia = f.get("I_A")
        a = max(ia) if isinstance(ia, (list, tuple)) and ia else (ia if isinstance(ia, (int, float)) else None)
        if a is None:
            a = f.get("I_sustained_A")
        if not isinstance(a, (int, float)) or a <= 0:
            continue
        rails = (pads_by_ref.get(ref) or set()) & set(power)
        for n in rails:
            out[n] = out.get(n, 0.0) + float(a)
        if rails:
            tot += float(a)
    for g in ground:
        out[g] = tot
    return out


def width_cap(max_width, current_a, margin=DEFAULTS["current_margin"], cap=DEFAULTS["current_cap"]):
    """Widest width (mm) to grow a net to: max_width, or the IPC width of margin x its current
    when that is wider, at most `cap`."""
    return max(max_width, min(cap, ipc_width(margin * (current_a or 0.0))))


def share(i_own, i_other):
    """This net's share of the room it contests with another power/ground net: total copper loss
    sum(I^2 R), R ~ 1/w, under sum(w) fixed is least at w ~ |I|. Without both currents: equal."""
    a, b = abs(i_own or 0.0), abs(i_other or 0.0)
    if a <= 0 or b <= 0:
        return 0.5
    return a / (a + b)


# Package classes of two-terminal SMD parts by land width (the pad's short side, IPC-7351 nominal
# lands): 01005/0201, 0402, 0603/0805, 1206 and larger.
PKG_CLASSES = ((0.35, "0201"), (0.65, "0402"), (1.05, "0603-0805"), (math.inf, "1206+"))
# Neck width (mm) at the land per process and class; None: no neck. Reflow (and unknown process, the
# common case): the tombstone-prone classes are 0201-0805 (torque ratio 49..4, hv-and-manufacturing-
# physics); vapour phase wets faster and tombstones more, so 1206 is necked too; hand soldering: an
# iron has to beat the copper's drain on every small land; wave: chips are glued, no tombstoning.
NECK_TABLE = {
    "reflow": {"0201": 0.15, "0402": 0.25, "0603-0805": 0.3, "1206+": None},
    "vapour_phase": {"0201": 0.15, "0402": 0.25, "0603-0805": 0.3, "1206+": 0.5},
    "hand": {"0201": 0.15, "0402": 0.25, "0603-0805": 0.3, "1206+": 0.5},
    "wave": {"0201": None, "0402": None, "0603-0805": None, "1206+": None},
}


def pkg_class(land_w):
    return next(name for lim, name in PKG_CLASSES if land_w <= lim)


def process_of(assembly):
    """Soldering process from the operating facts' requirements.assembly: 'reflow' (also when it is
    unknown or missing), 'vapour_phase', 'hand' or 'wave'."""
    a = assembly or {}
    p = str(a.get("process") or "").lower().replace(" ", "_").replace("-", "_")
    if a.get("hand_solder_ok") or p in ("hand", "hand_solder", "manual"):
        return "hand"
    if p in ("vapour_phase", "vapor_phase", "vps"):
        return "vapour_phase"
    if p in ("wave", "selective_wave"):
        return "wave"
    return "reflow"


# Plated through-hole pads (tht=True in neck_rule): wide copper into a THT pad drains the heat a wave,
# a selective nozzle or an iron must bring to fill the barrel; that is what thermal reliefs are for
# (hv-and-manufacturing-physics: "reliefs remain physics for hand and wave soldering of THT pins";
# derivation-audit D7: a relief cuts the joint's drain 1.8-4.2x). IPC-2222 9.1.2 sizes a relief's webs
# together at 60 % of the land diameter: the widest copper a relieved THT land is joined by. The rule
# holds whatever the board's declared process: THT parts on a reflow board are still wave, selective or
# hand soldered unless they are pin-in-paste.
THT_RELIEF_FRAC = 0.6
THT_NECK_MIN = 1e-3     # mm: a THT neck with no current to carry; the routed track (never narrowed) is the floor


def short_neck_width(current_a, length_mm, margin=DEFAULTS["current_margin"], dk=10.0, t_mm=MAT.CU_1OZ_MM):
    """Narrowest width (mm) a short copper neck of `length_mm` between two heat sinks (the THT pad's barrel
    and the wider grown copper) may have so that margin x current_a raises its middle at most `dk` K.
    One-dimensional conduction with uniform Joule heating and both ends held at the sinks' temperature:
    dT_max = q L^2 / (8 k), q = I^2 rho / (w t)^2, so w = I L sqrt(rho / (8 k dT)) / t (Incropera & DeWitt,
    Fundamentals of Heat and Mass Transfer, sec. 3.5: plane wall with generation). Conduction into the
    laminate and convection are left out, which only overstates the rise. IPC-2221's chart is for long
    traces, where no such axial path exists; a 0.5-2 mm neck carries several times the current of a long
    trace of its width. 0 without a current."""
    if not current_a:
        return 0.0
    i = margin * current_a
    rho = MAT.RHO_CU_OHM_MM * 1e-3            # ohm m
    return i * (length_mm * 1e-3) * math.sqrt(rho / (8.0 * MAT.K_CU * dk)) / (t_mm * 1e-3) * 1e3


def neck_rule(land_w, process, series_current_a=0.0, margin=DEFAULTS["current_margin"], tht=False, tht_len=None,
              tht_dk=10.0):
    """Width (mm) grown copper may have within neck_len of a two-terminal part's land, or None (no
    limit). The neck is the land class's NECK_TABLE width for the process, never below what the
    part's own series current needs (IPC-2221 at margin x I): a fuse, ferrite or shunt in a rail
    keeps its width. A part to ground (a decap) carries no DC and is necked. A class the process does
    not neck (1206 and up in reflow, every class in wave) is capped at its land width.

    tht: a plated through-hole pad (land_w: its short side, the diameter of a round pad), whose
    current is series_current_a. The neck is the width that current needs as a short neck of
    `tht_len` mm (short_neck_width, rise at most tht_dk) and nothing more: grown copper stays at the
    routed track's width (power copper never narrows a track) or that width, whichever is wider. None
    when even the short neck needs more than a relief's webs give (THT_RELIEF_FRAC x land_w): the copper
    keeps its width (tht_pad_heatsunk)."""
    if tht:
        need = short_neck_width(series_current_a, tht_len if tht_len is not None else DEFAULTS["neck_len"],
                                margin, tht_dk)
        if need > THT_RELIEF_FRAC * land_w:
            return None
        return max(need, THT_NECK_MIN)
    need = current_need(series_current_a, margin)
    w = NECK_TABLE.get(process, NECK_TABLE["reflow"]).get(pkg_class(land_w))
    if need >= land_w:
        return None           # the current needs more than the land: no neck (land_enlarged_by_track)
    if w is None:
        # a class the process does not neck still gets no copper wider than its land near it: copper
        # beside the land is exposed land under the mask opening or a heat sink under mask, and on one
        # terminal of two it unbalances the joint (1206 caps fed by 3 mm rails: 9-11 mm^2 per land)
        return land_w
    return max(min(w, land_w), need)


def current_need(current_a, margin=DEFAULTS["current_margin"]):
    """Width (mm) a current asks of copper: IPC-2221 at margin x I (0 without a current)."""
    return ipc_width(margin * current_a) if current_a else 0.0


def land_necks(lands, power, ground, current, process, margin=DEFAULTS["current_margin"], tht_current=None,
               tht_len=None, tht_dk=10.0):
    """The neck rule over a board's parts: ({key: neck width}, {key: series current A}) for the
    lands of two-terminal SMD parts. `lands`: {part: [(key, smd, net, land width)]}, one entry per
    copper pad; `current`: {net: A} (net_currents). A part with no ground pad and a power pad is in
    series with a rail (fuse, ferrite, shunt, jumper) and carries the rail's current; a land whose
    neck_rule is None (a series current that needs more than the land) gets no neck. The one implementation PowerCopper._necks and constraints.plan both use.

    tht_current: {key: A} for the plated through-hole pads to neck (neck_rule tht=True; the caller
    leaves out the pads the rule does not apply to: unsoldered, hot or heat-sunk parts, pads joined to
    a zone, pads kept wide by the tht_wide setting). Their current goes into the second dict too, so a
    key there with no neck is a pad whose current needs more than a relief (tht_pad_heatsunk)."""
    necks, series_a = {}, {}
    tht_w = {k: w for cu in lands.values() for k, smd, _n, w in cu if not smd} if tht_current else {}
    for key, amps in (tht_current or {}).items():
        land_w = tht_w.get(key)
        if land_w is None:
            continue
        series_a[key] = amps
        w = neck_rule(land_w, process, amps, margin, tht=True, tht_len=tht_len, tht_dk=tht_dk)
        if w is not None:
            necks[key] = w
    for _part, cu in lands.items():
        if len(cu) != 2 or not all(smd for _k, smd, _n, _w in cu):
            continue
        nets = {n for _k, _s, n, _w in cu}
        series = 0.0
        if not nets & set(ground) and nets & set(power):
            series = max(current.get(n, 0.0) for n in nets)
        for key, _smd, _net, land_w in cu:
            series_a[key] = series
            w = neck_rule(land_w, process, series, margin)
            if w is not None:
                necks[key] = w
    return necks, series_a


UNSOLDERED_KINDS = ("mounting_hole", "heatsink", "mechanical", "fiducial")


def tht_wide_set(v):
    """The tht_wide setting as a set of refs and ref.pad names: a list, or a string split at commas,
    semicolons or spaces ("J1, J3.2")."""
    items = v if isinstance(v, (list, tuple, set)) else re.split(r"[,;\s]+", str(v or ""))
    return {str(x).strip() for x in items if str(x).strip()}


def tht_exempt(ref, number, kind, attrs, hot, zone_joined, wide):
    """Why the THT neck leaves a plated pad alone, or None when it applies (PowerCopper._tht_pads has
    each reason's case): "tht_wide", "unsoldered", "hot" or "zone"."""
    if ref and (ref in wide or f"{ref}.{number}" in wide):
        return "tht_wide"
    if kind in UNSOLDERED_KINDS or "board_only" in set(attrs or ()):
        return "unsoldered"
    if ref in hot:
        return "hot"
    if zone_joined:
        return "zone"
    return None


def branch_currents(net, tracks, vias, pads, fills, inj, link=1e6, stats=None, grown_w=None, series=()):
    """{pad token: A}: the largest current in a track that enters (or runs through) each pad of `net`, from a resistive solve
    of the net's routed copper under the injections `inj` ({"REF.NUM": A}, kae.excite.dc.planned_injections).
    Tracks are conductances w/L; pads, vias and fill pieces (`fills`: {layer: [polygons]}) join what touches
    them at `link`. Each connected piece is balanced (a piece whose loads' source is off it, or unrouted,
    shares the imbalance over its injected pads). `pads`: [(token, geometry, layers)]. A pad a current
    flows through (a chain of headers or LEDs) carries the current of what is beyond it, not its own."""
    import scipy.sparse as SP
    import scipy.sparse.linalg as SPL
    from scipy.sparse.csgraph import connected_components
    from shapely.strtree import STRtree
    nodes, edges, ends = {}, [], []

    def node(k):
        return nodes.setdefault(k, len(nodes))
    pads = list(pads)
    ptree = STRtree([g for _t, g, _l in pads]) if pads else None
    nets = {net} if isinstance(net, str) else set(net)
    multi = not isinstance(net, str)
    mine = [t for t in tracks if t.net in nets]
    lines = [LineString([t.start, t.end]) for t in mine]
    ltree = STRtree(lines) if lines else None
    # T-junctions: a track ending on another's run (not at its ends) joins it there
    tees, of_track = {}, {}
    for t in mine:
        for xy in (t.start, t.end):
            q = Point(xy)
            for j in ltree.query(q.buffer(max(t.width, 1e-3) / 2), predicate="intersects"):
                u = mine[j]
                if u is t or u.layer != t.layer or math.dist(xy, u.start) < 1e-3 or math.dist(xy, u.end) < 1e-3:
                    continue
                if lines[j].distance(q) <= u.width / 2 + 1e-6:
                    tees.setdefault(j, []).append((lines[j].project(q), ("e", t.layer, round(xy[0], 3), round(xy[1], 3))))
    for ti, t in enumerate(mine):
        a = node(("e", t.layer, round(t.start[0], 3), round(t.start[1], 3)))
        b = node(("e", t.layer, round(t.end[0], 3), round(t.end[1], 3)))
        ends += [(t.layer, t.start, a), (t.layer, t.end, b)]
        L = math.dist(t.start, t.end)
        # pads the track runs through without ending in them (a bus through a row of pins): a node there
        cuts = []
        if ptree is not None and L > 1e-6:
            line = LineString([t.start, t.end])
            for j in ptree.query(line, predicate="intersects"):
                tok, g, lys = pads[j]
                if lys and t.layer not in set(lys):
                    continue
                gb = g.buffer(1e-3)
                if gb.contains(Point(t.start)) or gb.contains(Point(t.end)):
                    continue
                cuts.append((line.project(g.centroid), tok))
        seq = sorted([(x, node(("c", tok, id(t)))) for x, tok in cuts] + [(x, node(k)) for x, k in tees.get(ti, ())])
        seq = [(0.0, a)] + seq + [(L, b)]
        for (x0, n0), (x1, n1) in zip(seq, seq[1:]):
            if n0 != n1:
                of_track[len(edges)] = ti
                edges.append((n0, n1, t.width / max(x1 - x0, 1e-3), "track"))
        for x, tok in cuts:
            edges.append((node(("p", tok)), node(("c", tok, id(t))), link, tok))
    if not ends:
        return {}
    tree = STRtree(shapely.points([e[1] for e in ends]))

    def attach(geom, layers, k, tag=None):
        done = set()
        for i in tree.query(geom, predicate="intersects"):
            if (layers is None or ends[i][0] in layers) and ends[i][2] not in done:
                done.add(ends[i][2])
                edges.append((k, ends[i][2], link, tag))
    pad_nodes = []
    for tok, g, layers in pads:
        k = node(("p", tok))
        pad_nodes.append((tok, g, set(layers or ()), k))
        attach(g.buffer(1e-3), set(layers or ()), k, tok)
    via_nodes = []
    for v in vias:
        if v.net not in nets:
            continue
        k = node(("v", v.uuid or (v.x, v.y)))
        g = Point(v.x, v.y).buffer(v.size / 2)
        via_nodes.append((g, k))
        attach(g, None if (v.type or "through") == "through" else set(v.layers or ()), k)
    for layer, geoms in (fills or {}).items():
        for i, fg in enumerate(geoms or ()):
            k = node(("f", layer, i))
            attach(fg, {layer}, k)
            for _tok, g, lys, pk in pad_nodes:
                if layer in lys and fg.intersects(g):
                    edges.append((k, pk, link, None))
            for g, vk in via_nodes:
                if fg.intersects(g):
                    edges.append((k, vk, link, None))
    # parts that conduct at DC between pads of these nets (a fuse, ferrite or diode feeding a rail): conductance in
    # the copper's units (1 / squares at the 1 oz sheet resistance)
    rs = MAT.RHO_CU_OHM_MM / MAT.CU_1OZ_MM
    for pa, pb, ohm in series or ():
        ka, kb = nodes.get(("p", pa)), nodes.get(("p", pb))
        if ka is not None and kb is not None and ka != kb:
            edges.append((ka, kb, min(link, rs / ohm) if ohm > 0 else link, None))
    n = len(nodes)
    I = np.array([e[0] for e in edges]); J = np.array([e[1] for e in edges]); G = np.array([e[2] for e in edges])
    L = SP.coo_matrix((np.r_[-G, -G, G, G], (np.r_[I, J, I, J], np.r_[J, I, I, J])), shape=(n, n)).tocsc()
    b = np.zeros(n)
    for tok, _g, _l, k in pad_nodes:
        b[k] = inj.get(tok, 0.0)
    _nc, comp = connected_components(L, directed=False)
    for c in set(comp[b != 0]):
        m = (comp == c) & (b != 0)
        b[m] -= b[comp == c].sum() / m.sum()
    V = SPL.spsolve(L + SP.identity(n, format="csc") * 1e-9, b)
    at = {}                     # track end node -> the pads it lies in
    for a, k, g, tag in edges:
        if tag not in (None, "track"):
            at.setdefault(k, set()).add(tag)
    out, n_in, loss, loss_g = {}, {}, 0.0, 0.0
    t_i = {}
    for e, (a, k, g, tag) in enumerate(edges):
        if tag == "track":
            i = abs(g * (V[a] - V[k]))
            w = mine[of_track[e]].width
            if multi:
                st_n = stats.setdefault(mine[of_track[e]].net, {}) if stats is not None else {}
                st_n["loss_sq"] = st_n.get("loss_sq", 0.0) + g * (V[a] - V[k]) ** 2
                st_n["loss_grown_sq"] = st_n.get("loss_grown_sq", 0.0) + i * i * (w / g) / max(w, grown_w or 0.0)
            loss += g * (V[a] - V[k]) ** 2
            loss_g += i * i * (w / g) / max(w, grown_w or 0.0)       # the same current in copper grown to grown_w
            t_i[of_track[e]] = max(t_i.get(of_track[e], 0.0), i)
            for tok in at.get(a, set()) | at.get(k, set()):
                out[tok] = max(out.get(tok, 0.0), i)
                n_in[tok] = n_in.get(tok, 0) + 1
    if stats is not None and multi:
        # per net: loss_sq / loss_grown_sq (above), entries, track_i
        for ti, i in t_i.items():
            if i > 0:
                stats.setdefault(mine[ti].net, {}).setdefault("track_i", []).append((lines[ti], i))
        stats.setdefault("_entries", {}).update(n_in)
    elif stats is not None:
        # loss_sq: the tracks' I^2 R in units of the sheet resistance (squares); entries: tracks into each pad
        stats["loss_sq"] = stats.get("loss_sq", 0.0) + float(loss)
        stats["loss_grown_sq"] = stats.get("loss_grown_sq", 0.0) + float(loss_g)
        stats.setdefault("entries", {}).update(n_in)
        # each track's current (for the pads that grown copper of a loaded track would reach)
        stats["track_i"] = stats.get("track_i", []) + [(lines[ti], i) for ti, i in t_i.items() if i > 0]
    return out


def _tht_narrow_fix(ref):
    """The fix text of tht_pad_kept_wide: which setting necks the pins anyway."""
    who = f"'{ref}'" if ref else "the connectors"
    return (f"If {who} carries little current (a signal header, a programming port) and is wave or hand soldered, add it "
            f"to the project text variable KAE_THT_NARROW (comma-separated refs or ref.pad), or opts tht_narrow, to neck "
            f"its pins; or give the operating facts the rail's loads.")


def _tht_fix(ref, pad):
    """The fix text of tht_pad_necked: which setting keeps the copper wide."""
    if ref:
        what = f"'{ref}' (all its pads)" + (f" or '{pad}' (this pad)" if pad else "")
        return (f"If this copper must stay wide (a heat path, selective soldering, preheat): add {what} to the "
                f"project text variable KAE_THT_WIDE (comma-separated refs or ref.pad), or opts tht_wide; "
                f"KAE_THT_NECK=off (project, opts tht_neck or env) turns the THT neck off board-wide.")
    return ("Name parts or pads to keep wide in the project text variable KAE_THT_WIDE (comma-separated refs or "
            "ref.pad), or opts tht_wide; KAE_THT_NECK=off (project, opts tht_neck or env) turns it off board-wide.")


def pad_currents(operating, pads, power, ground):
    """{(ref, net): A} through each pad, from operating facts, by the rules of the neck: a part's own
    current (I_A's upper end, else I_sustained_A) on its power and (when it has a power pad) ground
    pads, shared over its pads on that net; a two-terminal part in series with a rail (no ground pad)
    carries the rail's current (net_currents), as power_copper._necks; a part to ground with no power
    pad (a decap) carries none; signal pads none. `pads`: iterable of (ref, net), one per pad."""
    by_ref = {}
    for ref, net in pads:
        if ref and net:
            by_ref.setdefault(ref, []).append(net)
    parts = (operating or {}).get("parts") or {}
    rail = net_currents(operating, {r: set(n) for r, n in by_ref.items()}, power, ground) if operating else {}
    out = {}
    for ref, nets in by_ref.items():
        f = parts.get(ref) or {}
        ia = f.get("I_A")
        own = max(ia) if isinstance(ia, (list, tuple)) and ia else (ia if isinstance(ia, (int, float)) else None)
        if own is None:
            own = f.get("I_sustained_A")
        own = float(own) if isinstance(own, (int, float)) and own > 0 else 0.0
        s = set(nets)
        series = len(nets) == 2 and not s & set(ground) and s & set(power)
        for net in s:
            if series:
                i = max(rail.get(n, 0.0) for n in s)
            elif net in power or (net in ground and s & set(power)):
                i = own
            else:
                i = 0.0
            out[(ref, net)] = i / nets.count(net) if i else 0.0
    return out


def neck_half(dist, neck_w, neck_len):
    """Largest half-width (mm) copper centred `dist` mm from a necked land may have: the neck's half
    width, or more only where the wider copper stays neck_len clear of the land."""
    return np.maximum(neck_w / 2, np.asarray(dist) - neck_len)


def strips(region, w, pitch=None, angle=0.0):
    """Track centrelines [(a, b)] that cover `region` (a shapely polygon) with strips w wide: the
    contour of region shrunk by w/2, and parallel lines `pitch` apart (default 0.8 w) clipped to it.
    Every strip of width w lies inside `region`."""
    from shapely import affinity
    inner = region.buffer(-w / 2, join_style=2)
    if inner.is_empty:
        return []
    out = []
    polys = getattr(inner, "geoms", [inner])
    for pg in polys:
        for ring in [pg.exterior, *pg.interiors]:
            c = list(ring.coords)
            out += [(c[i], c[i + 1]) for i in range(len(c) - 1) if math.dist(c[i], c[i + 1]) > 1e-4]
    pitch = pitch or 0.8 * w
    rot = affinity.rotate(inner, -angle, origin=(0, 0)) if angle else inner
    x0, y0, x1, y1 = rot.bounds
    y = y0 + pitch / 2
    while y < y1:
        ln = LineString([(x0 - 1, y), (x1 + 1, y)]).intersection(rot)
        for g in getattr(ln, "geoms", [ln]):
            if g.geom_type == "LineString" and g.length > 1e-4:
                if angle:
                    g = affinity.rotate(g, angle, origin=(0, 0))
                c = list(g.coords)
                out.append((c[0], c[-1]))
        y += pitch
    return out


def width_ladder(orig, cap, ladder=DEFAULTS["ladder"]):
    """Widths to try for a track now `orig` wide, widest first: the ladder steps above `orig` and
    at most `cap`. Never narrower than `orig` (empty: nothing to widen)."""
    return sorted({w for w in ladder if orig + 1e-6 < w <= cap + 1e-9}, reverse=True)


def victim_gap(h, k=DEFAULTS["victim_k"], lo=DEFAULTS["victim_gap_min"], hi=DEFAULTS["victim_gap_max"]):
    """Spacing (mm) from a sensitive net for copper at height h over its reference: the crosstalk
    budget K = 1/(1+(D/h)^2) solved for D, clipped to [lo, hi]."""
    d = h * math.sqrt(1.0 / k - 1.0) if 0 < k < 1 else hi
    return min(hi, max(lo, d))


def signal_gap(base, victim_w, clr_mult=DEFAULTS["signal_clr_mult"], w_mult=DEFAULTS["signal_w_mult"]):
    """Spacing (mm) grown power copper keeps from an ordinary signal item: the board's clearance
    `base`, times clr_mult, and at least w_mult x the signal's width (0 for pads)."""
    return max(base, clr_mult * base, w_mult * victim_w)


def runs(widths, xs, orig, min_run):
    """Group per-sample widths along a track into runs [(x0, x1, w)].

    widths[i] is the widest legal width at abscissa xs[i] (orig where none is). A run's width is
    the minimum over its samples, so every point of a run is legal at it. Runs shorter than
    `min_run` (other than orig ones) are lowered to the narrower neighbour and merged, until none
    is left. Adjacent runs share their end point."""
    n = len(widths)
    if n == 0:
        return []
    seg = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(widths[j + 1] - widths[i]) < 1e-9:
            j += 1
        seg.append([i, j, widths[i]])
        i = j + 1

    def length(s):
        return xs[s[1]] - xs[s[0]]

    changed = True
    while changed and len(seg) > 1:
        changed = False
        for k, s in enumerate(seg):
            if s[2] <= orig + 1e-9 or length(s) >= min_run:
                continue
            nb = [seg[x] for x in (k - 1, k + 1) if 0 <= x < len(seg)]
            lo = min(nb, key=lambda t: t[2])
            if lo[2] >= s[2] - 1e-9:
                continue            # a short pinch between wider runs: legal as it is
            s[2] = lo[2]
            changed = True
            break
        # merge neighbours of equal width
        out = [seg[0]]
        for s in seg[1:]:
            if abs(s[2] - out[-1][2]) < 1e-9:
                out[-1][1] = s[1]
            else:
                out.append(s)
        seg = out
    if len(seg) == 1 and seg[0][2] > orig + 1e-9 and length(seg[0]) < min_run and xs[-1] - xs[0] >= min_run:
        seg[0][2] = orig
    res = []
    for k, (a, b, w) in enumerate(seg):
        x0 = xs[a] if k == 0 else res[-1][1]
        x1 = xs[b] if k == len(seg) - 1 else 0.5 * (xs[b] + xs[b + 1])
        res.append((x0, x1, w))
    return res


def ring_candidates(pad_geom, r_via, reach, step=0.1, n_ang=24):
    """Via centres around a pad, nearest first: on offsets of the pad outline from r_via + step to
    reach + r_via (the via's edge clear of the pad, its centre within `reach` of the pad edge)."""
    out = []
    d = r_via + step
    while d <= reach + r_via + 1e-9:
        ring = pad_geom.buffer(d, quad_segs=8).exterior
        L = ring.length
        m = max(n_ang, int(L / step))
        for k in range(m):
            p = ring.interpolate(k * L / m)
            out.append((d, p.x, p.y))
        d += step
    return out


# ----------------------------------------------------------------------------- nets
def classify(brief, board_nets):
    """(power, ground, switch, victims): net-name sets from the physics brief (kae.circuit.brief)."""
    nets = brief.get("nets") or {}
    power = {n for n, r in nets.items() if (r or {}).get("role") == "rail"}
    ground = {n for n, r in nets.items() if (r or {}).get("role") == "ground"}
    switch = {n for n, r in nets.items() if (r or {}).get("role") == "switch_node"}
    victims = {n for n, r in nets.items() if (r or {}).get("role") in VICTIM_ROLES}
    for s in brief.get("structures") or []:
        if s.get("kind") in ("victim", "crystal"):
            victims |= set(s.get("nets") or [])
        if s.get("kind") == "commutation_cell":
            if isinstance(s.get("sw"), str):
                switch.add(s["sw"])
            switch |= {x for x in s.get("sw_nets") or [] if isinstance(x, str)}
    power -= switch | ground
    victims -= power | ground
    return power & set(board_nets), ground & set(board_nets), switch, victims


# ----------------------------------------------------------------------------- ground vias (also kae.route.lastmile's arm E)
def ground_fill(fills, cache, net, layer, r):
    """The fill of `net` on `layer` shrunk by r (where a via of radius r lies wholly inside),
    prepared; cached in `cache`."""
    key = (net, layer, r)
    if key not in cache:
        g = unary_union((fills.get(net) or {}).get(layer) or [])
        if not g.is_empty:
            g = g.buffer(-r)
            shapely.prepare(g)
        cache[key] = g
    return cache[key]


def barrels_near(sp, net, geom, reach):
    """Whether a via or plated hole of `net` lies within `reach` of `geom`."""
    x0, y0, x1, y1 = geom.bounds
    for l in sp.cu:
        for it in sp.query(l, (x0, y0, x1, y1), reach + 1.0):
            if it.net != net:
                continue
            if it.kind == "via" and it.geom.distance(geom) <= reach:
                return True
            if it.kind == "pad" and it.hole is not None and it.geom.distance(geom) <= reach:
                return True
    return False


def ground_via_pads(sp, brief, ground):
    """SMD ground pads (Space items) of capacitors and of decoupled ICs' ground pins: the pads
    that get a ground via (PDN-01, docs/topics/rules/decoupling-pdn.md)."""
    parts = brief.get("parts") or {}
    want = set()
    for s in brief.get("structures") or []:
        if s.get("kind") == "decap" and s.get("ic"):
            for p in s.get("ground_pins") or []:
                want.add((s["ic"], str(p)))
    out = []
    for it in sp.pads:
        if it.kind != "pad" or not it.smd or it.net not in ground or not it.fp:
            continue
        kind = (parts.get(it.fp) or {}).get("kind")
        num = str(it.owner[1]) if it.owner else ""
        if kind == "capacitor" or (it.fp, num) in want:
            out.append(it)
    return out


def lay_ground_vias(sp, pads, fills, necks, o, cache=None, owner="pc-via"):
    """One through via per pad of `pads` (ground_via_pads) with no ground barrel within
    o["via_reach"], as close as is legal, where the same ground has fill on another layer, with
    a pad-to-via track no wider than o["via_track_max"], the land and its neck (`necks`: {id(pad
    Item): width}; a necked land's via keeps o["neck_via_gap"] from it, or with neck_via "track"
    sits on the land's routed track). Committed to `sp` as found. Yields (pad, (x, y), D, d,
    track) with track (layer, width, a, b) or None."""
    cache = {} if cache is None else cache
    for pad in pads:
        net = pad.net
        if barrels_near(sp, net, pad.geom, o["via_reach"]):
            continue
        D, d = sp.via_size(net)
        rv = D / 2
        layer = next(iter(sorted(pad.layers, key=sp.cu.index)), None)
        others = [l for l in sp.cu if l != layer]
        fl = [ground_fill(fills, cache, net, l, rv) for l in others]
        fl = [f for f in fl if not f.is_empty]
        if not fl:
            continue
        own = ground_fill(fills, cache, net, layer, rv)
        pos = pad.pos or (pad.geom.centroid.x, pad.geom.centroid.y)
        wt = sp.clamp_width(net, layer, min(o["via_track_max"], _short_side(pad.geom), necks.get(id(pad), math.inf)))
        entries = []
        if id(pad) in necks and o["neck_via"] == "track":
            # a necked land keeps one entry (balance with its sister land): the via sits on the
            # land's own routed track, at least neck_len from the land, and no second track enters
            entries = [it for it in sp.items[layer] if it.kind == "track" and it.net == net
                       and it.geom.distance(pad.geom) <= it.r + 1e-6]
            if not entries:
                continue
            cands = _via_on_tracks(entries, pad.geom, rv, o["neck_len"], o["via_reach"])
        elif id(pad) in necks:
            cands = [c for c in ring_candidates(pad.geom, rv, o["via_reach"])
                     if c[0] >= rv + o["neck_via_gap"] - 1e-9]
        else:
            cands = ring_candidates(pad.geom, rv, o["via_reach"])
        for dist, x, y in cands:
            p = Point(x, y)
            if not any(f.contains(p) for f in fl):
                continue
            if sp.via_violations(net, x, y, first=True):
                continue
            track_ok = not entries and not sp.track_violations(net, layer, wt, pos, (x, y), first=True)
            if not entries and not track_ok and not (not own.is_empty and own.contains(p)):
                continue
            sp.add_via(net, x, y, owner=(owner, pad.uuid))
            track = None
            if track_ok:
                sp.add_track(net, layer, wt, pos, (x, y), owner=(owner, pad.uuid))
                track = (layer, wt, pos, (x, y))
            yield pad, (x, y), D, d, track
            break


# ----------------------------------------------------------------------------- the pass
class PowerCopper:
    """Plans the copper for one board: `widen()`, `ground_vias()`, `stitch()`, then `write(dst)`."""

    def __init__(self, board_path, opts=None, info=None, brief=None, fills=None, log=print):
        from kae.board import pcbnew_io
        from kae.board.kicad_file import load
        from .critical_space import Space
        from .bridge import severities
        t0 = clock_now()
        self.path = Path(board_path).resolve()
        self.o = {**DEFAULTS, **(opts or {})}
        self.log = log
        self.board = load(self.path)
        if brief is None:
            from kae.circuit.brief import build
            brief = build(self.board)
        self.brief = brief
        if info is None:
            with tempfile.TemporaryDirectory(prefix="kae-pc-") as d:
                info = pcbnew_io.export_dsn(self.path, Path(d) / "board.dsn")
        self.sp = Space(self.board, info, sev=severities(self.path), opts=dict(no_corridors=False))
        A.fix_space_arcs(self.sp, self.board.tracks)      # arcs as sampled arcs, not two chords
        if fills is None:
            from .critical_recheck import fills_of
            fills = fills_of(self.path)
        self.fills = fills
        self.power, self.ground, self.switch, self.victims = classify(brief, self.board.nets)
        self.antenna_fps = {s.get("part") for s in brief.get("structures") or [] if s.get("kind") == "antenna"}
        cu = self.sp.cu
        z = self.sp.z
        self.h = {l: (min(abs(z[l] - z[m]) for m in cu if m != l) if len(cu) > 1 else self.sp.thickness) for l in cu}
        self.adj = {l: [cu[i] for i in (k - 1, k + 1) if 0 <= i < len(cu)] for k, l in enumerate(cu)}
        op = _operating(self.path, self.o.get("operating"))
        nets_of = {}
        for f in self.board.footprints:
            nets_of.setdefault(f.ref, set()).update(p.net for p in f.pads if p.net)
        self.current = net_currents(op, nets_of, self.power, self.ground) if op else {}
        asm = ((op or {}).get("requirements") or {}).get("assembly") or {}
        self.hand_solder = bool(asm.get("hand_solder_ok")) or asm.get("process") == "hand"
        self.process = process_of(asm)
        self.op = op
        self.caps = {}
        self.tht_necks = {}       # {id(pad Item): width} for plated THT pads (neck_rule tht=True)
        self.tht_necked = {}      # {id(pad Item): planned widths} where the THT neck bound (tht_pad_necked)
        self.tht_skipped = {}     # {reason: n} THT power/ground pads the rule leaves alone
        self.tht_amps, self._tht_geom = {}, {}
        self.tht_unknown = []     # THT pads left wide: no DC plan (connectors) or a neck over the loss budget
        self.tht_unknown_why = {} # {id(pad): (A, width the loss budget asks)} for the latter
        self.tht_unknown_heat = {}  # {id(pad): (hot part, W, radius mm)} for pads on a hot part's heat path
        self.tht_heat = {}        # {ref: W} linear regulators' dissipation from the DC plan
        self.tht_plan = 0         # injections in the DC plan the THT currents came from (0: none)
        self._entering = None     # ids of the THT pads the track being widened enters (None: not widening a track)
        self.necks = self._necks() if self.o.get("neck", True) else {}
        za = self.o.get("zone_above_a")
        self.zone_nets = ({n for n in self.power | self.ground if self.current.get(n, 0.0) > float(za)}
                          if za is not None else set())
        self.vector = []       # (net, layer, [(a, b, w, uuid)]) strips of the vector mode, one group each
        self.zones = []        # (net, layer, polygon, uuid) pieces of the vector mode written as zones
        self.edits = {}        # orig track uuid -> [(a, b, w)]
        self.vias = []         # (net, x, y, size, drill, uuid, kind)
        self.tracks = []       # (net, layer, w, a, b, uuid, owner)
        self.stats = dict(widened=0, widened_mm=0.0, ground_vias=0, stitch_vias=0)
        self.t_setup = clock_now() - t0
        log(f"[power-copper] currents {dict((k, round(v, 3)) for k, v in self.current.items())}")
        log(f"[power-copper] {len(self.power)} rails, {len(self.ground)} grounds, {len(self.switch)} switch nodes, "
            f"{len(self.victims)} victim nets; setup {self.t_setup:.1f}s")

    # ---------------------------------------------------------------- spacing
    def _extra(self, it, layer, own_layer):
        """Extra spacing (mm, edge to edge) grown power copper keeps from item `it`, None when the
        board's clearance is all (same group, or not a signal)."""
        net = it.net or ""
        if it.kind not in ("track", "via", "pad"):
            return None
        if it.kind == "pad" and it.fp in self.antenna_fps:
            return self.o["antenna_gap"]
        if not net or net in self.power or net in self.ground:
            return None
        if net in self.switch:
            return self.o["victim_gap_max"]
        if net in self.victims:
            return victim_gap(self.h[own_layer], self.o["victim_k"], self.o["victim_gap_min"], self.o["victim_gap_max"])
        if layer != own_layer:
            return None
        base = self.sp.need(it, "__power__", "track", layer) or 0.0
        return signal_gap(base, it.width if it.kind == "track" else 0.0, self.o["signal_clr_mult"], self.o["signal_w_mult"])

    def _constraints(self, net, layer, geom, reach, ignore):
        """[(geometry, radius, required gap)] around `geom` for grown copper of `net` on `layer`."""
        x0, y0, x1, y1 = geom.bounds
        out = []
        seen = set()
        for l in [layer] + self.adj[layer]:
            for it in self.sp.query(l, (x0, y0, x1, y1), reach):
                if id(it) in seen or it in ignore:
                    continue
                seen.add(id(it))
                if l == layer and it.kind == "pad" and it.net == net and id(it) in self.tht_necks \
                        and self._entering is not None and self._tht_geom[id(it.geom)] not in self._entering:
                    # a THT pad this track only passes (it ends elsewhere): no neck along the run; the grown
                    # copper keeps a relief-like gap from the pad, so the pad's only joint stays its own entries
                    out.append((it.geom, 0.0, self.o["tht_gap"], 1.0))
                    continue
                if l == layer and it.kind == "pad" and it.net == net and (
                        id(it) in self.necks or id(it) in self.caps or id(it) in self.tht_necks):
                    # necked land: f < 0 carries the neck width (see _allowed_half, _legal)
                    w = self.necks.get(id(it), self.tht_necks.get(id(it), self.caps.get(id(it))))
                    out.append((it.geom, 0.0, self.o["neck_len"], -w))
                    continue
                ex = self._extra(it, l, layer)
                if l == layer:
                    nd = self.sp.need(it, net, "track", layer)
                    if nd is None and ex is None:
                        continue
                    req = max(nd or 0.0, ex or 0.0)
                    if it.kind in ("keepout", "corridor"):
                        req = 0.0
                elif ex is None or it.kind == "pad" and it.fp not in self.antenna_fps:
                    continue
                else:
                    req = ex
                f = 1.0
                if self.o["share"] and l == layer and it.kind == "track" and it.net != net \
                        and it.net in self.power | self.ground \
                        and not (isinstance(it.owner, tuple) and str(it.owner[0]).startswith("pc-")):
                    # a competing power/ground track that has not grown yet: this net takes its
                    # current-proportional share of the room between them (min sum I^2 R at w ~ I)
                    f = share(self.current.get(net), self.current.get(it.net))
                out.append((it.geom, it.r, req, f))
        return out

    def _allowed_half(self, pts, cons, net, layer, h0=0.0):
        """Per sample point: the largest half-width the copper may have there (h0: the track's own
        half-width; a competing net's ungrown track leaves this net only its share of the gap)."""
        a = np.full(len(pts), np.inf)
        if cons:
            P = shapely.points(pts)
            for g, r, req, f in cons:
                if f < 0:
                    a = np.minimum(a, neck_half(shapely.distance(g, P) - TOL, -f, req))
                    continue
                d = shapely.distance(g, P) - r - req - TOL
                if f < 1.0:
                    d = np.where(d > h0, h0 + f * (d - h0), d)
                a = np.minimum(a, d)
        if self.sp.outline is not None:
            e = self.sp.edge_need(net, "track", layer)
            d = shapely.distance(self.sp.outline_boundary, shapely.points(pts)) - e - TOL
            inside = shapely.contains(self.sp.outline, shapely.points(pts))
            a = np.minimum(a, np.where(inside, d, -1.0))
        return a

    def _legal(self, net, layer, w, a, b, ignore, coords=None):
        """Whether a piece of width w is legal: a segment a-b, or the sampled arc `coords` (every
        requirement raised by the sampling's sagitta, arcs.polyline_violations)."""
        sag = 0.0
        if coords is not None:
            if A.polyline_violations(self.sp, net, layer, w, coords, ignore=ignore, first=True):
                return False
            seg = LineString(coords)
            sag = A.SAG
        elif self.sp.track_violations(net, layer, w, a, b, ignore=ignore, first=True):
            return False
        else:
            seg = LineString([a, b])
        for g, r, req, f in self._constraints(net, layer, seg, w / 2 + self.o["victim_gap_max"] + self.o["antenna_gap"], ignore):
            if f < 0:
                if w > -f + 1e-9 and g.distance(seg) - w / 2 < req - TOL:
                    return False
                continue
            if g.distance(seg) - r - w / 2 < req + TOL + sag:
                return False
        return True

    # ---------------------------------------------------------------- 1. widen
    def widen(self):
        sp = self.sp
        nets = self.power | self.ground
        by_uuid = {it.uuid: it for it in sp.existing if it.kind == "track"}
        ladder = self.o["ladder"]
        order = sorted(self.board.tracks, key=lambda t: (-self.current.get(t.net, 0.0), t.net in self.ground))
        for t in order:
            if t.net not in nets or t.net in self.zone_nets or t.layer not in sp.items:
                continue
            if t.mid is not None:
                self._widen_arc(t, by_uuid.get(t.uuid), ladder)
                continue
            it = by_uuid.get(t.uuid)
            if it is None:
                continue
            cap = sp.clamp_width(t.net, t.layer, width_cap(self.o["max_width"], self.current.get(t.net),
                                                            self.o["current_margin"], self.o["current_cap"]))
            steps = width_ladder(t.width, cap, ladder)
            if not steps:
                continue
            L = math.dist(t.start, t.end)
            if L < 1e-6:
                continue
            n = max(2, int(math.ceil(L / self.o["sample"])) + 1)
            xs = np.linspace(0.0, L, n)
            ux, uy = (t.end[0] - t.start[0]) / L, (t.end[1] - t.start[1]) / L
            pts = np.c_[t.start[0] + ux * xs, t.start[1] + uy * xs]
            seg = LineString([t.start, t.end])
            self._entering = self._entered(t)
            cons = self._constraints(t.net, t.layer, seg, steps[0] / 2 + self.o["victim_gap_max"] + self.o["antenna_gap"]
                                     + sp.max_need, {it})
            half = self._allowed_half(pts, cons, t.net, t.layer, t.width / 2)
            self._note_tht(pts, cons, half, t, steps)
            ws = [next((w for w in steps if w / 2 <= h), t.width) for h in half]
            rs = runs(ws, xs, t.width, self.o["min_run"])
            if all(w <= t.width + 1e-9 for _, _, w in rs):
                continue
            pieces = []
            for x0, x1, w in rs:
                a = (t.start[0] + ux * x0, t.start[1] + uy * x0)
                b = (t.start[0] + ux * x1, t.start[1] + uy * x1)
                if w > t.width + 1e-9:
                    for w2 in [s for s in steps if s <= w + 1e-9] + [t.width]:
                        if w2 <= t.width + 1e-9 or self._legal(t.net, t.layer, w2, a, b, {it}):
                            w = w2
                            break
                pieces.append((a, b, w))
            # merge equal neighbours again after the exact check
            merged = [list(pieces[0])]
            for a, b, w in pieces[1:]:
                if abs(w - merged[-1][2]) < 1e-9:
                    merged[-1][1] = b
                else:
                    merged.append([a, b, w])
            if all(w <= t.width + 1e-9 for _, _, w in merged):
                continue
            merged[0][0], merged[-1][1] = t.start, t.end
            sp.remove([it])
            for a, b, w in merged:
                sp.add_track(t.net, t.layer, w, a, b, owner=("pc-widen", t.uuid))
            self.edits[t.uuid] = [(tuple(a), tuple(b), w, t.uuid if i == 0 else W.new_uuid())
                                  for i, (a, b, w) in enumerate(merged)]
            self.stats["widened"] += 1
            self.stats["widened_mm"] += sum(math.dist(a, b) for a, b, w in merged if w > t.width + 1e-9)
        self.stats["widened_mm"] = round(self.stats["widened_mm"], 2)
        self._entering = None
        return self.stats["widened"]

    def _entered(self, t):
        """The THT pads (main pad Items) track t ends in or runs through: the necks that apply to it."""
        if not self._tht_geom:
            return set()
        line = LineString(A.track_coords(t)) if t.mid is not None else LineString([t.start, t.end])
        out = set()
        for it in self.sp.query(t.layer, line.bounds, 0.01):
            if it.kind == "pad" and id(it.geom) in self._tht_geom and it.geom.distance(line) < 1e-3:
                out.add(self._tht_geom[id(it.geom)])
        return out

    def _note_tht(self, pts, cons, half, t, steps):
        """Record, per THT pad whose neck bounds this track's planned width, the width the track
        would have been planned at without the neck and the width it is planned at (tht_pad_necked)."""
        if not self.tht_necks or not cons:
            return
        th = [c for c in cons if c[3] < 0 and id(c[0]) in self._tht_geom]
        if not th:
            return
        free = self._allowed_half(pts, [c for c in cons if not (c[3] < 0 and id(c[0]) in self._tht_geom)],
                                  t.net, t.layer, t.width / 2)
        P = shapely.points(pts)

        def w_of(h):
            return next((w for w in steps if w / 2 <= h), t.width)

        for g, _r, req, f in th:
            # the samples within neck_len of the pad, where the neck holds the copper below what it had room for
            d = shapely.distance(g, P)
            nh = neck_half(d - TOL, -f, req)
            bind = (d <= req) & (nh < free - 1e-9) & (half < free - 1e-9)
            if not bind.any():
                continue
            would = max(w_of(h) for h in free[bind])
            got = max(w_of(h) for h in half[bind])
            if would <= got + 1e-9:
                continue
            p = self._tht_geom[id(g)]
            rec = self.tht_necked.setdefault(id(p), dict(pad=p, would=0.0, got=0.0, layers=set()))
            rec["would"] = max(rec["would"], would)
            rec["got"] = max(rec["got"], got)
            rec["layers"].add(t.layer)

    def _widen_arc(self, t, it, ladder):
        """widen() for an arc track: the same sampling, runs and ladder along its arc length; each
        run becomes an arc of the same circle at its own width, checked exactly (sampled arc)."""
        sp = self.sp
        if it is None:
            return
        got = A.sme_to_csa(t.start, t.mid, t.end)
        if got is None:
            return
        c, rad, a0, sw = got
        cap = sp.clamp_width(t.net, t.layer, width_cap(self.o["max_width"], self.current.get(t.net),
                                                        self.o["current_margin"], self.o["current_cap"]))
        steps = width_ladder(t.width, cap, ladder)
        if not steps:
            return
        L = abs(rad * sw)
        if L < 1e-6:
            return
        n = max(2, int(math.ceil(L / self.o["sample"])) + 1)
        xs = np.linspace(0.0, L, n)
        ang = a0 + sw * xs / L
        pts = np.c_[c[0] + rad * np.cos(ang), c[1] + rad * np.sin(ang)]
        geom = LineString(A.track_coords(t))
        self._entering = self._entered(t)
        cons = self._constraints(t.net, t.layer, geom, steps[0] / 2 + self.o["victim_gap_max"] + self.o["antenna_gap"]
                                 + sp.max_need, {it})
        half = self._allowed_half(pts, cons, t.net, t.layer, t.width / 2)
        self._note_tht(pts, cons, half, t, steps)
        ws = [next((w for w in steps if w / 2 <= h), t.width) for h in half]
        rs = runs(ws, xs, t.width, self.o["min_run"])
        if all(w <= t.width + 1e-9 for _, _, w in rs):
            return

        def sub(x0, x1):
            b0, b1 = a0 + sw * x0 / L, a0 + sw * x1 / L
            return (c, rad, b0, b1 - b0)

        pieces = []
        for x0, x1, w in rs:
            cc, rr, b0, bs = sub(x0, x1)
            coords = A.arc_coords(cc, rr, b0, bs)
            if w > t.width + 1e-9:
                for w2 in [s for s in steps if s <= w + 1e-9] + [t.width]:
                    if w2 <= t.width + 1e-9 or self._legal(t.net, t.layer, w2, None, None, {it}, coords=coords):
                        w = w2
                        break
            pieces.append([x0, x1, w])
        merged = [pieces[0]]
        for x0, x1, w in pieces[1:]:
            if abs(w - merged[-1][2]) < 1e-9:
                merged[-1][1] = x1
            else:
                merged.append([x0, x1, w])
        if all(w <= t.width + 1e-9 for _, _, w in merged):
            return
        sp.remove([it])
        out = []
        # joints computed once, so neighbouring pieces share their end points exactly
        joints = [tuple(t.start)] + [A.point_at(c, rad, a0 + sw * x1 / L) for _, x1, _ in merged[:-1]] + [tuple(t.end)]
        for i, (x0, x1, w) in enumerate(merged):
            cc, rr, b0, bs = sub(x0, x1)
            _, m_, _ = A.csa_to_sme(cc, rr, b0, bs)
            s_, e_ = joints[i], joints[i + 1]
            nit = sp.add_track(t.net, t.layer, w, s_, e_, owner=("pc-widen", t.uuid))
            nit.geom = LineString(A.arc_coords(cc, rr, b0, bs))
            x0_, y0_, x1_, y1_ = nit.geom.bounds
            nit.bbox = (x0_ - w / 2, y0_ - w / 2, x1_ + w / 2, y1_ + w / 2)
            out.append((tuple(s_), tuple(e_), w, t.uuid if i == 0 else W.new_uuid(), tuple(m_)))
        sp.invalidate(t.layer)
        self.edits[t.uuid] = out
        self.stats["widened"] += 1
        self.stats["widened_arcs"] = self.stats.get("widened_arcs", 0) + 1
        self.stats["widened_mm"] += sum(abs(rad * sw * (x1 - x0) / L) for x0, x1, w in merged if w > t.width + 1e-9)

    # ---------------------------------------------------------------- 1b. vector growth
    def grow_vector(self, nets=None, out=None):
        """Vector mode: per power/ground net and layer, the free region around the net's copper
        (the layer minus every foreign item grown by its required gap, the board edge, and other
        nets' fills unless into_pours), clipped to a corridor max_width/2 around the net's tracks
        and pads. Nets competing for the same room share it by current: all grow together, each
        at a speed proportional to its current (a multiplicatively weighted Voronoi split, by
        repeated buffering), keeping the board clearance between them; the boundary sits where
        d_i/I_i = d_j/I_j, so widths come out proportional to current (least sum I^2 R). Each
        connected piece that touches the net's copper and adds at least vector_min_gain mm2 is
        filled with overlapping track strips (or written as one zone: vector_out, or `out`). `nets`:
        the nets grown (default every power and ground net)."""
        sp = self.sp
        reach = self.o["victim_gap_max"] + self.o["antenna_gap"] + sp.max_need + 0.1
        n_strips = 0
        area = 0.0
        self.vector_share = {}
        for layer in sp.cu:
            cand = {}
            for net in sorted(nets if nets is not None else self.power | self.ground):
                own = [it for it in sp.items[layer] if it.net == net and it.kind in ("track", "pad")]
                if not any(it.kind == "track" for it in own):
                    continue
                cap = width_cap(self.o["max_width"], self.current.get(net), self.o["current_margin"], self.o["current_cap"])
                seeds = unary_union([it.geom.buffer(it.r) if it.r else it.geom for it in own])
                corridor = seeds.buffer(cap / 2)
                if sp.outline is not None:
                    corridor = corridor.intersection(sp.outline.buffer(-(sp.edge_need(net, "track", layer) + VTOL)))
                if corridor.is_empty:
                    continue
                # polygon margin: chord sag of round shapes (pads are already polygons inscribed in their
                # arcs) and the 0.01 mm simplification below
                obs = [g.buffer(r + req + VTOL, quad_segs=8) for g, r, req, _ in
                       self._constraints(net, layer, corridor, reach, ())]
                # (a necked land comes back as (land, 0, neck_len, -w): grown copper stays neck_len
                # away and only the routed track, no wider than the neck, enters the land)
                fills = []
                for n2, byl in self.fills.items():
                    for g in byl.get(layer) or []:
                        if n2 == net:
                            fills.append(g)
                        elif not self.o["into_pours"] and g.intersects(corridor):
                            obs.append(g.buffer(sp._generic_need(net, "track", layer) + VTOL))
                free = corridor.difference(unary_union(obs)) if obs else corridor
                own_fill = unary_union(fills) if fills else None
                if own_fill is not None and not own_fill.is_empty:
                    free = free.difference(own_fill.buffer(-0.3))
                cand[net] = dict(seeds=seeds, free=free, cap=cap, fill=own_fill, claim=None)
            if not cand:
                continue
            claims = self._share_room(cand, layer)
            for net, c in cand.items():
                claim = claims.get(net)
                if claim is None or claim.is_empty:
                    continue
                w = sp.clamp_width(net, layer, self.o["vector_strip"])
                seeds, own_fill = c["seeds"], c["fill"]
                for piece in getattr(claim, "geoms", [claim]):
                    if piece.is_empty or piece.geom_type != "Polygon" or not piece.intersects(seeds):
                        continue
                    gain = piece.difference(seeds)
                    if own_fill is not None and not own_fill.is_empty:
                        gain = gain.difference(own_fill)
                    if gain.area < self.o["vector_min_gain"]:
                        continue
                    piece = piece.simplify(0.01)
                    if (out or self.o["vector_out"]) == "zones":
                        gid = W.new_uuid()
                        self.zones.append((net, layer, piece, gid))
                        sp.add_track(net, layer, 0.0, *_any_segment(piece), owner=("pc-vector", gid))
                        n_strips += 1
                        area += gain.area
                        self.vector_share[net] = self.vector_share.get(net, 0.0) + gain.area
                        continue
                    segs = strips(piece, w)
                    if not segs:
                        continue
                    caps = [LineString([a, b]).buffer(w / 2, quad_segs=4) for a, b in segs]
                    U = unary_union(caps + [seeds.intersection(piece.buffer(0.01))])
                    keep_comp = [k for k in getattr(U, "geoms", [U]) if k.intersects(seeds)]
                    if not keep_comp:
                        continue
                    K = unary_union(keep_comp)
                    gid = W.new_uuid()
                    kept = [(a, b, w, W.new_uuid()) for (a, b), cp in zip(segs, caps) if cp.intersects(K)]
                    if not kept:
                        continue
                    for a, b, ww, u in kept:
                        sp.add_track(net, layer, ww, a, b, owner=("pc-vector", gid))
                    self.vector.append((net, layer, kept, gid))
                    n_strips += len(kept)
                    area += gain.area
                    self.vector_share.setdefault(net, 0.0)
                    self.vector_share[net] += gain.area
        self.stats["vector_pieces"] = len(self.vector)
        self.stats["vector_strips"] = n_strips
        self.stats["vector_mm2"] = round(area, 1)
        self.stats["vector_mm2_by_net"] = {k: round(v, 1) for k, v in sorted(self.vector_share.items())}
        return len(self.vector)

    def _gap(self, a, b, layer):
        c = self.sp._pair(a, b, layer)
        return (c.track_track if c is not None else self.sp.max_need) + VTOL

    def _share_room(self, cand, layer, steps=30):
        """{net: claimed region}: every net grows from its copper inside its own free region, at a
        speed proportional to its current (equal without currents; weights floored at 1/10 of the
        largest), never within the pair clearance of another net's claim; after `steps` rounds each
        net takes what is left of its corridor."""
        nets = list(cand)
        cur = {n: abs(self.current.get(n) or 0.0) for n in nets}
        top = max(cur.values()) if cur else 0.0
        wt = {n: (max(cur[n] / top, 0.1) if top > 0 and cur[n] > 0 else (1.0 if top <= 0 else 0.1)) for n in nets}
        order = sorted(nets, key=lambda n: -wt[n])
        claim = {n: None for n in nets}

        def others(n):
            gs = [claim[m].buffer(self._gap(n, m, layer), quad_segs=4) for m in nets
                  if m != n and claim[m] is not None and not claim[m].is_empty]
            return unary_union(gs) if gs else None

        def grow(n, radius):
            c = cand[n]
            g = c["seeds"].buffer(radius, quad_segs=4).intersection(c["free"])
            o = others(n)
            if o is not None:
                g = g.difference(o)
            claim[n] = g

        if len(nets) > 1 and self.o["share"]:
            R = max(cand[n]["cap"] / 2 for n in nets)
            for s in range(1, steps + 1):
                t = R * s / steps
                for n in order:
                    grow(n, min(cand[n]["cap"] / 2, t * wt[n]))
        for n in order:
            grow(n, cand[n]["cap"] / 2)
        return claim

    # ---------------------------------------------------------------- 2. ground vias at pads
    def _ground_fill(self, net, layer, r):
        c = getattr(self, "_gf", {})
        self._gf = c
        return ground_fill(self.fills, c, net, layer, r)

    def _barrels_near(self, net, geom, reach):
        return barrels_near(self.sp, net, geom, reach)

    def _target_pads(self):
        return ground_via_pads(self.sp, self.brief, self.ground)

    def ground_vias(self):
        cache = getattr(self, "_gf", {})
        self._gf = cache
        n = 0
        for pad, (x, y), D, d, track in lay_ground_vias(self.sp, self._target_pads(), self.fills, self.necks, self.o,
                                                        cache=cache):
            self.vias.append((pad.net, x, y, D, d, W.new_uuid(), "pad"))
            if track is not None:
                layer, wt, a, b = track
                self.tracks.append((pad.net, layer, wt, a, b, W.new_uuid(), self.vias[-1][5]))
            n += 1
        self.stats["ground_vias"] = n
        return n

    # ---------------------------------------------------------------- 3. stitch weak pour pieces
    def stitch(self):
        sp = self.sp
        added = 0
        nk = [it.geom for it in sp.pads if id(it) in self.necks]
        necked = unary_union(nk) if nk else None
        for net in sorted(self.ground):
            byl = self.fills.get(net) or {}
            unions = {l: unary_union(v) for l, v in byl.items() if v}
            D, d = sp.via_size(net)
            for l, u in unions.items():
                pieces = [g for g in getattr(u, "geoms", [u]) if g.area >= self.o["stitch_min_area"]]
                if len(pieces) < 2:
                    continue
                big = max(pieces, key=lambda g: g.area)
                others = [self._ground_fill(net, k, D / 2) for k in unions if k != l]
                others = [o for o in others if not o.is_empty]
                if not others:
                    continue
                for g in pieces:
                    if g is big:
                        continue
                    pads = [it for it in sp.pads if it.net == net and l in it.layers and it.geom.intersects(g)]
                    if not pads:
                        continue
                    bar = sum(1 for it in sp.pads if it.net == net and it.hole is not None and it.geom.intersects(g))
                    bar += sum(1 for it in sp.routed + sp.existing if it.kind == "via" and it.net == net and g.contains(it.geom))
                    if bar >= self.o["stitch_want"]:
                        continue
                    inner = g.buffer(-(D / 2 + 0.1))
                    if inner.is_empty:
                        continue
                    # candidates near the piece's pads (within 3 mm), nearest first
                    near = unary_union([p.geom for p in pads]).buffer(3.0).intersection(inner)
                    if near.is_empty:
                        continue
                    x0, y0, x1, y1 = near.bounds
                    step = max(0.25, D / 2)
                    gx, gy = np.meshgrid(np.arange(x0, x1 + 1e-9, step), np.arange(y0, y1 + 1e-9, step))
                    gx, gy = gx.ravel(), gy.ravel()
                    shapely.prepare(near)
                    ok = shapely.contains_xy(near, gx, gy)
                    for o in others:
                        shapely.prepare(o)
                    ok &= np.any([shapely.contains_xy(o, gx, gy) for o in others], axis=0)
                    gx, gy = gx[ok], gy[ok]
                    if not len(gx):
                        continue
                    padu = unary_union([p.geom for p in pads])
                    dist = shapely.distance(padu, shapely.points(np.c_[gx, gy]))
                    order = np.argsort(dist, kind="stable")
                    cands = [(float(gx[i]), float(gy[i])) for i in order]
                    placed = []
                    for x, y in cands:
                        if bar + len(placed) >= self.o["stitch_want"]:
                            break
                        if any(math.dist((x, y), q) < self.o["stitch_pitch"] for q in placed):
                            continue
                        if necked is not None and necked.distance(Point(x, y)) < self.o["neck_len"] + D / 2:
                            continue        # vias keep off small lands (thermal balance)
                        if sp.via_violations(net, x, y, first=True):
                            continue
                        sp.add_via(net, x, y, owner=("pc-stitch", l))
                        self.vias.append((net, x, y, D, d, W.new_uuid(), "stitch"))
                        placed.append((x, y))
                    added += len(placed)
        self.stats["stitch_vias"] = added
        return added

    # ---------------------------------------------------------------- writing
    def write(self, dst, skip=frozenset(), kinds=("widen", "vector", "pad", "stitch")):
        """dst = the input with the planned copper; `skip`: uuids (original track or added item)
        left out; `kinds`: the stages written. Returns {uuid of a written item: its group}."""
        text = self.path.read_text(encoding="utf-8")
        groups = {}
        widen = {u: p for u, p in self.edits.items() if "widen" in kinds and u not in skip}
        out, pos = [], 0
        tracks = {}
        for head, a, b in W._blocks(text, ("segment", "arc")):
            blk = text[a:b]
            u = W._uuid_of(blk)
            if u not in widen:
                continue
            m_net = re.search(r'\(net\s+("(?:[^"\\]|\\.)*"|\S+?)\)', blk)
            m_layer = re.search(r'\(layer\s+"([^"]+)"\)', blk)
            locked = "(locked yes)" in blk
            net = self._net_name(m_net.group(1)) if m_net else None
            out.append(text[pos:a])
            pos = W._eat_newline(text, b)
            for piece in widen[u]:
                pa, pb, w, nu = piece[:4]
                groups[nu] = u
                if len(piece) > 4 and piece[4] is not None:
                    out.append(A.arc_sexpr(net, m_layer.group(1), w, pa, piece[4], pb, uid=nu, locked=locked))
                else:
                    out.append(W.track_sexpr(net, m_layer.group(1), w, pa, pb, uid=nu, locked=locked))
            tracks[u] = True
        out.append(text[pos:])
        text = "".join(out)
        chunks = []
        if "vector" in kinds:
            for net, layer, kept, gid in self.vector:
                for a, b, w, u in kept:
                    if u in skip:
                        continue
                    groups[u] = u           # one strip per group: a violation reverts only its strip
                    chunks.append(W.track_sexpr(net, layer, w, a, b, uid=u, locked=False))
        if "vector" in kinds and self.zones:
            prio = {}
            for z in self.board_zone_priorities():
                prio[z[0]] = max(prio.get(z[0], 0), z[1])
            for net, layer, poly, u in self.zones:
                if u in skip:
                    continue
                groups[u] = u
                chunks.append(zone_sexpr(net, layer, poly, u, priority=prio.get(layer, 0) + 1,
                                         solid=self.process != "hand",
                                         min_thickness=max(0.1, self.sp.width_limits(net, layer)[0])))
        vias = [v for v in self.vias if v[6] in kinds and v[5] not in skip]
        keep = {v[5] for v in vias}
        for v in vias:
            groups[v[5]] = v[5]
            chunks.append(W.via_sexpr(v[0], v[1], v[2], v[3], v[4], uid=v[5], locked=False))
        for net, layer, w, a, b, u, owner in self.tracks:
            if owner in keep:
                groups[u] = owner
                chunks.append(W.track_sexpr(net, layer, w, a, b, uid=u, locked=False))
        Path(dst).write_text(W._insert(text, chunks), encoding="utf-8")
        for ext in (".kicad_pro", ".kicad_dru"):
            s, t = self.path.with_suffix(ext), Path(dst).with_suffix(ext)
            if s.exists() and s.resolve() != t.resolve():
                shutil.copy2(s, t)
        return groups

    def group_geoms(self):
        """{group: shapely geometry} of every planned change (a widened track's pieces, a via
        with its pad-to-via track)."""
        out = {}
        for u, pieces in self.edits.items():
            gs = []
            for pc in pieces:
                a, b, w = pc[:3]
                if len(pc) > 4 and pc[4] is not None:
                    gs.append(LineString(A.arc_coords(*A.sme_to_csa(a, pc[4], b))).buffer(w / 2))
                else:
                    gs.append(LineString([a, b]).buffer(w / 2))
            out[u] = unary_union(gs)
        for net, layer, kept, gid in self.vector:
            for a, b, w, u in kept:
                out[u] = LineString([a, b]).buffer(w / 2, quad_segs=4)
        for net, layer, poly, u in self.zones:
            out[u] = poly
        for v in self.vias:
            out[v[5]] = Point(v[1], v[2]).buffer(v[3] / 2)
        for net, layer, w, a, b, u, owner in self.tracks:
            if owner in out:
                out[owner] = out[owner].union(LineString([a, b]).buffer(w / 2))
        return out

    def _necks(self):
        """{id(pad Item): neck width} for the lands of two-terminal SMD parts (land_necks). Lands that get
        no neck because their series current needs more than the land go to self.unnecked (hazards)."""
        lands = {fp: [(id(p), p.smd, p.net, _short_side(p.geom)) for p in pads if p.kind == "pad"]
                 for fp, pads in self.sp.pads_by_fp.items()}
        self.caps = {}
        tht_cur = self._tht_pads(lands)
        necks, series = land_necks(lands, self.power, self.ground, self.current, self.process, self.o["current_margin"],
                                   tht_len=self._tht_len(), tht_dk=self.o["tht_neck_dK"],
                                   tht_current=tht_cur)
        if self.o.get("land_cap", True):
            # every other SMD land (IC pins, parts with alternate pads) gets no grown copper wider than
            # itself within neck_len: a 2.5 mm ground track into a 0.6 mm SOIC pin is a bridge and
            # wicking risk (route-finish-ab stage 1: 16 mm^2 on one pin); the land's own copper and
            # the router's track are untouched
            for fp, pads in self.sp.pads_by_fp.items():
                for p in pads:
                    if p.kind == "pad" and p.smd and id(p) not in necks and id(p) not in series:
                        self.caps[id(p)] = _short_side(p.geom)
        self.unnecked = []
        for fp, pads in self.sp.pads_by_fp.items():
            for p in pads:
                if p.kind == "pad" and id(p) in series and id(p) not in necks:
                    self.unnecked.append((fp, p, series[id(p)]))
        # plated THT pads: their necks go to tht_necks (ground vias and stitching only see SMD necks); the
        # barrel copy of a pad on a layer where it has no ring (critical_space) gets its pad's neck
        self.tht_necks, self.tht_amps = {}, {}
        self._tht_geom = {}
        for fp, pads in self.sp.pads_by_fp.items():
            for p in pads:
                if id(p) in tht_cur:
                    self.tht_amps[id(p)] = tht_cur[id(p)]
                    if id(p) in necks:
                        self.tht_necks[id(p)] = max(necks.pop(id(p)), getattr(self, "tht_floor", {}).get(id(p), 0.0))
                        self._tht_geom[id(p.geom)] = p
        for fp, hbs in getattr(self.sp, "barrels_by_fp", {}).items():
            for hb in hbs:
                main = next((p for p in self.sp.pads_by_fp.get(fp, ()) if p.idx == hb.idx and p is not hb), None)
                if main is not None and id(main) in self.tht_necks:
                    self.tht_necks[id(hb)] = self.tht_necks[id(main)]
                    self._tht_geom[id(hb.geom)] = main
        return necks

    def tht_stats(self):
        """THT pads necked (planned), pads where the neck bound grown copper, pads left alone by reason."""
        return dict(necked_pads=len({id(p) for p in self._tht_geom.values()}), bound_pads=len(self.tht_necked),
                    unnecked_for_current=sum(1 for _f, p, _a in getattr(self, "unnecked", []) if not p.smd),
                    skipped=dict(self.tht_skipped), dc_plan_pads=self.tht_plan)

    def _tht_pads(self, lands):
        """{id(pad Item): A} for the plated through-hole pads of power and ground nets the THT neck
        applies to, and self.tht_skipped counts the others by reason. Left alone, each for its reason:
        - "off": the tht_neck setting is off (board-wide);
        - "tht_wide": the pad or its part is in the tht_wide setting (the commanding LLM knows it is a
          heat path or selectively soldered);
        - "unsoldered": mounting holes, heat sinks, mechanical parts and fiducials (kae.circuit.brief's
          part kinds), board-only footprints: no joint whose heat the copper could drain;
        - "hot": parts the operating facts give at least heat_min_W (P_sustained_W), a heat sink on the
          part, or a thermal resistance (theta_jb / jc / ja): copper spreading their heat is wanted (thermal_vias' and pcb-cooling's rule: no relief
          on heat-carrying pins);
        - "zone": pads joined to a fill of their own net: the zone's own pad connection (thermal relief
          or solid, the zone's setting) already sets the joint's drain, and the plane dominates any track.
        A pad's current: the largest current in a track entering it (branch_currents) under the physics
        evaluator's DC plan (_tht_flows): a feed pin carries its rail's loads, a pad in a chain what lies
        beyond it. Without a plan: a connector's pins keep their copper ("no_current", tht_pad_kept_wide,
        unless named in tht_narrow); other parts' pads take their part's own current (pad_currents)."""
        from . import constraints as CN
        from kae.place import heat
        on = str(CN.setting_env("tht_neck", self.path, self.o)).strip().lower() not in ("0", "0.0", "off", "no", "false")
        wide = tht_wide_set(CN.setting_env("tht_wide", self.path, self.o))
        nets = self.power | self.ground
        cand = []
        for fp, pads in self.sp.pads_by_fp.items():
            for p in pads:
                if p.kind != "pad" or p.smd or p.hole is None or p.net not in nets:
                    continue
                pd = (self.sp.info.get("pads") or [])[p.idx] if p.idx is not None else {}
                if pd.get("attr") != "pth":
                    continue
                cand.append((fp, p))
        skipped = {}
        if not cand:
            self.tht_skipped = skipped
            return {}
        if not on:
            self.tht_skipped = {"off": len(cand)}
            return {}
        kinds = {u: (d or {}).get("kind") for u, d in ((self.brief or {}).get("parts") or {}).items()}
        attrs = {f.uuid: set(f.attrs or ()) for f in self.board.footprints}
        op = self.op or {}
        w_min = float(CN.setting("heat_min_W", self.path, self.o))
        # hot: dissipating heat_min_W or more, a heat sink on the part, or a thermal path the facts give (theta_jb /
        # theta_jc / theta_ja: the compiler gives them for parts whose heat matters, e.g. an LM7805's TO-220 pins)
        hot = ({r for r, w in heat.watts(op).items() if w >= w_min} | {h.get("part") for h in heat.sinks(op) if h.get("part")}
               | {r for r, f in (op.get("parts") or {}).items() if isinstance(f, dict)
                  and any(f.get(k) is not None for k in ("theta_jb_C_W", "theta_jc_C_W", "theta_ja_C_W"))})
        keep = []
        for fp, p in cand:
            ref, num = p.owner if isinstance(p.owner, tuple) else (None, None)
            why = tht_exempt(ref, num, kinds.get(fp), attrs.get(fp, ()), hot, self._zone_joined(p), wide)
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            keep.append((fp, p, ref, num))
        narrow = tht_wide_set(CN.setting_env("tht_narrow", self.path, self.o))
        flows = self._tht_flows({p.net for _f, p, _r, _n in keep}) if keep else None
        own = {}
        if flows is None and keep:
            all_pads = [(p.owner[0] if isinstance(p.owner, tuple) else None, p.net)
                        for pads in self.sp.pads_by_fp.values() for p in pads if p.kind == "pad"]
            own = pad_currents(op, all_pads, self.power, self.ground) if op else {}
        heat_near = self._heat_paths(hot, op, w_min) if keep else set()
        out = {}
        floor = self._loss_floor(keep, flows) if flows is not None else {}
        self.tht_floor = {}
        for fp, p, ref, num in keep:
            if id(p) in heat_near and not (ref in narrow or f"{ref}.{num}" in narrow):
                # within a hot part's spreading radius: its copper carries that part's heat (any net); the
                # pad keeps it and the commanding LLM decides (tht_pad_kept_wide, KAE_THT_NARROW)
                skipped["heat_path"] = skipped.get("heat_path", 0) + 1
                self.tht_unknown.append(p)
                self.tht_unknown_heat[id(p)] = heat_near[id(p)]
                continue
            if flows is not None:
                fl = floor.get(id(p), 0.0)
                if fl == math.inf and not (ref in narrow or f"{ref}.{num}" in narrow):
                    # a neck narrow enough to act as a relief would cost more copper loss than the budget: the
                    # pad keeps its copper and the commanding LLM decides (tht_pad_kept_wide, KAE_THT_NARROW)
                    skipped["loss"] = skipped.get("loss", 0) + 1
                    self.tht_unknown.append(p)
                    self.tht_unknown_why[id(p)] = (flows.get(f"{ref}.{num}", 0.0), fl)
                    continue
                if fl and not (ref in narrow or f"{ref}.{num}" in narrow):
                    self.tht_floor[id(p)] = fl
                out[id(p)] = flows.get(f"{ref}.{num}", 0.0)
                continue
            if kinds.get(fp) == "connector" and not (ref in narrow or f"{ref}.{num}" in narrow):
                # no DC plan: a connector pin on a rail may feed the board with any current; it keeps its copper
                # and the commanding LLM decides (tht_pad_kept_wide, KAE_THT_NARROW)
                skipped["no_current"] = skipped.get("no_current", 0) + 1
                self.tht_unknown.append(p)
                continue
            out[id(p)] = own.get((ref, p.net), 0.0)
        self.tht_skipped = skipped
        return out

    def _tht_flows(self, nets):
        """{pad token: A} through the tracks into the pads of `nets` (branch_currents) under the physics
        evaluator's DC plan (kae.excite.dc.planned_injections) of this board and its operating facts; None
        when there is no plan (no rail with a source and a load), so callers do not read 0 A into it."""
        from kae.board.kicad_file import load
        from kae.excite import dc as DC
        from shapely.strtree import STRtree
        self.tht_heat = {}
        branches = []
        try:
            inj = DC.planned_injections(load(self.path), self.op, heat=self.tht_heat, branches=branches)
        except Exception as e:      # noqa: BLE001 - no plan: the caller's fallback, never a failed pass
            self.log(f"[power-copper] THT neck: no DC plan ({type(e).__name__}: {e})")
            return None
        if not inj:
            return None
        # one solve over every rail and ground with the parts that conduct at DC between them, as the evaluator's DC
        # copper: current fed through a fuse, ferrite or diode into a rail is seen on both sides
        solve_nets = set(nets) | self.power | self.ground
        pads = {}
        for fps in self.sp.pads_by_fp.values():
            for p in fps:
                if p.kind == "pad" and p.net in solve_nets and isinstance(p.owner, tuple):
                    pads.setdefault(p.net, []).append((f"{p.owner[0]}.{p.owner[1]}", p.geom, p.layers))
        fills = {}
        for n_ in solve_nets:
            for l, gs in (self.fills.get(n_) or {}).items():
                fills.setdefault(l, []).extend(gs)
        self.tht_flow_stats = {}
        out = branch_currents(solve_nets, self.board.tracks, getattr(self.board, "vias", []) or [],
                              [x for v in pads.values() for x in v], fills, inj, stats=self.tht_flow_stats,
                              grown_w=self.o["max_width"], series=branches)
        ent = self.tht_flow_stats.pop("_entries", {})
        for n_ in solve_nets:
            self.tht_flow_stats.setdefault(n_, {})["entries"] = ent
        self.tht_plan = len(inj)
        # a pad within reach of a loaded track's grown copper (max_width / 2 + neck_len) is part of that path once
        # the copper grows (wide rails merge into neighbouring pads of their net): it counts that current too
        reach = self.o["max_width"] / 2 + self.o["neck_len"]
        for net, plist in pads.items():
            tr = (self.tht_flow_stats.get(net) or {}).get("track_i") or []
            if not tr:
                continue
            tree = STRtree([ln for ln, _i in tr])
            for tok, g, _l in plist:
                for j in tree.query(g.buffer(reach)):
                    ln, i = tr[j]
                    if i > out.get(tok, 0.0) and ln.distance(g) <= reach:
                        out[tok] = i
        return out

    def _heat_paths(self, hot, op, w_min):
        """{id(pad): (ref, W, radius)} for the THT pads within a hot part's heat-spreading radius. A part is hot
        as in _tht_pads (the "hot" exemption covers its own pads) or by the DC plan's linear-regulator drop of
        at least heat_min_W. Radius: where the part's dissipation P holds an infinite board fin (kernels.fin_point:
        the board's copper layers at tht_heat_fill, k_Cu 390, FR-4 0.8, h 10 W/m^2K a face) tht_heat_dK above
        ambient; a hot part without a known P (theta or a heat sink only) has no heat path beyond its own pads.
        Copper there carries that part's heat (pcb-cooling: the pour within ~1.5-2 lambda is what cools it)."""
        from kae.physics import kernels as KN
        from scipy.special import k0
        watts = {}
        for r, f in (op.get("parts") or {}).items():
            w = (f or {}).get("P_sustained_W") if isinstance(f, dict) else None
            if isinstance(w, (int, float)) and w > 0:
                watts[r] = float(w)
        for r, w in (getattr(self, "tht_heat", {}) or {}).items():
            watts[r] = max(watts.get(r, 0.0), w)
        refs = set(hot) | {r for r, w in watts.items() if w >= w_min}
        if not refs:
            return {}
        n = len(self.sp.cu)
        gs, lam = KN.fin_params([MAT.CU_1OZ_MM] * n, [self.o["tht_heat_fill"]] * n, self.sp.thickness)
        dk = float(self.o["tht_heat_dK"])
        radius = {}
        for r in refs:
            P = watts.get(r)
            if not P:
                continue          # no dissipation known (theta or a heat sink only): its own pads only ("hot")
            # P K0(x) / (2 pi gs) = dK, K0 decreasing: bisect x = r / lambda
            lo, hi = 1e-4, 20.0
            if P * k0(lo) / (2 * math.pi * gs) < dk:
                continue
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if P * k0(mid) / (2 * math.pi * gs) > dk else (lo, mid)
            radius[r] = lo * lam
        pads_of = {}
        for fps in self.sp.pads_by_fp.values():
            for p in fps:
                if p.kind == "pad" and isinstance(p.owner, tuple) and p.owner[0] in radius:
                    pads_of.setdefault(p.owner[0], []).append(p.geom)
        src = {r: unary_union(g) for r, g in pads_of.items()}
        out = {}
        for fps in self.sp.pads_by_fp.values():
            for p in fps:
                if p.kind != "pad" or p.smd or p.hole is None:
                    continue
                for r, g in src.items():
                    if (not isinstance(p.owner, tuple) or p.owner[0] != r) and g.distance(p.geom) <= radius[r]:
                        out[id(p)] = (r, round(watts.get(r, 0.0), 3), round(radius[r], 1))
                        break
        return out

    def _tht_len(self):
        """mm of narrow copper a THT neck is: neck_len plus the taper round-capped wider copper needs to keep its
        edge neck_len off the pad (half the widest grown copper)."""
        return self.o["neck_len"] + self.o["max_width"] / 2

    def _tht_need(self, amps):
        """The width a THT neck needs for `amps` (short_neck_width over _tht_len at tht_neck_dK)."""
        return short_neck_width(amps, self._tht_len(), self.o["current_margin"], self.o["tht_neck_dK"])

    def _routed_w(self, p):
        """Widest routed track of p's net that ends in or runs through pad Item p (0 without one)."""
        w = 0.0
        for t in self.board.tracks:
            if t.net == p.net and t.layer in p.layers and t.mid is None \
                    and LineString([t.start, t.end]).distance(p.geom) < 1e-3:
                w = max(w, t.width)
        return w

    def _loss_floor(self, keep, flows):
        """{id(pad): width} the neck may not go below so that the necks of a net together add at most
        tht_loss_frac of the net's copper loss under the DC plan once grown (routed currents at max_width). A neck of width w where grown copper
        would be w_f wide adds I^2 R_sq L (1/w - 1/w_f) per track entering the pad, L = neck_len + w_f / 2 (the
        neck and the taper the round-capped wider copper needs to keep its edge neck_len off the pad). Within a
        net the budget first caps pads at their land's width (no overhang), then necks capped pads fully, cheapest
        first; a pad it cannot cap gets an infinite floor (kept wide)."""
        frac = float(self.o["tht_loss_frac"])
        wf = self.o["max_width"]
        L = self.o["neck_len"] + wf / 2
        stats = getattr(self, "tht_flow_stats", {}) or {}
        # each pad's cost: I^2 n L (1/w - 1/w_f) for a neck at w (the routed track or the short neck's width), and
        # for a cap at the land's own width (no copper past the land: no overhang, about 1.7x a relief's webs).
        # Within a net the budget first buys caps, cheapest first (they remove the overhang at little loss), then
        # upgrades capped pads to full necks, cheapest first; what the budget cannot buy keeps its copper
        cost = {}
        for _f, p, ref, num in keep:
            tok = f"{ref}.{num}"
            i = flows.get(tok, 0.0)
            if i <= 0:
                continue
            n = max(1, ((stats.get(p.net) or {}).get("entries") or {}).get(tok, 1))
            k = i * i * n * L
            w_neck = max(self._routed_w(p), self._tht_need(i), 1e-3)
            w_cap = max(_short_side(p.geom), w_neck)
            cost.setdefault(p.net, []).append((k * max(0.0, 1.0 / w_cap - 1.0 / wf),
                                               k * max(0.0, 1.0 / w_neck - 1.0 / wf), w_cap, id(p)))
        out = {}
        for net, cs in cost.items():
            # the budget is a share of the loss the net will have once grown (its routed currents in copper at
            # max_width: a floor of the grown loss, so the budget errs small); the routed copper's own loss is
            # several times larger and would let necks cost several % of the finished board's loss
            st = stats.get(net) or {}
            budget = frac * st.get("loss_grown_sq", st.get("loss_sq", 0.0))
            spent = 0.0
            capped = []
            for c_cap, c_neck, w_cap, k in sorted(cs):
                if spent + c_cap <= budget:
                    spent += c_cap
                    capped.append((c_neck - c_cap, k, w_cap))
                    out[k] = w_cap
                else:
                    out[k] = math.inf
            for dc_, k, _w in sorted(capped):
                if spent + dc_ <= budget:
                    spent += dc_
                    out.pop(k)
        return out

    def _zone_joined(self, p):
        """Whether pad Item p touches a fill of its own net on one of its layers."""
        byl = self.fills.get(p.net) or {}
        return any(g.intersects(p.geom) for l in p.layers for g in byl.get(l) or [])

    def tht_hazards(self):
        """tht_pad_necked (info): per part, the THT pads whose neck kept planned copper narrower than
        it would have been, with the setting that keeps them wide; at most MAX_PER_CODE entries (the
        parts with the most width taken first, the rest in one entry). tht_pad_heatsunk (warn): a THT
        pad whose current needs more than a relief's webs, entered by grown copper wider than them."""
        from kae import hazards as H
        out = []
        by_ref = {}
        for rec in self.tht_necked.values():
            p = rec["pad"]
            ref, num = p.owner if isinstance(p.owner, tuple) else (None, None)
            amps = self.tht_amps.get(id(p), 0.0)
            by_ref.setdefault(ref or "?", []).append(dict(
                pad=f"{ref}.{num}", net=p.net, would_w_mm=round(rec["would"], 3), got_w_mm=round(rec["got"], 3),
                current_a=round(amps, 4), need_w_mm=round(self._tht_need(amps), 3),
                land_w_mm=round(_short_side(p.geom), 3)))
        order = sorted(by_ref.items(), key=lambda kv: -sum(x["would_w_mm"] - x["got_w_mm"] for x in kv[1]))
        nl = self.o["neck_len"]
        limit = H.MAX_PER_CODE
        head = order if len(order) <= limit else order[:limit - 1]
        for ref, pads in head:
            pads.sort(key=lambda x: x["pad"])
            nets = sorted({x["net"] for x in pads})
            w0, w1 = max(x["would_w_mm"] for x in pads), max(x["got_w_mm"] for x in pads)
            one = pads[0]["pad"] if len(pads) == 1 else None
            out.append(H.make(
                "tht_pad_necked", "info", "assembly",
                f"{ref}: power copper kept {len(pads)} through-hole pad(s) on {', '.join(nets)} at {w1:.2f} mm within "
                f"{nl} mm instead of {w0:.2f} mm, so wave, selective or iron soldering is not starved of heat.",
                objects=[ref] + [x["pad"] for x in pads], fix=_tht_fix(ref, one),
                evidence=dict(pads=pads[:12], n_pads=len(pads), neck_len_mm=nl,
                              source="thermal relief: IPC-2222 9.1.2 (webs 60% of the land); power_copper.neck_rule tht")))
        rest = order[len(head):]
        if rest:
            refs = [r for r, _ in rest]
            out.append(H.make(
                "tht_pad_necked", "info", "assembly",
                f"Power copper also necked the through-hole pads of {len(refs)} more parts "
                f"({sum(len(p) for _, p in rest)} pads), same rule.",
                objects=refs, fix=_tht_fix(None, None),
                evidence=dict(parts=len(refs), pads=sum(len(p) for _, p in rest))))
        # no DC plan: connector pins on rails keep their copper; the LLM may neck them
        unk = {}
        for p in self.tht_unknown:
            ref, num = p.owner if isinstance(p.owner, tuple) else ("?", "?")
            unk.setdefault(ref, []).append((f"{ref}.{num}", p.net))
        refs = sorted(unk)
        for i, ref in enumerate(refs):
            if i == H.MAX_PER_CODE - 1 and len(refs) > H.MAX_PER_CODE:
                rest = refs[i:]
                out.append(H.make("tht_pad_kept_wide", "info", "assembly",
                                  f"{len(rest)} more connectors' power pins keep wide copper for want of a DC plan.",
                                  objects=rest, fix=_tht_narrow_fix(None)))
                break
            pads = unk[ref]
            why = [self.tht_unknown_why.get(id(p)) for p in self.tht_unknown
                   if isinstance(p.owner, tuple) and p.owner[0] == ref]
            loss = any(w is not None for w in why)
            hp = [self.tht_unknown_heat.get(id(p)) for p in self.tht_unknown
                  if isinstance(p.owner, tuple) and p.owner[0] == ref and id(p) in self.tht_unknown_heat]
            out.append(H.make(
                "tht_pad_kept_wide", "info", "assembly",
                f"{ref}: {len(pads)} through-hole power pin(s) on {', '.join(sorted({n for _, n in pads}))} keep wide "
                + (f"copper: they are on {hp[0][0]}'s heat path ({hp[0][1]} W, within {hp[0][2]} mm)." if hp else
                   "copper: a neck narrow enough to relieve the joint would add more copper loss than the budget."
                   if loss else "copper: no DC plan says what current they carry, and a neck could starve a feed."),
                objects=[ref] + [x for x, _ in pads], fix=_tht_narrow_fix(ref),
                evidence=dict(pads=[dict(pad=x, net=n) for x, n in pads][:12], n_pads=len(pads),
                              current_a=[round(w[0], 3) for w in why if w][:12] or None,
                              loss_width_mm=[round(w[1], 3) for w in why if w][:12] or None,
                              heat_path=[dict(part=h[0], W=h[1], radius_mm=h[2]) for h in hp][:4] or None,
                              reason=("on a hot part's heat path (tht_heat_dK)" if hp else
                                      "neck over tht_loss_frac of the net's copper loss (DC plan)" if loss else
                                      "no rail with a source and a load in the operating facts (kae.excite.dc plan)"))))
        # current needs more than a relief: the copper stays wide, and the joint pays for it
        net_of = {t.uuid: t.net for t in self.board.tracks}
        for fp, p, amps in getattr(self, "unnecked", []):
            if p.smd:
                continue
            land_w = _short_side(p.geom)
            relief = THT_RELIEF_FRAC * land_w
            widest = 0.0
            for u, pieces in self.edits.items():
                if net_of.get(u) != p.net:
                    continue
                for pc_ in pieces:
                    a, b, w = pc_[:3]
                    if w > relief + 1e-9 and LineString([a, b]).buffer(w / 2).distance(p.geom) < self.o["neck_len"]:
                        widest = max(widest, w)
            # vector copper written as zones (rails above zone_above_a) joins the pad solid unless hand soldered
            zoned = [z for z in self.zones if z[0] == p.net and z[1] in p.layers and z[2].distance(p.geom) < 1e-6]
            if zoned and not self.hand_solder:
                widest = max(widest, max(_short_side(z[2]) for z in zoned))
            if widest:
                ref, num = p.owner if isinstance(p.owner, tuple) else (None, None)
                need = self._tht_need(amps)
                out.append(H.make(
                    "tht_pad_heatsunk", "warn", "assembly",
                    f"{ref}.{num} ({p.net}): its {amps:.2f} A needs {need:.2f} mm even as a short neck, more than a "
                    f"thermal relief's {relief:.2f} mm; the {widest:.2f} mm copper stays and drains soldering heat.",
                    objects=[f"{ref}.{num}", ref, p.net],
                    evidence=dict(track_w_mm=round(widest, 3), need_w_mm=round(need, 3), relief_w_mm=round(relief, 3),
                                  land_w_mm=round(land_w, 3), current_a=round(amps, 4),
                                  neck_len_mm=round(self._tht_len(), 3), neck_dK=self.o["tht_neck_dK"],
                                  source="short-neck conduction (power_copper.short_neck_width) at current_margin x the "
                                         "pad's current; relief webs IPC-2222 9.1.2"),
                    fix="Preheat or a selective/iron profile for this joint, a larger pad or more pins in parallel; or "
                        "accept it if the joint is checked after soldering."))
        return out

    def land_hazards(self):
        """land_enlarged_by_track for each unnecked two-terminal land a widened track enters wider than it."""
        from . import pad_entry as PE
        out = []
        for fp, p, amps in getattr(self, "unnecked", []):
            if not p.smd:
                continue          # a THT pad: tht_hazards (tht_pad_heatsunk)
            land_w = _short_side(p.geom)
            widest = 0.0
            for pieces in self.edits.values():
                for pc_ in pieces:
                    a, b, w = pc_[:3]
                    if w > land_w + 1e-9 and LineString([a, b]).buffer(w / 2).intersects(p.geom):
                        widest = max(widest, w)
            if widest:
                ref, num = p.owner if isinstance(p.owner, tuple) else (None, None)
                out.append(PE.land_hazard(ref, num, p.net, widest, land_w,
                                          current_need(amps, self.o["current_margin"]), amps))
        return out

    def vector_or_widen(self):
        if self.o.get("mode") == "vector":
            return self.grow_vector()
        n = self.widen()
        if self.zone_nets:
            # rails above zone_above_a: pours, not tracks (their tracks stay as routed, the zone joins them)
            n += self.grow_vector(nets=self.zone_nets, out="zones")
            self.stats["zone_nets"] = sorted(self.zone_nets)
        return n

    def board_zone_priorities(self):
        """[(layer, priority)] of the input's zones."""
        out = []
        for z in self.sp.info.get("zones") or []:
            for l in z.get("layers") or []:
                out.append((l, int(z.get("priority") or 0)))
        return out

    def group_kind(self, g):
        if g in self.edits:
            return "widen"
        return next((v[6] for v in self.vias if v[5] == g), None)

    def _net_name(self, tok):
        if tok.startswith('"'):
            return json.loads(tok)
        if tok.isdigit():
            # KiCad <= 9 (net N "name"): resolve the number
            nm = {str(i): n for i, n in enumerate(self.board.nets)} if isinstance(self.board.nets, list) else {}
            return nm.get(tok, tok)
        return tok


def _operating(board_path, path=None):
    """Operating facts: `path`, else the KAE_OPERATING text variable of the board's .kicad_pro."""
    if not path:
        pro = Path(board_path).with_suffix(".kicad_pro")
        try:
            path = (json.loads(pro.read_text()).get("text_variables") or {}).get("KAE_OPERATING")
        except (OSError, ValueError):
            path = None
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _via_on_tracks(tracks, land, rv, neck_len, reach, step=0.05):
    """Via centres on the centrelines of `tracks` (Space items) whose via edge is at least neck_len
    and its centre at most reach + rv from the land, nearest first: (distance, x, y)."""
    out = []
    for it in tracks:
        g = it.geom
        n = max(2, int(g.length / step) + 1)
        for k in range(n):
            q = g.interpolate(k * g.length / (n - 1))
            d = q.distance(land)
            if neck_len + rv - 1e-9 <= d <= reach + rv + 1e-9:
                out.append((d, q.x, q.y))
    return sorted(out)


def _any_segment(poly):
    c = list(poly.exterior.coords)
    return c[0], c[1]


def zone_sexpr(net, layer, poly, uid, priority=0, solid=True, min_thickness=0.2):
    """A copper zone of `net` on `layer` over shapely `poly` (holes as further polygon blocks, which
    KiCad reads as holes of the first), named kae-pc:<net>; solid pad connection, or thermal reliefs."""
    def pts(ring):
        c = list(ring.coords)[:-1]
        return " ".join(f"(xy {W.fmt(x)} {W.fmt(y)})" for x, y in c)
    conn = "(connect_pads yes\n\t\t\t(clearance 0)\n\t\t)" if solid else "(connect_pads\n\t\t\t(clearance 0)\n\t\t)"
    polys = "".join(f"\t\t(polygon\n\t\t\t(pts {pts(r)})\n\t\t)\n" for r in [poly.exterior, *poly.interiors])
    return (f"\t(zone\n\t\t(net {W.q(net)})\n\t\t(layer {W.q(layer)})\n\t\t(uuid {W.q(uid)})\n"
            f"\t\t(name {W.q('kae-pc:' + net)})\n\t\t(hatch edge 0.5)\n\t\t(priority {int(priority)})\n"
            f"\t\t{conn}\n\t\t(min_thickness {W.fmt(min_thickness)})\n\t\t(filled_areas_thickness no)\n"
            f"\t\t(fill\n\t\t\t(thermal_gap 0.3)\n\t\t\t(thermal_bridge_width 0.3)\n\t\t)\n{polys}\t)\n")


def _short_side(g):
    r = g.minimum_rotated_rectangle
    xs, ys = r.exterior.coords.xy
    e = [math.dist((xs[i], ys[i]), (xs[i + 1], ys[i + 1])) for i in range(len(xs) - 1)]
    return min(e) if e else 0.2


# ----------------------------------------------------------------------------- DRC gate
def _drc(board, out_json, timeout):
    from . import drc
    rep = drc.run(board, out_json, timeout=timeout)
    return rep, drc.summary(rep)


def _worse(s, base):
    """Error types (and 'unconnected') where summary `s` exceeds `base`."""
    out = {t: n - base["by_type"].get(t, 0) for t, n in s["by_type"].items() if n > base["by_type"].get(t, 0)}
    if s["unconnected"] > base["unconnected"]:
        out["unconnected"] = s["unconnected"] - base["unconnected"]
    return out


def _new_violations(rep, base_rep):
    from . import drc

    def key(v):
        return (v.get("type"), tuple(sorted((i.get("description") or "") for i in v.get("items") or [])))
    old = {key(v) for v in drc.errors(base_rep)} | {key(v) for v in base_rep.get("unconnected_items") or []}
    return [v for v in drc.errors(rep) + list(rep.get("unconnected_items") or []) if key(v) not in old]


def _culprits(rep, base_rep, groups, geoms, near=1.0):
    """Groups behind violations of `rep` not in `base_rep`: named by uuid (`groups`: written uuid
    -> group), else within `near` mm of a reported position (zones' anchors aside)."""
    bad = set()
    for v in _new_violations(rep, base_rep):
        named = {groups[i.get("uuid")] for i in v.get("items") or [] if i.get("uuid") in groups}
        if named:
            bad |= named
            continue
        pts = [i.get("pos") for i in v.get("items") or [] if i.get("pos") and not (i.get("description") or "").startswith("Zone")]
        for p in pts:
            q = Point(p["x"], p["y"])
            bad |= {g for g, geo in geoms.items() if g in set(groups.values()) and geo.distance(q) <= near}
    return bad


def journal_keys(pc, kinds):
    """{uuid: group} of every item the plan writes or replaces, by kae.route.journal's grouping:
    a widened track's pieces under the track, a via with its pad-to-via track, a strip or zone alone."""
    keys = {}
    for u, pieces in pc.edits.items():
        keys[u] = u
        for pc_ in pieces:
            keys[pc_[3]] = u
    for net, layer, kept, gid in pc.vector:
        for a, b, w, u in kept:
            keys[u] = u
    for z in pc.zones:
        keys[z[3]] = z[3]
    for v in pc.vias:
        keys[v[5]] = v[5]
    for net, layer, w, a, b, u, owner in pc.tracks:
        keys[u] = owner
    return keys


def run(input_path, output_path, opts=None, workdir=None, timeout=1800, log=print, gate=True):
    """The DRC-gated pass: plan, write, check, revert what made DRC worse. Returns a report.
    `gate=False` (kae.route.finish): no DRC; the whole plan is written and returned as
    kae.route.journal entries in rep["_entries"] (one per group: a widened track, a via with its
    track, a strip, a zone)."""
    t0 = clock_now()
    o = {**DEFAULTS, **(opts or {})}
    inp = Path(input_path).resolve()
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-pc-"))
    wd.mkdir(parents=True, exist_ok=True)
    staged = W.stage(inp, wd / "in", "board")
    pc = PowerCopper(staged, o, log=log)
    vec = o.get("mode") == "vector"
    for k, f in (("widen", pc.vector_or_widen), ("vias", pc.ground_vias), ("stitch", pc.stitch)):
        if o[k]:
            t1 = clock_now()
            f()
            log(f"[power-copper] {k}: {clock_now() - t1:.1f}s")
    t_plan = clock_now() - t0
    log(f"[power-copper] planned {pc.stats} in {t_plan:.1f}s")
    kinds = ["vector" if vec else "widen", "pad", "stitch"] + (["vector"] if pc.zone_nets and not vec else [])
    if not gate:
        from . import journal as J
        out = Path(output_path)
        groups = pc.write(out, kinds=tuple(kinds))
        J.write(out.read_text(encoding="utf-8"), out, inp)
        kind_of = {}
        for u in set(groups.values()):
            kind_of[u] = dict(kind=pc.group_kind(u) or ("zone" if any(z[3] == u for z in pc.zones) else "vector"))
        return dict(board=str(inp), planned=pc.stats, kept=dict(pc.stats), kinds=kinds, reverted=0, gate=False,
                    hazards=pc.land_hazards() + pc.tht_hazards(), tht=pc.tht_stats(),
                    nets=dict(power=sorted(pc.power), ground=sorted(pc.ground), switch=sorted(pc.switch),
                              victims=sorted(pc.victims), zones=sorted(pc.zone_nets)),
                    plan_s=round(t_plan, 2), total_s=round(clock_now() - t0, 2),
                    _entries=J.diff_entries("power", staged.read_text(encoding="utf-8"),
                                            out.read_text(encoding="utf-8"), journal_keys(pc, kinds), kind_of))
    base_rep, base = _drc(staged, wd / "in.drc.json", timeout)
    skip = set()
    rounds = []
    cand = wd / "out" / "board.kicad_pcb"
    cand.parent.mkdir(parents=True, exist_ok=True)
    geoms = pc.group_geoms()
    final = None
    budget = [int(o["drc_budget"])]
    best = {}                  # the no-worse board with the fewest changes left out, from any check

    def check(skip_set, tag):
        groups = pc.write(cand, skip=skip_set, kinds=tuple(kinds))
        if not groups:
            return None, None, groups
        budget[0] -= 1
        rep, s = _drc(cand, wd / f"out.{tag}.json", timeout)
        worse = _worse(s, base)
        rounds.append(dict(tag=tag, skipped=len(skip_set), summary=s, worse=worse))
        if not worse and (not best or len(skip_set) < best["skipped"]):
            shutil.copy2(cand, wd / "best.kicad_pcb")
            best.update(skipped=len(skip_set), skip=set(skip_set), summary=s)
        log(f"[power-copper] {tag}: {s['errors']} errors, {s['unconnected']} unconnected "
            f"(input {base['errors']}, {base['unconnected']}); skipped {len(skip_set)}; worse {worse or 'none'}")
        return rep, worse, groups

    r = 0
    near = 1.0
    while budget[0] > 0:
        rep, worse, groups = check(skip, f"r{r}")
        r += 1
        if rep is None:
            break
        if not worse:
            final = rounds[-1]["summary"]
            break
        bad = _culprits(rep, base_rep, groups, geoms) - skip
        if bad:
            skip |= bad
            near = 1.0
            continue
        # nothing within 1 mm: widen the search once (a mask bridge or starved spoke is reported
        # against neighbouring items, not the copper that caused it)
        if near < 2.5:
            near = 2.5
            bad = _culprits(rep, base_rep, groups, geoms, near=near) - skip
            if bad:
                skip |= bad
                continue
        # not attributable (several changes together, e.g. two tracks that between them starve a
        # pad's spokes): build up from the input, batch by batch, keeping each batch that leaves
        # DRC no worse and splitting the ones that do not (ddmin-style; finds a maximal set)
        allg = sorted(set(groups.values()) - skip)
        accepted = set()
        queue = [allg[i:i + max(1, len(allg) // 4)] for i in range(0, len(allg), max(1, len(allg) // 4))]
        k = 0
        while queue and budget[0] > 0:
            batch = queue.pop(0)
            _, w2, _ = check(skip | (set(allg) - accepted - set(batch)), f"r{r}a{k}")
            k += 1
            if w2 is None or not w2:
                accepted |= set(batch)
            elif len(batch) > 1:
                queue[:0] = [batch[:len(batch) // 2], batch[len(batch) // 2:]]
        skip |= set(allg) - accepted
        break           # the best checked board below is the accepted set (or better)
    if final is None and best:
        # out of DRC budget: the best no-worse board any check saw (a bisection probe is a whole board)
        shutil.copy2(wd / "best.kicad_pcb", cand)
        skip, final = best["skip"], best["summary"]
        log(f"[power-copper] budget spent: keeping the best checked board ({len(skip)} changes left out)")
    if final is None:
        kinds = []
    out = Path(output_path)
    if final is not None:
        shutil.copy2(cand, out)
    else:
        shutil.copy2(staged, out)
    for ext in (".kicad_pro", ".kicad_dru"):
        s_ = inp.with_suffix(ext)
        if s_.exists() and s_.resolve() != out.with_suffix(ext).resolve():
            shutil.copy2(s_, out.with_suffix(ext))
    kept = dict(widened=sum(1 for u in pc.edits if u not in skip) if "widen" in kinds else 0,
                ground_vias=sum(1 for v in pc.vias if v[6] == "pad" and v[5] not in skip) if "pad" in kinds else 0,
                stitch_vias=sum(1 for v in pc.vias if v[6] == "stitch" and v[5] not in skip) if "stitch" in kinds else 0,
                vector_strips=sum(1 for x in pc.vector for k in x[2] if k[3] not in skip) if "vector" in kinds else 0,
                vector_zones=sum(1 for z in pc.zones if z[3] not in skip) if "vector" in kinds else 0)
    return dict(board=str(inp), planned=pc.stats, kept=kept, kinds=kinds, reverted=len(skip), hazards=pc.land_hazards() + pc.tht_hazards(), tht=pc.tht_stats(),
                drc_in=base, drc_out=final or base, rounds=rounds,
                nets=dict(power=sorted(pc.power), ground=sorted(pc.ground), switch=sorted(pc.switch),
                          victims=sorted(pc.victims)),
                plan_s=round(t_plan, 2), total_s=round(clock_now() - t0, 2))


def hook(output_path, project_board, workdir, opts=None, timeout=900, log=print):
    """The router's final-stage hook (bridge opts power_copper=True): runs the pass on the routed
    `output_path` (staged with `project_board`'s .kicad_pro/.kicad_dru) and replaces it only when
    something was kept. Returns the pass's report, without the per-round detail."""
    from . import drc
    wd = Path(workdir)
    staged = drc.stage_board(output_path, project_board, wd / "routed")
    try:
        rep = run(staged, wd / "out.kicad_pcb", opts=opts, workdir=wd / "pass", timeout=timeout, log=log)
    except Exception as e:      # noqa: BLE001 - a post-pass never costs the routed board
        from kae import hazards as H
        log(f"[power-copper] skipped: {type(e).__name__}: {e}")
        return dict(error=f"{type(e).__name__}: {e}", hazards=[H.make(
            "power_copper_failed", "warn", "data", f"Power copper failed and was skipped: {type(e).__name__}: {e}"[:300],
            objects=["power_copper"], fix="Report the board; rails and grounds keep their routed widths.")])
    if any(rep["kept"].values()):
        text = (wd / "out.kicad_pcb").read_text(encoding="utf-8")
        Path(output_path).write_text(text, encoding="utf-8")
    rep.pop("rounds", None)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m kae.route.power_copper", description=__doc__.split("\n\n")[0])
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--no-widen", action="store_true")
    ap.add_argument("--no-vias", action="store_true")
    ap.add_argument("--no-stitch", action="store_true")
    ap.add_argument("--max-width", type=float, default=DEFAULTS["max_width"])
    ap.add_argument("--current-cap", type=float, default=DEFAULTS["current_cap"])
    ap.add_argument("--mode", choices=("widen", "vector"), default=DEFAULTS["mode"])
    ap.add_argument("--into-pours", action="store_true")
    ap.add_argument("--vector-out", choices=("strips", "zones"), default=DEFAULTS["vector_out"],
                    help="vector copper as track strips (route tasks today) or KiCad zones")
    ap.add_argument("--no-share", action="store_true", help="first come, first served between power/ground nets")
    ap.add_argument("--no-neck", action="store_true", help="no necks at small two-terminal lands")
    ap.add_argument("--neck-via", choices=("own", "track"), default=DEFAULTS["neck_via"])
    ap.add_argument("--operating", help="operating facts JSON (default: KAE_OPERATING of the .kicad_pro)")
    ap.add_argument("--workdir")
    ap.add_argument("--report")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    rep = run(a.input, a.output, dict(widen=not a.no_widen, vias=not a.no_vias, stitch=not a.no_stitch,
                                      max_width=a.max_width, current_cap=a.current_cap, mode=a.mode,
                                      into_pours=a.into_pours, neck=not a.no_neck, neck_via=a.neck_via, share=not a.no_share, vector_out=a.vector_out, operating=a.operating), workdir=a.workdir, timeout=a.timeout)
    txt = json.dumps(rep, indent=1)
    if a.report:
        Path(a.report).write_text(txt)
    print(json.dumps(dict(planned=rep["planned"], kept=rep["kept"], drc_in=rep["drc_in"], drc_out=rep["drc_out"],
                          total_s=rep["total_s"])))


if __name__ == "__main__":
    main()
