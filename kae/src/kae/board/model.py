# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The board model: Contract 1 of docs/topics/architecture/month-plan.md.

Units are mm and degrees; coordinates are KiCad board coordinates (y down). Field names
of the contract are fixed. Angles are normalized to [0, 360).

Frames:
- Footprint frame = the library frame: the footprint as drawn in its library (front
  side, 0 degrees). `Pad.lx, ly, lrot`, `Footprint.courtyard`, `courtyard_back`, `body`
  and `edge_cuts` are in this frame, so two copies of a part have the same local data on
  either side. A pose (x, y, rot, side) maps a local point to
  `(x, y) + R(rot) (lx, s*ly)`, s = -1 on the back, with KiCad's rotation
  `R(a) (u, v) = (u cos a + v sin a, -u sin a + v cos a)` (y down, positive angle
  counter-clockwise on screen); a pad's absolute angle is `rot + s*lrot`
  (see kae.board.transform).
- `Pad.x, y` and `Pad.layers` are the pad's absolute position and board layers at the
  footprint's current pose and side.

Beyond the contract (documented extras, all with defaults): `Pad.uuid, slot, rratio,
offset`; `Footprint.courtyard_back, edge_cuts, path, sheet, flags`; `Board.generator,
layers, thickness, warnings`; `Stackup.thickness, source`; the `Rules` extras below.

Footprint.flags (loader notes, "<flag>:<library layer>" for courtyards):
courtyard_malformed (a chain does not close); courtyard_gap (drawn endpoints joined across
a gap of up to 20 um, as KiCad's chaining does); courtyard_overlap (outlines overlap or
touch: we keep their union, KiCad's DRC copy is not deflated); courtyard_degenerate (a
contour without area was dropped); uuid_synthesized / uuid_duplicate (see
kicad_file.synth_uuid); bad_graphic:<kind>.

Geometry fields hold shapely objects; `to_dict` writes polygons as lists of rings
(`[shell, hole, ...]`, each ring a list of [x, y]) and lines as lists of [x, y].
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

from shapely.geometry import LineString, Polygon


# ----------------------------------------------------------------------------- geometry
def poly_to_rings(p):
    return [[list(c) for c in p.exterior.coords]] + [[list(c) for c in r.coords] for r in p.interiors]


def rings_to_poly(rings):
    return Polygon(rings[0], rings[1:]) if rings else Polygon()


def _line_to(ls):
    return [list(c) for c in ls.coords]


def _polys_to(ps):
    return [poly_to_rings(p) for p in ps]


def _polys_from(v):
    return [rings_to_poly(r) for r in v or []]


def _lines_from(v):
    return [LineString(c) for c in v or []]


def _lines_to(ls):
    return [_line_to(x) for x in ls]


def _xy(v):
    return None if v is None else (float(v[0]), float(v[1]))


class _Dict:
    """to_dict/from_dict for flat dataclasses; geometry and nested types per class."""
    _to = {}     # field -> encoder
    _from = {}   # field -> decoder

    def to_dict(self):
        out = {}
        for f in fields(self):
            v = getattr(self, f.name)
            enc = self._to.get(f.name)
            if enc is not None:
                v = enc(v)
            elif isinstance(v, tuple):
                v = list(v)
            elif isinstance(v, (list, dict)):
                v = _plain(v)
            out[f.name] = v
        return out

    @classmethod
    def from_dict(cls, d):
        kw = {}
        names = {f.name for f in fields(cls)}
        for k, v in d.items():
            if k not in names:
                continue  # tolerate fields from newer writers
            dec = cls._from.get(k)
            kw[k] = dec(v) if dec is not None else v
        return cls(**kw)


def _plain(v):
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if hasattr(v, "to_dict"):
        return v.to_dict()
    return v


# ----------------------------------------------------------------------------- types
@dataclass
class Pad(_Dict):
    number: str
    net: str                         # '' = no net
    kind: str                        # smd | thru_hole | np_thru_hole | connect
    shape: str                       # rect | roundrect | circle | oval | trapezoid | custom | ...
    size: tuple                      # (w, h) in the pad's own frame
    lx: float                        # library frame
    ly: float
    lrot: float
    x: float                         # absolute, current pose
    y: float
    layers: list = field(default_factory=list)   # board layers, current side, wildcards expanded
    drill: float = 0.0               # hole diameter (slot: its width); 0 without a hole
    pinfunction: str = ""
    pintype: str = ""
    # extras
    uuid: str = ""
    slot: tuple | None = None        # (w, h) of an oval hole, else None
    rratio: float = 0.0              # roundrect corner radius / min(w, h)
    offset: tuple = (0.0, 0.0)       # copper shape offset from the hole, pad frame
    clearance: float = 0.0           # local clearance override (pad's own, else the footprint's); 0 = none
    mask_margin: float | None = None  # solder-mask expansion override (pad's own, else the footprint's);
    #                                   None = the board's pad_to_mask_clearance (Rules.mask_margin)

    _from = {"size": tuple, "slot": lambda v: None if v is None else tuple(v), "offset": tuple}


@dataclass
class Footprint(_Dict):
    ref: str
    value: str
    lib_id: str
    uuid: str
    x: float
    y: float
    rot: float
    side: str                        # 'F' | 'B'
    locked: bool
    attrs: list = field(default_factory=list)     # smd, through_hole, board_only, dnp, ...
    fields: dict = field(default_factory=dict)    # all properties (Reference, Value, MPN, ...)
    pads: list = field(default_factory=list)
    courtyard: list = field(default_factory=list)  # Polygons, library frame, own side (library F.CrtYd)
    body: list = field(default_factory=list)       # fallback extent when courtyard is empty
    on_board: bool = True            # False when outside the board, e.g. in a place task's staging area
    # extras
    courtyard_back: list = field(default_factory=list)  # library B.CrtYd (the side opposite the part)
    edge_cuts: list = field(default_factory=list)       # LineStrings on Edge.Cuts, library frame
    graphics: dict = field(default_factory=dict)  # library layer (F/B.Cu, F/B.Mask) -> [Polygon], library frame,
    #                                               stroke widths included (logos, mask apertures, copper shapes)
    path: str = ""                   # schematic path
    sheet: str = ""                  # schematic sheet name
    flags: list = field(default_factory=list)  # loader notes (module docstring)
    silk: dict = field(default_factory=dict)   # library layer (F/B.SilkS, F/B.Fab) -> [Polygon], library
    #                                            frame: stroked graphics and visible silk texts' boxes

    _to = {"pads": lambda v: [p.to_dict() for p in v], "courtyard": _polys_to, "body": _polys_to,
           "courtyard_back": _polys_to, "edge_cuts": _lines_to,
           "graphics": lambda v: {k: _polys_to(p) for k, p in v.items()},
           "silk": lambda v: {k: _polys_to(p) for k, p in v.items()}}
    _from = {"pads": lambda v: [Pad.from_dict(p) for p in v], "courtyard": _polys_from,
             "body": _polys_from, "courtyard_back": _polys_from, "edge_cuts": _lines_from,
             "graphics": lambda v: {k: _polys_from(p) for k, p in v.items()},
             "silk": lambda v: {k: _polys_from(p) for k, p in v.items()}}


@dataclass
class Net(_Dict):
    name: str
    netclass: str = "Default"     # KiCad's effective class name; key into Rules.netclasses
    pads: list = field(default_factory=list)   # [(ref, number)]

    _to = {"pads": lambda v: [list(p) for p in v]}
    _from = {"pads": lambda v: [tuple(p) for p in v]}


@dataclass
class Keepout(_Dict):
    """A rule area: what it keeps out, on which layers."""
    uuid: str
    name: str
    layers: list
    outline: Polygon
    tracks: bool = False             # True = not allowed
    vias: bool = False
    pads: bool = False
    copperpour: bool = False
    footprints: bool = False
    placement: dict | None = None    # KiCad placement rule area: {'enabled', 'sheetname', ...}
    footprint: str = ""              # uuid of the footprint that owns it ('' = board level)

    _to = {"outline": poly_to_rings}
    _from = {"outline": rings_to_poly}


@dataclass
class Zone(_Dict):
    """A copper zone (pour). Fills are not read."""
    uuid: str
    name: str
    net: str
    layers: list
    outline: Polygon
    priority: int = 0
    clearance: float = 0.0
    min_thickness: float = 0.0
    connect: str = "thermal"         # thermal | solid | none | thru_hole_only
    teardrop: bool = False
    locked: bool = False
    footprint: str = ""

    _to = {"outline": poly_to_rings}
    _from = {"outline": rings_to_poly}


@dataclass
class Track(_Dict):
    uuid: str
    net: str
    layer: str
    width: float
    start: tuple
    end: tuple
    mid: tuple | None = None         # arcs only
    locked: bool = False

    _from = {"start": _xy, "end": _xy, "mid": _xy}


@dataclass
class Via(_Dict):
    uuid: str
    net: str
    x: float
    y: float
    size: float
    drill: float
    layers: list                     # copper layers spanned, top to bottom
    type: str = "through"            # through | blind | buried | micro
    locked: bool = False


@dataclass
class Stackup(_Dict):
    copper: list                     # copper layer names, top to bottom
    cu_thickness: list               # mm, per copper layer
    gaps: list                       # mm, dielectric between copper[i] and copper[i+1]
    er: list                         # relative permittivity per gap (thickness-weighted)
    thickness: float = 1.6           # board thickness, mm
    source: str = "file"             # 'file' | 'default' (no usable stackup in the board)


@dataclass
class NetClass(_Dict):
    name: str
    clearance: float | None = None
    track_width: float | None = None
    via_diameter: float | None = None
    via_drill: float | None = None
    microvia_diameter: float | None = None
    microvia_drill: float | None = None
    diff_pair_width: float | None = None
    diff_pair_gap: float | None = None
    priority: int | None = None


@dataclass
class Rules(_Dict):
    clearance: float = 0.0           # board minimum clearance
    track_min: float = 0.0
    via_min: float = 0.0             # minimum via diameter
    edge_clearance: float = 0.0      # copper to board edge
    hole_clearance: float = 0.0
    netclasses: dict = field(default_factory=dict)   # name -> NetClass, incl. composites ('HS,Default')
    # extras
    via_drill_min: float = 0.0       # min_through_hole_diameter
    hole_to_hole: float = 0.0
    annular_min: float = 0.0
    microvia_min: float = 0.0
    microvia_drill_min: float = 0.0
    silk_clearance: float = 0.0
    max_error: float = 0.005         # KiCad's arc approximation error
    track_widths: list = field(default_factory=list)   # user presets
    via_sizes: list = field(default_factory=list)      # user presets [(diameter, drill)]
    netclass_patterns: list = field(default_factory=list)  # [(pattern, netclass)]
    custom: list = field(default_factory=list)  # .kicad_dru rules: {'name', 'condition', 'layer', 'constraints'}
    severities: dict = field(default_factory=dict)  # DRC check -> 'error' | 'warning' | 'ignore' (.kicad_pro)
    mask_margin: float = 0.0         # board (setup) pad_to_mask_clearance: pads' default mask expansion
    mask_min_width: float = 0.0      # board (setup) solder_mask_min_width: thinner webs bridge
    mask_to_copper: float = 0.0      # .kicad_pro solder_mask_to_copper_clearance (mask opening to other copper)
    mask_bridges_in_footprints: bool = False  # board (setup) allow_soldermask_bridges_in_footprints
    source: str = ""                 # where the numbers came from

    _to = {"netclasses": lambda v: {k: c.to_dict() for k, c in v.items()}}
    _from = {"netclasses": lambda v: {k: NetClass.from_dict(c) for k, c in v.items()},
             "via_sizes": lambda v: [tuple(x) for x in v], "netclass_patterns": lambda v: [tuple(x) for x in v]}

    def severity(self, check, default="error"):
        """The project's DRC severity for a check key (e.g. 'courtyards_overlap'); `default`
        when the project does not set it."""
        return self.severities.get(check, default)


@dataclass
class Board(_Dict):
    path: str
    version: int
    footprints: list = field(default_factory=list)
    nets: dict = field(default_factory=dict)        # name -> Net
    outline: list = field(default_factory=list)     # Polygons with holes, from Edge.Cuts
    keepouts: list = field(default_factory=list)
    zones: list = field(default_factory=list)
    tracks: list = field(default_factory=list)
    vias: list = field(default_factory=list)
    stackup: Stackup | None = None
    rules: Rules | None = None
    # extras
    generator: str = ""
    layers: dict = field(default_factory=dict)      # layer name -> KiCad type (signal, power, user, ...)
    thickness: float = 1.6
    warnings: list = field(default_factory=list)
    graphics: dict = field(default_factory=dict)    # board-level copper/mask graphics: layer -> [Polygon]
    #                                                 (gr_* shapes with stroke widths; gr_text as its box)

    _to = {"footprints": lambda v: [f.to_dict() for f in v],
           "graphics": lambda v: {k: _polys_to(p) for k, p in v.items()},
           "nets": lambda v: {k: n.to_dict() for k, n in v.items()},
           "outline": _polys_to,
           "keepouts": lambda v: [k.to_dict() for k in v],
           "zones": lambda v: [z.to_dict() for z in v],
           "tracks": lambda v: [t.to_dict() for t in v],
           "vias": lambda v: [t.to_dict() for t in v],
           "stackup": lambda v: v.to_dict() if v is not None else None,
           "rules": lambda v: v.to_dict() if v is not None else None}
    _from = {"footprints": lambda v: [Footprint.from_dict(f) for f in v],
             "graphics": lambda v: {k: _polys_from(p) for k, p in v.items()},
             "nets": lambda v: {k: Net.from_dict(n) for k, n in v.items()},
             "outline": _polys_from,
             "keepouts": lambda v: [Keepout.from_dict(k) for k in v],
             "zones": lambda v: [Zone.from_dict(z) for z in v],
             "tracks": lambda v: [Track.from_dict(t) for t in v],
             "vias": lambda v: [Via.from_dict(t) for t in v],
             "stackup": lambda v: Stackup.from_dict(v) if v is not None else None,
             "rules": lambda v: Rules.from_dict(v) if v is not None else None}

    # convenience lookups (not serialized)
    def footprint(self, ref):
        """The first footprint with this reference (references can repeat; uuids cannot)."""
        for f in self.footprints:
            if f.ref == ref:
                return f
        raise KeyError(ref)

    def by_uuid(self):
        return {f.uuid: f for f in self.footprints}
