# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure-Python reader for .kicad_pcb files: KiCad 10, tolerant of KiCad 6-9 (and 5).

    board = load("board.kicad_pcb")   # also reads board.kicad_pro and board.kicad_dru

No KiCad needed. Zone fills and embedded files are skipped unread (kae.board.sexpr).

Format facts this relies on (checked against pcbnew 10, see kae.board.pcbnew_io.verify):
- Footprint children are stored in the footprint's placed frame: board =
  (x, y) + R(rot) (u, v); for a back-side footprint (u, v) is already mirrored, so the
  library frame is (u, -v) with layers flipped.
- A pad's `(at u v a)` angle is absolute (footprint angle included).
- Zones inside footprints are stored in board coordinates.
- Boards stamped above 20241229 (KiCad 10) name nets in place, `(net "GND")`, and have
  no net table; older boards use `(net 3 "GND")` in pads and `(net 3)` elsewhere.
- Locks: `(locked yes)` (KiCad 9+) or a bare `locked` atom (KiCad 6-8).

`on_board`: a footprint is on the board when its extent (courtyard, else body, else
pads) touches the region inside the board-level Edge.Cuts outline (or, without a closed
outline, its bounding box). kaebench place tasks stage unplaced parts 10 mm right of the
board's bounding box, so those load with on_board=False. Board.outline adds the Edge.Cuts
graphics of on-board footprints (as pcbnew does); off-board footprints keep theirs in
`Footprint.edge_cuts`.
"""
import json
import math
import re
import uuid as _uuid
from pathlib import Path

from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union

from . import geom, sexpr
from .model import Board, Footprint, Keepout, Net, NetClass, Pad, Rules, Stackup, Track, Via, Zone
from .sexpr import first, flag, kids, value
from .transform import courtyard, flip_layer, fp_pads_xy, norm_deg, rotate, transform_coords

NAMED_NETS_AFTER = 20241229   # KiCad 10 boards (stamp > this) name nets in place
CHAIN_EPS = 0.01              # mm: Edge.Cuts endpoints closer than this are joined
COURTYARD_CHAIN_EPS = 0.02    # mm: the same for courtyards (FOOTPRINT::BuildCourtyardCaches)
FP_SHAPES = ("fp_line", "fp_arc", "fp_circle", "fp_rect", "fp_poly", "fp_curve")
GR_SHAPES = ("gr_line", "gr_arc", "gr_circle", "gr_rect", "gr_poly", "gr_curve")
_NUM = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")


def _shape_layers(g):
    """Layers a graphic shape is on: (layer "X"), or (layers "X" "Y") (KiCad 9+ copper logos
    with their mask opening)."""
    ly = value(g, "layer")
    if ly is not None:
        return [ly]
    ls = first(g, "layers")
    return [x for x in (ls or [])[1:] if type(x) is str]


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _xy(node):
    return float(node[1]), float(node[2])


def _pts(node, tol):
    """Points of a (pts (xy ..) (arc (start) (mid) (end)) ..) list."""
    out = []
    for e in node[1:] if node else ():
        if type(e) is list and e:
            if e[0] == "xy":
                out.append((float(e[1]), float(e[2])))
            elif e[0] == "arc":
                a = geom.arc_points(_xy(first(e, "start")), _xy(first(e, "mid")), _xy(first(e, "end")), tol)
                if out and out[-1] == a[0]:
                    a = a[1:]
                out.extend(a)
    return out


def shape_pieces(node, tol=geom.ARC_TOL):
    """A graphic shape as (open polylines, closed rings), in its stored coordinates."""
    kind = node[0][3:]   # fp_line -> line, gr_arc -> arc
    if kind == "line":
        return [[_xy(first(node, "start")), _xy(first(node, "end"))]], []
    if kind == "arc":
        if first(node, "mid") is not None:
            mid = _xy(first(node, "mid"))
            return [geom.ArcPiece(geom.arc_points(_xy(first(node, "start")), mid, _xy(first(node, "end")), tol),
                                  mid, tol)], []
        ang = first(node, "angle")   # KiCad 5: (start center) (end arc-start) (angle sweep)
        if ang is not None:
            return [geom.arc_center_points(_xy(first(node, "start")), _xy(first(node, "end")),
                                           float(ang[1]), tol)], []
        return [], []
    if kind == "circle":
        c = _xy(first(node, "center"))
        e = _xy(first(node, "end"))
        r = math.hypot(e[0] - c[0], e[1] - c[1])
        return ([], [geom.circle_points(c, r, tol)]) if r > 0 else ([], [])
    if kind == "rect":
        (x1, y1), (x2, y2) = _xy(first(node, "start")), _xy(first(node, "end"))
        if x1 == x2 or y1 == y2:
            return [], []
        return [], [[(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]]
    if kind == "poly":
        p = _pts(first(node, "pts"), tol)
        if len(p) >= 3:
            if p[0] != p[-1]:
                p.append(p[0])
            return [], [p]
        return [], []
    if kind == "curve":
        p = _pts(first(node, "pts"), tol)
        if len(p) == 4:
            return [geom.bezier_points(*p, tol=tol)], []
        return ([p], []) if len(p) >= 2 else ([], [])
    return [], []


def synth_uuid(lib_id, x, y, rot, side, index):
    """Stable key for a footprint without a usable uuid (missing, or repeating an earlier
    footprint's): a hash of lib_id, pose (nm, millidegrees) and file index. pcbnew_bridge
    computes the same key, so write_poses accepts it."""
    xn, yn = int(round(x * 1e6)), int(round(y * 1e6))
    rm = int(round((rot % 360.0) * 1000)) % 360000
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"kae-footprint:{lib_id}:{xn}:{yn}:{rm}:{side}:{index}"))


def _kiid(v):
    """KiCad 5 tstamps (8 hex digits) become KIIDs as pcbnew reads them."""
    if v and len(v) == 8 and re.fullmatch(r"[0-9A-Fa-f]{8}", v):
        return "00000000-0000-0000-0000-0000" + v.lower()
    return v


def _map_pieces(pieces, fn):
    opens, rings = pieces
    return ([pl.mapped(fn) if isinstance(pl, geom.ArcPiece) else [fn(*p) for p in pl] for pl in opens],
            [[fn(*p) for p in r] for r in rings])


GRAPHIC_LAYERS = ("F.Cu", "B.Cu", "F.Mask", "B.Mask")


class _Reader:
    def __init__(self, tree, path, arc_tol):
        self.tree = tree
        self.path = str(path)
        self.tol = arc_tol
        self.warnings = []
        self.version = int(_f(value(tree, "version"), 0))
        self.named_nets = self.version > NAMED_NETS_AFTER
        self.netname = {}
        for n in kids(tree, "net"):
            if len(n) >= 3:
                self.netname[n[1]] = n[2]
        self._layers()
        self.stackup = self._stackup()
        self.ncu = len(self.cu)

    # ------------------------------------------------------------------ layers, stackup
    def _layers(self):
        self.layer_types = {}
        lay = first(self.tree, "layers")
        for e in (lay[1:] if lay else []):
            if type(e) is list and len(e) >= 3:
                self.layer_types[e[1]] = e[2]
        names = [n for n in self.layer_types if n.endswith(".Cu")]
        if not names:
            names = ["F.Cu", "B.Cu"]
            self.warnings.append("no copper layers in the layer table; assuming F.Cu, B.Cu")

        def order(nm):
            return -1 if nm == "F.Cu" else 10**6 if nm == "B.Cu" else int(re.sub(r"\D", "", nm) or 0)
        self.cu = sorted(names, key=order)
        self.cu_set = set(self.cu)

    def _stackup(self):
        thickness = _f(value(first(self.tree, "general") or [], "thickness"), 1.6)
        su = first(first(self.tree, "setup") or [], "stackup")
        order, tcu, gaps, ers = [], [], [], []
        diel = []   # (thickness, er) since the last copper layer
        if su is not None:
            for e in kids(su, "layer"):
                name = e[1] if len(e) > 1 else ""
                typ = value(e, "type", "")
                groups, cur = [], []
                for c in e[2:]:
                    if c == "addsublayer":
                        groups.append(cur)
                        cur = []
                    elif type(c) is list:
                        cur.append(c)
                groups.append(cur)

                def th(g):
                    t = next((c for c in g if c[0] == "thickness"), None)
                    return _f(t[1]) if t is not None and len(t) > 1 and _NUM.match(t[1]) else 0.0
                if name.endswith(".Cu"):
                    if order:
                        tot = sum(t for t, _ in diel)
                        gaps.append(tot)
                        ers.append(sum(t * x for t, x in diel) / tot if tot > 0 else 4.5)
                    order.append(name)
                    tcu.append(th(groups[0]) or 0.035)
                    diel = []
                elif typ in ("core", "prepreg") or "dielectric" in name:
                    for g in groups:
                        er = next((_f(c[1], 4.5) for c in g if c[0] == "epsilon_r" and len(c) > 1), 4.5)
                        diel.append((th(g), er))
        if order and sorted(order) == sorted(self.cu) and all(g > 0 for g in gaps):
            self.cu = order
            return Stackup(copper=order, cu_thickness=tcu, gaps=gaps, er=ers, thickness=thickness, source="file")
        if su is not None and order:
            self.warnings.append("stackup does not match the copper layers; using KiCad's default stackup")
        # KiCad's default (BOARD_STACKUP::BuildDefaultStackupList): 35 um copper, 10 um mask
        # per side, the rest split evenly between the dielectrics
        n = len(self.cu)
        d = (thickness - 0.035 * n - 0.02) / max(1, n - 1)
        return Stackup(copper=list(self.cu), cu_thickness=[0.035] * n, gaps=[d] * (n - 1), er=[4.5] * (n - 1),
                       thickness=thickness, source="default")

    def expand_layers(self, names):
        out = []
        for nm in names:
            if not isinstance(nm, str):
                continue
            if nm == "*.Cu":
                out += self.cu
            elif nm == "F&B.Cu":
                out += ["F.Cu", "B.Cu"]
            elif nm.startswith("*."):
                out += ["F." + nm[2:], "B." + nm[2:]]
            elif nm.startswith("F&B."):
                out += ["F." + nm[4:], "B." + nm[4:]]
            else:
                out.append(nm)
        seen = set()
        return [x for x in out if not (x in seen or seen.add(x))]

    def span(self, a, b):
        """Copper layers from a to b inclusive, in stackup order."""
        if a not in self.cu_set or b not in self.cu_set:
            return list(self.cu)
        i, j = sorted((self.cu.index(a), self.cu.index(b)))
        return self.cu[i:j + 1]

    def net(self, node):
        n = first(node, "net")
        if n is None or len(n) < 2:
            return ""
        if self.named_nets:
            return n[1]
        if len(n) >= 3:
            return n[2]
        return self.netname.get(n[1], "")

    # ------------------------------------------------------------------ footprints
    def footprint(self, node):
        lib_id = node[1] if len(node) > 1 and type(node[1]) is str else ""
        layer = value(node, "layer", "F.Cu")
        side = "B" if layer == "B.Cu" else "F"
        s = -1.0 if side == "B" else 1.0
        at = first(node, "at")
        fx, fy = (float(at[1]), float(at[2])) if at else (0.0, 0.0)
        frot = float(at[3]) if at is not None and len(at) > 3 else 0.0
        fields = {}
        for p in kids(node, "property"):
            if len(p) > 1 and type(p[1]) is str:
                fields[p[1]] = p[2] if len(p) > 2 and type(p[2]) is str else ""
        for t in kids(node, "fp_text"):
            if len(t) > 2 and t[1] in ("reference", "value"):
                fields.setdefault(t[1].capitalize(), t[2])
        attrs = [a for a in (first(node, "attr") or [])[1:] if type(a) is str]
        uuid = value(node, "uuid") or _kiid(value(node, "tstamp")) or ""
        fp = Footprint(ref=fields.get("Reference", ""), value=fields.get("Value", ""), lib_id=lib_id,
                       uuid=uuid, x=fx, y=fy, rot=norm_deg(frot), side=side,
                       locked=flag(node, "locked"), attrs=attrs, fields=fields,
                       path=value(node, "path", "") or "", sheet=value(node, "sheetname", "") or "")
        if flag(node, "dnp") and "dnp" not in fp.attrs:
            fp.attrs.append("dnp")
        cr, sr = rotate(1.0, 0.0, frot)   # (cos, -sin)
        c, sn = cr, -sr
        fp_clear = _f(value(node, "clearance"), 0.0)
        fp_mask = _f(value(node, "solder_mask_margin"), None)

        for pd in kids(node, "pad"):
            fp.pads.append(self.pad(pd, fx, fy, frot, c, sn, s, fp_clear))
            pm = _f(value(pd, "solder_mask_margin"), None)
            fp.pads[-1].mask_margin = pm if pm is not None else fp_mask

        # graphics in the library frame: (u, v) stored -> (u, s*v), layers flipped on the back
        by_layer = {}
        for g in node:
            if type(g) is not list or not g or g[0] not in FP_SHAPES:
                continue
            # one layer, or several: KiCad 9+ writes a copper logo as (layers "F.Cu" "F.Mask")
            lys = _shape_layers(g)
            for ly in lys:
                if s < 0:
                    ly = flip_layer(ly, self.ncu)
                by_layer.setdefault(ly, []).append(g)
        if s < 0:
            def lib(u, v):
                return (u, -v)
        else:
            lib = None

        def pieces_on(ly):
            opens, rings = [], []
            for g in by_layer.get(ly, ()):
                try:
                    o, r = shape_pieces(g, self.tol)
                except (TypeError, ValueError, IndexError):
                    fp.flags.append(f"bad_graphic:{g[0]}")
                    continue
                opens += o
                rings += r
            if lib is not None:
                opens, rings = _map_pieces((opens, rings), lib)
            return opens, rings

        for ly, attr in (("F.CrtYd", "courtyard"), ("B.CrtYd", "courtyard_back")):
            if ly in by_layer:
                polys, info = geom.polygons(*pieces_on(ly), eps=COURTYARD_CHAIN_EPS)
                setattr(fp, attr, polys)
                if info["open_ends"] or not polys:
                    fp.flags.append(f"courtyard_malformed:{ly}")
                if info["overlap"]:
                    fp.flags.append(f"courtyard_overlap:{ly}")
                if info["gap"] > 1e-6:
                    fp.flags.append(f"courtyard_gap:{ly}")
                if info["degenerate"]:
                    fp.flags.append(f"courtyard_degenerate:{ly}")
        if "Edge.Cuts" in by_layer:
            opens, rings = pieces_on("Edge.Cuts")
            fp.edge_cuts = [LineString(p) for p in opens + rings if len(p) >= 2]
        fp.graphics = self._graphics(fp, by_layer, lib)
        if not fp.courtyard:
            fp.body = self._body(fp, pieces_on, by_layer)
        for z in kids(node, "zone"):
            self.zone(z, fp.uuid)
        return fp

    def pad(self, pd, fx, fy, frot, c, sn, s, fp_clear=0.0):
        number = pd[1] if len(pd) > 1 and type(pd[1]) is str else ""
        kind = pd[2] if len(pd) > 2 and type(pd[2]) is str else "smd"
        shape = pd[3] if len(pd) > 3 and type(pd[3]) is str else "rect"
        at = first(pd, "at")
        u, v = float(at[1]), float(at[2])
        arot = float(at[3]) if len(at) > 3 else 0.0
        size = first(pd, "size")
        sx = float(size[1]) if size else 0.0
        sy = float(size[2]) if size is not None and len(size) > 2 else sx
        drill, slot, offset = 0.0, None, (0.0, 0.0)
        dr = first(pd, "drill")
        if dr is not None:
            nums = [float(t) for t in dr[1:] if type(t) is str and _NUM.match(t)]
            if "oval" in dr[1:] and len(nums) >= 2:
                slot = (nums[0], nums[1])
                drill = min(nums[0], nums[1])
            elif nums:
                drill = nums[0]
            off = first(dr, "offset")
            if off is not None:
                offset = (float(off[1]), s * float(off[2]))
        # absolute position: KiCad's SetFPRelativePosition = pos + RotatePoint(local, angle)
        px = fx + u * c + v * sn
        py = fy - u * sn + v * c
        layers = self.expand_layers((first(pd, "layers") or ["layers"])[1:])
        return Pad(number=number, net=self.net(pd), kind=kind, shape=shape, size=(sx, sy),
                   lx=u, ly=s * v, lrot=norm_deg(s * (arot - frot)), x=px, y=py, layers=layers,
                   drill=drill, pinfunction=value(pd, "pinfunction", "") or "",
                   pintype=value(pd, "pintype", "") or "",
                   uuid=value(pd, "uuid") or value(pd, "tstamp") or "", slot=slot,
                   rratio=_f(value(pd, "roundrect_rratio"), 0.0), offset=offset,
                   clearance=_f(value(pd, "clearance"), 0.0) or fp_clear)

    def _graphics(self, fp, by_layer, lib):
        """Copper and mask graphics of a footprint (logos, mask apertures, copper shapes) as
        polygons per library layer, with stroke widths: lines and arcs buffered by half their
        width, closed shapes filled when KiCad fills them (fp_poly by default), else stroked."""
        out = {}
        for ly in GRAPHIC_LAYERS:
            shapes = []
            for g in by_layer.get(ly, ()):
                try:
                    o, r = shape_pieces(g, self.tol)
                except (TypeError, ValueError, IndexError):
                    fp.flags.append(f"bad_graphic:{g[0]}")
                    continue
                if lib is not None:
                    o, r = _map_pieces((o, r), lib)
                shapes += _stroked(g, o, r)
            polys = _polys(shapes)
            if polys:
                out[ly] = polys
        return out

    def _body(self, fp, pieces_on, by_layer):
        """Fallback extent when there is no courtyard: the box around the closed Fab
        shapes and the pads; without either, around all graphics."""
        xs, ys = [], []
        if "F.Fab" in by_layer:
            polys, _ = geom.polygons(*pieces_on("F.Fab"), eps=COURTYARD_CHAIN_EPS)
            for p in polys:
                b = p.bounds
                xs += [b[0], b[2]]
                ys += [b[1], b[3]]
        for p in fp.pads:
            w, h = p.size
            ox, oy = p.offset
            for du, dv in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
                ru, rv = rotate(du + ox, dv + oy, p.lrot)
                xs.append(p.lx + ru)
                ys.append(p.ly + rv)
        if not xs:
            for ly in by_layer:
                o, r = pieces_on(ly)
                for pl in o + r:
                    xs += [q[0] for q in pl]
                    ys += [q[1] for q in pl]
        if not xs or max(xs) - min(xs) <= 0 or max(ys) - min(ys) <= 0:
            return []
        return [box(min(xs), min(ys), max(xs), max(ys))]

    # ------------------------------------------------------------------ zones
    def zone(self, z, fp_uuid=""):
        lys = []
        for key in ("layer", "layers"):
            e = first(z, key)
            if e is not None:
                lys += self.expand_layers(e[1:])
        cu = [l for l in self.cu if l in lys]   # copper in stackup order, then the rest
        lys = cu + [l for l in lys if l not in self.cu_set]
        rings = []
        for pol in kids(z, "polygon"):
            p = _pts(first(pol, "pts"), self.tol)
            if len(p) >= 3:
                rings.append(p)
        if not rings:
            return
        outline = Polygon(rings[0], rings[1:])
        if not outline.is_valid:
            outline = outline.buffer(0)
            if outline.geom_type != "Polygon":
                outline = max(getattr(outline, "geoms", [Polygon()]), key=lambda g: g.area, default=Polygon())
        uuid = value(z, "uuid") or value(z, "tstamp") or ""
        name = value(z, "name", "") or ""
        ko = first(z, "keepout")
        if ko is not None:
            rules = {c[0]: (len(c) > 1 and c[1] == "not_allowed") for c in ko[1:] if type(c) is list and c}
            pl = first(z, "placement")
            placement = None
            if pl is not None:
                placement = {c[0]: (c[1] if len(c) > 1 else True) for c in pl[1:] if type(c) is list and c}
                if "enabled" in placement:
                    placement["enabled"] = placement["enabled"] in ("yes", True)
            self.keepouts.append(Keepout(
                uuid=uuid, name=name, layers=lys, outline=outline,
                tracks=rules.get("tracks", False), vias=rules.get("vias", False), pads=rules.get("pads", False),
                copperpour=rules.get("copperpour", False), footprints=rules.get("footprints", False),
                placement=placement, footprint=fp_uuid))
            return
        cp = first(z, "connect_pads")
        mode = "thermal"
        if cp is not None:
            atoms = [a for a in cp[1:] if type(a) is str]
            mode = {"yes": "solid", "no": "none", "thru_hole_only": "thru_hole_only"}.get(atoms[0], "thermal") \
                if atoms else "thermal"
        attr = first(z, "attr")
        self.zones.append(Zone(
            uuid=uuid, name=name, net=self.net(z) or (value(z, "net_name", "") or ""), layers=lys,
            outline=outline, priority=int(_f(value(z, "priority"), 0)),
            clearance=_f(value(cp or [], "clearance"), 0.0), min_thickness=_f(value(z, "min_thickness"), 0.0),
            connect=mode, teardrop=attr is not None and first(attr, "teardrop") is not None,
            locked=flag(z, "locked"), footprint=fp_uuid))

    # ------------------------------------------------------------------ routing
    def track(self, node, arc):
        ly = value(node, "layer")
        if ly is None:  # KiCad 9 track with a mask opening: (layers "F.Cu" "F.Mask")
            ly = next((n for n in (first(node, "layers") or [])[1:] if type(n) is str and n.endswith(".Cu")), "")
        mid = first(node, "mid") if arc else None
        return Track(uuid=value(node, "uuid") or value(node, "tstamp") or "", net=self.net(node), layer=ly,
                     width=_f(value(node, "width"), 0.0), start=_xy(first(node, "start")),
                     end=_xy(first(node, "end")), mid=_xy(mid) if mid is not None else None,
                     locked=flag(node, "locked"))

    def via(self, node):
        at = first(node, "at")
        ly = [n for n in (first(node, "layers") or [])[1:] if type(n) is str]
        atoms = [a for a in node[1:] if type(a) is str]
        typ = next((a for a in atoms if a in ("blind", "buried", "micro", "through")), None)
        t = value(node, "type")
        typ = t if t in ("blind", "buried", "micro", "through") else typ
        lys = self.span(ly[0], ly[-1]) if len(ly) >= 2 else list(self.cu)
        if typ is None:
            typ = "through" if lys == self.cu else "blind"
        return Via(uuid=value(node, "uuid") or value(node, "tstamp") or "", net=self.net(node),
                   x=float(at[1]), y=float(at[2]), size=_f(value(node, "size"), 0.0),
                   drill=_f(value(node, "drill"), 0.0), layers=lys, type=typ, locked=flag(node, "locked"))


# ----------------------------------------------------------------------------- rules
def _mm(v):
    """A DRU value ('0.2mm', '10mil', '0.2') in mm, or the raw string."""
    if not isinstance(v, str):
        return v
    m = re.match(r"^([-+]?[\d.]+(?:[eE][-+]?\d+)?)\s*(mm|mil|in|um)?$", v.strip())
    if not m:
        return v
    x = float(m.group(1))
    return x * {None: 1.0, "mm": 1.0, "mil": 0.0254, "in": 25.4, "um": 1e-3}[m.group(2)]


def read_dru(path):
    """Custom rules from a .kicad_dru: [{'name', 'condition', 'layer', 'constraints'}]."""
    text = "\n".join(ln for ln in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
                     if not ln.lstrip().startswith("#"))
    tree = sexpr.parse("(dru " + text + ")")
    out = []
    for r in kids(tree, "rule"):
        cons = []
        for c in kids(r, "constraint"):
            d = {"type": c[1] if len(c) > 1 and type(c[1]) is str else ""}
            for k in ("min", "opt", "max"):
                v = value(c, k)
                if v is not None:
                    d[k] = _mm(v)
            extra = [a for a in c[2:] if type(a) is str]
            if extra:
                d["args"] = extra
            cons.append(d)
        out.append(dict(name=r[1] if len(r) > 1 and type(r[1]) is str else "",
                        condition=value(r, "condition", ""), layer=value(r, "layer", ""), constraints=cons))
    return out


# KiCad 10's BOARD_DESIGN_SETTINGS defaults, used for keys a .kicad_pro leaves out
# (measured: pcbnew on a board without a project file)
RULE_DEFAULTS = dict(min_clearance=0.0, min_track_width=0.2, min_via_diameter=0.5,
                     min_copper_edge_clearance=0.5, min_hole_clearance=0.25, min_through_hole_diameter=0.3,
                     min_hole_to_hole=0.25, min_via_annular_width=0.1, min_microvia_diameter=0.2,
                     min_microvia_drill=0.1, min_silk_clearance=0.0, max_error=0.005)
_RULE_FIELDS = dict(clearance="min_clearance", track_min="min_track_width", via_min="min_via_diameter",
                    edge_clearance="min_copper_edge_clearance", hole_clearance="min_hole_clearance",
                    via_drill_min="min_through_hole_diameter", hole_to_hole="min_hole_to_hole",
                    annular_min="min_via_annular_width", microvia_min="min_microvia_diameter",
                    microvia_drill_min="min_microvia_drill", silk_clearance="min_silk_clearance",
                    max_error="max_error")


def read_rules(pcb_path, tree=None):
    """Rules from the sibling .kicad_pro (KiCad 6+) and .kicad_dru; legacy KiCad 5
    setup and net_class blocks in the board as a fallback; KiCad's defaults otherwise."""
    pcb_path = Path(pcb_path)
    r = Rules()
    for f, key in _RULE_FIELDS.items():
        setattr(r, f, RULE_DEFAULTS[key])
    r._assign = {}
    pro = pcb_path.with_suffix(".kicad_pro")
    d = None
    if pro.exists():
        try:
            d = json.loads(pro.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError):
            d = None
    if d is not None:
        ds = (d.get("board") or {}).get("design_settings") or {}
        rr = ds.get("rules") or {}
        for f, key in _RULE_FIELDS.items():
            if rr.get(key) is not None:
                setattr(r, f, float(rr[key]))
        r.mask_to_copper = float(rr.get("solder_mask_to_copper_clearance") or 0.0)
        r.severities = {str(k): str(v) for k, v in (ds.get("rule_severities") or {}).items()
                        if v in ("error", "warning", "ignore")}
        r.track_widths = [float(w) for w in ds.get("track_widths") or [] if w]
        r.via_sizes = [(float(v.get("diameter", 0)), float(v.get("drill", 0)))
                       for v in ds.get("via_dimensions") or [] if v.get("diameter")]
        ns = d.get("net_settings") or {}
        r._raw_classes = {c.get("name", ""): c for c in ns.get("classes") or []}
        for c in ns.get("classes") or []:
            nc = NetClass(name=c.get("name", ""), clearance=c.get("clearance"), track_width=c.get("track_width"),
                          via_diameter=c.get("via_diameter"), via_drill=c.get("via_drill"),
                          microvia_diameter=c.get("microvia_diameter"), microvia_drill=c.get("microvia_drill"),
                          diff_pair_width=c.get("diff_pair_width"), diff_pair_gap=c.get("diff_pair_gap"),
                          priority=c.get("priority"))
            r.netclasses[nc.name] = nc
        r.netclass_patterns = [(p.get("pattern", ""), p.get("netclass", "")) for p in ns.get("netclass_patterns") or []]
        assign = ns.get("netclass_assignments") or {}
        r._assign = {k: ([v] if isinstance(v, str) else list(v)) for k, v in assign.items()} \
            if isinstance(assign, dict) else {}
        r.source = pro.name
    elif tree is not None:
        _legacy_rules(r, tree)
    if tree is not None:
        st = first(tree, "setup") or []
        r.mask_margin = _f(value(st, "pad_to_mask_clearance"), 0.0) or 0.0
        r.mask_min_width = _f(value(st, "solder_mask_min_width"), 0.0) or 0.0
        r.mask_bridges_in_footprints = value(st, "allow_soldermask_bridges_in_footprints") == "yes"
    if "Default" not in r.netclasses:
        r.netclasses["Default"] = NetClass(name="Default", clearance=0.2, track_width=0.2, via_diameter=0.6,
                                           via_drill=0.3, microvia_diameter=0.3, microvia_drill=0.1,
                                           diff_pair_width=0.2, diff_pair_gap=0.25, priority=2147483647)
    dru = pcb_path.with_suffix(".kicad_dru")
    if dru.exists():
        try:
            r.custom = read_dru(dru)
            r.source = (r.source + " + " if r.source else "") + dru.name
        except (ValueError, OSError) as e:
            r.custom = [dict(name="(unreadable)", condition=str(e), layer="", constraints=[])]
    return r


def _legacy_rules(r, tree):
    """KiCad 5 boards keep rules in (setup) and (net_class) blocks; keys they lack keep
    KiCad's defaults."""
    st = first(tree, "setup") or []
    for f, key in (("track_min", "trace_min"), ("via_min", "via_min_size"), ("via_drill_min", "via_min_drill"),
                   ("edge_clearance", "edge_clearance"), ("microvia_min", "uvia_min_size"),
                   ("microvia_drill_min", "uvia_min_drill")):
        v = value(st, key)
        if v is not None:
            setattr(r, f, _f(v, getattr(r, f)))
    ncs = kids(tree, "net_class")
    if not ncs:
        return
    r.source = "board setup (legacy)"
    for nc in ncs:
        name = nc[1] if len(nc) > 1 else ""
        r.netclasses[name] = NetClass(name=name, clearance=_f(value(nc, "clearance"), None),
                                      track_width=_f(value(nc, "trace_width"), None),
                                      via_diameter=_f(value(nc, "via_dia"), None), via_drill=_f(value(nc, "via_drill"), None),
                                      microvia_diameter=_f(value(nc, "uvia_dia"), None),
                                      microvia_drill=_f(value(nc, "uvia_drill"), None),
                                      diff_pair_width=_f(value(nc, "diff_pair_width"), None),
                                      diff_pair_gap=_f(value(nc, "diff_pair_gap"), None))
        for a in kids(nc, "add_net"):
            r._assign.setdefault(a[1], []).append(name)


def _wildcard_re(p):
    return "".join(".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in p)


# Fields whose absence from every matched class makes KiCad 10 fill them from Default and
# name the effective class "<classes>,Default" (measured with pcbnew, one field at a time;
# diff_pair_via_gap, line_style, colours and tuning_profile do not count)
_NC_REQUIRED = ("clearance", "track_width", "via_diameter", "via_drill", "microvia_diameter",
                "microvia_drill", "diff_pair_width", "diff_pair_gap", "wire_width", "bus_width")


def _nc_match(pat, net):
    """KiCad's netclass pattern match: an anchored regex (EDA_PATTERN_MATCH_REGEX_ANCHORED
    adds '^' and '$' by plain concatenation, so '/SW*|/RST' matches any '/S...'), or an
    anchored wildcard."""
    rx = ("" if pat.startswith("^") else "^") + pat + ("" if pat.endswith("$") else "$")
    try:
        if re.search(rx, net) is not None:
            return True
    except re.error:
        pass
    return re.fullmatch(_wildcard_re(pat), net) is not None


def netclass_of(rules, net):
    """Effective netclass name of a net, as KiCad 10 names it.

    Classes come from explicit assignments and every matching pattern. One class that
    sets all the fields in _NC_REQUIRED keeps its name; otherwise the classes in priority
    order are joined by ',' with 'Default' last when it fills a missing field
    (e.g. 'HS,Default'); no class gives 'Default'."""
    names = list(getattr(rules, "_assign", {}).get(net, []))
    for pat, cls in rules.netclass_patterns:
        if cls not in names and _nc_match(pat, net):
            names.append(cls)
    names = [n for n in dict.fromkeys(names) if n]
    if not names or names == ["Default"]:
        return "Default"

    def prio(n):
        c = rules.netclasses.get(n)
        if n == "Default":
            return 2147483647
        return c.priority if c is not None and c.priority is not None else 2147483646
    names = sorted(names, key=prio)
    if "Default" not in names:
        raws = getattr(rules, "_raw_classes", None)   # None: legacy board classes, complete
        have = set()
        for n in names:
            if raws is None:
                have |= set(_NC_REQUIRED) if n in rules.netclasses else set()
            else:
                have |= {f for f in _NC_REQUIRED if (raws.get(n) or {}).get(f) is not None}
        if not set(_NC_REQUIRED) <= have:
            names.append("Default")
    return ",".join(names)


def _composite(rules, name):
    """A NetClass for a composite name: each value from the first class (in priority
    order) that sets it, as KiCad's effective netclass."""
    parts = [rules.netclasses[n] for n in name.split(",") if n in rules.netclasses]
    nc = NetClass(name=name)
    for f in ("clearance", "track_width", "via_diameter", "via_drill", "microvia_diameter", "microvia_drill",
              "diff_pair_width", "diff_pair_gap", "priority"):
        setattr(nc, f, next((getattr(p, f) for p in parts if getattr(p, f) is not None), None))
    return nc


# ----------------------------------------------------------------------------- load
def _stroked(g, opens, rings):
    """Copper/mask area of a graphic shape: lines and arcs buffered by half the stroke width,
    closed shapes filled when KiCad fills them (polygons by default), else stroked."""
    st = first(g, "stroke")
    w = _f(value(st, "width") if st is not None else value(g, "width"), 0.0)
    fill = value(g, "fill")
    filled = fill in ("solid", "yes") or (fill is None and g[0] in ("fp_poly", "gr_poly"))
    out = []
    for pl in opens:
        if len(pl) >= 2 and w > 0:
            out.append(LineString(list(pl)).buffer(w / 2))
    for ring in rings:
        if filled:
            p = Polygon(ring).buffer(0)
            out.append(p.buffer(w / 2) if w > 0 else p)
        elif w > 0:
            out.append(LineString(ring).buffer(w / 2))
    return out


def _polys(shapes):
    u = unary_union(shapes) if shapes else None
    if u is None or u.is_empty:
        return []
    return [p for p in getattr(u, "geoms", [u]) if p.geom_type == "Polygon" and p.area > 0]


def _text_box(node):
    """A copper/mask text's area, approximated by its box: KiCad's stroke font advances about
    one glyph width per character; the stroke thickness pads every side."""
    txt = node[1] if len(node) > 1 and type(node[1]) is str else ""
    at = first(node, "at")
    if not txt or at is None:
        return None
    x, y = float(at[1]), float(at[2])
    rot = float(at[3]) if len(at) > 3 else 0.0
    eff = first(node, "effects")
    font = first(eff, "font") if eff is not None else None
    size = first(font, "size") if font is not None else None
    h = float(size[1]) if size is not None else 1.0
    wch = float(size[2]) if size is not None and len(size) > 2 else h
    th = _f(value(font, "thickness") if font is not None else None, 0.15 * h)
    lines = txt.replace("\\n", "\n").split("\n")
    w = max(len(s) for s in lines) * wch
    hh = len(lines) * h * 1.6 - 0.6 * h
    just = (first(eff, "justify") or [])[1:] if eff is not None else []
    x0 = 0.0 if "left" in just else (-w if "right" in just else -w / 2)
    y0 = 0.0 if "top" in just else (-hh if "bottom" in just else -hh / 2)
    from shapely import affinity
    b = box(x0 - th / 2, y0 - th / 2, x0 + w + th / 2, y0 + hh + th / 2)
    return affinity.translate(affinity.rotate(b, -rot, origin=(0, 0)), x, y)


def _board_graphics(tree, tol, warnings):
    """Board-level copper and mask graphics (gr_* shapes and gr_text) per layer, board frame."""
    by = {}
    for g in tree:
        if type(g) is not list or not g:
            continue
        for ly in _shape_layers(g):
            if not (ly.endswith(".Cu") or ly.endswith(".Mask")):
                continue
            if g[0] in GR_SHAPES:
                try:
                    o, r = shape_pieces(g, tol)
                except (TypeError, ValueError, IndexError):
                    warnings.append(f"unreadable {ly} {g[0]}")
                    continue
                by.setdefault(ly, []).extend(_stroked(g, o, r))
            elif g[0] == "gr_text":
                b = _text_box(g)
                if b is not None:
                    by.setdefault(ly, []).append(b)
    return {ly: p for ly, p in ((ly, _polys(s)) for ly, s in by.items()) if p}



def _outline_pieces(tree, tol, warnings):
    opens, rings = [], []
    for g in tree:
        if type(g) is not list or not g or g[0] not in GR_SHAPES:
            continue
        if value(g, "layer") != "Edge.Cuts":
            continue
        try:
            o, r = shape_pieces(g, tol)
        except (TypeError, ValueError, IndexError):
            warnings.append(f"unreadable Edge.Cuts {g[0]}")
            continue
        opens += o
        rings += r
    return opens, rings


def _place_edges(fp):
    """A footprint's Edge.Cuts pieces at its pose, as open polylines."""
    out = []
    for ls in fp.edge_cuts:
        xy = transform_coords(list(ls.coords), fp.x, fp.y, fp.rot, fp.side)
        out.append([tuple(p) for p in xy.tolist()])
    return out


def _extent(fp):
    g = courtyard(fp, which="extent")
    if g:
        return unary_union(g)
    xy = fp_pads_xy(fp)
    if len(xy):
        return MultiPoint(xy.tolist())
    return Point(fp.x, fp.y)


def load(path, *, arc_tol=geom.ARC_TOL, rules=True):
    """Read a .kicad_pcb (and its sibling .kicad_pro / .kicad_dru) into a Board."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = sexpr.parse(sexpr.strip_blocks(text))
    if not tree or tree[0] not in ("kicad_pcb",):
        raise ValueError(f"{path}: not a KiCad board")
    rd = _Reader(tree, path, arc_tol)
    rd.keepouts, rd.zones = [], []
    fps = []
    for node in tree:
        if type(node) is list and node and node[0] in ("footprint", "module"):
            fps.append(rd.footprint(node))
    seen = set()
    for i, fp in enumerate(fps):   # the footprint uuid is the part key: make it unique
        if not fp.uuid or fp.uuid in seen:
            fp.flags.append("uuid_synthesized" if not fp.uuid else "uuid_duplicate")
            fp.uuid = synth_uuid(fp.lib_id, fp.x, fp.y, fp.rot, fp.side, i)
        seen.add(fp.uuid)
    for node in tree:
        if type(node) is list and node and node[0] == "zone":
            rd.zone(node)
    tracks = [rd.track(n, False) for n in kids(tree, "segment")] + [rd.track(n, True) for n in kids(tree, "arc")]
    vias = [rd.via(n) for n in kids(tree, "via")]

    # outline: board-level Edge.Cuts decide what is on the board; on-board footprints'
    # Edge.Cuts (cut-outs, card edges) join the outline as pcbnew does
    opens, rings = _outline_pieces(tree, arc_tol, rd.warnings)
    base, info = geom.polygons(opens, rings, eps=CHAIN_EPS) if (opens or rings) else \
        ([], dict(open_ends=0, degenerate=0))
    dangling, degenerate = info["open_ends"], info["degenerate"]
    region = unary_union([Polygon(p.exterior) for p in base]) if base else None
    bbox = None
    if region is None:
        pts = [q for pl in opens + rings for q in pl]
        for fp in fps:
            if fp.locked and fp.edge_cuts:
                pts += [q for pl in _place_edges(fp) for q in pl]
        if pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            bbox = box(min(xs), min(ys), max(xs), max(ys))
    for fp in fps:
        if region is not None:
            fp.on_board = bool(region.intersects(_extent(fp)))
        elif bbox is not None:
            fp.on_board = bool(bbox.intersects(_extent(fp)))
    fp_edges = [pl for fp in fps if fp.on_board and fp.edge_cuts for pl in _place_edges(fp)]
    if fp_edges:
        outline, info = geom.polygons(opens + fp_edges, rings, eps=CHAIN_EPS)
        dangling, degenerate = info["open_ends"], info["degenerate"]
    else:
        outline = base
    if dangling:
        rd.warnings.append(f"Edge.Cuts: {dangling} chains do not close")
    if degenerate:
        rd.warnings.append(f"Edge.Cuts: {degenerate} closed contours without area dropped")
    if not outline:
        rd.warnings.append("no closed Edge.Cuts outline")

    rules_obj = read_rules(path, tree) if rules else Rules()
    nets = {}
    for name in rd.netname.values():
        if name:
            nets.setdefault(name, Net(name=name))
    for fp in fps:
        for p in fp.pads:
            if p.net:
                nets.setdefault(p.net, Net(name=p.net)).pads.append((fp.ref, p.number))
    for item in [*rd.zones, *tracks, *vias]:
        if item.net:
            nets.setdefault(item.net, Net(name=item.net))
    for n in nets.values():
        n.netclass = netclass_of(rules_obj, n.name)
        if n.netclass not in rules_obj.netclasses:
            rules_obj.netclasses[n.netclass] = _composite(rules_obj, n.netclass)
    for tmp in ("_assign", "_raw_classes"):
        if hasattr(rules_obj, tmp):
            delattr(rules_obj, tmp)

    gen = value(tree, "generator", "") or ""
    gv = value(tree, "generator_version")
    return Board(path=str(path), version=rd.version, footprints=fps, nets=nets, outline=outline,
                 keepouts=rd.keepouts, zones=rd.zones, tracks=tracks, vias=vias, stackup=rd.stackup,
                 rules=rules_obj, generator=f"{gen} {gv}".strip() if gv else gen,
                 layers=dict(rd.layer_types), thickness=rd.stackup.thickness, warnings=rd.warnings,
                 graphics=_board_graphics(tree, arc_tol, rd.warnings))
