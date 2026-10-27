# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Footprints that carry part of the board edge.

Some footprints draw open Edge.Cuts pieces: a card-edge connector or a sensor notch that the
board outline needs. A place task stages them off the board, so the outline is either open
(the board's own pieces leave dangling ends) or closed without the notch. Such a footprint
has (almost) one legal pose: the one where its free ends meet the board's.

`mate(board)` finds that pose for every movable footprint with open edge pieces:
- open outline: a rotation (multiple of 90 degrees, side kept) and translation that put every
  free end of the footprint's pieces onto a dangling end of the board's pieces;
- closed outline: the free ends lie on one straight boundary segment with the pieces inside
  the board (a notch); the position along the segment is free, and the one nearest the
  segment's middle is taken.
Mated footprints are set to that pose, held fixed for the rest of the placement, and their
pieces join the outline (as pcbnew joins on-board footprints' Edge.Cuts).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Point

from kae.board import geom as bgeom
from kae.board import sexpr, transform
from kae.board.kicad_file import GR_SHAPES, shape_pieces

EPS = 0.02   # mm: ends closer than this meet


def _board_pieces(board):
    """Board-level Edge.Cuts pieces (open polylines, closed rings) from the file, plus the
    pieces of footprints that stay where they are (locked or on the board)."""
    opens, rings = [], []
    path = getattr(board, "path", "")
    if path and Path(path).exists():
        tree = sexpr.parse(sexpr.strip_blocks(Path(path).read_text(encoding="utf-8", errors="replace")))
        for node in tree:
            if type(node) is list and node and node[0] in GR_SHAPES and sexpr.value(node, "layer") == "Edge.Cuts":
                try:
                    o, r = shape_pieces(node)
                except (TypeError, ValueError, IndexError):
                    continue
                opens += o
                rings += r
    for fp in board.footprints:
        if fp.edge_cuts and (fp.locked or fp.on_board):
            opens += _placed(fp, fp.x, fp.y, fp.rot, fp.side)
    return opens, rings


def _placed(fp, x, y, rot, side):
    out = []
    for ls in fp.edge_cuts:
        xy = transform.transform_coords(list(ls.coords), x, y, rot, side)
        out.append([tuple(p) for p in xy.tolist()])
    return out


def _free_ends(opens):
    """Endpoints met by an odd number of piece ends (after snapping within EPS)."""
    pts = []
    for pl in opens:
        if len(pl) >= 2 and math.dist(pl[0], pl[-1]) > EPS:
            pts += [pl[0], pl[-1]]
    groups = []
    for p in pts:
        for gr in groups:
            if math.dist(gr[0], p) <= EPS:
                gr.append(p)
                break
        else:
            groups.append([p])
    return [gr[0] for gr in groups if len(gr) % 2 == 1]


def _lib_free_ends(fp):
    opens = [list(ls.coords) for ls in fp.edge_cuts if not ls.is_closed]
    return _free_ends([[tuple(p) for p in pl] for pl in opens])


def _try_open(fp, ends_lib, dangling):
    """Poses putting every free end of the footprint on a dangling board end."""
    out = []
    D = np.array(dangling)
    for rot in (0.0, 90.0, 180.0, 270.0):
        E = transform.transform_coords(ends_lib, 0, 0, rot, fp.side)
        for d in D:
            t = d - E[0]
            Et = E + t
            dist = np.sqrt(((Et[:, None, :] - D[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
            if (dist <= EPS).all():
                out.append((float(t[0]), float(t[1]), rot))
    return out


def _try_closed(fp, ends_lib, outline, step=0.5):
    """Notch poses: free ends on one straight boundary segment, pieces inside the board."""
    if len(ends_lib) != 2:
        return []
    cands = []
    rings = [outline.exterior] + list(outline.interiors)
    for rot in (0.0, 90.0, 180.0, 270.0):
        E = transform.transform_coords(ends_lib, 0, 0, rot, fp.side)
        v = E[1] - E[0]
        L = float(np.hypot(*v))
        if L <= EPS:
            continue
        for ring in rings:
            c = list(ring.coords)
            for a, b in zip(c[:-1], c[1:]):
                a, b = np.array(a), np.array(b)
                s = b - a
                sl = float(np.hypot(*s))
                if sl < L - EPS:
                    continue
                if abs(float(np.cross(s / sl, v / L))) > 1e-3:
                    continue
                sign = 1.0 if float(np.dot(s, v)) > 0 else -1.0
                # first end at a + lam * s_hat, second at first + v (same direction as s if sign > 0)
                lo = 0.0 if sign > 0 else L
                hi = sl - L if sign > 0 else sl
                n = max(1, int((hi - lo) / step))
                for j in range(n + 1):
                    lam = lo + (hi - lo) * j / n
                    p0 = a + s / sl * lam
                    t = p0 - E[0]
                    mid = [np.mean(transform.transform_coords(list(ls.coords), t[0], t[1], rot, fp.side), axis=0)
                           for ls in fp.edge_cuts]
                    if all(outline.buffer(EPS).contains(Point(m)) for m in mid):
                        mid_seg = abs(lam + (L / 2 if sign > 0 else -L / 2) - sl / 2)
                        cands.append((mid_seg, -sl, (float(t[0]), float(t[1]), rot)))
    cands.sort(key=lambda c: (c[1], c[0]))
    return [c[2] for c in cands]


def _n_open(v):
    return v.get("open_ends", 0) if isinstance(v, dict) else int(v or 0)


def _rank(fp, poses, opens, rings):
    """Mating poses that close the outline, best first: most of the footprint's pads inside
    the closed outline, then the larger board."""
    out = []
    for (x, y, rot) in poses:
        polys, open_ends = bgeom.polygons(opens + _placed(fp, x, y, rot, fp.side), rings, eps=0.01)
        if not polys or _n_open(open_ends):
            continue
        region = polys[0] if len(polys) == 1 else max(polys, key=lambda p: p.area)
        pads = transform.fp_pads_xy(fp, x, y, rot, fp.side)
        inside = sum(1 for (px, py) in pads if region.contains(Point(px, py)))
        out.append((-inside, -region.area, (x, y, rot)))
    out.sort(key=lambda c: (c[0], c[1]))
    return [c[2] for c in out]


def mate(board, log=None):
    """Place footprints that complete the board edge; returns {uuid: pose} of those placed
    (the board model is updated: pose set, footprint held fixed, outline rebuilt)."""
    log = log or (lambda *a, **k: None)
    movers = [fp for fp in board.footprints if not fp.locked and fp.edge_cuts
              and any(not ls.is_closed for ls in fp.edge_cuts)]
    if not movers:
        return {}
    opens, rings = _board_pieces(board)
    placed = {}
    for fp in movers:
        ends = _lib_free_ends(fp)
        if not ends:
            continue
        dangling = _free_ends(opens)
        poses = []
        if len(dangling) >= len(ends):
            poses = _rank(fp, _try_open(fp, ends, dangling), opens, rings)
        if not poses and board.outline:
            out = max(board.outline, key=lambda p: p.area)
            poses = _try_closed(fp, ends, out)
        if not poses:
            log(f"edge footprint {fp.ref}: no mating pose found; placed like any part")
            continue
        x, y, rot = poses[0]
        fp.x, fp.y, fp.rot = x, y, transform.norm_deg(rot)
        for p in fp.pads:
            p.x, p.y = transform.pad_xy(fp, p)
        fp.locked = True       # internal: hold it for the rest of the placement
        fp.on_board = True
        placed[fp.uuid] = (round(x, 6), round(y, 6), fp.rot, fp.side)
        opens += _placed(fp, fp.x, fp.y, fp.rot, fp.side)
        log(f"edge footprint {fp.ref}: mated at ({x:.3f}, {y:.3f}) rot {fp.rot:g}")
    if placed:
        polys, open_ends = bgeom.polygons(opens, rings, eps=0.01)
        if polys:
            board.outline = polys
        if _n_open(open_ends):
            log(f"outline after mating still has open ends: {open_ends}")
    _ = LineString
    return placed
