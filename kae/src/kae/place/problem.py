# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The placement problem: what moves, what is fixed, and the shapes legality is judged on.

    prob = Problem.build(board)            # kae.board.model.Board
    prob.parts[i].rots[k]                  # shapes of movable part i at rotation 90*k degrees

Movable parts are the unlocked footprints with pads or graphics; fixed obstacles are the
locked footprints, rule areas that keep out footprints (or pads), and everything outside the
Edge.Cuts outline. Each part keeps its side (v0). Through-hole and NPTH pads block both
sides.

Shapes, per rotation, as rectangles (x0, y0, x1, y1) in mm relative to the footprint origin
(board frame, y down):
- `own`: the occupancy on the part's side: the bounding box of the courtyard (else the body,
  else the pads), grown to cover every pad inflated by half the copper clearance. Two parts
  whose `own` rectangles are disjoint have disjoint courtyards and pads at least the
  clearance apart.
- `opp`: rectangles on the other side: drilled pads (inflated likewise) and the courtyard the
  footprint draws on the opposite side (`Footprint.courtyard_back`).
- `board`: what must lie inside the outline: the pads' copper inflated by the copper-to-edge
  clearance, plus the courtyard when the part fits on the board with it.
- `pins`: every pad's position.
CP-SAT works on these rectangles at the grid `g` (rounded outward, so grid-legal is legal);
the exact check in kae.place.legalize uses KiCad's polygons.

Grid coordinates: a part's origin is at (ox + X*g, oy + Y*g) for integers X, Y; grid cell
(i, j) covers [ox + i*g, ox + (i+1)*g] x [oy + j*g, oy + (j+1)*g]. A grid rectangle
(a, b, c, d) relative to the origin covers cells X+a .. X+b-1 and Y+c .. Y+d-1.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import box

from kae.board import transform

ROTS = (0.0, 90.0, 180.0, 270.0)
COURTYARD_EXCESS = 0.25   # mm around pads for footprints that draw no courtyard
GRID_LADDER = (0.025, 0.05, 0.1, 0.2, 0.25)
EPS = 1e-6

_GROUND_RE = re.compile(r"^(A|D|P|S|C|PWR|SIG|CHASSIS|EARTH)?(GND|VSS|GROUND|0V)\w*$|^(EARTH|PE|SHIELD)$", re.I)
_POWER_RE = re.compile(
    r"^([+-]?\d+V\d*|[+-]?\d+V\d*\w*|V(CC|DD|BUS|BAT|IN|SYS|CORE|IO|USB|EE|SS|PP|M|AA|CCA|CCIO|DDA|DDIO)\w*|"
    r"\+\w+|PWR\w*|VPWR\w*|BAT\w*|VBAT\w*|[+-]?\d+V\d*_\w+|\w*_(\d+V\d*|VCC|VDD|PWR))$", re.I)


def clean_net(name):
    """Net name without the sheet path, for name heuristics."""
    n = name.rsplit("/", 1)[-1] if name else ""
    return n.replace("{slash}", "/").strip()


def net_class_guess(name, n_pins, n_parts_total):
    """'ground', 'power' or 'signal' from the name and fan-out (fallback without a brief)."""
    n = clean_net(name)
    if _GROUND_RE.match(n):
        return "ground"
    if _POWER_RE.match(n):
        return "power"
    if n_pins >= max(12, 0.4 * n_parts_total):
        return "power"
    return "signal"


# ----------------------------------------------------------------------------- rectangles
def rect_union(rs):
    rs = [r for r in rs if r is not None]
    if not rs:
        return None
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


def rect_grow(r, d):
    return None if r is None else (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def rect_area(r):
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def rot_rect(r, rot, s):
    """A library-frame rectangle at pose rotation `rot` (a multiple of 90 degrees) and side
    sign `s`, as offsets from the origin. Exact: axis-aligned rectangles stay axis-aligned."""
    x0, y0, x1, y1 = r
    px, py = transform.pads_xy(np.array([x0, x1, x1, x0]), np.array([y0, y0, y1, y1]), 0.0, 0.0, rot, s)
    return (float(px.min()), float(py.min()), float(px.max()), float(py.max()))


def to_grid(r, g):
    """mm offsets -> grid rectangle (a, b, c, d), rounded outward."""
    return (math.floor(r[0] / g + EPS), math.ceil(r[2] / g - EPS), math.floor(r[1] / g + EPS),
            math.ceil(r[3] / g - EPS))


def pad_corners(p):
    """(4, 2) library-frame corners of a pad's copper (its rectangle; circles and ovals by
    their bounding rectangle)."""
    w, h = p.size
    ox, oy = p.offset or (0.0, 0.0)
    u = np.array([-w / 2, w / 2, w / 2, -w / 2]) + ox
    v = np.array([-h / 2, -h / 2, h / 2, h / 2]) + oy
    c, s = transform.cos_sin(p.lrot)
    return np.column_stack([p.lx + u * c + v * s, p.ly - u * s + v * c])


def pad_lib_rect(p):
    """Library-frame bounding rectangle of a pad's copper and hole (custom pads: of their
    anchor only; the courtyard covers the primitives, see Problem._part)."""
    c = pad_corners(p)
    r = (float(c[:, 0].min()), float(c[:, 1].min()), float(c[:, 0].max()), float(c[:, 1].max()))
    return rect_union([r, hole_lib_rect(p)])


def hole_lib_rect(p):
    if not p.drill:
        return None
    w, h = p.slot if p.slot else (p.drill, p.drill)
    u = np.array([-w / 2, w / 2, w / 2, -w / 2])
    v = np.array([-h / 2, -h / 2, h / 2, h / 2])
    c, s = transform.cos_sin(p.lrot)
    x = p.lx + u * c + v * s
    y = p.ly - u * s + v * c
    return (float(x.min()), float(y.min()), float(x.max()), float(y.max()))


def polys_lib_rect(polys):
    if not polys:
        return None
    b = shapely.total_bounds(np.asarray(polys, dtype=object))
    if not np.all(np.isfinite(b)):
        return None
    return tuple(float(v) for v in b)


def _cluster_rects(rects, max_n=64):
    """Merge rectangles that touch or overlap into their bounding boxes (rows and columns of
    pads become one rectangle each, the gaps between them stay open), repeated until stable;
    beyond max_n groups, the pair whose union adds the least area merges, repeatedly (many
    groups are first pooled on a coarse grid). Vectorized: a 676-ball BGA takes milliseconds
    (the pairwise Python loop took minutes, 461 s of Problem.build on one board)."""
    rs = [tuple(r) for r in rects if r is not None]
    if len(rs) <= 1:
        return rs
    R = np.array(rs, dtype=float)
    R = _merge_touching(R)
    if len(R) > 4 * max_n:
        # pool on a coarse grid first: k x k cells over the extent
        k = int(math.ceil(math.sqrt(4 * max_n)))
        x0, y0 = R[:, 0].min(), R[:, 1].min()
        w = max(1e-9, R[:, 2].max() - x0)
        h = max(1e-9, R[:, 3].max() - y0)
        cx = np.minimum(k - 1, ((R[:, 0] + R[:, 2]) / 2 - x0) / w * k).astype(int)
        cy = np.minimum(k - 1, ((R[:, 1] + R[:, 3]) / 2 - y0) / h * k).astype(int)
        cell = cx * k + cy
        R = np.array([[R[cell == c, 0].min(), R[cell == c, 1].min(), R[cell == c, 2].max(), R[cell == c, 3].max()]
                      for c in np.unique(cell)])
        R = _merge_touching(R)
    while len(R) > max_n:
        area = (R[:, 2] - R[:, 0]) * (R[:, 3] - R[:, 1])
        ux0 = np.minimum(R[:, None, 0], R[None, :, 0])
        uy0 = np.minimum(R[:, None, 1], R[None, :, 1])
        ux1 = np.maximum(R[:, None, 2], R[None, :, 2])
        uy1 = np.maximum(R[:, None, 3], R[None, :, 3])
        cost = (ux1 - ux0) * (uy1 - uy0) - area[:, None] - area[None, :]
        np.fill_diagonal(cost, np.inf)
        i, j = np.unravel_index(int(np.argmin(cost)), cost.shape)
        u = [ux0[i, j], uy0[i, j], ux1[i, j], uy1[i, j]]
        keep = np.ones(len(R), dtype=bool)
        keep[[i, j]] = False
        R = _merge_touching(np.vstack([R[keep], [u]]))
    return [tuple(float(v) for v in r) for r in R]


def _inside(r, c):
    return c[0] - 1e-9 <= r[0] and c[1] - 1e-9 <= r[1] and r[2] <= c[2] + 1e-9 and r[3] <= c[3] + 1e-9


def _merge_touching(R):
    """Rectangles (n, 4) merged into the bounding boxes of their touching groups, until no two
    groups touch."""
    from scipy.sparse.csgraph import connected_components
    while len(R) > 1:
        t = ((R[:, None, 0] <= R[None, :, 2] + 1e-9) & (R[None, :, 0] <= R[:, None, 2] + 1e-9)
             & (R[:, None, 1] <= R[None, :, 3] + 1e-9) & (R[None, :, 1] <= R[:, None, 3] + 1e-9))
        n, lab = connected_components(t, directed=False)
        if n == len(R):
            break
        out = np.empty((n, 4))
        for c in range(n):
            m = lab == c
            out[c] = (R[m, 0].min(), R[m, 1].min(), R[m, 2].max(), R[m, 3].max())
        R = out
    return R


def edge_cut_polys(fp):
    """Closed regions a footprint's Edge.Cuts graphics cut out (library frame)."""
    if not fp.edge_cuts:
        return []
    polys = list(shapely.polygonize(fp.edge_cuts).geoms)
    return [p for p in polys if p.area > 0]


def edge_cut_lib_rect(fp):
    if not fp.edge_cuts:
        return None
    return polys_lib_rect(list(fp.edge_cuts))


_HEATSINK_MOUNT = re.compile(r"TO-?(220|247|3P|218|264|126|3)\b|Heatsink|heatsink|HeatSink", re.I)


def right_angles_only(fp):
    """Footprints that keep right angles when every other part may turn freely: heatsink-
    mount packages with a tab hole (TO-220, TO-247, TO-3P, ...) and heatsinks themselves."""
    name = f"{fp.lib_id} {getattr(fp, 'value', '')}"
    if not _HEATSINK_MOUNT.search(name):
        return False
    if "heatsink" in name.lower():
        return True
    return any(p.drill and (p.kind == "np_thru_hole" or max(p.size) >= 3.0) for p in fp.pads)


def _turn_tables(angles):
    """turn[k][q]: the rotation q quarter turns from rotation k (k itself when the set has no
    such angle); ring[k]: (previous, next) rotation in angle order."""
    key = {round(a % 360.0, 6): k for k, a in enumerate(angles)}
    turn = []
    for a in angles:
        turn.append([key.get(round((a + 90.0 * q) % 360.0, 6), None) for q in range(4)])
    for k, row in enumerate(turn):
        for q in range(4):
            if row[q] is None:
                row[q] = k
    order = sorted(range(len(angles)), key=lambda k: angles[k] % 360.0)
    ring = [None] * len(angles)
    for t, k in enumerate(order):
        ring[k] = (order[t - 1], order[(t + 1) % len(order)])
    return turn, ring


def _on_far_copper(p, part_side):
    """The pad has copper on the side opposite its footprint's (B.Cu under a front part,
    F.Cu under a back part, *.Cu, F&B.Cu, inner layers count as both)."""
    far = "B.Cu" if part_side == "F" else "F.Cu"
    for ly in p.layers or []:
        if ly == far or ly in ("*.Cu", "F&B.Cu") or (ly.startswith("In") and ly.endswith(".Cu")):
            return True
    return False


def is_drilled(p):
    return p.kind in ("thru_hole", "np_thru_hole") or bool(p.drill)


def fixed_copper(board):
    """Copper graphics at board level (gr_line/arc/circle/rect/poly on F.Cu or B.Cu): fixed
    copper a place task keeps, with its net. [(side, shapely geometry, net)].
    Read from the board file with kae.board's own S-expression parser (the board model does
    not carry copper graphics yet)."""
    from pathlib import Path

    from kae.board import sexpr
    from kae.board.kicad_file import GR_SHAPES, shape_pieces
    path = getattr(board, "path", "")
    if not path or not Path(path).exists():
        return []
    try:
        tree = sexpr.parse(sexpr.strip_blocks(Path(path).read_text(encoding="utf-8", errors="replace")))
    except (ValueError, OSError):
        return []
    out = []
    for node in tree:
        if type(node) is not list or not node or node[0] not in GR_SHAPES:
            continue
        layer = sexpr.value(node, "layer")
        if layer not in ("F.Cu", "B.Cu"):
            continue
        st = sexpr.first(node, "stroke")
        w = sexpr.value(st, "width") if st is not None else sexpr.value(node, "width")
        try:
            w = float(w) if w is not None else 0.0
        except ValueError:
            w = 0.0
        try:
            opens, rings = shape_pieces(node)
        except (TypeError, ValueError, IndexError):
            continue
        fill = sexpr.value(node, "fill")
        geoms = []
        from shapely.geometry import LineString, Polygon
        for pl in opens:
            if len(pl) >= 2:
                geoms.append(LineString(pl).buffer(max(w, 1e-3) / 2))
        for r in rings:
            if len(r) >= 4:
                geoms.append(Polygon(r).buffer(w / 2) if fill in ("yes", "solid") else
                             LineString(r).buffer(max(w, 1e-3) / 2))
        net = ""
        nn = sexpr.first(node, "net")
        if nn is not None and len(nn) > 1:
            net = nn[-1] if len(nn) > 2 else nn[1]
        for gm in geoms:
            if not gm.is_empty:
                out.append((0 if layer == "F.Cu" else 1, gm, net))
    return out


def geom_cover_rects(geom, tol):
    """Small rectangles covering a geometry: its outline simplified at `tol` and cut into
    one bounding box per piece of a grid of cells (keeps thin arcs from blocking the area
    they enclose)."""
    x0, y0, x1, y1 = geom.bounds
    if geom.area >= 0.9 * max(1e-12, (x1 - x0) * (y1 - y0)):
        return [(x0, y0, x1, y1)]
    step = max(tol * 10, max(x1 - x0, y1 - y0) / 24)
    out = []
    nx = max(1, int(math.ceil((x1 - x0) / step)))
    ny = max(1, int(math.ceil((y1 - y0) / step)))
    for i in range(nx):
        for j in range(ny):
            cell = box(x0 + i * step, y0 + j * step, min(x1, x0 + (i + 1) * step), min(y1, y0 + (j + 1) * step))
            piece = geom.intersection(cell)
            if not piece.is_empty and piece.area > 0:
                out.append(piece.bounds)
    return out


# ----------------------------------------------------------------------------- types
@dataclass
class Rot:
    """One rotation of a part: rectangles in mm (offsets from the origin) and on the grid."""
    rot: float
    own: tuple
    opp: tuple            # tuple of rects on the other side
    board: tuple          # must lie inside the outline
    crt: tuple            # courtyard (or body) only, for reporting
    pins: np.ndarray      # (n_pads, 2) mm offsets
    g_own: tuple = None
    g_opp: tuple = ()
    g_board: tuple = None
    own_rects: tuple = ()        # occupancy on the part's side: courtyard cover, pad groups (own = their box)
    g_own_rects: tuple = ()
    g_own_rects_exact: tuple = ()
    g_own_exact: tuple = None   # g_own without the routing margin
    g_board_exact: tuple = None  # g_board without the routing margin
    boards: tuple = ()           # rectangles that must each lie inside (one, or pad groups)
    g_boards: tuple = ()
    g_boards_exact: tuple = ()


@dataclass
class Part:
    i: int
    uuid: str
    ref: str
    value: str
    lib_id: str
    side: str
    s: float              # +1 front, -1 back
    movable: bool
    fp: object            # kae.board.model.Footprint
    x0: float             # input pose
    y0: float
    rot0: float
    tht: bool             # has drilled pads (blocks both sides)
    decor: bool           # no pads (logo, graphic): never blocks routing
    has_courtyard: bool
    rots: list = field(default_factory=list)   # Rot per allowed rotation (fixed parts: one)
    pad_net: np.ndarray = None                   # net index per pad, -1 = none
    fits: bool = True     # the courtyard fits on the board (else only pads must be inside)
    shape_key: tuple = ()  # parts with equal keys are interchangeable geometrically
    kind: str = ""        # the brief's part kind (connector, capacitor, ic, ...)

    @property
    def area(self):
        return rect_area(self.rots[0].own)


@dataclass
class Net:
    i: int
    name: str
    kind: str             # ground | power | signal (or a brief role)
    weight: float
    pins: list            # [(part index, pad index)]


@dataclass
class Obstacle:
    """A fixed rectangle on one side (0 = front, 1 = back), in mm and on the grid."""
    side: int
    rect: tuple
    g: tuple              # absolute grid rect (i0, i1, j0, j1): cells i0..i1-1, j0..j1-1
    why: str


class Problem:
    """Everything the seed, annealer and legalizer need, derived once from a Board."""

    def __init__(self):
        self.board = None
        self.parts = []
        self.nets = []
        self.obstacles = []
        self.g = 0.1
        self.ox = self.oy = 0.0
        self.ncx = self.ncy = 0
        self.outline = None
        self.inside = None          # bool (ncx, ncy): cell fully inside the outline
        self.sat_out = None         # summed-area table of cells NOT inside, shape (ncx+1, ncy+1)
        self.cover = []             # grid rects (i0, i1, j0, j1) inside the outline, overlapping
        self.held = set()
        self.clearance = 0.0
        self.edge_clearance = 0.0
        self.notes = []

    # ------------------------------------------------------------------ construction
    @classmethod
    def build(cls, board, grid=None, net_kinds=None, rotations=ROTS, held=(), angle_step=None):
        """net_kinds: optional {net name: 'ground'|'power'|'signal'|role} (from the brief).
        held: footprint uuids kept where they are and left out of the nets (e.g. staged parts
        that carry Edge.Cuts, whose place on the board the task does not tell).
        angle_step: also offer every multiple of this many degrees to parts that may turn
        freely (not heatsink-mount packages); the right angles stay the first rotations."""
        P = cls()
        P.board = board
        P.held = set(held)
        P.angle_step = angle_step
        P._rules(board)
        P._severities(board)
        P._domain(board, grid)
        name_to_net = P._nets(board, net_kinds)
        for i, fp in enumerate(board.footprints):
            P.parts.append(P._part(i, fp, name_to_net, rotations))
        P._fit_check()
        P._grid_shapes()
        P._fixed_obstacles(board)
        P.mov = [p.i for p in P.parts if p.movable]
        return P

    def _severities(self, board):
        """DRC rule severities of the board's project (kae.board Rules.severities, from the
        .kicad_pro): a check the project sets to 'warning' or 'ignore' is no error, so legality
        does not need it (e.g. courtyards_overlap: ignore lets courtyards overlap and only
        copper counts)."""
        r = getattr(board, "rules", None)
        self.severity = dict(getattr(r, "severities", None) or {}) if r is not None else {}

    def is_error(self, check):
        """The project reports `check` as an error (KiCad's default when the project is silent)."""
        return (getattr(self, "severity", {}) or {}).get(check, "error") == "error"

    def _rules(self, board):
        r = board.rules
        clr = [r.clearance or 0.0] if r else [0.0]
        if r:
            for nc in r.netclasses.values():
                if nc.clearance:
                    clr.append(float(nc.clearance))
        self.clr_min = min([c for c in clr if c > 0] or [0.2])
        self.clr_max = max(clr + [0.0])
        self.clearance = self.clr_max
        e = (r.edge_clearance if r else 0.0) or 0.0
        if r:
            for rule in r.custom or []:
                for c in rule.get("constraints", []):
                    if c.get("type") == "edge_clearance" and isinstance(c.get("min"), (int, float)):
                        e = max(e, float(c["min"]))
        self.edge_clearance = e
        self.max_error = (r.max_error if r else 0.005) or 0.005
        self.netclass_clr = {}
        if r:
            for name, nc in r.netclasses.items():
                self.netclass_clr[name] = float(nc.clearance) if nc.clearance else self.clr_min

    def _domain(self, board, grid):
        polys = [p for p in board.outline if p.area > 0]
        if polys:
            outline = shapely.union_all(polys)
        else:
            # no closed outline: the box around locked parts, else around everything
            fps = [f for f in board.footprints if f.locked] or board.footprints
            pts = np.array([[f.x, f.y] for f in fps]) if fps else np.zeros((1, 2))
            area = sum(rect_area(polys_lib_rect(f.courtyard or f.body) or (0, 0, 1, 1)) for f in board.footprints)
            half = max(10.0, math.sqrt(max(area, 1.0) * 2.5) / 2)
            c = pts.mean(axis=0)
            outline = box(c[0] - half, c[1] - half, c[0] + half, c[1] + half)
            self.notes.append("no closed Edge.Cuts outline: placing in a box")
        self.outline = outline
        x0, y0, x1, y1 = outline.bounds
        span = max(x1 - x0, y1 - y0)
        if grid is None:
            grid = next((g for g in GRID_LADDER if span / g <= 1000), GRID_LADDER[-1])
        self.g = g = float(grid)
        self.ox, self.oy = x0, y0
        self.ncx = max(1, int(math.ceil((x1 - x0) / g - EPS)))
        self.ncy = max(1, int(math.ceil((y1 - y0) / g - EPS)))
        # a cell is inside when its whole square is: test centres against the outline
        # shrunk by the half-diagonal
        shrunk = outline.buffer(-g * 0.70711, join_style="mitre")
        cx = x0 + (np.arange(self.ncx) + 0.5) * g
        cy = y0 + (np.arange(self.ncy) + 0.5) * g
        XX, YY = np.meshgrid(cx, cy, indexing="ij")
        if shrunk.is_empty:
            inside = np.zeros((self.ncx, self.ncy), dtype=bool)
        else:
            inside = shapely.contains_xy(shrunk, XX, YY)
        self.inside = inside
        self.sat_out = sat(~inside)
        self.cover = cover_rects(inside)
        self.rect_board = abs(outline.area - (x1 - x0) * (y1 - y0)) < 1e-6 * max(1.0, outline.area)

    def _nets(self, board, net_kinds):
        pins = {}
        for i, fp in enumerate(board.footprints):
            if fp.uuid in self.held and not fp.on_board:
                continue      # a staged part held off the board: its pins would only mislead
            for k, p in enumerate(fp.pads):
                if p.net:
                    pins.setdefault(p.net, []).append((i, k))
        n_parts = max(1, len(board.footprints))
        name_to_net = {}
        for name in sorted(pins):
            pl = pins[name]
            kind = (net_kinds or {}).get(name) or net_class_guess(name, len(pl), n_parts)
            w = {"ground": 0.1, "power": 0.2}.get(kind, 1.0)
            net = Net(i=len(self.nets), name=name, kind=kind, weight=w, pins=pl)
            name_to_net[name] = net.i
            self.nets.append(net)
        return name_to_net

    def _part(self, i, fp, name_to_net, rotations):
        s = transform.side_sign(fp.side)
        has_cy = bool(fp.courtyard)
        cy = polys_lib_rect(fp.courtyard) or polys_lib_rect(fp.body)
        pads = fp.pads
        pad_rects = [pad_lib_rect(p) for p in pads]
        # pads inflated by the clearance they need from other copper (see module docstring)
        infl = []
        # a footprint without a courtyard gets the courtyard excess IPC-7351 would have drawn
        # (0.25 mm): pads closer than that bridge solder mask and starve routing
        excess = 0.0 if has_cy else COURTYARD_EXCESS
        for p, r in zip(pads, pad_rects):
            c = self.clr_min / 2
            if p.net and self.board.nets.get(p.net) is not None:
                nc = self.board.nets[p.net].netclass or "Default"
                cn = self.netclass_clr.get(nc, self.netclass_clr.get(nc.split(",")[0], self.clr_min))
                c = max(self.clr_min / 2, cn - self.clr_min / 2)
            infl.append(rect_grow(r, max(c, excess)))
        # occupancy pieces: the courtyard (only when the project checks courtyard overlap as an
        # error; a cover of its polygon when it is not a rectangle) or the body of a part that
        # has none, and the pad groups outside it (+ clearance). One box around everything would
        # swallow the space a module leaves between its pin rows (an Arduino footprint on a
        # shield covered 37% of the board) or inside an L-shaped courtyard.
        cy_pieces = []
        if cy is not None and self.is_error("courtyards_overlap"):
            if has_cy:
                u = shapely.union_all(fp.courtyard)
                bx0, by0, bx1, by1 = u.bounds
                # at most 4 strips (they touch, so they are not clustered back into one box)
                cy_pieces = poly_cover_rects(u, max(1e-3, (bx1 - bx0) / 4.0)) or [cy]
            else:
                cy_pieces = [cy]
        pad_pieces = _cluster_rects(infl, max_n=6)
        own_pieces = cy_pieces + [r for r in pad_pieces if not any(_inside(r, c) for c in cy_pieces)]
        if len(own_pieces) > 8:
            own_pieces = _cluster_rects(own_pieces, max_n=8)
        lib_own = rect_union(own_pieces)
        if lib_own is None:   # no courtyard, body or pads: a point
            lib_own = (-0.05, -0.05, 0.05, 0.05)
            own_pieces = [lib_own]
        drilled = [k for k, p in enumerate(pads) if is_drilled(p)]
        # SMD copper on the other side too (a back-side thermal pad under a front part, pads on
        # *.Cu): other parts' copper on that side keeps clear of it
        far = [k for k, p in enumerate(pads) if not is_drilled(p) and _on_far_copper(p, fp.side)]
        lib_opp = _cluster_rects([rect_union([infl[k], rect_grow(hole_lib_rect(pads[k]), self.clr_min / 2)])
                                  for k in drilled] + [infl[k] for k in far])
        if fp.courtyard_back and self.is_error("courtyards_overlap"):
            lib_opp.append(polys_lib_rect(fp.courtyard_back))
        lib_opp = [r for r in lib_opp if r is not None]
        cut = edge_cut_lib_rect(fp)
        if cut is not None:
            # the footprint cuts the board (a lens hole, a window): nothing on either side may
            # come within the copper-to-edge clearance of the cut, and the cut stays inside the
            # outline (a hole across the edge would turn it into a notch)
            lib_cut = cut
            cut = rect_grow(cut, self.edge_clearance + 0.002)
            lib_own = rect_union([lib_own, cut])
            own_pieces = own_pieces + [cut]
            lib_opp.append(cut)
        else:
            lib_cut = None
        # every pad, bare NPTH holes included, keeps the copper-to-edge clearance (conservative:
        # whether KiCad exempts bare holes is unverified, and agreement with KiCad comes first)
        cu_rects = list(pad_rects)
        holes = []
        copper = rect_union(cu_rects)
        if any(p.shape == "custom" for p in pads) and cy is not None:
            copper = rect_union([copper, cy])   # primitives are not in the model: assume the courtyard
        lib_edge = rect_union([rect_grow(copper, self.edge_clearance + 0.002) if copper is not None else None,
                               rect_union(holes)])
        lib_board_full = rect_union([lib_edge, cy if cy is not None else lib_own, lib_cut])
        lib_board_pads = rect_union([lib_edge if lib_edge is not None else lib_own, lib_cut])
        # pad groups that must each lie inside (a module may bridge a cut-out with its pad rows)
        groups = _cluster_rects([rect_grow(r, self.edge_clearance + 0.002) for r in cu_rects] +
                                [h for h in holes if h is not None], max_n=4)
        if lib_cut is not None:
            groups.append(lib_cut)
        lib_board_groups = groups or [lib_board_pads]
        pad_net = np.array([name_to_net.get(p.net, -1) if p.net else -1 for p in pads], dtype=int)
        local = transform.local_pads(fp)
        movable = not fp.locked and fp.uuid not in self.held
        part = Part(i=i, uuid=fp.uuid, ref=fp.ref, value=fp.value, lib_id=fp.lib_id, side=fp.side, s=s,
                    movable=movable, fp=fp, x0=fp.x, y0=fp.y, rot0=fp.rot, tht=bool(drilled),
                    decor=not pads, has_courtyard=has_cy, pad_net=pad_net)
        own_parts = ([cy] if (cy is not None and self.is_error("courtyards_overlap")) else []) + infl + \
            ([cut] if cut is not None else [])
        part._lib = dict(own=lib_own, opp=lib_opp, board_full=lib_board_full, board_pads=lib_board_pads,
                         board_groups=lib_board_groups, crt=cy if cy is not None else lib_own,
                         own_pads=rect_union(infl + ([cut] if cut is not None else [])) or lib_own,
                         own_parts=[r for r in own_parts if r is not None] or [lib_own],
                         own_pieces=own_pieces,
                         own_pads_pieces=(pad_pieces + ([cut] if cut is not None else [])) or [lib_own])
        rots = list(rotations) if movable else [fp.rot]
        part.n_ortho = len(rots)
        if movable and self.angle_step and not right_angles_only(fp):
            step = float(self.angle_step)
            rots += [a for a in np.arange(0.0, 360.0, step).tolist() if a % 90.0 > 1e-9]
        for rot in rots:
            part.rots.append(self._rot(part, rot, local, lib_board_full))
        part.turn, part.ring = _turn_tables([r.rot for r in part.rots])
        part.shape_key = (fp.lib_id, fp.side, tuple(np.round(local.ravel(), 4)),
                          tuple(round(v, 4) for v in lib_own))
        return part

    def _rot(self, part, rot, local, lib_board):
        s = part.s
        L = part._lib
        if rot % 90.0 == 0.0:
            rr = lambda r: rot_rect(r, rot, s)  # noqa: E731
            own_rects = tuple(rr(r) for r in L.get("own_pieces") or [L["own"]])
            own = rr(L["own"])
        else:
            # an odd angle: bounding boxes of each rotated piece (courtyard, every pad), so the
            # grid stays conservative (grid-legal implies legal at the actual angle) without
            # boxing the box of the whole footprint
            rr = lambda r: rot_rect_any(r, rot, s)  # noqa: E731
            own = rect_union([rr(r) for r in L.get("own_parts") or [L["own"]]])
            own_rects = tuple(rr(r) for r in L.get("own_pieces") or [L["own"]])
            own = rect_union([own] + list(own_rects))
        if len(local):
            px, py = transform.pads_xy(local[:, 0], local[:, 1], 0.0, 0.0, rot, s)
            pins = np.column_stack([px, py])
        else:
            pins = np.zeros((0, 2))
        board = rr(lib_board)
        return Rot(rot=float(rot), own=own, opp=tuple(rr(r) for r in L["opp"]), board=board,
                   crt=rr(L["crt"]), pins=pins, boards=(board,), own_rects=own_rects)

    def _fit_check(self):
        """A part whose courtyard cannot fit inside the outline in any rotation only keeps
        its pads inside (e.g. a sensor overhanging the board edge)."""
        for p in self.parts:
            if not p.movable:
                continue
            ok = False
            for r in p.rots:
                if self._fits_somewhere(to_grid(r.board, self.g)):
                    ok = True
                    break
            if not ok:
                p.fits = False
                for r in p.rots:
                    rr = rot_rect if r.rot % 90.0 == 0.0 else rot_rect_any
                    r.board = rr(p._lib["board_pads"], r.rot, p.s)
                    r.boards = tuple(rr(gr, r.rot, p.s) for gr in p._lib["board_groups"])
                self.notes.append(f"{p.ref}: courtyard does not fit on the board; only its pads are kept inside")

    def _fits_somewhere(self, gr):
        a, b, c, d = gr
        w, h = b - a, d - c
        return any(i1 - i0 >= w and j1 - j0 >= h for (i0, i1, j0, j1) in self.cover)

    def _grid_shapes(self):
        g = self.g
        for p in self.parts:
            for r in p.rots:
                r.g_own = to_grid(r.own, g)
                r.g_own_rects = tuple(to_grid(o, g) for o in (r.own_rects or (r.own,)))
                r.g_own_rects_exact = r.g_own_rects
                r.g_opp = tuple(to_grid(o, g) for o in r.opp)
                r.g_board = to_grid(r.board, g)
                r.g_boards = tuple(to_grid(b, g) for b in r.boards)
                r.g_own_exact = r.g_own
                r.g_board_exact = r.g_board
                r.g_boards_exact = r.g_boards
        self.margin = 0.0

    def relax_bodies(self):
        """Footprints without a courtyard keep only their pads (plus the courtyard excess) as
        occupancy: KiCad does not check bodies, and on a full board a body standing above
        others (a display on headers) must be allowed to. Returns the parts relaxed."""
        out = []
        g = self.g
        fixed_relaxed = False
        for p in self.parts:
            if p.has_courtyard or p.decor or getattr(p, "relaxed", False):
                continue
            if not p.movable:
                fixed_relaxed = True     # a locked module's body (an Arduino under its shield)
            p.relaxed = True
            for r in p.rots:
                rr = rot_rect if r.rot % 90.0 == 0.0 else rot_rect_any
                r.own_rects = tuple(rr(x, r.rot, p.s) for x in p._lib["own_pads_pieces"])
                r.own = rect_union(list(r.own_rects))
                r.g_own_exact = to_grid(r.own, g)
                r.g_own_rects_exact = tuple(to_grid(x, g) for x in r.own_rects)
            out.append(p.ref)
        if out:
            if fixed_relaxed:
                self.obstacles = []
                self._fixed_obstacles(self.board)
            self.set_margin(self.margin)
            self.notes.append(f"bodies relaxed to pads: {', '.join(out[:10])}")
        return out

    def bump(self, i, mm):
        """Grow part i's occupancy rectangle by `mm` more on every side, for good (a KiCad
        violation the rectangles missed becomes a constraint the model keeps)."""
        if not hasattr(self, "extra_cells"):
            self.extra_cells = {}
        self.extra_cells[i] = self.extra_cells.get(i, 0) + max(1, int(math.ceil(mm / self.g - EPS)))
        self.set_margin(self.margin)

    def utilization(self):
        """Per side: occupancy-rectangle area of all parts on (or drilling through) the side
        over the board area."""
        area = max(1e-9, float(self.outline.area))
        u = [0.0, 0.0]
        for p in self.parts:
            r = p.rots[0]
            si = 0 if p.s > 0 else 1
            u[si] += sum(rect_area(x) for x in (r.own_rects or (r.own,)))
            for o in r.opp:
                u[1 - si] += rect_area(o)
        return [x / area for x in u]

    def auto_margin(self):
        """Routing room between movable parts, from how full the board is: about 1 mm on an
        empty board, nothing above 70% utilization (part rectangles are mutually exclusive
        inflated by half the margin each)."""
        util = max(self.utilization())
        return float(min(1.0, max(0.0, 2.0 * (0.7 - util))))

    def set_margin(self, m):
        """Grow every movable part's occupancy and board rectangles by m/2 on each side (0
        restores the exact rectangles): routing room between parts and towards the board edge.
        Parts with many pins get more (escape space: m * min(0.8, 0.1 sqrt(pins)) extra, so a
        32-pin QFN on an empty board keeps about 0.6 mm more around it than a resistor).
        Legality does not need any of it; routability does."""
        g = self.g
        self.margin = float(m)
        extra = getattr(self, "extra_cells", {})
        # room for a track between a pad and the edge (beyond the copper-to-edge clearance), as
        # far as the board's slack allows: Freerouting narrows tracks it squeezes in there
        r = self.board.rules
        track = (r.track_min if r and r.track_min else 0.2)
        edge_room = min(1.0, m / 0.5) * (track + self.clr_min) if m > 0 else 0.0
        for p in self.parts:
            if not p.movable:
                continue
            esc = m * min(0.8, 0.1 * math.sqrt(len(p.fp.pads))) if m > 0 else 0.0
            k = (int(round((m + esc) / 2 / g)) if m > 0 else 0) + extra.get(p.i, 0)
            kb = int(round((m / 2 + edge_room) / g)) if m > 0 else 0
            for r in p.rots:
                a, b, c, d = r.g_own_exact
                r.g_own = (a - k, b + k, c - k, d + k)
                r.g_own_rects = tuple((a - k, b + k, c - k, d + k) for (a, b, c, d) in r.g_own_rects_exact)
                a, b, c, d = r.g_board_exact          # room to route between parts and the edge
                r.g_board = (a - kb, b + kb, c - kb, d + kb)
                r.g_boards = tuple((a - kb, b + kb, c - kb, d + kb) for (a, b, c, d) in r.g_boards_exact)
        return int(round(m / 2 / g)) if m > 0 else 0

    def _fixed_obstacles(self, board):
        g = self.g
        for p in self.parts:
            if p.movable or (p.uuid in self.held and not p.fp.on_board):
                continue
            r = p.rots[0]
            si = 0 if p.s > 0 else 1
            for piece in (r.own_rects or (r.own,)):
                self._add_obstacle(si, shift(piece, p.x0, p.y0), f"locked {p.ref}")
            for o in r.opp:
                self._add_obstacle(1 - si, shift(o, p.x0, p.y0), f"locked {p.ref} (through)")
        self.fixed_copper = fixed_copper(board)
        for side, gm, net in self.fixed_copper:
            for r in geom_cover_rects(gm.buffer(self.clr_max / 2), g):
                self._add_obstacle(side, r, f"fixed copper {net or '(no net)'}")
        for ko in board.keepouts:
            if not (ko.footprints or ko.pads):
                continue
            sides = set()
            for ly in ko.layers or []:
                if ly in ("F.Cu", "F.Courtyard", "F.CrtYd") or ly.startswith("F."):
                    sides.add(0)
                elif ly in ("B.Cu",) or ly.startswith("B."):
                    sides.add(1)
                elif ly in ("*.Cu", "F&B.Cu") or ly.startswith("In"):
                    sides.update((0, 1))
            if not sides:
                sides = {0, 1}
            for r in poly_cover_rects(ko.outline, g * 2):
                for si in sides:
                    self._add_obstacle(si, r, f"keepout {ko.name or ko.uuid[:8]}")
        _ = g

    def _add_obstacle(self, side, rect, why):
        g = self.g
        gi = (math.floor((rect[0] - self.ox) / g + EPS), math.ceil((rect[2] - self.ox) / g - EPS),
              math.floor((rect[1] - self.oy) / g + EPS), math.ceil((rect[3] - self.oy) / g - EPS))
        self.obstacles.append(Obstacle(side=side, rect=rect, g=gi, why=why))

    # ------------------------------------------------------------------ helpers
    def xy(self, X, Y):
        """Grid origin -> board mm."""
        return self.ox + X * self.g, self.oy + Y * self.g

    def grid_of(self, x, y):
        return int(round((x - self.ox) / self.g)), int(round((y - self.oy) / self.g))

    def side_index(self, i):
        return 0 if self.parts[i].s > 0 else 1

    def outside_cells(self, X, Y, gr):
        """Cells of grid rect gr (relative to origin X, Y) not inside the outline."""
        a, b, c, d = gr
        return sat_query(self.sat_out, X + a, X + b, Y + c, Y + d, self.ncx, self.ncy)

    def outside_cells_all(self, X, Y, grs):
        return sum(self.outside_cells(X, Y, gr) for gr in grs)

    def summary(self):
        mov = [p for p in self.parts if p.movable]
        return dict(parts=len(self.parts), movable=len(mov), fixed=len(self.parts) - len(mov),
                    nets=len(self.nets), grid_mm=self.g, margin_mm=self.margin,
                    utilization=[round(u, 3) for u in self.utilization()], cells=[self.ncx, self.ncy], cover_rects=len(self.cover),
                    rectangular=self.rect_board, obstacles=len(self.obstacles),
                    clearance=self.clearance, edge_clearance=self.edge_clearance,
                    not_fitting=[p.ref for p in mov if not p.fits], notes=self.notes)


def shift(r, x, y):
    return (r[0] + x, r[1] + y, r[2] + x, r[3] + y)


def rot_rect_any(r, rot, s):
    x0, y0, x1, y1 = r
    px, py = transform.pads_xy(np.array([x0, x1, x1, x0]), np.array([y0, y0, y1, y1]), 0.0, 0.0, rot, s)
    return (float(px.min()), float(py.min()), float(px.max()), float(py.max()))


# ----------------------------------------------------------------------------- raster
def sat(mask):
    """Summed-area table with a zero first row and column: S[i, j] = sum(mask[:i, :j])."""
    S = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.int64)
    S[1:, 1:] = np.cumsum(np.cumsum(mask.astype(np.int64), axis=0), axis=1)
    return S


def sat_query(S, i0, i1, j0, j1, ni, nj):
    """Count of mask cells in [i0, i1) x [j0, j1); cells beyond the grid count as set."""
    area = max(0, i1 - i0) * max(0, j1 - j0)
    if area == 0:
        return 0
    a0, a1 = min(max(i0, 0), ni), min(max(i1, 0), ni)
    b0, b1 = min(max(j0, 0), nj), min(max(j1, 0), nj)
    inside_grid = max(0, a1 - a0) * max(0, b1 - b0)
    cnt = int(S[a1, b1] - S[a0, b1] - S[a1, b0] + S[a0, b0]) if inside_grid else 0
    return cnt + (area - inside_grid)


def _best_rect(mask, weight_sat=None):
    """The all-True rectangle of a bool matrix with the highest score, among the maximal
    rectangles the histogram method enumerates. Score = area, or the count of cells of a
    weight mask (given by its summed-area table) inside the rectangle.
    Returns (score, i0, i1, j0, j1) with i1, j1 exclusive."""
    ni, nj = mask.shape
    h = np.zeros(nj, dtype=np.int64)
    best = (0, 0, 0, 0, 0)
    for i in range(ni):
        h = np.where(mask[i], h + 1, 0)
        stack = []
        hl = h.tolist()
        for j in range(nj + 1):
            cur = hl[j] if j < nj else 0
            start = j
            while stack and stack[-1][1] >= cur:
                sj, sh = stack.pop()
                if sh > 0:
                    i0, i1 = i - sh + 1, i + 1
                    if weight_sat is None:
                        score = sh * (j - sj)
                    else:
                        S = weight_sat
                        score = int(S[i1, j] - S[i0, j] - S[i1, sj] + S[i0, sj])
                    if score > best[0]:
                        best = (score, i0, i1, sj, j)
                start = sj
            if not stack or stack[-1][1] < cur:
                stack.append((start, cur))
    return best


def cover_rects(inside, max_rects=8, coarse=120, min_gain=0.004):
    """A few overlapping rectangles inside the mask that together cover most of it: greedy
    on a coarse copy (each next rectangle holds the most still-uncovered cells), then every
    rectangle grown back to full resolution."""
    ni, nj = inside.shape
    if not inside.any():
        return []
    if inside.all():
        return [(0, ni, 0, nj)]
    f = max(1, int(math.ceil(max(ni, nj) / coarse)))
    ci, cj = (ni + f - 1) // f, (nj + f - 1) // f
    pad = np.zeros((ci * f, cj * f), dtype=bool)
    pad[:ni, :nj] = inside
    coarse_m = pad.reshape(ci, f, cj, f).all(axis=(1, 3))
    S = sat(~inside)
    total = int(inside.sum())
    covered = np.zeros_like(inside)
    rects = []
    uncov = coarse_m.copy()
    for _ in range(max_rects):
        if not uncov.any():
            break
        score, i0, i1, j0, j1 = _best_rect(coarse_m, sat(uncov) if rects else None)
        if score <= 0:
            break
        r = _grow_rect([i0 * f, min(i1 * f, ni), j0 * f, min(j1 * f, nj)], S, ni, nj)
        gain = int((~covered[r[0]:r[1], r[2]:r[3]]).sum())
        if rects and gain < min_gain * total:
            break
        rects.append(tuple(r))
        covered[r[0]:r[1], r[2]:r[3]] = True
        uncov[i0:i1, j0:j1] = False
    return rects


def _grow_rect(r, S_out, ni, nj):
    """Grow a grid rectangle edge by edge while it stays free of outside cells."""
    i0, i1, j0, j1 = r
    changed = True
    while changed:
        changed = False
        if i0 > 0 and sat_query(S_out, i0 - 1, i0, j0, j1, ni, nj) == 0:
            i0 -= 1
            changed = True
        if i1 < ni and sat_query(S_out, i1, i1 + 1, j0, j1, ni, nj) == 0:
            i1 += 1
            changed = True
        if j0 > 0 and sat_query(S_out, i0, i1, j0 - 1, j0, ni, nj) == 0:
            j0 -= 1
            changed = True
        if j1 < nj and sat_query(S_out, i0, i1, j1, j1 + 1, ni, nj) == 0:
            j1 += 1
            changed = True
    return (i0, i1, j0, j1)


def poly_cover_rects(poly, step):
    """Rectangles whose union covers a polygon (vertical strips of width ~step, each the
    polygon's extent within the strip); a rectangle polygon gives itself."""
    if poly is None or poly.is_empty:
        return []
    x0, y0, x1, y1 = poly.bounds
    if abs(poly.area - (x1 - x0) * (y1 - y0)) < 1e-6 * max(poly.area, 1e-9):
        return [(x0, y0, x1, y1)]
    n = max(1, min(64, int(math.ceil((x1 - x0) / max(step, 1e-3)))))
    xs = np.linspace(x0, x1, n + 1)
    out = []
    for a, b in zip(xs[:-1], xs[1:]):
        piece = poly.intersection(box(a, y0 - 1, b, y1 + 1))
        if not piece.is_empty and piece.area > 0:
            px0, py0, px1, py1 = piece.bounds
            out.append((a, py0, b, py1))
    return out
