# SPDX-FileCopyrightText: 2026 kicad-auto-everything contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Footprint transforms with KiCad's conventions (the one transform module).

KiCad's board frame is y-down. `RotatePoint` (libs/kimath trigo.cpp) maps
(u, v) -> (u cos a + v sin a, -u sin a + v cos a): a positive angle turns
counter-clockwise on screen. The textbook matrix agrees only at 0 and 180 degrees
(docs/topics/kicad/transform-math-pitfalls.md).

Local coordinates are in the library frame (front side, 0 degrees; see kae.board.model).
Flipping a footprint to the back (FOOTPRINT::Flip) mirrors its children about the
footprint's own x axis in the footprint frame, so for a pose (x, y, rot, side):

    board = (x, y) + R(rot) (lx, s*ly),   s = +1 front, -1 back
    pad angle = rot + s*lrot
    layers: F.* <-> B.*, In(k) <-> In(n-1-k) on the back

`rot` is the orientation KiCad reports for the placed footprint (after a left-right flip
of a part at angle a, KiCad reports 180 - a; any (rot, side) pair is a valid pose).
Positions in a .kicad_pcb are stored in the placed frame, i.e. (lx, s*ly).
These rules are verified against pcbnew pad by pad (kae.board.pcbnew_io.verify).
"""
import math

import numpy as np
import shapely
from shapely import affinity

# exact cos/sin at multiples of 90 degrees, as RotatePoint special-cases them
_QUARTER = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}


def norm_deg(a):
    """Angle in [0, 360)."""
    a = float(a) % 360.0
    return 0.0 if a >= 360.0 or a == -0.0 else a


def cos_sin(deg):
    a = norm_deg(deg)
    q = _QUARTER.get(a)
    if q is not None:
        return q
    r = math.radians(a)
    return math.cos(r), math.sin(r)


def rotate(u, v, deg):
    """KiCad RotatePoint(u, v, deg) in floating point."""
    c, s = cos_sin(deg)
    return u * c + v * s, -u * s + v * c


def side_sign(side):
    """+1 for the front, -1 for the back. Accepts 'F'/'B', layer names, bools (True =
    back) and +1/-1, or numpy arrays of them."""
    if isinstance(side, str):
        if side in ("F", "F.Cu", "front", "top"):
            return 1.0
        if side in ("B", "B.Cu", "back", "bottom"):
            return -1.0
        raise ValueError(f"unknown side {side!r}")
    if isinstance(side, (bool, np.bool_)):
        return -1.0 if side else 1.0
    if isinstance(side, (int, float, np.integer, np.floating)):
        return -1.0 if side < 0 else 1.0
    arr = np.asarray(side)
    if arr.dtype == bool:
        return np.where(arr, -1.0, 1.0)
    if arr.dtype.kind in "iuf":
        return np.where(arr < 0, -1.0, 1.0)
    return np.where(np.char.startswith(arr.astype(str), "B"), -1.0, 1.0)


def to_board(lx, ly, x, y, rot, side):
    """Library-frame point -> board coordinates for the pose (x, y, rot, side)."""
    u, v = rotate(lx, side_sign(side) * ly, rot)
    return x + u, y + v


def to_local(bx, by, x, y, rot, side):
    """Board point -> library frame for the pose (x, y, rot, side)."""
    u, v = rotate(bx - x, by - y, -rot)
    return u, side_sign(side) * v


def _pose(fp, x, y, rot, side):
    return (fp.x if x is None else x, fp.y if y is None else y,
            fp.rot if rot is None else rot, fp.side if side is None else side)


def pad_xy(fp, pad, x=None, y=None, rot=None, side=None):
    """Absolute (x, y) of `pad` with its footprint at a trial pose (defaults: current)."""
    x, y, rot, side = _pose(fp, x, y, rot, side)
    return to_board(pad.lx, pad.ly, x, y, rot, side)


def pad_angle(fp, pad, rot=None, side=None):
    """Absolute pad orientation (degrees, [0, 360)) at a trial pose."""
    rot = fp.rot if rot is None else rot
    side = fp.side if side is None else side
    return norm_deg(rot + side_sign(side) * pad.lrot)


def _cs_array(rot):
    rot = np.mod(np.asarray(rot, dtype=float), 360.0)
    r = np.radians(rot)
    c, s = np.cos(r), np.sin(r)
    if c.ndim == 0:
        q = _QUARTER.get(float(rot))
        return (np.float64(q[0]), np.float64(q[1])) if q else (c, s)
    for deg, (qc, qs) in _QUARTER.items():
        m = rot == deg
        if m.any():
            c = np.where(m, qc, c)
            s = np.where(m, qs, s)
    return c, s


def pads_xy(lx, ly, x, y, rot, side):
    """Vectorized pad_xy: all arguments broadcast (numpy). Returns (px, py).

    Typical use: per-pad arrays lx, ly and the owning footprint's pose gathered per pad,
    e.g. pads_xy(lx, ly, X[fi], Y[fi], ROT[fi], BACK[fi]) for many pads at once, or
    pads_xy(lx[None, :], ly[None, :], x[:, None], y[:, None], rot[:, None], side) for
    many poses of one footprint.
    """
    lx = np.asarray(lx, dtype=float)
    ly = np.asarray(ly, dtype=float) * side_sign(side)
    c, s = _cs_array(rot)
    return np.asarray(x, dtype=float) + lx * c + ly * s, np.asarray(y, dtype=float) - lx * s + ly * c


def local_pads(fp):
    """(N, 2) array of the footprint's pad positions in the library frame."""
    return np.array([(p.lx, p.ly) for p in fp.pads], dtype=float).reshape(-1, 2)


def fp_pads_xy(fp, x=None, y=None, rot=None, side=None):
    """(N, 2) absolute pad positions of `fp` at a trial pose."""
    x, y, rot, side = _pose(fp, x, y, rot, side)
    loc = local_pads(fp)
    px, py = pads_xy(loc[:, 0], loc[:, 1], x, y, rot, side)
    return np.column_stack([px, py])


def affine(x, y, rot, side):
    """shapely affine_transform parameters [a, b, d, e, xoff, yoff] for a pose."""
    c, s = cos_sin(rot)
    m = side_sign(side)
    return [c, m * s, -s, m * c, x, y]


def place_geom(geom, x, y, rot, side):
    """A library-frame shapely geometry placed at a pose."""
    return affinity.affine_transform(geom, affine(x, y, rot, side))


def courtyard(fp, x=None, y=None, rot=None, side=None, which="own"):
    """Courtyard polygons of `fp` at a trial pose, in board coordinates.

    which='own': the courtyard on the part's own side (F.CrtYd on the front, B.CrtYd on
    the back); 'opposite': the other side's courtyard (e.g. a through-hole part's);
    'extent': the courtyard, or the body fallback when the footprint has none.
    """
    x, y, rot, side = _pose(fp, x, y, rot, side)
    if which == "own":
        polys = fp.courtyard
    elif which == "opposite":
        polys = fp.courtyard_back
    elif which == "extent":
        polys = fp.courtyard or fp.body
    else:
        raise ValueError(f"which={which!r}")
    if not polys:
        return []
    m = affine(x, y, rot, side)
    return [affinity.affine_transform(p, m) for p in polys]


def courtyard_layers(fp, side=None):
    """Board courtyard layer of the part's own side and of the opposite side."""
    side = fp.side if side is None else side
    return ("F.CrtYd", "B.CrtYd") if side_sign(side) > 0 else ("B.CrtYd", "F.CrtYd")


def flip_layer(name, n_copper=2):
    """KiCad's BOARD::FlipLayer: F.* <-> B.*, In(k) <-> In(n_copper - 1 - k)."""
    if name.startswith("F."):
        return "B." + name[2:]
    if name.startswith("B."):
        return "F." + name[2:]
    if name.startswith("In") and name.endswith(".Cu"):
        try:
            k = int(name[2:-3])
        except ValueError:
            return name
        n_inner = max(0, n_copper - 2)
        if 1 <= k <= n_inner:
            return f"In{n_inner + 1 - k}.Cu"
    return name


def layers_at(layers, from_side, to_side, n_copper=2):
    """Pad or graphic layers after moving a footprint from one side to another."""
    if side_sign(from_side) == side_sign(to_side):
        return list(layers)
    return [flip_layer(l, n_copper) for l in layers]


def transform_coords(coords, x, y, rot, side):
    """(N, 2) library-frame coordinates -> board coordinates (numpy)."""
    a = np.asarray(coords, dtype=float).reshape(-1, 2)
    px, py = pads_xy(a[:, 0], a[:, 1], x, y, rot, side)
    return np.column_stack([px, py])


def bounds(geoms):
    """(minx, miny, maxx, maxy) of a list of geometries, or None."""
    if not geoms:
        return None
    return tuple(shapely.total_bounds(np.asarray(geoms, dtype=object)))
