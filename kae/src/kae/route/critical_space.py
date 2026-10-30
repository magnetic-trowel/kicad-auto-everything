# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The world of the critical router: KiCad's effective constraints and the exact geometry of
everything a critical track or via must keep clear of.

Constraints are not re-derived here. They are the numbers the bridge enforces, from
`kae.route.effective.Rules` (over `kae.route.constraints.plan` and the port of KiCad's rule
engine, `kae.route.rules`):

- track widths: Rules.track_width(net, layer) = (min, opt, max); a wider critical track
  stays inside [min, max];
- vias: Rules.via(net) (diameter, drill) and Rules.same_net_via_pitch(net);
- copper of another net: Rules.clearance(net, other, layer) for track-track, track-via,
  via-track and via-via (hole clearance through the ring, hole-to-hole through both drills);
- pads: the pad's clearance class, the table behind Rules.pad_clearance (per DSN pin, so
  pads that repeat a number keep their own class): copper clearance, hole clearance through
  the ring, solder-mask aperture, real copper beyond the DSN shape;
- edges: Rules.edge_clearance(net, layer), and the plan's via edge band;
- obstacles the plan holds for the bridge: NPTH holes, cut-outs and stray edges, copper
  graphics (with their net: copper of that net), rule areas, each with its class;
- thermal-spoke corridors (`constraints.thermal_corridors`) as keepouts for other nets, so
  critical copper never starves a zone connection.

Geometry: pads carry their DSN shape (board frame; library frame kept for pose changes),
holes, layers, net and clearance class; routed items (tracks, vias) are added as they are
committed. `track_violations` and `via_violations` check a candidate exactly (shapely
distances, `TOL` above every requirement); the grid router uses `need` to inflate obstacles.

Every length is mm. KiCad stores nanometres, and pads come as polygons that lie outside the
true shape (ERROR_OUTSIDE), so a TOL of 2 um above each requirement is safe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from . import constraints as CN
from . import effective as EF
from . import rules as R

TOL = 0.002          # mm kept above every requirement
EXACT_TOL = -1e-7    # mm: no margin, only float slack (0.1 nm; KiCad stores whole nm), for the
                     # pieces where the requirement itself is all the room there is (a track
                     # exactly as wide as a 0.4 mm-pitch pad, centred on it, between its neighbours)
INF = math.inf


# ----------------------------------------------------------------------------- items
class Item:
    """An obstacle or a piece of copper.

    kind: 'pad' | 'track' | 'via' | 'shape' (graphic, cut-out, edge, keepout) | 'hole' |
          'corridor' (thermal spokes: keep other nets out) | 'keepout' (rule area)
    net: net name ('' none); for 'keepout' and 'shape' obstacles of no net, None = every net
    layers: frozenset of copper layers
    geom: shapely geometry (pads: DSN shape; tracks: centreline; vias, holes: centre point)
    r: radius added to geom (track half width, via radius, hole radius)
    cls: pad/obstacle clearance class (plan.obstacle_classes) or routing class (tracks, vias)
    vias_only: a rule area that keeps out vias only
    """
    __slots__ = ('kind', 'net', 'layers', 'geom', 'r', 'cls', 'bbox', 'owner', 'hole', 'smd', 'vias_only',
                 'local', 'fp', 'idx', 'uuid', 'width', 'drill', 'locked', 'pos')

    def __init__(self, kind, net, layers, geom, r=0.0, cls=None, owner=None, hole=None, smd=False,
                 vias_only=False):
        self.kind, self.net, self.layers, self.geom, self.r, self.cls = kind, net, frozenset(layers), geom, r, cls
        self.owner, self.hole, self.smd, self.vias_only = owner, hole, smd, vias_only
        self.local = None
        self.fp = None
        self.idx = -1
        self.uuid = ''
        self.width = 0.0
        self.drill = 0.0
        self.locked = True
        self.pos = None
        self.bbox = _bbox(geom, r)

    def __repr__(self):
        return f"Item({self.kind}, {self.net!r}, {sorted(self.layers)}, {self.owner})"


def _bbox(g, r=0.0):
    x0, y0, x1, y1 = g.bounds
    return (x0 - r, y0 - r, x1 + r, y1 + r)


def _poly(rings):
    if not rings or len(rings[0]) < 3:
        return None
    g = Polygon(rings[0], [h for h in rings[1:] if len(h) >= 3])
    return g if g.is_valid else g.buffer(0)


def _hole_geom(h):
    """(centre geometry, radius) of a pad's hole record {a, b, width}."""
    if not h:
        return None
    a, b = tuple(h["a"]), tuple(h["b"])
    g = Point(a) if a == b else LineString([a, b])
    return g, h["width"] / 2.0


@dataclass
class Terminal:
    """Where a connection may start or end: a pad (or its copper on given layers)."""
    net: str
    layers: tuple
    geom: object             # board-frame copper (union of the pad's DSN shapes)
    x: float
    y: float
    fp: str = ''             # footprint uuid
    pad: str = ''            # pad number
    width: float = 0.0       # smaller copper dimension of the pad (mm)
    length: float = 0.0      # larger dimension
    items: list = field(default_factory=list)
    by_layer: dict = field(default_factory=dict)   # layer -> the copper on that layer only

    def geom_on(self, layer):
        """The terminal's copper on `layer` (a pad with an SMD twin has less on one side)."""
        return self.by_layer.get(layer, self.geom) if self.by_layer else self.geom

    def centre_on(self, layer):
        """A point of the terminal's copper on `layer`: the centre when it lies there."""
        g = self.geom_on(layer)
        from shapely.geometry import Point as _Pt
        if g.distance(_Pt(self.x, self.y)) <= 1e-9:
            return (self.x, self.y)
        c = g.centroid
        if g.distance(c) <= 1e-9:
            return (c.x, c.y)
        r = g.representative_point()
        return (r.x, r.y)


# ----------------------------------------------------------------------------- the space
class Space:
    """Obstacles, requirements and committed copper for one board.

        sp = Space(board, info)                # kicad_file.load, pcbnew_io.export_dsn
        sp.need(item, net, 'track', layer)     # clearance (mm) a track of `net` keeps from item
        sp.track_violations(net, layer, w, a, b)
        sp.via_violations(net, x, y)
        sp.add_track(...), sp.add_via(...)    # commit copper (becomes an obstacle for other nets)

    `plan` defaults to constraints.plan(info, board.path, {severities}) and `rules` to
    effective.Rules(info, board.path, plan): the bridge's own numbers.
    """

    def __init__(self, board, info, plan=None, sev=None, opts=None, rules=None):
        self.opts = dict(opts or {})
        self.sev = sev or {}
        self.notes = []          # what the space could not model (reported by Session.report)
        if plan is None:
            plan = CN.plan(info, board.path, dict(severities=self.sev))
        self.board, self.info, self.plan = board, info, plan
        self.eff = rules or EF.Rules(info, board.path, plan)
        self.cu = list(plan.copper)
        self.rb = plan.rule_board
        self.settings = info.get("settings") or {}
        self.via_in_pad = bool(self.opts.get("via_in_pad", False))
        st = board.stackup
        z = [0.0]
        if st is not None and st.copper == self.cu and len(st.gaps) == len(self.cu) - 1:
            for k in range(1, len(self.cu)):
                z.append(z[-1] + st.cu_thickness[k - 1] / 2 + st.gaps[k - 1] + st.cu_thickness[k] / 2)
            self.er = list(st.er)
            self.tcu = dict(zip(self.cu, st.cu_thickness))
        else:
            th = getattr(board, "thickness", 1.6) or 1.6
            for k in range(1, len(self.cu)):
                z.append(th * k / max(1, len(self.cu) - 1))
            self.er = [4.5] * (len(self.cu) - 1)
            self.tcu = {l: 0.035 for l in self.cu}
        self.z = dict(zip(self.cu, z))
        self.thickness = z[-1] if len(z) > 1 else 1.6
        polys = [p for p in (_poly(r) for r in info.get("outline") or []) if p is not None]
        self.outline = unary_union(polys) if polys else None
        if self.outline is not None:
            shapely.prepare(self.outline)
            self.outline_boundary = self.outline.boundary
        else:
            self.outline_boundary = None
        self.fp_by_index = {i: fp for i, fp in enumerate(board.footprints)}
        self.fp_by_uuid = {fp.uuid: fp for fp in board.footprints}
        self.items = {l: [] for l in self.cu}     # layer -> [Item]
        self._arr = {}                             # layer -> bbox array cache
        self.pads = []                             # pad Items (info order)
        self.pads_of = {}                          # (fp uuid, number) -> [pad Item]
        self.pads_by_fp = {}
        self.corridors_by_fp = {}
        self.routed = []                           # committed critical copper (Items)
        self.existing = []                         # tracks and vias already in the board
        self.zones = []                            # (net, layer, polygon, rec)
        self._req_cache = {}
        self._build_pads()
        self._build_obstacles()
        self._build_existing()
        self._build_zones()
        self.max_need = self._max_need()

    # ------------------------------------------------------------------ build
    def _build_pads(self):
        plan = self.plan
        for k, pd in enumerate(self.info.get("pads") or []):
            if not pd.get("layers"):
                continue
            dsn, real = CN._pad_shapes(pd)
            geom = dsn
            if geom is None or geom.is_empty:
                vals = [g for g in real.values() if g is not None and not g.is_empty]
                if not vals:
                    continue
                geom = unary_union(vals)
            cls = plan.pin_class.get((pd.get("comp"), pd.get("pin"))) if pd.get("pin") else None
            hole = _hole_geom(pd.get("hole"))
            it = Item("pad", pd.get("net") or "", pd["layers"], geom, 0.0, cls,
                      owner=(pd.get("ref"), pd.get("number")), hole=hole, smd=pd.get("attr") == "smd")
            fp = self.fp_by_index.get(pd.get("fp_index"))
            it.fp = fp.uuid if fp is not None and fp.ref == pd.get("ref") else None
            if it.fp is None:
                for f in self.board.footprints:
                    if f.ref == pd.get("ref"):
                        it.fp = f.uuid
                        break
            it.idx = k
            it.uuid = pd.get("uuid") or ""
            pos = pd.get("pos") or [geom.centroid.x, geom.centroid.y]
            it.pos = (float(pos[0]), float(pos[1]))
            if cls is None:
                # a pad that is no DSN pin (round keepout, no copper): kept as a hole obstacle
                it.kind = "pad_nopin"
            self.pads.append(it)
            self.pads_of.setdefault((it.fp, str(pd.get("number"))), []).append(it)
            self.pads_by_fp.setdefault(it.fp, []).append(it)
            for l in it.layers:
                if l in self.items:
                    self.items[l].append(it)

    def _build_obstacles(self):
        plan = self.plan
        for ob in plan.obstacles:
            layers = self.cu if ob.layer == "signal" else [ob.layer]
            if isinstance(ob.geom, tuple) and ob.geom[0] == "circle":
                _, x, y, d = ob.geom
                it = Item("hole", None, layers, Point(x, y), d / 2.0, ob.cls, owner=ob.why)
            else:
                g = ob.geom
                if g is None or g.is_empty:
                    continue
                kind = "keepout" if ob.cls == "kae_zero" else "shape"
                it = Item(kind, None, layers, g, 0.0, ob.cls, owner=ob.why, vias_only=ob.kind == "via_keepout")
            for l in layers:
                if l in self.items:
                    self.items[l].append(it)
        # copper graphics of a net: copper of that net (an obstacle in its class for others)
        for net, shapes, cls, why in getattr(plan, "net_graphics", []) or []:
            for l, g in shapes.items():
                if l in self.items and g is not None and not g.is_empty:
                    self.items[l].append(Item("shape", net, [l], g, 0.0, cls, owner=why))
        # thermal-spoke corridors: other nets keep out (zero clearance)
        if not self.opts.get("no_corridors"):
            try:
                cors = CN.thermal_corridors(self.info, plan, None, self.sev)
            except Exception as e:   # noqa: BLE001 - not fatal, but reported (Session.report)
                self.notes.append(f"thermal corridors unavailable: {type(e).__name__}: {e}")
                cors = []
            for geo, layer, pad in cors:
                it = Item("corridor", pad.get("net") or "", [layer], geo, 0.0, None,
                          owner=f"spokes {pad.get('ref')}.{pad.get('number')}")
                fp = self.fp_by_index.get(pad.get("fp_index"))
                it.fp = fp.uuid if fp is not None else None
                if it.fp is not None:
                    self.corridors_by_fp.setdefault(it.fp, []).append(it)
                if layer in self.items:
                    self.items[layer].append(it)

    def _build_existing(self):
        b = self.board
        for t in b.tracks:
            if t.layer not in self.items:
                continue
            g = LineString([t.start, t.end]) if t.mid is None else LineString([t.start, t.mid, t.end])
            it = Item("track", t.net or "", [t.layer], g, t.width / 2.0, self.rc(t.net), owner="existing")
            it.uuid, it.width, it.locked = t.uuid, t.width, t.locked
            self.existing.append(it)
            self.items[t.layer].append(it)
        for v in b.vias:
            layers = [l for l in v.layers if l in self.items] or self.cu
            if len(v.layers) == 2 and v.layers[0] in self.cu and v.layers[1] in self.cu:
                i, j = sorted((self.cu.index(v.layers[0]), self.cu.index(v.layers[1])))
                layers = self.cu[i:j + 1]
            it = Item("via", v.net or "", layers, Point(v.x, v.y), v.size / 2.0, self.rc(v.net), owner="existing")
            it.uuid, it.width, it.drill, it.locked = v.uuid, v.size, v.drill, v.locked
            it.hole = (Point(v.x, v.y), v.drill / 2.0)
            self.existing.append(it)
            for l in layers:
                self.items[l].append(it)

    def _build_zones(self):
        for z in self.info.get("zones") or []:
            if z.get("rule_area") or not z.get("net") or z.get("teardrop"):
                continue
            g = unary_union([x for x in (_poly(r) for r in z.get("rings") or []) if x is not None])
            if g.is_empty:
                continue
            if self.outline is not None:
                g = g.intersection(self.outline)
            for l in z.get("layers") or []:
                self.zones.append((z["net"], l, g, z))

    def _max_need(self):
        m = 0.0
        for oc in self.plan.obstacle_classes.values():
            for v in oc.values.values():
                m = max(m, *v)
        for v in self.plan.matrix.values():
            m = max(m, *v)
        return m

    # ------------------------------------------------------------------ classes, widths
    def rc(self, net):
        """Routing class name of a net (None for nets the plan does not know)."""
        return self.plan.net_class.get(net)

    def width_limits(self, net, layer):
        """(min, opt, max) track width of `net` on `layer`: effective.Rules.track_width
        (KiCad's limits; opt = the bridge's class width)."""
        key = ("w", net, layer)
        v = self._req_cache.get(key)
        if v is None:
            try:
                w = self.eff.track_width(net, layer)
                v = (w.min or 0.0, max(w.opt or 0.0, w.min or 0.0), w.max)
            except KeyError:
                mn = self.settings.get("min_track", 0.0) or 0.0
                v = (mn, max(mn, 0.2), None)
            self._req_cache[key] = v
        return v

    def clamp_width(self, net, layer, w):
        """w inside [min, max] of `net` on `layer`, in whole micrometres."""
        mn, _, mx = self.width_limits(net, layer)
        w = CN.up(max(w, mn), 0.001)
        if mx is not None and w > mx + 1e-9:
            w = mx
        return w

    def via_size(self, net):
        """(diameter, drill) of a through via of `net`: effective.Rules.via."""
        try:
            v = self.eff.via(net)
            return (v.diameter, v.drill)
        except KeyError:
            s = self.settings
            return (max(s.get("min_via", 0.6) or 0.6, 0.6), max(s.get("min_drill", 0.3) or 0.3, 0.3))

    def same_net_via_pitch(self, net):
        key = ("pitch", net)
        v = self._req_cache.get(key)
        if v is None:
            try:
                v = self.eff.same_net_via_pitch(net)
            except KeyError:
                v = self.via_size(net)[0] + (self.settings.get("hole_to_hole", 0.25) or 0.25)
            self._req_cache[key] = v
        return v

    # ------------------------------------------------------------------ requirements
    def need(self, it, net, kind, layer):
        """Clearance (mm) a `kind` ('track' | 'via') of `net` on `layer` keeps from item `it`,
        measured from it.geom grown by it.r; None when it does not constrain this copper."""
        if it.kind in ("pad", "track", "via", "corridor", "shape") and it.net and it.net == net:
            return None
        if it.kind == "corridor":
            return 0.0 if kind == "track" else None
        if it.kind == "keepout":
            if it.vias_only and kind == "track":
                return None
            return 0.0
        if it.kind in ("pad", "shape", "hole", "pad_nopin"):
            oc = self.plan.obstacle_classes.get(it.cls) if it.cls else None
            v = oc.values.get((self.rc(net), layer)) if oc is not None else None
            if v is None:
                return self._generic_need(net, kind, layer)
            return v[0] if kind == "track" else v[1]
        if it.kind in ("track", "via"):
            c = self._pair(net, it.net, layer)
            if c is None:
                return self._generic_need(net, kind, layer)
            if kind == "track":
                return c.track_track if it.kind == "track" else c.track_via
            return c.via_track if it.kind == "track" else c.via_via
        return self._generic_need(net, kind, layer)

    def _pair(self, net, other, layer):
        """effective.Rules.clearance(net, other, layer), cached (None for unknown nets)."""
        key = ("c", net, other, layer)
        if key in self._req_cache:
            return self._req_cache[key]
        try:
            c = self.eff.clearance(net, other, layer) if other else None
        except KeyError:
            c = None
        self._req_cache[key] = c
        return c

    def _generic_need(self, net, kind, layer):
        key = ("g", net, kind, layer)
        v = self._req_cache.get(key)
        if v is None:
            it = CN.net_item(self.info, net, kind, layer, width=0.2)
            v = R.strictest(self.rb, "clearance", it, dict(it, net="", netclass="Default", constituents=["Default"]),
                            layer).min or 0.0
            self._req_cache[key] = v
        return v

    def edge_need(self, net, kind, layer):
        """effective.Rules.edge_clearance (track or via) of `net` on `layer`."""
        key = ("e", net, layer)
        v = self._req_cache.get(key)
        if v is None:
            try:
                e = self.eff.edge_clearance(net, layer)
                v = (e.track, e.via)
            except KeyError:
                e = self.settings.get("edge_clearance", 0.0) or 0.0
                v = (e, e)
            self._req_cache[key] = v
        return v[0] if kind == "track" else v[1]

    # ------------------------------------------------------------------ queries
    def _arrays(self, layer):
        a = self._arr.get(layer)
        lst = self.items[layer]
        if a is None or a[1] != len(lst):
            bb = np.array([it.bbox for it in lst], float).reshape(-1, 4)
            a = (bb, len(lst))
            self._arr[layer] = a
        return a[0]

    def query(self, layer, bbox, grow=0.0):
        """Items on `layer` whose (grown) bbox overlaps `bbox`."""
        lst = self.items.get(layer)
        if not lst:
            return []
        bb = self._arrays(layer)
        x0, y0, x1, y1 = bbox
        m = (bb[:, 0] - grow <= x1) & (bb[:, 2] + grow >= x0) & (bb[:, 1] - grow <= y1) & (bb[:, 3] + grow >= y0)
        return [lst[i] for i in np.nonzero(m)[0]]

    def invalidate(self, layer=None):
        if layer is None:
            self._arr.clear()
        else:
            self._arr.pop(layer, None)

    # ------------------------------------------------------------------ exact checks
    def _dist(self, it, g):
        d = it.geom.distance(g)
        return d - it.r

    def track_violations(self, net, layer, w, a, b, ignore=(), first=False, tol=TOL):
        """Requirements a track of `net`, width w, from a to b on `layer` breaks:
        [(item or 'edge', distance, needed)] (empty when legal); `tol` mm kept above each."""
        TOL = tol
        out = []
        seg = LineString([a, b]) if (abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9) else Point(a)
        half = w / 2.0
        x0, y0 = min(a[0], b[0]), min(a[1], b[1])
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        reach = half + self.max_need + TOL
        for it in self.query(layer, (x0, y0, x1, y1), reach):
            if it in ignore:
                continue
            nd = self.need(it, net, "track", layer)
            if nd is None:
                continue
            d = self._dist(it, seg) - half
            if d < nd + TOL:
                if it.kind in ("keepout", "corridor") and d >= 0:
                    # keepouts and corridors forbid overlap, not proximity
                    if d > TOL:
                        continue
                out.append((it, d, nd))
                if first:
                    return out
        if self.outline is not None:
            e = self.edge_need(net, "track", layer)
            if not self.outline.contains(seg):
                out.append(("edge", -1.0, e))
            else:
                d = self.outline_boundary.distance(seg) - half
                if d < e + TOL:
                    out.append(("edge", d, e))
        return out

    def via_violations(self, net, x, y, size=None, drill=None, ignore=(), first=False, layers=None):
        """Requirements a through via of `net` at (x, y) breaks (empty when legal)."""
        D, d = (size, drill) if size else self.via_size(net)
        rv, rh = D / 2.0, d / 2.0
        p = Point(x, y)
        out = []
        h2h = self.settings.get("hole_to_hole", 0.0) or 0.0
        pitch = self.same_net_via_pitch(net)
        seen = set()
        for layer in (layers or self.cu):
            reach = rv + self.max_need + max(h2h, pitch) + TOL
            for it in self.query(layer, (x, y, x, y), reach):
                if id(it) in seen or it in ignore:
                    continue
                seen.add(id(it))
                same = it.net is not None and it.net == net and it.kind in ("pad", "track", "via", "corridor", "shape")
                if same:
                    if it.kind == "via":
                        dc = it.geom.distance(p)
                        if dc < pitch - TOL:
                            out.append((it, dc, pitch))
                    elif it.kind == "pad":
                        if it.hole is not None:
                            hg, hr = it.hole
                            dh = hg.distance(p) - hr - rh
                            if dh < h2h + TOL:
                                out.append((it, dh, h2h))
                        if it.smd and not self.via_in_pad:
                            dd = it.geom.distance(p) - rv
                            if dd < -TOL:
                                out.append((it, dd, 0.0))
                    if first and out:
                        return out
                    continue
                nd = self.need(it, net, "via", layer)
                if nd is None:
                    continue
                dd = self._dist(it, p) - rv
                if dd < nd + TOL:
                    if it.kind in ("keepout", "corridor") and dd > TOL:
                        continue
                    out.append((it, dd, nd))
                    if first:
                        return out
                if it.hole is not None and it.kind in ("pad", "via"):
                    hg, hr = it.hole
                    dh = hg.distance(p) - hr - rh
                    if dh < h2h + TOL:
                        out.append((it, dh, h2h))
                        if first:
                            return out
        if self.outline is not None:
            e = max(self.edge_need(net, "via", l) for l in self.cu)
            band = self.plan.notes.get("via_edge_band") or 0.0
            e = max(e, band)
            if not self.outline.contains(p):
                out.append(("edge", -1.0, e))
            else:
                dd = self.outline_boundary.distance(p) - rv
                if dd < e + TOL:
                    out.append(("edge", dd, e))
        return out

    # ------------------------------------------------------------------ commits
    def add_track(self, net, layer, w, a, b, owner=None, uuid=""):
        g = LineString([a, b])
        it = Item("track", net, [layer], g, w / 2.0, self.rc(net), owner=owner)
        it.width = w
        it.uuid = uuid
        self.items[layer].append(it)
        self.routed.append(it)
        return it

    def add_via(self, net, x, y, owner=None, size=None, drill=None, uuid=""):
        D, d = (size, drill) if size else self.via_size(net)
        it = Item("via", net, self.cu, Point(x, y), D / 2.0, self.rc(net), owner=owner)
        it.hole = (Point(x, y), d / 2.0)
        it.width, it.drill = D, d
        it.uuid = uuid
        for l in self.cu:
            self.items[l].append(it)
        self.routed.append(it)
        return it

    def remove(self, items):
        """Remove committed copper (rip-up)."""
        ids = {id(i) for i in items}
        for l in self.cu:
            self.items[l] = [it for it in self.items[l] if id(it) not in ids]
        self.routed = [it for it in self.routed if id(it) not in ids]
        self.existing = [it for it in self.existing if id(it) not in ids]
        self.invalidate()

    # ------------------------------------------------------------------ terminals and zones
    def terminal(self, fp_uuid, numbers, layers=None):
        """A Terminal for the pads `numbers` of footprint `fp_uuid` (the copper union)."""
        if isinstance(numbers, (str, int)):
            numbers = [numbers]
        its = []
        for n in numbers:
            its += self.pads_of.get((fp_uuid, str(n)), [])
        if not its:
            return None
        its = [i for i in its if i.kind == "pad"] or its
        lays = set()
        for i in its:
            lays |= set(i.layers)
        if layers:
            lays &= set(layers)
        geom = unary_union([i.geom for i in its])
        c = geom.centroid
        # pad dimensions: from the minimum rotated rectangle of the copper
        w, ln = _dims(its[0].geom)
        nets = {i.net for i in its}
        net = its[0].net if len(nets) == 1 else its[0].net
        cx, cy = (c.x, c.y)
        if len(its) == 1 and its[0].pos is not None:
            cx, cy = its[0].pos
        by_layer = {l: unary_union([i.geom for i in its if l in i.layers]) for l in self.cu if l in lays}
        return Terminal(net=net, layers=tuple(l for l in self.cu if l in lays), geom=geom, x=cx, y=cy,
                        fp=fp_uuid, pad=",".join(str(n) for n in numbers), width=w, length=ln, items=its,
                        by_layer=by_layer)

    def component(self, net, seeds):
        """Copper of `net` electrically connected to the seed geometries (pads, committed
        tracks and vias that touch, transitively; zones are not counted): [Item]."""
        items = [it for it in self.pads if it.net == net and it.kind == "pad"]
        items += [it for it in self.routed + self.existing if it.net == net]
        if not items:
            return []
        geo = [it.geom.buffer(it.r) if it.r > 0 else it.geom for it in items]
        lay = [set(it.layers) for it in items]
        done = set()
        front = []
        for g, ls in seeds:
            for k, (gg, ll) in enumerate(zip(geo, lay)):
                if k not in done and ll & set(ls) and gg.distance(g) <= 1e-6:
                    done.add(k)
                    front.append(k)
        while front:
            k = front.pop()
            for j, (gg, ll) in enumerate(zip(geo, lay)):
                if j in done or not (ll & lay[k]):
                    continue
                if gg.distance(geo[k]) <= 1e-6:
                    done.add(j)
                    front.append(j)
        return [items[k] for k in sorted(done)]

    def zones_of(self, net, layer=None):
        return [(l, g) for n, l, g, _ in self.zones if n == net and (layer is None or l == layer)]

    def zone_covers(self, net, layer, x, y, margin=0.0):
        p = Point(x, y)
        for n, l, g, _ in self.zones:
            if n == net and l == layer:
                if margin <= 0 and g.contains(p):
                    return True
                if margin > 0 and g.contains(p) and g.boundary.distance(p) >= margin:
                    return True
        return False

    def foreign_zone_polys(self, net, layer):
        return [g for n, l, g, _ in self.zones if l == layer and n != net]

    def plane_below(self, layer, x, y, nets=None):
        """(height above the nearest plane layer, its layer, its net) for copper on `layer`
        at (x, y): any zone on another copper layer covering the point is a plane (its net
        images the current at HF); `nets` restricts to those nets. (inf, None, None) without."""
        best = (INF, None, None)
        zl = self.z[layer]
        p = Point(x, y)
        for n, l, g, _ in self.zones:
            if l == layer or (nets is not None and n not in nets):
                continue
            d = abs(self.z[l] - zl)
            if d < best[0] and g.contains(p):
                best = (d, l, n)
        return best

    # ------------------------------------------------------------------ poses (module moves)
    def set_pose(self, fp_uuid, old, new):
        """Move the pads of a footprint from pose `old` to pose `new` ((x, y, rot, side));
        sides must agree (critical moves never flip parts)."""
        from kae.board import transform as T
        if old[3] != new[3]:
            raise ValueError("set_pose cannot flip a part")
        its = list(self.pads_by_fp.get(fp_uuid) or []) + list(self.corridors_by_fp.get(fp_uuid) or [])
        if not its:
            return
        inv = _inverse(T.affine(*old))
        fwd = T.affine(*new)
        for it in its:
            # library-frame copies, made once from the pose the pads are at now
            if it.local is None:
                hl = None
                if it.hole is not None:
                    hl = (affinity.affine_transform(it.hole[0], inv), it.hole[1])
                pl = affinity.affine_transform(Point(it.pos), inv) if it.pos is not None else None
                it.local = (affinity.affine_transform(it.geom, inv), hl, pl)
            g, hl, pl = it.local
            it.geom = affinity.affine_transform(g, fwd)
            if hl is not None:
                it.hole = (affinity.affine_transform(hl[0], fwd), hl[1])
            if pl is not None:
                q = affinity.affine_transform(pl, fwd)
                it.pos = (q.x, q.y)
            it.bbox = _bbox(it.geom, it.r)
        self.invalidate()


def _inverse(params):
    a, b, d, e, xo, yo = params
    det = a * e - b * d
    ia, ib, id_, ie = e / det, -b / det, -d / det, a / det
    return [ia, ib, id_, ie, -(ia * xo + ib * yo), -(id_ * xo + ie * yo)]


def _dims(g):
    """(smaller, larger) side of the minimum rotated rectangle of a pad shape."""
    try:
        r = g.minimum_rotated_rectangle
        c = list(r.exterior.coords)
        a = math.dist(c[0], c[1])
        b = math.dist(c[1], c[2])
        return (min(a, b), max(a, b))
    except Exception:   # noqa: BLE001
        x0, y0, x1, y1 = g.bounds
        return (min(x1 - x0, y1 - y0), max(x1 - x0, y1 - y0))
