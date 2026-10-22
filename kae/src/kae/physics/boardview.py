# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A flat, read-only view of a Contract-1 board (kae.board.model.Board) for the place terms.

Reads only Contract-1 fields: Board.footprints, nets, outline, keepouts, zones, stackup,
rules; Footprint.ref, value, lib_id, x, y, rot, side, locked, attrs, pads, courtyard, body,
on_board; Pad.number, net, kind, size, lx, ly, lrot, layers, drill, pinfunction, pintype.
Pads and courtyards are in the library frame; a pose (x, y, rot, side) maps a local point
to (x, y) + R(rot) (lx, s ly), s = -1 on the back (kae.board.transform).

What it precomputes, once per board:
  * per part: library-frame pad offsets, pad sizes and nets, the courtyard's library-frame
    bounding box, a body-height prior;
  * per net: its pads as (part index, pad index);
  * the stackup's copper heights z (mm from the top copper, downwards) and, per board side,
    a raster of the height of the nearest reference plane under that side's copper
    (`h_ref(side, x, y)`): any zone on another copper layer that covers the point images
    a horizontal current at HF (lens SY, P3), whatever its net. Zones are taken as filled
    over their outline (a place task has no fills);
  * the board outline (shapely), its bounding box and area.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

INF = float('inf')

# body (current-path) height above the copper, mm, by package keyword (E5 prior: the
# capacitor electrode stack centre or the lead frame; used for internal part segments)
BODY_Z = (
    (r'0201', 0.15), (r'0402|1005Metric', 0.25), (r'0603|1608Metric', 0.4), (r'0805|2012Metric', 0.5),
    (r'1206|3216Metric', 0.6), (r'1210|3225Metric', 0.8), (r'1812|2220|2225', 1.0),
    (r'QFN|DFN|SON|WSON|VSON|LGA|BGA|CSP|WLP|MLF|MLP', 0.2), (r'SOT|SC-?70|SOD', 0.5),
    (r'SOIC|SO-|SOP|TSSOP|MSOP|VSSOP|QSOP', 0.6), (r'QFP|LQFP|TQFP', 0.6),
    (r'TO-?252|DPAK|TO-?263|D2PAK|PowerPAK|SO-8FL|LFPAK', 0.8), (r'Elec|CP_|Radial|Axial|THT|TO-?220|TO-?247', 2.0),
)


def body_z(lib_id, value=''):
    s = f'{lib_id} {value}'
    for pat, z in BODY_Z:
        if re.search(pat, s, re.I):
            return z
    return 0.5


@dataclass
class PartView:
    i: int
    ref: str
    uuid: str
    value: str
    lib_id: str
    x0: float
    y0: float
    rot0: float
    side0: int                      # +1 front, -1 back
    locked: bool
    on_board: bool
    pad_num: list = field(default_factory=list)
    pad_net: list = field(default_factory=list)
    pad_lx: np.ndarray = None       # library frame
    pad_ly: np.ndarray = None
    pad_sx: np.ndarray = None       # pad size in the part frame (rotated by lrot)
    pad_sy: np.ndarray = None
    pad_kind: list = field(default_factory=list)
    pad_func: list = field(default_factory=list)
    pad_type: list = field(default_factory=list)
    pad_drill: np.ndarray = None
    cy_bbox: tuple = (-0.5, -0.5, 0.5, 0.5)    # library-frame courtyard bbox (minx, miny, maxx, maxy)
    cy_polys: list = field(default_factory=list)
    zbody: float = 0.5
    attrs: tuple = ()


def _get(o, name, default=None):
    if isinstance(o, dict):
        return o.get(name, default)
    return getattr(o, name, default)


def _side_sign(side):
    if isinstance(side, str):
        return -1 if side.upper().startswith('B') else 1
    if isinstance(side, (bool, np.bool_)):
        return -1 if side else 1
    try:
        return -1 if float(side) < 0 else 1
    except (TypeError, ValueError):
        return 1


def cos_sin(deg):
    a = float(deg) % 360.0
    if a == 0.0:
        return 1.0, 0.0
    if a == 90.0:
        return 0.0, 1.0
    if a == 180.0:
        return -1.0, 0.0
    if a == 270.0:
        return 0.0, -1.0
    r = math.radians(a)
    return math.cos(r), math.sin(r)


class BoardView:
    """Flat arrays for one board. Build with `BoardView.from_board(board)`."""

    def __init__(self):
        self.parts: list[PartView] = []
        self.idx: dict[str, int] = {}
        self.nets: dict[str, list] = {}
        self.outline = None
        self.bbox = (0.0, 0.0, 100.0, 100.0)
        self.area = 1e4
        self.copper: list[str] = ['F.Cu', 'B.Cu']
        self.zcu: dict[str, float] = {'F.Cu': 0.0, 'B.Cu': 1.5}
        self.tcu: dict[str, float] = {'F.Cu': 0.035, 'B.Cu': 0.035}
        self.er = 4.3
        self.thickness = 1.6
        self.track_min = 0.15
        self.clearance = 0.15
        self.netclass_width: dict[str, float] = {}
        self.zones = []          # (net, layer, polygon)
        self.keepouts = []
        self.path = ''
        self._hraster = {}       # side -> (x0, y0, res, H (ny, nx), NETIDX (ny, nx))
        self._plane_nets: list[str] = []

    # ------------------------------------------------------------------ build
    @classmethod
    def from_board(cls, board, raster_res=None):
        bv = cls()
        bv.path = str(_get(board, 'path', '') or '')
        fps = _get(board, 'footprints', []) or []
        if isinstance(fps, dict):
            fps = list(fps.values())
        st = _get(board, 'stackup', None)
        if st is not None and _get(st, 'copper'):
            cu = list(_get(st, 'copper'))
            tc = list(_get(st, 'cu_thickness') or [0.035] * len(cu))
            gaps = list(_get(st, 'gaps') or [])
            ers = list(_get(st, 'er') or [])
            if len(gaps) != len(cu) - 1 or not all(g and g > 0 for g in gaps):
                th = float(_get(st, 'thickness', 1.6) or 1.6)
                gaps = [max(0.05, th / max(1, len(cu) - 1) - 0.035)] * (len(cu) - 1)
            z = [0.0]
            for k in range(1, len(cu)):
                z.append(z[-1] + tc[k - 1] / 2 + gaps[k - 1] + tc[k] / 2)
            bv.copper = cu
            bv.zcu = dict(zip(cu, z))
            bv.tcu = dict(zip(cu, tc))
            bv.gaps = gaps
            bv.er = float(np.average(ers, weights=gaps)) if ers and len(ers) == len(gaps) else 4.3
            bv.thickness = float(_get(st, 'thickness', z[-1]) or z[-1])
        else:
            th = float(_get(board, 'thickness', 1.6) or 1.6)
            bv.copper = ['F.Cu', 'B.Cu']
            bv.zcu = {'F.Cu': 0.0, 'B.Cu': th}
            bv.tcu = {'F.Cu': 0.035, 'B.Cu': 0.035}
            bv.gaps = [th]
            bv.thickness = th
        rules = _get(board, 'rules', None)
        if rules is not None:
            bv.track_min = float(_get(rules, 'track_min', 0.15) or 0.15)
            bv.clearance = float(_get(rules, 'clearance', 0.15) or 0.15)
            ncs = _get(rules, 'netclasses', {}) or {}
            for name, nc in (ncs.items() if isinstance(ncs, dict) else []):
                tw = _get(nc, 'track_width', None)
                if tw:
                    bv.netclass_width[name] = float(tw)
        bv.netclass_of = {}
        for name, net in (_get(board, 'nets', {}) or {}).items():
            bv.netclass_of[name] = _get(net, 'netclass', 'Default') or 'Default'
        # parts
        for fp in fps:
            pads = _get(fp, 'pads', []) or []
            ref = _get(fp, 'ref', '?')
            pv = PartView(i=len(bv.parts), ref=ref, uuid=str(_get(fp, 'uuid', '') or ''),
                          value=_get(fp, 'value', '') or '', lib_id=_get(fp, 'lib_id', '') or '',
                          x0=float(_get(fp, 'x', 0.0)), y0=float(_get(fp, 'y', 0.0)), rot0=float(_get(fp, 'rot', 0.0) or 0.0),
                          side0=_side_sign(_get(fp, 'side', 'F')), locked=bool(_get(fp, 'locked', False)),
                          on_board=bool(_get(fp, 'on_board', True)))
            pv.attrs = tuple(_get(fp, 'attrs', []) or [])
            lx, ly, sx, sy, dr = [], [], [], [], []
            for p in pads:
                pv.pad_num.append(str(_get(p, 'number', '')))
                pv.pad_net.append(_get(p, 'net', '') or '')
                lx.append(float(_get(p, 'lx', 0.0)))
                ly.append(float(_get(p, 'ly', 0.0)))
                size = _get(p, 'size', (0.5, 0.5)) or (0.5, 0.5)
                w0, h0 = float(size[0]), float(size[1] if len(size) > 1 else size[0])
                lr = float(_get(p, 'lrot', 0.0) or 0.0) % 180.0
                if 45.0 <= lr < 135.0:
                    w0, h0 = h0, w0
                sx.append(w0)
                sy.append(h0)
                pv.pad_kind.append(_get(p, 'kind', 'smd') or 'smd')
                pv.pad_func.append(_get(p, 'pinfunction', '') or '')
                pv.pad_type.append(_get(p, 'pintype', '') or '')
                dr.append(float(_get(p, 'drill', 0.0) or 0.0))
            pv.pad_lx = np.array(lx, float)
            pv.pad_ly = np.array(ly, float)
            pv.pad_sx = np.array(sx, float)
            pv.pad_sy = np.array(sy, float)
            pv.pad_drill = np.array(dr, float)
            cys = list(_get(fp, 'courtyard', []) or []) or list(_get(fp, 'body', []) or [])
            cys = [c for c in cys if c is not None and not getattr(c, 'is_empty', True)]
            pv.cy_polys = cys
            if cys:
                b = shapely.total_bounds(np.asarray(cys, dtype=object))
                pv.cy_bbox = tuple(float(v) for v in b)
            elif len(lx):
                hx = (pv.pad_sx / 2).max() if len(sx) else 0.25
                hy = (pv.pad_sy / 2).max() if len(sy) else 0.25
                pv.cy_bbox = (float(min(lx)) - hx - 0.25, float(min(ly)) - hy - 0.25,
                              float(max(lx)) + hx + 0.25, float(max(ly)) + hy + 0.25)
            pv.zbody = body_z(pv.lib_id, pv.value)
            bv.idx.setdefault(ref, pv.i)
            bv.parts.append(pv)
            for k, n in enumerate(pv.pad_net):
                if n:
                    bv.nets.setdefault(n, []).append((pv.i, k))
        # outline
        outl = _get(board, 'outline', []) or []
        if isinstance(outl, (Polygon,)) or hasattr(outl, 'geom_type'):
            outl = [outl]
        polys = [p for p in outl if p is not None and not p.is_empty]
        if polys:
            bv.outline = unary_union(polys)
        else:
            pts = [(p.x0, p.y0) for p in bv.parts if p.on_board]
            if pts:
                xs, ys = zip(*pts)
                bv.outline = box(min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5)
            else:
                bv.outline = box(0, 0, 100, 100)
        bv.bbox = tuple(float(v) for v in bv.outline.bounds)
        bv.area = float(bv.outline.area)
        shapely.prepare(bv.outline)
        # zones
        for z in _get(board, 'zones', []) or []:
            net = _get(z, 'net', '') or ''
            poly = _get(z, 'outline', None)
            if not net or poly is None or poly.is_empty:
                continue
            g = poly.intersection(bv.outline) if bv.outline is not None else poly
            if g.is_empty:
                continue
            for ly in _get(z, 'layers', []) or []:
                if ly in bv.zcu:
                    bv.zones.append((net, ly, g))
        bv.keepouts = list(_get(board, 'keepouts', []) or [])
        bv._build_rasters(raster_res)
        return bv

    # ------------------------------------------------------------------ planes
    def _build_rasters(self, res=None):
        x0, y0, x1, y1 = self.bbox
        if res is None:
            res = max(0.5, max(x1 - x0, y1 - y0) / 200.0)
        nx = max(2, int(math.ceil((x1 - x0) / res)) + 1)
        ny = max(2, int(math.ceil((y1 - y0) / res)) + 1)
        xs = x0 + np.arange(nx) * res
        ys = y0 + np.arange(ny) * res
        X, Y = np.meshgrid(xs, ys)
        by_layer = {}
        for net, ly, g in self.zones:
            by_layer.setdefault(ly, []).append((net, g))
        cover = {}
        nets = sorted({n for n, _, _ in self.zones})
        self._plane_nets = nets
        nid = {n: k for k, n in enumerate(nets)}
        for ly, items in by_layer.items():
            C = -np.ones((ny, nx), np.int32)
            for net, g in items:
                m = shapely.contains_xy(g, X, Y)
                C[m & (C < 0)] = nid[net]
            cover[ly] = C
        self.cover = cover
        self.cover_grid = (x0, y0, res, nx, ny)
        for side, layer in ((1, self.copper[0]), (-1, self.copper[-1])):
            H = np.full((ny, nx), INF)
            N = -np.ones((ny, nx), np.int32)
            zs = self.zcu[layer]
            for ly, C in cover.items():
                if ly == layer:
                    continue
                d = abs(self.zcu[ly] - zs)
                m = (C >= 0) & (d < H)
                H[m] = d
                N[m] = C[m]
            self._hraster[side] = (x0, y0, res, H, N)

    def h_ref(self, side, x, y):
        """Height (mm) of the nearest reference plane below (front) or above (back) the
        outer copper of `side` at (x, y); inf when no zone covers the point."""
        x0, y0, res, H, _ = self._hraster[1 if side > 0 else -1]
        i = int((x - x0) / res + 0.5)
        j = int((y - y0) / res + 0.5)
        ny, nx = H.shape
        if i < 0 or j < 0 or i >= nx or j >= ny:
            return INF
        return float(H[j, i])

    def plane_net(self, side, x, y):
        x0, y0, res, _, N = self._hraster[1 if side > 0 else -1]
        i = int((x - x0) / res + 0.5)
        j = int((y - y0) / res + 0.5)
        ny, nx = N.shape
        if i < 0 or j < 0 or i >= nx or j >= ny or N[j, i] < 0:
            return None
        return self._plane_nets[int(N[j, i])]

    def gmask(self, nets):
        """Boolean mask over plane-net ids: True for the given (ground) nets. Cached."""
        key = frozenset(nets)
        cache = self.__dict__.setdefault('_gmask', {})
        m = cache.get(key)
        if m is None:
            m = np.array([n in key for n in self._plane_nets] or [False], np.bool_)
            cache[key] = m
        return m

    def net_plane_layers(self, net):
        """Copper layers on which `net` has a zone, with the zone's coverage fraction of the board."""
        out = {}
        for n, ly, g in self.zones:
            if n == net:
                out[ly] = out.get(ly, 0.0) + g.area / max(self.area, 1e-9)
        return out

    def covers(self, net, layer, x, y):
        C = self.cover.get(layer)
        if C is None or net not in self._plane_nets:
            return False
        x0, y0, res, nx, ny = self.cover_grid
        i = int((x - x0) / res + 0.5)
        j = int((y - y0) / res + 0.5)
        if i < 0 or j < 0 or i >= nx or j >= ny:
            return False
        return C[j, i] == self._plane_nets.index(net)

    # ------------------------------------------------------------------ poses
    def pose0(self):
        """Reference poses as a dict uuid -> (x, y, rot, side)."""
        return {p.uuid: (p.x0, p.y0, p.rot0, 'F' if p.side0 > 0 else 'B') for p in self.parts}

    def pad_xy(self, i, k, x, y, rot, side):
        p = self.parts[i]
        c, s = cos_sin(rot)
        lx = p.pad_lx[k]
        ly = p.pad_ly[k] * (1 if side > 0 else -1)
        return x + lx * c + ly * s, y - lx * s + ly * c

    def part_pads_xy(self, i, x, y, rot, side):
        p = self.parts[i]
        c, s = cos_sin(rot)
        ly = p.pad_ly * (1.0 if side > 0 else -1.0)
        return x + p.pad_lx * c + ly * s, y - p.pad_lx * s + ly * c

    def courtyard_obb(self, i, x, y, rot, side):
        """Axis-aligned bounding box (minx, miny, maxx, maxy) of the part's courtyard bbox at a pose."""
        p = self.parts[i]
        a0, b0, a1, b1 = p.cy_bbox
        c, s = cos_sin(rot)
        sg = 1.0 if side > 0 else -1.0
        xs, ys = [], []
        for lx, ly in ((a0, b0), (a1, b0), (a1, b1), (a0, b1)):
            ly = ly * sg
            xs.append(x + lx * c + ly * s)
            ys.append(y - lx * s + ly * c)
        return min(xs), min(ys), max(xs), max(ys)
