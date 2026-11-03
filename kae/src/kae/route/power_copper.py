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
    vector_strip=0.5,         # mm: strip width of the vector fill (pitch 0.8 x that)
    vector_min_gain=0.5,      # mm^2: a vector piece adding less copper than this is dropped
    into_pours=False,         # vector: may grow into other nets' zone fills (False: those fills are obstacles,
                              # so a rail never cuts a ground pour)
    neck=True,                # necks at the pads of small two-terminal parts (tombstoning; see neck_rule):
                              # within neck_len of such a pad, grown copper is at most the neck width
    neck_len=0.5,             # mm from the pad edge
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
    drc_budget=40,            # KiCad DRC runs the gate may spend (attribution and bisection)
)

VICTIM_ROLES = ("clock", "high_speed", "analog", "rf")
TOL = 0.002
VTOL = 0.03          # mm: vector mode's margin over each requirement (polygonal shapes, simplification)


# ----------------------------------------------------------------------------- pure rules
def ipc_width(current_a, dt_k=10.0, t_mm=0.035, external=True):
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


def neck_rule(land_w, process, series_current_a=0.0, margin=DEFAULTS["current_margin"]):
    """Width (mm) grown copper may have within neck_len of a two-terminal part's land, or None (no
    limit). The neck is the land class's NECK_TABLE width for the process, never below what the
    part's own series current needs (IPC-2221 at margin x I): a fuse, ferrite or shunt in a rail
    keeps its width. A part to ground (a decap) carries no DC and is necked."""
    w = NECK_TABLE.get(process, NECK_TABLE["reflow"]).get(pkg_class(land_w))
    if w is None:
        return None
    w = min(w, land_w)
    need = ipc_width(margin * series_current_a) if series_current_a else 0.0
    return None if need >= land_w else max(w, need)


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


# ----------------------------------------------------------------------------- the pass
class PowerCopper:
    """Plans the copper for one board: `widen()`, `ground_vias()`, `stitch()`, then `write(dst)`."""

    def __init__(self, board_path, opts=None, info=None, brief=None, fills=None, log=print):
        from kae.board import pcbnew_io
        from kae.board.kicad_file import load
        from .critical_space import Space
        from .bridge import severities
        t0 = time.monotonic()
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
        self.necks = self._necks() if self.o.get("neck", True) else {}
        self.vector = []       # (net, layer, [(a, b, w, uuid)]) strips of the vector mode, one group each
        self.zones = []        # (net, layer, polygon, uuid) pieces of the vector mode written as zones
        self.edits = {}        # orig track uuid -> [(a, b, w)]
        self.vias = []         # (net, x, y, size, drill, uuid, kind)
        self.tracks = []       # (net, layer, w, a, b, uuid, owner)
        self.stats = dict(widened=0, widened_mm=0.0, ground_vias=0, stitch_vias=0)
        self.t_setup = time.monotonic() - t0
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
                if l == layer and it.kind == "pad" and it.net == net and id(it) in self.necks:
                    # necked land: f < 0 carries the neck width (see _allowed_half, _legal)
                    out.append((it.geom, 0.0, self.o["neck_len"], -self.necks[id(it)]))
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

    def _legal(self, net, layer, w, a, b, ignore):
        if self.sp.track_violations(net, layer, w, a, b, ignore=ignore, first=True):
            return False
        seg = LineString([a, b])
        for g, r, req, f in self._constraints(net, layer, seg, w / 2 + self.o["victim_gap_max"] + self.o["antenna_gap"], ignore):
            if f < 0:
                if w > -f + 1e-9 and g.distance(seg) - w / 2 < req - TOL:
                    return False
                continue
            if g.distance(seg) - r - w / 2 < req + TOL:
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
            if t.mid is not None or t.net not in nets or t.layer not in sp.items:
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
            cons = self._constraints(t.net, t.layer, seg, steps[0] / 2 + self.o["victim_gap_max"] + self.o["antenna_gap"]
                                     + sp.max_need, {it})
            half = self._allowed_half(pts, cons, t.net, t.layer, t.width / 2)
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
        return self.stats["widened"]

    # ---------------------------------------------------------------- 1b. vector growth
    def grow_vector(self):
        """Vector mode: per power/ground net and layer, the free region around the net's copper
        (the layer minus every foreign item grown by its required gap, the board edge, and other
        nets' fills unless into_pours), clipped to a corridor max_width/2 around the net's tracks
        and pads. Nets competing for the same room share it by current: all grow together, each
        at a speed proportional to its current (a multiplicatively weighted Voronoi split, by
        repeated buffering), keeping the board clearance between them; the boundary sits where
        d_i/I_i = d_j/I_j, so widths come out proportional to current (least sum I^2 R). Each
        connected piece that touches the net's copper and adds at least vector_min_gain mm2 is
        filled with overlapping track strips."""
        sp = self.sp
        reach = self.o["victim_gap_max"] + self.o["antenna_gap"] + sp.max_need + 0.1
        n_strips = 0
        area = 0.0
        self.vector_share = {}
        for layer in sp.cu:
            cand = {}
            for net in sorted(self.power | self.ground):
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
                    if self.o["vector_out"] == "zones":
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
        key = (net, layer, r)
        c = getattr(self, "_gf", {})
        self._gf = c
        if key not in c:
            g = unary_union((self.fills.get(net) or {}).get(layer) or [])
            if not g.is_empty:
                g = g.buffer(-r)
                shapely.prepare(g)
            c[key] = g
        return c[key]

    def _barrels_near(self, net, geom, reach):
        sp = self.sp
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

    def _target_pads(self):
        """SMD ground pads of capacitors and of decoupled ICs' ground pins."""
        parts = self.brief.get("parts") or {}
        want = set()
        for s in self.brief.get("structures") or []:
            if s.get("kind") == "decap" and s.get("ic"):
                for p in s.get("ground_pins") or []:
                    want.add((s["ic"], str(p)))
        out = []
        for it in self.sp.pads:
            if it.kind != "pad" or not it.smd or it.net not in self.ground or not it.fp:
                continue
            kind = (parts.get(it.fp) or {}).get("kind")
            num = str(it.owner[1]) if it.owner else ""
            if kind == "capacitor" or (it.fp, num) in want:
                out.append(it)
        return out

    def ground_vias(self):
        sp = self.sp
        n = 0
        for pad in self._target_pads():
            net = pad.net
            if self._barrels_near(net, pad.geom, self.o["via_reach"]):
                continue
            D, d = sp.via_size(net)
            rv = D / 2
            layer = next(iter(sorted(pad.layers, key=sp.cu.index)), None)
            others = [l for l in sp.cu if l != layer]
            fills = [self._ground_fill(net, l, rv) for l in others]
            fills = [f for f in fills if not f.is_empty]
            if not fills:
                continue
            own = self._ground_fill(net, layer, rv)
            pos = pad.pos or (pad.geom.centroid.x, pad.geom.centroid.y)
            wt = sp.clamp_width(net, layer, min(self.o["via_track_max"], _short_side(pad.geom),
                                                self.necks.get(id(pad), math.inf)))
            entries = []
            if id(pad) in self.necks:
                # a necked land keeps one entry (balance with its sister land): the via sits on the
                # land's own routed track, at least neck_len from the land, and no second track enters
                entries = [it for it in sp.items[layer] if it.kind == "track" and it.net == net
                           and it.geom.distance(pad.geom) <= it.r + 1e-6]
                if not entries:
                    continue
                cands = _via_on_tracks(entries, pad.geom, rv, self.o["neck_len"], self.o["via_reach"])
            else:
                cands = ring_candidates(pad.geom, rv, self.o["via_reach"])
            for dist, x, y in cands:
                p = Point(x, y)
                if not any(f.contains(p) for f in fills):
                    continue
                if sp.via_violations(net, x, y, first=True):
                    continue
                track_ok = not entries and not sp.track_violations(net, layer, wt, pos, (x, y), first=True)
                if not entries and not track_ok and not (not own.is_empty and own.contains(p)):
                    continue
                v = sp.add_via(net, x, y, owner=("pc-via", pad.uuid))
                self.vias.append((net, x, y, D, d, W.new_uuid(), "pad"))
                if track_ok:
                    sp.add_track(net, layer, wt, pos, (x, y), owner=("pc-via", pad.uuid))
                    self.tracks.append((net, layer, wt, pos, (x, y), W.new_uuid(), self.vias[-1][5]))
                n += 1
                break
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
        for head, a, b in W._blocks(text, ("segment",)):
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
            for pa, pb, w, nu in widen[u]:
                groups[nu] = u
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
            out[u] = unary_union([LineString([a, b]).buffer(w / 2) for a, b, w, _ in pieces])
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
        """{id(pad Item): neck width} for the lands of two-terminal SMD parts the process necks."""
        parts = self.brief.get("parts") or {}
        out = {}
        for fp, pads in self.sp.pads_by_fp.items():
            cu = [p for p in pads if p.kind == "pad"]
            if len(cu) != 2 or not all(p.smd for p in cu):
                continue
            nets = {p.net for p in cu}
            series = 0.0
            if not nets & self.ground and nets & self.power:
                # in series with a rail (fuse, ferrite, shunt, jumper): its current flows through it
                series = max(self.current.get(n, 0.0) for n in nets)
            for p in cu:
                w = neck_rule(_short_side(p.geom), self.process, series, self.o["current_margin"])
                if w is not None:
                    out[id(p)] = w
        return out

    def vector_or_widen(self):
        return self.grow_vector() if self.o.get("mode") == "vector" else self.widen()

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


def run(input_path, output_path, opts=None, workdir=None, timeout=1800, log=print):
    """The DRC-gated pass: plan, write, check, revert what made DRC worse. Returns a report."""
    t0 = time.monotonic()
    o = {**DEFAULTS, **(opts or {})}
    inp = Path(input_path).resolve()
    wd = Path(workdir or tempfile.mkdtemp(prefix="kae-pc-"))
    wd.mkdir(parents=True, exist_ok=True)
    staged = W.stage(inp, wd / "in", "board")
    pc = PowerCopper(staged, o, log=log)
    vec = o.get("mode") == "vector"
    for k, f in (("widen", pc.vector_or_widen), ("vias", pc.ground_vias), ("stitch", pc.stitch)):
        if o[k]:
            t1 = time.monotonic()
            f()
            log(f"[power-copper] {k}: {time.monotonic() - t1:.1f}s")
    t_plan = time.monotonic() - t0
    log(f"[power-copper] planned {pc.stats} in {t_plan:.1f}s")
    base_rep, base = _drc(staged, wd / "in.drc.json", timeout)
    skip = set()
    kinds = ["vector" if vec else "widen", "pad", "stitch"]
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
    return dict(board=str(inp), planned=pc.stats, kept=kept, kinds=kinds, reverted=len(skip),
                drc_in=base, drc_out=final or base, rounds=rounds,
                nets=dict(power=sorted(pc.power), ground=sorted(pc.ground), switch=sorted(pc.switch),
                          victims=sorted(pc.victims)),
                plan_s=round(t_plan, 2), total_s=round(time.monotonic() - t0, 2))


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
        log(f"[power-copper] skipped: {type(e).__name__}: {e}")
        return dict(error=f"{type(e).__name__}: {e}")
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
    ap.add_argument("--operating", help="operating facts JSON (default: KAE_OPERATING of the .kicad_pro)")
    ap.add_argument("--workdir")
    ap.add_argument("--report")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    rep = run(a.input, a.output, dict(widen=not a.no_widen, vias=not a.no_vias, stitch=not a.no_stitch,
                                      max_width=a.max_width, current_cap=a.current_cap, mode=a.mode,
                                      into_pours=a.into_pours, neck=not a.no_neck, share=not a.no_share, vector_out=a.vector_out, operating=a.operating), workdir=a.workdir, timeout=a.timeout)
    txt = json.dumps(rep, indent=1)
    if a.report:
        Path(a.report).write_text(txt)
    print(json.dumps(dict(planned=rep["planned"], kept=rep["kept"], drc_in=rep["drc_in"], drc_out=rep["drc_out"],
                          total_s=rep["total_s"])))


if __name__ == "__main__":
    main()
