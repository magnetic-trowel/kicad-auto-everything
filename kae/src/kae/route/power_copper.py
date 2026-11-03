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
    max_width=1.0,            # mm: widest power/ground track (the feed width of 0603-1206 passives;
                              # power-copper.md: area efficiency peaks at feed width)
    ladder=(3.0, 2.5, 2.0, 1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.4, 0.3),
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
    drc_rounds=3,
)

VICTIM_ROLES = ("clock", "high_speed", "analog", "rf")
TOL = 0.002


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
                out.append((it.geom, it.r, req))
        return out

    def _allowed_half(self, pts, cons, net, layer):
        """Per sample point: the largest half-width the copper may have there."""
        a = np.full(len(pts), np.inf)
        if cons:
            P = shapely.points(pts)
            for g, r, req in cons:
                d = shapely.distance(g, P) - r - req - TOL
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
        for g, r, req in self._constraints(net, layer, seg, w / 2 + self.o["victim_gap_max"] + self.o["antenna_gap"], ignore):
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
            half = self._allowed_half(pts, cons, t.net, t.layer)
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
            self.edits[t.uuid] = [(tuple(a), tuple(b), w) for a, b, w in merged]
            self.stats["widened"] += 1
            self.stats["widened_mm"] += sum(math.dist(a, b) for a, b, w in merged if w > t.width + 1e-9)
        self.stats["widened_mm"] = round(self.stats["widened_mm"], 2)
        return self.stats["widened"]

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
            wt = sp.clamp_width(net, layer, min(self.o["via_track_max"], _short_side(pad.geom)))
            for dist, x, y in ring_candidates(pad.geom, rv, self.o["via_reach"]):
                p = Point(x, y)
                if not any(f.contains(p) for f in fills):
                    continue
                if sp.via_violations(net, x, y, first=True):
                    continue
                track_ok = not sp.track_violations(net, layer, wt, pos, (x, y), first=True)
                if not track_ok and not (not own.is_empty and own.contains(p)):
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
                        if sp.via_violations(net, x, y, first=True):
                            continue
                        sp.add_via(net, x, y, owner=("pc-stitch", l))
                        self.vias.append((net, x, y, D, d, W.new_uuid(), "stitch"))
                        placed.append((x, y))
                    added += len(placed)
        self.stats["stitch_vias"] = added
        return added

    # ---------------------------------------------------------------- writing
    def write(self, dst, skip=frozenset(), kinds=("widen", "pad", "stitch")):
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
            for i, (pa, pb, w) in enumerate(widen[u]):
                nu = u if i == 0 else W.new_uuid()
                groups[nu] = u
                out.append(W.track_sexpr(net, m_layer.group(1), w, pa, pb, uid=nu, locked=locked))
            tracks[u] = True
        out.append(text[pos:])
        text = "".join(out)
        chunks = []
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


def _culprits(rep, base_rep, groups):
    """Groups (original track uuid or via uuid) named by violations of `rep` not in `base_rep`."""
    from . import drc

    def key(v):
        return (v.get("type"), tuple(sorted((i.get("description") or "") for i in v.get("items") or [])))
    old = {key(v) for v in drc.errors(base_rep)} | {key(v) for v in base_rep.get("unconnected_items") or []}
    bad = set()
    for v in drc.errors(rep) + list(rep.get("unconnected_items") or []):
        if key(v) in old:
            continue
        for i in v.get("items") or []:
            g = groups.get(i.get("uuid"))
            if g:
                bad.add(g)
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
    for k, f in (("widen", pc.widen), ("vias", pc.ground_vias), ("stitch", pc.stitch)):
        if o[k]:
            t1 = time.monotonic()
            f()
            log(f"[power-copper] {k}: {time.monotonic() - t1:.1f}s")
    t_plan = time.monotonic() - t0
    log(f"[power-copper] planned {pc.stats} in {t_plan:.1f}s")
    base_rep, base = _drc(staged, wd / "in.drc.json", timeout)
    skip = set()
    kinds = ["widen", "pad", "stitch"]
    rounds = []
    cand = wd / "out" / "board.kicad_pcb"
    cand.parent.mkdir(parents=True, exist_ok=True)
    final = None
    for r in range(int(o["drc_rounds"]) + 3):
        groups = pc.write(cand, skip=skip, kinds=tuple(kinds))
        if not groups:
            break
        rep, s = _drc(cand, wd / f"out.drc{r}.json", timeout)
        worse = _worse(s, base)
        rounds.append(dict(kinds=list(kinds), skipped=len(skip), summary=s, worse=worse))
        log(f"[power-copper] round {r}: {s['errors']} errors, {s['unconnected']} unconnected "
            f"(input {base['errors']}, {base['unconnected']}); worse {worse or 'none'}")
        if not worse:
            final = s
            break
        bad = _culprits(rep, base_rep, groups) - skip
        if bad and r < int(o["drc_rounds"]):
            skip |= bad
            continue
        # not attributable (or out of rounds): drop the last stage still written
        if not kinds:
            break
        kinds.pop()
    out = Path(output_path)
    if final is not None:
        shutil.copy2(cand, out)
    else:
        shutil.copy2(staged, out)
        kinds = []
    for ext in (".kicad_pro", ".kicad_dru"):
        s_ = inp.with_suffix(ext)
        if s_.exists() and s_.resolve() != out.with_suffix(ext).resolve():
            shutil.copy2(s_, out.with_suffix(ext))
    kept = dict(widened=sum(1 for u in pc.edits if u not in skip) if "widen" in kinds else 0,
                ground_vias=sum(1 for v in pc.vias if v[6] == "pad" and v[5] not in skip) if "pad" in kinds else 0,
                stitch_vias=sum(1 for v in pc.vias if v[6] == "stitch" and v[5] not in skip) if "stitch" in kinds else 0)
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
    ap.add_argument("--operating", help="operating facts JSON (default: KAE_OPERATING of the .kicad_pro)")
    ap.add_argument("--workdir")
    ap.add_argument("--report")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args(argv)
    rep = run(a.input, a.output, dict(widen=not a.no_widen, vias=not a.no_vias, stitch=not a.no_stitch,
                                      max_width=a.max_width, operating=a.operating), workdir=a.workdir, timeout=a.timeout)
    txt = json.dumps(rep, indent=1)
    if a.report:
        Path(a.report).write_text(txt)
    print(json.dumps(dict(planned=rep["planned"], kept=rep["kept"], drc_in=rep["drc_in"], drc_out=rep["drc_out"],
                          total_s=rep["total_s"])))


if __name__ == "__main__":
    main()
